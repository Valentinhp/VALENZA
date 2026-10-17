"""Informational snapshots in the existing encrypted audit store.

Credit liability always comes from list_card_summaries. Grouping never changes
an instrument, transaction, payment, or financial calculation.
"""
import json
from datetime import date, datetime

BALANCE_TYPES = {
    'TOTAL': 'Deuda total actual aplicada (incluye principal MSI futuro)',
    'STATEMENT': 'Saldo al corte',
    'MONTHLY': 'Pago exigible del mes',
    'PENDING': 'Saldo que incluye movimientos pendientes',
    'UNKNOWN': 'Tipo de saldo sin confirmar',
    'NO_INTEREST': 'Pago para no generar intereses',
    'MINIMUM': 'Pago mínimo',
    'OTHER': 'Otro saldo (especificar)',
}


def same_moment(value):
    """Only a recent, timed consultation can describe the current snapshot."""
    try:
        if len(value) == 10:
            return False
        instant = datetime.fromisoformat(value).astimezone()
        return abs((datetime.now().astimezone() - instant).total_seconds()) <= 300
    except (ValueError, TypeError):
        return False


class BankReconciliation:
    def __init__(self, repository):
        self.repo = repository
        self.connection = repository.database.connection

    def scopes(self):
        cards = {c['instrument_id']: c for c in self.repo.list_card_summaries(include_inactive=True)
                 if c['instrument_type'] in ('CREDIT_CARD', 'CREDIT_LINE')}
        mapping = {key: key for key in cards}
        for row in self.connection.execute("SELECT entity_id,new_value FROM audit_event WHERE entity_type='instrument' AND action='BANK_RECONCILIATION_SCOPE' ORDER BY rowid"):
            value = json.loads(row['new_value'])
            if row['entity_id'] in cards and value['account_id'] in cards:
                mapping[row['entity_id']] = value['account_id']
        return cards, mapping

    def set_scope(self, instrument_id, account_id, actor):
        cards, mapping = self.scopes()
        if instrument_id not in cards or account_id not in cards:
            raise ValueError('Selecciona cuentas de crédito registradas.')
        institutions = {r['id']: r['institution_id'] for r in self.connection.execute('SELECT id,institution_id FROM payment_instrument')}
        if institutions[instrument_id] != institutions[account_id]:
            raise ValueError('La línea compartida debe pertenecer a la misma institución.')
        if mapping[account_id] != account_id and instrument_id != account_id:
            raise ValueError('Selecciona la cuenta principal de la línea, no otra tarjeta vinculada.')
        if instrument_id != account_id and any(k != instrument_id and v == instrument_id for k,v in mapping.items()):
            raise ValueError('Esta cuenta ya agrupa tarjetas. Desvincúlalas antes de cambiar su cuenta principal.')
        if mapping[instrument_id] == account_id:
            return
        with self.repo.database.transaction() as connection:
            self.repo._insert_person_audit(connection,instrument_id,'BANK_RECONCILIATION_SCOPE',actor,
                dict(account_id=mapping[instrument_id]),dict(account_id=account_id),entity_type='instrument')

    def components(self, members, cards):
        result = []
        for key in members:
            card = cards[key]
            orders = self.repo.list_card_purchases(key)
            interest = self.connection.execute("SELECT COALESCE(SUM(f.interest_cents),0) FROM financing_plan f JOIN order_record o ON o.id=f.order_id WHERE f.instrument_id=? AND o.order_status='ACTIVE'",(key,)).fetchone()[0]
            movements = [dict(r) for r in self.connection.execute('SELECT kind,SUM(amount_cents) AS amount_cents FROM institution_movement WHERE instrument_id=? GROUP BY kind',(key,))]
            pending_refunds = self.connection.execute("SELECT COUNT(*) FROM imported_product_refund f JOIN order_record o ON o.id=f.order_id WHERE o.instrument_id=? AND o.order_status='ACTIVE' AND f.status='PENDING'",(key,)).fetchone()[0]
            result.append(dict(instrument_id=key,alias=card['alias'],order_charges_cents=sum(o['charged_cents'] for o in orders),
                financing_interest_cents=interest,movements=movements,charged_cents=card['charged_cents'],
                bank_payments_cents=card['paid_cents'],calculated_cents=card['remaining_cents'],credit_cents=card['credit_cents'],
                future_msi_cents=card['scheduled_future_cents'],exigible_cents=card['exigible_cents'],pending_refunds=pending_refunds))
        return result

    def accounts(self, as_of=None):
        from .bank_periods import period_forecast
        as_of = as_of or date.today()
        cards, mapping = self.scopes()
        result = []
        for key,card in cards.items():
            if mapping[key] != key:
                continue
            members = sorted(k for k,v in mapping.items() if v == key)
            components = self.components(members,cards)
            forecast = period_forecast(self.repo, members, as_of)
            if sum(e['remaining_cents'] for e in forecast['entries']) != sum(cards[k]['remaining_cents'] for k in members):
                forecast['warnings'].append('El calendario y la deuda neta no cuadran por asignaciones o ajustes pendientes. No se distribuye la diferencia automáticamente.')
                forecast['pending_complete'] = False
            warnings = []
            if len(members) > 1:
                warnings.append('Línea compartida declarada: cada identificador se cuenta una vez. Los movimientos deben ser distintos; no se detectan registros duplicados entre tarjetas.')
            comparable = not (len(members)>1 and any(c['credit_cents'] for c in components))
            if not comparable:
                warnings.append('Hay saldo a favor en una tarjeta de la línea. El modelo no compensa saldos entre instrumentos: no es posible confirmar una deuda neta compartida fiable.')
                forecast['pending_complete'] = False
            if any(c['pending_refunds'] for c in components):
                warnings.append('Hay devoluciones pendientes; no se descuentan hasta su acreditación en el destino correspondiente.')
            result.append(dict(instrument_id=key,account_id=key,alias=card['alias'],institution_name=card['institution_name'],
                members=members,components=components,warnings=warnings,comparable=comparable,
                calculated_cents=sum(cards[k]['remaining_cents'] for k in members),
                monthly_forecast=forecast, current_month_cents=forecast['current_cents']))
        return result

    @staticmethod
    def timestamp(value):
        if not isinstance(value,str) or not value.strip():
            raise ValueError('Introduce fecha y hora de consulta.')
        try:
            if len(value.strip()) == 10:
                return date.fromisoformat(value.strip()).isoformat()
            parsed=datetime.fromisoformat(value.strip())
            if parsed.tzinfo is None:
                parsed=parsed.astimezone()
            return parsed.isoformat(timespec='seconds')
        except ValueError as error:
            raise ValueError('Fecha y hora inválidas; usa AAAA-MM-DD HH:MM:SS con zona horaria opcional.') from error

    def record(self,instrument_id,amount_cents,consulted_at,balance_type,actor, *, period=None, balance_label='', closing_date=None, due_date=None, total_confirmed=True):
        with self.repo.database.transaction():
            self._record_snapshot(instrument_id,amount_cents,consulted_at,balance_type,actor, period, balance_label, closing_date, due_date, total_confirmed)

    def _record_snapshot(self,instrument_id,amount_cents,consulted_at,balance_type,actor,period,balance_label,closing_date,due_date,total_confirmed):
        if type(amount_cents) is not int or not 0 <= amount_cents <= 999_999_999_999:
            raise ValueError('El saldo bancario debe ser un importe no negativo en centavos.')
        if type(total_confirmed) is not bool:
            raise ValueError('Confirma el alcance del importe bancario.')
        for value in (closing_date, due_date):
            if value is not None:
                try:
                    if date.fromisoformat(value).isoformat() != value:
                        raise ValueError()
                except (ValueError, TypeError):
                    raise ValueError('Usa fechas de corte y límite válidas (AAAA-MM-DD).')
        if bool(closing_date) != bool(due_date) or (closing_date and due_date < closing_date):
            raise ValueError('Introduce corte y fecha límite juntos; el límite no puede ser anterior al corte.')
        if balance_type not in BALANCE_TYPES:
            raise ValueError('Selecciona el tipo de saldo consultado.')
        if balance_type == 'OTHER' and not balance_label.strip():
            raise ValueError('Especifica qué saldo muestra el banco.')
        try:
            as_of = date.fromisoformat(period+'-01') if period else date.today()
            if period and as_of.strftime('%Y-%m') != period:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('Selecciona un periodo AAAA-MM válido.')
        consulted_at=self.timestamp(consulted_at)
        _,mapping=self.scopes()
        account_id=mapping.get(instrument_id)
        account=next((a for a in self.accounts(as_of) if a['account_id']==account_id),None)
        if account is None:
            raise ValueError('Selecciona una tarjeta o línea de crédito; una billetera no es deuda bancaria.')
        warnings=list(account['warnings'])
        if balance_type != 'TOTAL':
            warnings.append('Este saldo no equivale a deuda total aplicada. No se calcula una diferencia comparable.')
            warnings.append('El calendario mensual no reconstruye el pago mínimo ni el pago para no generar intereses: faltan los componentes confirmados del estado de cuenta.')
            warnings.extend(account['monthly_forecast']['warnings'])
            if as_of.strftime('%Y-%m') != date.today().strftime('%Y-%m'):
                warnings.append('Periodo distinto del actual: es el calendario pendiente al guardar, no una reconstrucción de lo que se debía entonces.')
        if len(consulted_at)==10:
            warnings.append('Consulta sin hora. La deuda Valenza corresponde al momento de guardar, no a una reconstrucción de esa fecha.')
        recorded_at=datetime.now().astimezone().isoformat(timespec='seconds')
        if consulted_at[:10] != recorded_at[:10]:
            warnings.append('Fecha de consulta distinta del registro: la deuda Valenza se fotografió al guardar. La diferencia no confirma un error bancario.')
        if not same_moment(consulted_at):
            warnings.append('No comparable en el tiempo: la consulta no corresponde a la fotografía actual. No se confirma coincidencia.')
        same_period = as_of.strftime('%Y-%m') == date.today().strftime('%Y-%m')
        if balance_type == 'TOTAL' and not same_period:
            warnings.append('El periodo seleccionado no es el actual. No se compara un saldo de otro periodo con la deuda total actual.')
        if balance_type == 'TOTAL' and not total_confirmed:
            warnings.append('Alcance sin confirmar: incluye todos los cargos aplicados y MSI futuros de esta misma cuenta. No se compara con saldo actual, saldo a pagar o crédito disponible.')
        comparable=balance_type=='TOTAL' and total_confirmed and account['comparable'] and same_moment(consulted_at) and same_period
        value=dict(schema=4,account_id=account_id,members=account['members'],amount_cents=amount_cents,
            calculated_cents=account['calculated_cents'],difference_cents=amount_cents-account['calculated_cents'] if comparable else None,
            consulted_at=consulted_at,recorded_at=recorded_at,balance_type=balance_type,comparable=comparable,
            warnings=list(dict.fromkeys(warnings)),components=account['components'],currency='MXN',
            period=as_of.strftime('%Y-%m'), balance_label=balance_label.strip()[:120] if balance_type=='OTHER' else '',
            monthly_forecast=account['monthly_forecast'],
            closing_date=closing_date,due_date=due_date,total_confirmed=total_confirmed,
            orientative_difference_cents=None)
        # A repeated click must not append the same observation. Compare the
        # snapshot too: a later financial change is a distinct observation.
        identity = ('account_id','members','amount_cents','calculated_cents','consulted_at',
                    'balance_type','period','balance_label','closing_date','due_date',
                    'total_confirmed','components','monthly_forecast','comparable')
        for previous in self.history(account_id):
            if all(previous.get(key) == value.get(key) for key in identity):
                return
        self.repo._insert_person_audit(self.connection,account_id,'BANK_BALANCE_QUERIED',actor,None,value,entity_type='instrument')

    def history(self,account_id=None):
        result=[]
        for row in self.connection.execute("SELECT rowid AS sequence,id,entity_id,occurred_at,new_value FROM audit_event WHERE entity_type='instrument' AND action='BANK_BALANCE_QUERIED' ORDER BY rowid DESC"):
            value=json.loads(row['new_value'])
            key=value.get('account_id',row['entity_id'])
            if account_id is not None and key!=account_id:
                continue
            value.update(id=row['id'],sequence=row['sequence'],account_id=key)
            if 'schema' not in value:
                value.update(members=[key],calculated_cents=None,difference_cents=None,comparable=False,
                    balance_type='UNKNOWN',recorded_at=row['occurred_at'],components=[],
                    warnings=['Consulta anterior sin fotografía de deuda ni hora bancaria. No se reconstruye una diferencia histórica.'])
            result.append(value)
        def sort_key(value):
            parsed=datetime.fromisoformat(value['consulted_at'])
            return (parsed.astimezone().timestamp(),value['sequence'])
        return sorted(result,key=sort_key,reverse=True)

    def comparisons(self, as_of=None):
        history=self.history()
        result=self.accounts(as_of)
        for account in result:
            last=next((q for q in history if q['account_id']==account['account_id']),None)
            account.update(reported_cents=last['amount_cents'] if last else None,
                consulted_at=last['consulted_at'] if last else None,difference_cents=last['difference_cents'] if last else None,
                snapshot_calculated_cents=last['calculated_cents'] if last else None,last_query=last)
            if last and last['members']!=account['members']:
                account['warnings'].append('La última consulta tenía otro alcance de tarjetas. Su diferencia pertenece únicamente a la fotografía histórica.')
        return result
