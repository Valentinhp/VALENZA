"""Current scheduled amounts and identified applications, grouped by due month."""
from calendar import monthrange
from datetime import date

from valenza.finance.monthly import month_totals


def normal_due(connection, instrument_id, purchased_at):
    calendar = connection.execute(
        "SELECT closing_day,due_day FROM instrument_calendar WHERE instrument_id=? "
        "AND effective_from<=? AND (effective_to IS NULL OR effective_to>?) "
        "ORDER BY revision DESC LIMIT 1", (instrument_id, purchased_at, purchased_at)).fetchone()
    if not calendar:
        # This is a forecast, not a reconstruction of a bank statement. If no
        # historical rule was recorded, use the configured current rule without
        # altering its effective date or the purchase. Never invent missing days.
        calendar = connection.execute(
            "SELECT closing_day,due_day FROM instrument_calendar WHERE instrument_id=? "
            "AND effective_to IS NULL AND effective_from<=? ORDER BY revision DESC LIMIT 1",
            (instrument_id,date.today().isoformat())).fetchone()
    if not calendar or not calendar['closing_day'] or not calendar['due_day']:
        return None
    try:
        purchased = date.fromisoformat(purchased_at)
    except (TypeError, ValueError):
        return None
    index = purchased.year * 12 + purchased.month - 1
    closing = min(calendar['closing_day'], monthrange(purchased.year, purchased.month)[1])
    index += purchased.day > closing
    index += calendar['due_day'] <= calendar['closing_day']
    year, month = index // 12, index % 12 + 1
    return date(year, month, min(calendar['due_day'], monthrange(year, month)[1])).isoformat()


def period_forecast(repository, members, as_of):
    entries, warnings = [], []
    connection = repository.database.connection
    unapplied = 0
    has_credits = False
    for member in sorted(set(members)):
        installments = repository.list_installments(member)
        for item in installments:
            entries.append(dict(due_date=item['due_date'], amount_cents=item['principal_cents']+item['interest_cents'],
                                applied_cents=item['applied_cents'], remaining_cents=item['remaining_cents'],
                                kind='MSI', source_id=item['order_id'], number=item['number'], merchant=item['merchant'],
                                confirmed=not item['requires_review']))
        normal = connection.execute(
            "SELECT id,ordered_at,charged_cents,purchase_mode FROM order_record o WHERE instrument_id=? "
            "AND order_status='ACTIVE' AND NOT EXISTS (SELECT 1 FROM financing_plan f WHERE f.order_id=o.id)",
            (member,)).fetchall()
        for item in normal:
            due = normal_due(connection, member, item['ordered_at']) if item['purchase_mode'] != 'MSI' else None
            entries.append(dict(due_date=due, amount_cents=item['charged_cents'],
                                applied_cents=0, remaining_cents=item['charged_cents'],
                                kind='NORMAL' if item['purchase_mode']!='MSI' else 'UNPLANNED',
                                source_id=item['id'], confirmed=False))
        for movement in connection.execute('SELECT id,kind,posted_at,amount_cents FROM institution_movement WHERE instrument_id=?', (member,)):
            if movement['kind'] in ('INTEREST','COMMISSION','ADJUSTMENT'):
                # Financing interest is already inside installments.
                entries.append(dict(due_date=normal_due(connection, member, movement['posted_at'][:10]),
                                    amount_cents=movement['amount_cents'], applied_cents=0,
                                    remaining_cents=movement['amount_cents'], kind='OTHER',
                                    source_id=movement['id'], confirmed=False))
            elif movement['kind'] in ('REFUND','BONUS'):
                has_credits = True
        paid = connection.execute(
            "SELECT COALESCE(SUM(amount_cents),0) FROM institution_payment "
            "WHERE instrument_id=? AND payment_status='ACTIVE'", (member,)).fetchone()[0]
        applied = sum(i['applied_cents'] for i in installments)
        unapplied += max(0, paid-applied)
        if normal:
            warnings.append('Compras normales: vencimiento estimado con el calendario registrado para la compra o, si falta historial, con las reglas actuales configuradas. No reconstruye un estado de cuenta. Sin reglas queda sin periodo.')
        if any(item['purchase_mode']=='MSI' for item in normal):
            warnings.append('Hay MSI sin cuotas capturadas: su principal queda sin periodo, no se adelanta al mes actual.')
    if has_credits:
        warnings.append('Hay devoluciones o bonificaciones acreditadas: reducen la deuda total, pero no tienen aplicación mensual verificada. El pendiente identificado es incompleto.')
    if unapplied:
        warnings.append('Hay pagos bancarios sin asignar a cuotas. Reducen la deuda total, pero no sabemos qué meses cubren; el pendiente identificado es incompleto.')
    if any(not e['confirmed'] and e['kind']=='MSI' and e['amount_cents'] for e in entries):
        warnings.append('Fechas MSI capturadas: calendario bancario por confirmar. Los meses anteriores no se declaran vencidos confirmados.')
    totals = month_totals(entries, as_of)
    remaining = month_totals([dict(due_date=e['due_date'],amount_cents=e['remaining_cents']) for e in entries],as_of)
    key = as_of.strftime('%Y-%m')
    current = [e for e in entries if e['due_date'] and e['due_date'][:7]==key]
    confirmed_previous = sum(e['remaining_cents'] for e in entries if e['confirmed'] and e['due_date']
                             and e['due_date'][:7] < as_of.strftime('%Y-%m'))
    if totals['undated_cents']:
        warnings.append('Vencimiento pendiente de configurar o confirmar: los importes sin fecha no se adelantan al mes seleccionado.')
    breakdown = {kind:sum(e['amount_cents'] for e in current if e['kind']==kind) for kind in ('NORMAL','MSI','OTHER')}
    return dict(totals, period=key, entries=entries, basis='scheduled_due_v1',
                scheduled_cents=totals['current_cents'], breakdown=breakdown,
                payments_applied_cents=sum(e['applied_cents'] for e in current), credits_applied_cents=0,
                pending_identified_cents=remaining['current_cents'],
                pending_complete=not (unapplied or has_credits or totals['undated_cents']),
                msi_future_cents=sum(e['amount_cents'] for e in entries if e['kind']=='MSI' and e['due_date'] and e['due_date'][:7]>key),
                future_pending_cents=remaining['future_cents'], scheduled_previous_cents=totals['overdue_cents'],
                overdue_cents=remaining['overdue_cents'],
                confirmed_overdue_cents=confirmed_previous,
                previous_unconfirmed_cents=remaining['overdue_cents']-confirmed_previous,
                unassigned_payments_cents=unapplied, warnings=list(dict.fromkeys(warnings)))
