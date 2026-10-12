import pytest

from valenza.finance.models import (
    Allocation,
    AllocationMethod,
    PaymentInstrumentType,
    ProductLine,
    Receivable,
    ReceiptApplication,
    UserPayment,
)
from valenza.finance.rules import (
    build_financing_plan,
    internal_cost_by_user,
    prorate_discount,
    summarize_receipts,
    validate_financing_instrument,
    validate_line_allocations,
)


def test_allocations_must_equal_line_total():
    line = ProductLine("line", "Producto", 3, 1999)
    allocations = (
        Allocation("line", "owner", AllocationMethod.UNITS, 1, 1999),
        Allocation("line", "ana", AllocationMethod.UNITS, 2, 3998),
    )
    validate_line_allocations(line, allocations)


def test_allocation_residual_is_rejected():
    line = ProductLine("line", "Producto", 1, 1999)
    allocations = (Allocation("line", "ana", AllocationMethod.PERCENT, None, 1998),)
    with pytest.raises(ValueError, match="no cuadran"):
        validate_line_allocations(line, allocations)


def test_discount_is_prorated_in_cents_and_does_not_change_third_party_price():
    allocations = (
        Allocation("line", "owner", AllocationMethod.WHOLE, None, 60000),
        Allocation("line", "carlos", AllocationMethod.WHOLE, None, 85000),
        Allocation("line", "ana", AllocationMethod.WHOLE, None, 55000),
    )
    internal = internal_cost_by_user(allocations=allocations, discount_cents=40000)
    assert internal == {"owner": 48000, "carlos": 68000, "ana": 44000}
    assert sum(item.share_cents for item in allocations if item.user_id != "owner") == 140000


def test_discount_residual_is_deterministic():
    assert prorate_discount(1, {"b": 1, "a": 1}) == {"a": 1, "b": 0}


def test_msi_principal_is_not_duplicated():
    plan = build_financing_plan(
        plan_id="plan",
        purchase_id="purchase",
        instrument_id="nu",
        principal_cents=120000,
        interest_cents=0,
        installment_specs=(("2026-11-03", 0), ("2026-12-03", 0), ("2027-01-03", 0)),
    )
    assert [item.principal_cents for item in plan.installments] == [40000, 40000, 40000]
    assert sum(item.principal_cents for item in plan.installments) == plan.principal_cents


def test_interest_is_separate_from_principal():
    plan = build_financing_plan(
        plan_id="plan",
        purchase_id="purchase",
        instrument_id="nu",
        principal_cents=120000,
        interest_cents=9000,
        installment_specs=(("2026-11-03", 0), ("2026-12-03", 0), ("2027-01-03", 0)),
    )
    assert sum(item.principal_cents for item in plan.installments) == 120000
    assert sum(item.interest_cents for item in plan.installments) == 9000


def test_wallet_does_not_create_credit_obligation():
    with pytest.raises(ValueError, match="wallet"):
        validate_financing_instrument(PaymentInstrumentType.WALLET_BALANCE)


def test_partial_applied_payment_recognizes_proportional_realized_margin():
    receivable = Receivable("r", "carlos", "purchase", 100000, 80000)
    payment = UserPayment("p", "carlos", "2026-10-10", 50000)
    result = summarize_receipts(
        receivable=receivable,
        payments=(payment,),
        applications=(ReceiptApplication("p", "r", 50000),),
    )
    assert result.projected_margin_cents == 20000
    assert result.realized_margin_cents == 10000
    assert result.recognized_cost_cents == 40000


def test_two_payments_finish_without_rounding_drift():
    receivable = Receivable("r", "carlos", "purchase", 100000, 80000)
    payments = (
        UserPayment("p1", "carlos", "2026-10-10", 33333),
        UserPayment("p2", "carlos", "2026-11-10", 66667),
    )
    result = summarize_receipts(
        receivable=receivable,
        payments=payments,
        applications=(
            ReceiptApplication("p1", "r", 33333),
            ReceiptApplication("p2", "r", 66667),
        ),
    )
    assert result.recognized_cost_cents == 80000
    assert result.realized_margin_cents == 20000


def test_unassigned_payment_does_not_realize_margin():
    receivable = Receivable("r", "carlos", "purchase", 100000, 80000)
    result = summarize_receipts(
        receivable=receivable,
        payments=(UserPayment("p", "carlos", "2026-10-10", 50000),),
        applications=(),
    )
    assert result.realized_margin_cents == 0
    assert result.unapplied_collections_cents == 50000


def test_overpayment_is_not_automatically_profit():
    receivable = Receivable("r", "carlos", "purchase", 100000, 80000)
    result = summarize_receipts(
        receivable=receivable,
        payments=(UserPayment("p", "carlos", "2026-10-10", 110000),),
        applications=(ReceiptApplication("p", "r", 100000),),
    )
    assert result.realized_margin_cents == 20000
    assert result.unapplied_collections_cents == 10000


def test_zero_sale_is_reviewed_without_division():
    receivable = Receivable("r", "carlos", "purchase", 0, 80000)
    result = summarize_receipts(
        receivable=receivable,
        payments=(UserPayment("p", "carlos", "2026-10-10", 100),),
        applications=(),
    )
    assert result.realized_margin_cents == 0
