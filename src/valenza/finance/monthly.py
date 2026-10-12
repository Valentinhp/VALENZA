"""Read-only month buckets for existing unpaid installments."""


def month_totals(entries, as_of):
    key = as_of.strftime('%Y-%m')
    result = dict(current_cents=0, overdue_cents=0, future_cents=0, undated_cents=0)
    for entry in entries:
        due = entry.get('due_date')
        if not due:
            bucket = 'undated_cents'
        elif due[:7] == key:
            bucket = 'current_cents'
        elif due[:7] < key:
            bucket = 'overdue_cents'
        else:
            bucket = 'future_cents'
        result[bucket] += entry['amount_cents']
    return result
