"""Exact amounts shared by the editor and atomic refund/repurchase saving."""


def refund_repurchase_amounts(original, refund, replacement=None, apply_surplus=False):
    if any(type(v) is not int for v in (original, refund)) or not 0 < refund <= original:
        raise ValueError('El reembolso debe ser positivo y no superar el producto original.')
    if replacement is None:
        return dict(difference=original-refund, surplus=refund, applied=0,
                    final_total=original-refund, wallet_change=refund)
    if type(replacement) is not int or not 0 < replacement <= refund or type(apply_surplus) is not bool:
        raise ValueError('Revisa la recompra: debe ser positiva y no superar el reembolso disponible.')
    surplus = refund - replacement
    applied = surplus if apply_surplus else 0
    return dict(difference=original-refund, surplus=surplus, applied=applied,
                final_total=original-applied, wallet_change=surplus)
