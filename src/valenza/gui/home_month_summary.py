"""Original Home monthly residual, independent of the newer Cards forecast."""
from valenza.finance.monthly import month_totals
from valenza.gui.warm_finance import period_label
from valenza.gui.clarity_text import MONTHLY_BASES_EXPLANATION


def home_month_summary(repository, comparisons, as_of):
    cards = {c['instrument_id']:c for c in repository.list_card_summaries(include_inactive=True)
             if c['instrument_type'] in ('CREDIT_CARD','CREDIT_LINE')}
    accounts, seen = [], set()
    fields = ('current_cents','debt_cents','future_cents','overdue_cents','undated_cents','msi_month_cents')
    for account in comparisons:
        row = dict(account_id=account['account_id'],alias=account['alias'])
        row.update({key:0 for key in fields})
        for member in account['members']:
            if member in seen or member not in cards:
                continue
            seen.add(member)
            card = cards[member]
            # Same pending installment buckets as list_card_summaries at session
            # start, using the selected month without reconstructing past balances.
            buckets = month_totals([dict(due_date=i['due_date'],amount_cents=i['remaining_cents'])
                                   for i in repository.list_installments(member)], as_of)
            debt = int(card['remaining_cents'])  # Already includes all active bank payments.
            # Exact original formula. Clamp per instrument BEFORE grouping lines.
            row['current_cents'] += max(0, debt-buckets['future_cents']
                                       -buckets['overdue_cents']-buckets['undated_cents'])
            row['debt_cents'] += debt
            row['msi_month_cents'] += buckets['current_cents']
            for key in ('future_cents','overdue_cents','undated_cents'):
                row[key] += buckets[key]
        accounts.append(row)
    summary = {key:sum(a[key] for a in accounts) for key in fields}
    return dict(summary,period=as_of.strftime('%Y-%m'),basis='initial_home_residual',accounts=accounts)


def home_month_text(summary, money):
    return (f"{period_label(summary['period'])} · desglose del pendiente mensual.\n"
            f"MSI futuros separados: {money(summary['future_cents'])} · Cuotas anteriores: {money(summary['overdue_cents'])} · Cuotas sin fecha: {money(summary['undated_cents'])}\n"
            'La deuda pendiente ya descuenta los pagos bancarios; no se restan otra vez. '
            'Este indicador no sustituye el importe oficial informado por el banco.\n'
            + MONTHLY_BASES_EXPLANATION)
