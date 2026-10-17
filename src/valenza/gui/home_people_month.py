"""Read-only projection of existing receivables for the Home people chart."""
from datetime import date


def people_month_breakdown(repository, as_of):
    period = as_of.strftime('%Y-%m')
    monthly = repository.collection_monthly_summaries(as_of=as_of)
    modes = {r['id']: r['purchase_mode'] for r in repository.database.connection.execute(
        'SELECT id,purchase_mode FROM order_record')}
    amounts, sources, warnings = {}, {}, []
    for share in repository.list_collection_items():
        user = share['user_id']
        schedule = monthly[share['receivable_id']]
        is_msi = schedule['is_msi'] or modes.get(share.get('order_id')) == 'MSI'
        if is_msi:
            # No full-principal fallback for MSI without a usable plan/calendar.
            if not schedule['is_msi'] or schedule['undated_cents']:
                warnings.append(f"{share['user_name']} · {share['source_name']}: MSI con fechas o plan pendientes.")
            amount = max(0, schedule['current_cents']) if schedule['is_msi'] else 0
            basis = 'MSI del mes'
        else:
            try:
                purchased = date.fromisoformat(share['source_date'])
            except (TypeError, ValueError):
                warnings.append(f"{share['user_name']} · {share['source_name']}: fecha pendiente.")
                continue
            if purchased.strftime('%Y-%m') > period:
                continue
            # Outstanding normal purchases carry forward; selecting another month
            # does not settle them. A credit on one order is not a receipt on another.
            amount = max(0, share['remaining_cents'])
            basis = 'Compra pendiente' if purchased.strftime('%Y-%m') == period else 'Compra anterior pendiente'
        amounts[user] = amounts.get(user, 0) + amount
        if amount:
            sources.setdefault(user, []).append(dict(receivable_id=share['receivable_id'],
                source_name=share['source_name'], amount_cents=amount, basis=basis))
    return dict(amounts=amounts, sources=sources, warnings=warnings)
