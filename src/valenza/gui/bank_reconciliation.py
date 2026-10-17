"""Shared presentation for live banking debt and immutable consultations."""
from html import escape
from valenza.persistence.bank_reconciliation import BALANCE_TYPES
from valenza.gui.warm_finance import date_label, period_label
from valenza.gui.clarity_text import MONTHLY_BASES_EXPLANATION


def scheduled_text(forecast, money):
    if forecast['undated_cents']:
        return 'Total sin determinar' if forecast['scheduled_cents'] else 'Por configurar'
    return money(forecast['scheduled_cents'])


def forecast_notice(forecast):
    """Short, visible caveats; the complete explanation stays in the breakdown."""
    notices = ['Previsión; no es el pago confirmado por el banco.']
    if forecast['undated_cents']:
        notices.append('Total incompleto: hay cargos sin vencimiento confirmado.')
    if forecast['unassigned_payments_cents'] or any('devoluciones o bonificaciones' in warning for warning in forecast['warnings']):
        notices.append('Pendiente incompleto: hay pagos o créditos sin aplicación al periodo.')
    if any('Fechas MSI' in warning for warning in forecast['warnings']):
        notices.append('Calendario MSI por confirmar; las cuotas anteriores no son vencidos confirmados.')
    return ' '.join(notices)


def forecast_text(forecast, money):
    if forecast.get('basis') == 'scheduled_due_v1':
        b = forecast['breakdown']
        status = ' · incompleto' if not forecast['pending_complete'] else ' · según aplicaciones registradas'
        amount_label = 'Parte identificada' if forecast['undated_cents'] else 'Programación vigente antes de pagos'
        return (f"Periodo {forecast['period']} · {amount_label}: {money(forecast['scheduled_cents'])}\n"
            f"Compras normales: {money(b['NORMAL'])} · MSI del mes: {money(b['MSI'])} · Otros cargos: {money(b['OTHER'])}\n"
            f"Pagos aplicados al periodo: {money(forecast['payments_applied_cents'])} · Créditos aplicados: {money(forecast['credits_applied_cents'])}\n"
            f"Pendiente identificado actualmente: {money(forecast['pending_identified_cents'])}{status}\n"
            f"MSI futuros programados: {money(forecast['msi_future_cents'])} · Otros futuros: {money(forecast['future_cents']-forecast['msi_future_cents'])}\n"
            f"Vencidos según calendario: {money(forecast['confirmed_overdue_cents'])} · Anteriores por confirmar: {money(forecast['previous_unconfirmed_cents'])} · Sin vencimiento: {money(forecast['undated_cents'])}\n"
            'Estimación según tus compras, MSI y fechas configuradas. El importe oficial puede variar según el estado de cuenta del banco. '
            'El pendiente es conocido actualmente, no una fotografía histórica del mes. '
            + ' '.join(forecast['warnings'])+'\n'+MONTHLY_BASES_EXPLANATION)
    return (f"Periodo de vencimiento {forecast['period']} · programado pendiente: {money(forecast['current_cents'])}\n"
            f"Meses futuros: {money(forecast['future_cents'])} · Vencidos identificados: {money(forecast['confirmed_overdue_cents'])}\n"
            f"Anteriores por confirmar: {money(forecast['previous_unconfirmed_cents'])} · Sin periodo: {money(forecast['undated_cents'])}\n"
            + (f"Pagos sin asignar a cuotas: {money(forecast['unassigned_payments_cents'])}\n" if forecast.get('unassigned_payments_cents') else '') +
            'No es el pago mínimo ni el pago para no generar intereses. '
            + ' '.join(forecast['warnings']))


def difference_text(cents, money):
    if cents is None:
        return 'No comparable'
    if cents == 0:
        return 'Coincide'
    return ('El banco muestra más: ' if cents > 0 else 'Valenza muestra más: ') + money(abs(cents))


def reported_text(query, money):
    if not query:
        return 'Sin consulta'
    labels={'TOTAL':'','STATEMENT':'Al corte: ','MONTHLY':'Pago del mes: ',
            'PENDING':'Incluye pendientes: ','UNKNOWN':'Tipo sin confirmar: ',
            'NO_INTEREST':'Sin generar intereses: ', 'MINIMUM':'Pago mínimo: ', 'OTHER':'Otro saldo: '}
    return labels[query['balance_type']]+money(query['amount_cents'])


def official_period_query(history, account, period):
    candidates = [q for q in history if q.get('period')==period
                  and q['balance_type'] in ('NO_INTEREST','MINIMUM')
                  and q['account_id']==account['account_id']
                  and sorted(q.get('members',[]))==sorted(account['members'])]
    return next((q for q in candidates if q['balance_type']=='NO_INTEREST'), candidates[0] if candidates else None)


def official_text(query, money, *, compact=False):
    if not query:
        return ''
    text = (f"Lo que pide el banco: {money(query['amount_cents'])} · {BALANCE_TYPES[query['balance_type']]} "
            f"· {period_label(query['period'])} · capturado manualmente")
    return text if compact else text+f", consulta {date_label(query['consulted_at'])}"


def monthly_comparison_text(forecast, amount, balance_type, money, *, reliable=True):
    if balance_type=='MINIMUM':
        return f"Pago mínimo informado: {money(amount)}. No comparable con la previsión mensual: son conceptos diferentes. No se calcula una diferencia."
    if balance_type=='NO_INTEREST':
        return (f'Referencia oficial introducida manualmente: {money(amount)}. '
                'No se calcula ni se descuenta automáticamente. Compromisos del mes es una estimación interna diferente; '
                'no se calcula una diferencia entre estos conceptos.')
    return f"Saldo informado: {money(amount)}. No comparable con la previsión mensual: confirma el concepto del banco."


def query_text(query, money):
    if not query:
        return 'Sin consulta'
    calculated=money(query['calculated_cents']) if query['calculated_cents'] is not None else 'Sin fotografía'
    monthly = query.get('monthly_forecast')
    context = (f"Periodo de vencimiento: {query['period']} · {query.get('balance_label', '')}\n"
               f"Calendario Valenza al guardar: {money(monthly['current_cents'])} (no es el pago confirmado por el banco)\n") if monthly else ''
    if monthly and monthly.get('basis')=='scheduled_due_v1':
        context = forecast_text(monthly,money)+'\n'
        if query.get('orientative_difference_cents') is not None:
            context += f"Diferencia orientativa guardada (banco − programado): {money(query['orientative_difference_cents'])}. No es una coincidencia bancaria exacta.\n"
    return (f"Consulta: {date_label(query['consulted_at'])} · {BALANCE_TYPES[query['balance_type']]}\n"
            + (f"Corte: {query['closing_date']} · Fecha límite: {query['due_date']}\n" if query.get('closing_date') else '')
            + context +
            f"Banco: {money(query['amount_cents'])} · Deuda total Valenza al guardar: {calculated}\n"
            f"Guardado: {date_label(query['recorded_at'])}\n"
            f"Diferencia histórica: {difference_text(query['difference_cents'],money)}\n"
            + ' '.join(query['warnings']))


def breakdown_html(components, money):
    parts=[]
    labels={'INTEREST':'Intereses registrados','COMMISSION':'Comisiones registradas','ADJUSTMENT':'Ajustes registrados',
            'REFUND':'Devoluciones acreditadas en esta cuenta (reducen cargo)', 'BONUS':'Bonificaciones en esta cuenta (reducen cargo)'}
    for row in components:
        parts.append(f"<p><b>{escape(row['alias'])}</b><br>"
            f"Cargos reales de pedidos activos: {money(row['order_charges_cents'])}<br>"
            f"Intereses del financiamiento: {money(row['financing_interest_cents'])}<br>")
        for movement in row['movements']:
            if movement['kind'] in labels:
                parts.append(f"{labels[movement['kind']]}: {money(movement['amount_cents'])}<br>")
        parts.append(f"Cargo neto registrado: {money(row['charged_cents'])} · Pagos reales al banco: {money(row['bank_payments_cents'])}<br>"
            f"Deuda total calculada: <b>{money(row['calculated_cents'])}</b> · Saldo a favor separado: {money(row['credit_cents'])}<br>"
            f"MSI futuros: {money(row['future_msi_cents'])} (ya incluidos; no se suman otra vez).<br>"
            f"Cuotas vencidas según calendario: {money(row['exigible_cents'])} (no son el pago confirmado por el banco).</p>")
    parts.append('<p>Los cargos ya incluyen descuentos. Las participaciones, abonos familiares y compensaciones de Wallet no son pagos bancarios. '
                 'Devoluciones y recompras solo afectan la cuenta de su movimiento registrado. '
                 'El saldo al corte y los movimientos bancarios pendientes de aplicación no se conocen con precisión; no se reconstruyen. '
                 'Una diferencia es una observación, no un error confirmado.</p>')
    return ''.join(parts)
