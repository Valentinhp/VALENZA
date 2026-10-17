"""Read-only presentation of recorded refunds. Never reconstructs Wallet cash."""
from html import escape
from valenza.gui.warm_finance import format_money, date_label


def refund_tracking_html(order, linked_orders):
    """Derive only the initial remainder when recorded funding supports it."""
    refunds = order.get('product_refunds', [])
    if not refunds:
        amount = (order.get('import_evidence') or {}).get('refund', 0)
        return (f'Reembolso indicado en el comprobante: <b>{format_money(amount)}</b>.<br>'
                'Sin devolución vinculada: destino, acreditación y uso no confirmados.') if type(amount) is int and amount > 0 else ''
    blocks = []
    for refund in refunds:
        amount = refund.get('amount_cents')
        credited = refund.get('status') == 'ACCREDITED'
        amount_text = format_money(amount) if type(amount) is int and amount >= 0 else 'Importe no confirmado'
        destination = escape(str(refund.get('destination_name') or 'Destino no indicado'))
        status = ('Acreditado' + (' · ' + escape(date_label(refund['accredited_at'])) if refund.get('accredited_at') else ' · fecha no indicada')) if credited else 'Pendiente de acreditación' if refund.get('status') == 'PENDING' else 'Acreditación no confirmada'
        lines = [f'<b>{amount_text}</b> · {destination} · {status}']
        link = refund.get('repurchase')
        if link:
            cost = link.get('charged_cents')
            known_cost = type(cost) is int and cost > 0
            cost_text = format_money(cost) if known_cost else 'importe no confirmado'
            linked = linked_orders.get(link.get('order_id'))
            same_source = bool(linked and refund.get('destination_id')
                               and linked.get('instrument_id') == refund['destination_id'])
            valid_link = bool(linked and linked.get('order_status') == 'ACTIVE')
            funding_known = bool(credited and same_source and valid_link and known_cost
                                 and linked.get('charged_cents') == cost)
            medium = escape(str(link.get('payment_name') or 'medio no indicado'))
            lines.append(f'Recompra registrada: <b>{cost_text}</b> · {medium}.')
            applied = link.get('applied_cents')
            lines.append('Aplicado al reparto familiar: ' +
                (f'<b>{format_money(applied)}</b> (compensación contable).' if credited and valid_link and type(applied) is int and applied >= 0 else 'no confirmado.'))
            if (funding_known and type(amount) is int
                    and 0 <= cost <= amount and refund.get('destination_type') in ('WALLET_BALANCE', 'OTHER')):
                lines.append(f'Remanente inicial tras esa recompra: <b>{format_money(amount-cost)}</b>.')
            else:
                lines.append('Remanente: no calculable con la financiación y el estado registrados.')
        else:
            lines.append('Sin recompra vinculada; compensación por sobrante no registrada.')
        if refund.get('destination_type') in ('WALLET_BALANCE', 'OTHER'):
            lines.append('Uso posterior: no rastreado. Este seguimiento no confirma dinero disponible hoy.')
        elif refund.get('destination_type') in ('CREDIT_CARD', 'CREDIT_LINE'):
            lines.append('Destino registrado: tarjeta o línea de crédito; no es un ingreso en Wallet.')
        else:
            lines.append('Tipo de destino y uso posterior no confirmados.')
        blocks.append('<br>'.join(lines))
    blocks.append('Compensar el reparto no mueve dinero, no registra un cobro familiar ni paga Nu. '
                  'Se muestran registros, no una verificación externa.')
    return '<br><br>'.join(blocks)
