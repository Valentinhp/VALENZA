import pytest

from sgccc.finance.models import (
    BonusEvent,
    BonusStatus,
    InitialBalance,
    InstitutionMovement,
    InstitutionMovementKind,
    InstrumentCalendar,
    Receivable,
    ReceivableAdjustmentEvent,
    ReceivableAdjustmentKind,
    ReconciliationStatus,
    RefundEvent,
    UserPayment,
)
from sgccc.finance.rules import (
    accept_match_suggestion,
    assign_installment_period,
    confirmed_bonus_effect,
    correct_installment_period,
    propose_initial_balance_overlap,
    propose_proportional_payment,
    summarize_receivable_adjustments,
    validate_no_duplicate_movements,
    validate_receivable_adjustment,
    validate_refund_event,
)


def test_initial_balance_overlap_is_only_a_proposal():
    opening = InitialBalance("open", "nu", "2026-10-01", 500000, "MXN", "statement")
    movement = InstitutionMovement(
        "movement", "nu", "2026-09-30", InstitutionMovementKind.CHARGE, 500000, "old"
    )
    suggestion = propose_initial_balance_overlap(opening, (movement,))
    assert suggestion is not None
    assert suggestion.status is ReconciliationStatus.PROPOSED
    assert suggestion.source_b_id == "movement"


def test_accepting_match_is_explicit_and_auditable():
    opening = InitialBalance("open", "nu", "2026-10-01", 500000, "MXN", "statement")
    movement = InstitutionMovement(
        "movement", "nu", "2026-09-30", InstitutionMovementKind.CHARGE, 500000, "old"
    )
    suggestion = propose_initial_balance_overlap(opening, (movement,))
    accepted = accept_match_suggestion(suggestion, actor="owner", occurred_at="2026-10-10")
    assert accepted.status is ReconciliationStatus.ACCEPTED
    assert accepted.approved_by == "owner"


def test_duplicate_institution_reference_is_rejected():
    movements = (
        InstitutionMovement("a", "nu", "2026-10-01", InstitutionMovementKind.CHARGE, 100, "x", "ref"),
        InstitutionMovement("b", "nu", "2026-10-02", InstitutionMovementKind.CHARGE, 100, "x", "ref"),
    )
    with pytest.raises(ValueError, match="Referencia"):
        validate_no_duplicate_movements(movements)


def test_installment_without_calendar_requires_review():
    assignment = assign_installment_period(
        installment_id="installment",
        instrument_id="nu",
        calendar=None,
        period_key=None,
        source="manual",
    )
    assert assignment.requires_review
    assert assignment.status is ReconciliationStatus.PROPOSED


def test_installment_calendar_correction_preserves_audit_event():
    calendar = InstrumentCalendar(
        "cal", "nu", "2026-10-01", None, "day:23", "day:03", "statement", 2
    )
    assignment = assign_installment_period(
        installment_id="installment",
        instrument_id="nu",
        calendar=calendar,
        period_key="2026-11",
        source="statement",
    )
    correction = correct_installment_period(
        assignment,
        new_period_key="2026-12",
        new_due_date="2026-12-03",
        reason="Estado oficial corregido",
        actor="owner",
        occurred_at="2026-10-10",
        evidence_id="doc-1",
    )
    assert correction.old_period_key == "2026-11"
    assert correction.new_period_key == "2026-12"
    assert correction.evidence_id == "doc-1"


def test_pending_bonus_has_no_effect_and_reversal_needs_confirmed_original():
    pending = BonusEvent("b", "purchase", 1000, "promo", "line", BonusStatus.PENDING, "2026-10-10")
    assert confirmed_bonus_effect((pending,)) == 0
    bad_reversal = BonusEvent(
        "r", "purchase", 1000, "promo", "line", BonusStatus.REVERTED, "2026-10-10", reversal_of="b"
    )
    with pytest.raises(ValueError, match="confirmada"):
        confirmed_bonus_effect((pending, bad_reversal))


def test_confirmed_bonus_and_reversal_net_to_zero():
    confirmed = BonusEvent("b", "purchase", 1000, "promo", "line", BonusStatus.CONFIRMED, "2026-10-10")
    reversal = BonusEvent(
        "r", "purchase", 1000, "promo", "line", BonusStatus.REVERTED, "2026-10-11", reversal_of="b"
    )
    assert confirmed_bonus_effect((confirmed, reversal)) == 0


def test_refund_pending_does_not_claim_applied_destination():
    event = RefundEvent(
        "refund", "purchase", "line", 20000, None, None, None, "carlos", "PENDING", "2026-10-10"
    )
    validate_refund_event(event)


def test_refund_destinations_cannot_exceed_approved_amount():
    event = RefundEvent(
        "refund", "purchase", "line", 20000, 15000, 10000, 6000, "carlos", "APPROVED", "2026-10-10"
    )
    with pytest.raises(ValueError, match="destinos"):
        validate_refund_event(event)


def test_write_off_is_explicit_and_keeps_original_receivable_id():
    event = ReceivableAdjustmentEvent(
        "loss", "receivable", ReceivableAdjustmentKind.WRITE_OFF, 5000,
        "2026-10-10", "Incobrable declarado", "owner"
    )
    validate_receivable_adjustment(event)
    assert event.receivable_id == "receivable"


def test_write_off_forgiveness_and_recovery_remain_separate():
    events = (
        ReceivableAdjustmentEvent(
            "loss", "receivable", ReceivableAdjustmentKind.WRITE_OFF, 20000,
            "2026-10-10", "Castigo manual", "owner"
        ),
        ReceivableAdjustmentEvent(
            "recovery", "receivable", ReceivableAdjustmentKind.RECOVERY, 5000,
            "2026-11-10", "Recuperacion posterior", "owner", prior_event_id="loss"
        ),
    )
    summary = summarize_receivable_adjustments(
        original_sale_cents=50000,
        applied_collections_cents=10000,
        events=events,
    )
    assert summary["outstanding_cents"] == 20000
    assert summary["write_off"] == 20000
    assert summary["recovery"] == 5000
    assert summary["recovery_cash_cents"] == 5000


def test_unreferenced_payment_proposal_is_proportional_and_user_scoped():
    payment = UserPayment("payment", "carlos", "2026-10-10", 50000)
    receivables = (
        Receivable("a", "carlos", "pa", 60000, 40000),
        Receivable("b", "carlos", "pb", 40000, 30000),
        Receivable("other", "ana", "pc", 90000, 50000),
    )
    proposal = propose_proportional_payment(payment, receivables)
    assert proposal == {"a": 30000, "b": 20000}


def test_unreferenced_payment_excess_remains_unassigned():
    payment = UserPayment("payment", "carlos", "2026-10-10", 110000)
    receivables = (
        Receivable("a", "carlos", "pa", 60000, 40000),
        Receivable("b", "carlos", "pb", 40000, 30000),
    )
    proposal = propose_proportional_payment(payment, receivables)
    assert proposal == {"a": 60000, "b": 40000}
