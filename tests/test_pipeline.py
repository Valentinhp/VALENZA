from sgccc.ocr.models import DocumentKind, MovementKind
from sgccc.ocr.pipeline import analyze_text


def test_mercado_pago_wallet_does_not_become_credit():
    result = analyze_text(
        "Comprobante de pago\n03/10/2026 19:41\nTotal $129.99\n"
        "Medio de pago: Dinero en Mercado Pago",
        source_platform="mercado_pago",
        source_kind="synthetic_text",
    )
    assert result.document_type is DocumentKind.MP_RECEIPT
    assert result.movements[0].amount_cents == 12999
    assert result.movements[0].payment_instrument == "WALLET_BALANCE"
    assert result.movements[0].movement_type is MovementKind.CHARGE
    assert result.review_status == "proposed"


def test_nu_keeps_three_same_day_same_amount_rows():
    result = analyze_text(
        "NU Resumen de transacciones\n"
        "Tus gastos actuales en la tarjeta $6,587.41\n"
        "08/10/2026 CFE $100.00\n"
        "08/10/2026 CFE $100.00\n"
        "08/10/2026 CFE $100.00\n"
        "Captura parcial",
        source_platform="nu",
        source_kind="synthetic_text",
    )
    assert result.document_type is DocumentKind.NU_TRANSACTIONS_SCREEN
    assert len(result.movements) == 3
    assert [item.amount_cents for item in result.movements] == [10000, 10000, 10000]
    assert result.is_partial_capture
    assert result.review_status == "proposed"


def test_unknown_fields_are_none_and_no_accounting_write_occurs():
    result = analyze_text(
        "Comprobante de pago Mercado Pago\n03/10/2026\nMedio de pago: desconocido",
        source_platform="mercado_pago",
        source_kind="synthetic_text",
    )
    movement = result.movements[0]
    assert movement.amount_cents is None
    assert movement.payment_instrument is None
    assert movement.status == "proposed"
    assert "No se identifico" in movement.warnings[0]
