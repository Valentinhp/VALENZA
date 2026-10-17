"""Shared wording and read-only projection of the existing personal calculation."""

EXPLANATION = (
    'Supone cobrar todas las participaciones familiares, antes de abonos personales. '
    'No representa dinero ya recibido, dinero disponible ni una cantidad exigible hoy. '
    'Los descuentos ya están incluidos en el costo efectivo y no se restan otra vez. '
    'Devoluciones y recompras vinculadas se incluyen una sola vez.'
)


def result_label(cents):
    return 'a favor' if cents >= 0 else 'a tu cargo'


def personal_result(repository):
    summary = repository.dashboard_summary()
    return dict(rows=repository.expected_result_breakdown(),
                result_cents=summary['personal_expected_result_cents'],
                discount_cents=summary['discount_benefit_cents'])
