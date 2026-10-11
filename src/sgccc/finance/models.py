from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class AllocationMethod(StrEnum):
    WHOLE = "WHOLE"
    UNITS = "UNITS"
    PERCENT = "PERCENT"


class ChargeKind(StrEnum):
    INTEREST = "INTEREST"
    COMMISSION = "COMMISSION"
    SHIPPING = "SHIPPING"
    OTHER = "OTHER"


class PaymentInstrumentType(StrEnum):
    CREDIT_LINE = "CREDIT_LINE"
    CREDIT_CARD = "CREDIT_CARD"
    WALLET_BALANCE = "WALLET_BALANCE"
    OTHER = "OTHER"


class InstallmentStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    DUE = "DUE"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    ADJUSTED = "ADJUSTED"


class ReconciliationStatus(StrEnum):
    UNRECONCILED = "UNRECONCILED"
    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"


class InstitutionMovementKind(StrEnum):
    CHARGE = "CHARGE"
    PAYMENT = "PAYMENT"
    INTEREST = "INTEREST"
    COMMISSION = "COMMISSION"
    REFUND = "REFUND"
    BONUS = "BONUS"
    ADJUSTMENT = "ADJUSTMENT"


class BonusStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REVERTED = "REVERTED"


class ReceivableAdjustmentKind(StrEnum):
    WRITE_OFF = "write_off"
    FORGIVENESS = "forgiveness"
    RECOVERY = "recovery"


@dataclass(frozen=True, slots=True)
class User:
    id: str
    name: str
    is_owner: bool = False
    active: bool = True


@dataclass(frozen=True, slots=True)
class Institution:
    id: str
    name: str
    active: bool = True


@dataclass(frozen=True, slots=True)
class FinancialInstrument:
    id: str
    institution_id: str
    alias: str
    instrument_type: PaymentInstrumentType
    active: bool = True


@dataclass(frozen=True, slots=True)
class ProductLine:
    id: str
    description: str
    quantity: int
    unit_price_cents: int

    @property
    def gross_cents(self) -> int:
        return self.quantity * self.unit_price_cents


@dataclass(frozen=True, slots=True)
class Allocation:
    line_id: str
    user_id: str
    method: AllocationMethod
    quantity: int | None
    share_cents: int
    percentage_basis: int | None = None


@dataclass(frozen=True, slots=True)
class Discount:
    id: str
    amount_cents: int
    line_id: str | None = None
    eligible: bool = True
    confirmed: bool = True
    source: str = "unknown"


@dataclass(frozen=True, slots=True)
class Charge:
    kind: ChargeKind
    amount_cents: int
    allocated_to_user_id: str | None = None


@dataclass(frozen=True, slots=True)
class Purchase:
    id: str
    purchased_at: str
    merchant: str
    instrument_id: str
    lines: tuple[ProductLine, ...]
    allocations: tuple[Allocation, ...]
    discounts: tuple[Discount, ...] = ()
    charges: tuple[Charge, ...] = ()


@dataclass(frozen=True, slots=True)
class FinancingPlan:
    id: str
    purchase_id: str
    instrument_id: str
    principal_cents: int
    interest_cents: int
    installments: tuple[Installment, ...]


@dataclass(frozen=True, slots=True)
class Installment:
    id: str
    number: int
    due_date: str
    principal_cents: int
    interest_cents: int
    status: InstallmentStatus = InstallmentStatus.SCHEDULED


@dataclass(frozen=True, slots=True)
class InstrumentCalendar:
    id: str
    instrument_id: str
    effective_from: str
    effective_to: str | None
    closing_rule: str | None
    due_rule: str | None
    source: str
    revision: int
    status: str = "confirmed"


@dataclass(frozen=True, slots=True)
class InstallmentPeriodAssignment:
    id: str
    installment_id: str
    calendar_id: str | None
    period_key: str | None
    source: str
    calendar_revision: int | None
    status: ReconciliationStatus = ReconciliationStatus.PROPOSED
    requires_review: bool = False


@dataclass(frozen=True, slots=True)
class PeriodCorrectionEvent:
    id: str
    assignment_id: str
    old_period_key: str | None
    new_period_key: str | None
    old_due_date: str | None
    new_due_date: str | None
    reason: str
    actor: str
    occurred_at: str
    evidence_id: str | None = None


@dataclass(frozen=True, slots=True)
class InstitutionMovement:
    id: str
    instrument_id: str
    posted_at: str
    kind: InstitutionMovementKind
    amount_cents: int
    description: str
    external_ref: str | None = None
    source_document_id: str | None = None
    status: ReconciliationStatus = ReconciliationStatus.UNRECONCILED


@dataclass(frozen=True, slots=True)
class InitialBalance:
    id: str
    instrument_id: str
    effective_date: str
    amount_cents: int
    currency: str
    source: str
    notes: str | None = None
    reconciliation_status: ReconciliationStatus = ReconciliationStatus.UNRECONCILED


@dataclass(frozen=True, slots=True)
class InitialBalanceReconciliation:
    id: str
    opening_balance_id: str
    movement_id: str | None
    delta_cents: int
    reason: str
    status: ReconciliationStatus = ReconciliationStatus.PROPOSED
    approved_by: str | None = None
    approved_at: str | None = None


@dataclass(frozen=True, slots=True)
class MatchSuggestion:
    id: str
    source_a_id: str
    source_b_id: str
    evidence: tuple[str, ...]
    confidence: str | None = None
    status: ReconciliationStatus = ReconciliationStatus.PROPOSED
    approved_by: str | None = None
    approved_at: str | None = None


@dataclass(frozen=True, slots=True)
class RefundEvent:
    id: str
    purchase_id: str
    line_id: str
    requested_cents: int
    approved_cents: int | None
    applied_to_institution_cents: int | None
    paid_to_user_cents: int | None
    beneficiary_user_id: str | None
    status: str
    occurred_at: str
    source_document_id: str | None = None


@dataclass(frozen=True, slots=True)
class BonusEvent:
    id: str
    purchase_id: str
    amount_cents: int
    source: str
    eligibility: str
    status: BonusStatus
    occurred_at: str
    destination_instrument_id: str | None = None
    reversal_of: str | None = None
    source_document_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReceivableAdjustmentEvent:
    id: str
    receivable_id: str
    kind: ReceivableAdjustmentKind
    amount_cents: int
    occurred_at: str
    reason: str
    actor: str
    prior_event_id: str | None = None
    evidence_id: str | None = None


@dataclass(frozen=True, slots=True)
class AuditEvent:
    id: str
    entity_type: str
    entity_id: str
    action: str
    occurred_at: str
    actor: str
    reason: str
    old_value: str | None = None
    new_value: str | None = None

@dataclass(frozen=True, slots=True)
class Receivable:
    id: str
    user_id: str
    purchase_id: str
    sale_cents: int
    attributable_cost_cents: int
    due_date: str | None = None


@dataclass(frozen=True, slots=True)
class UserPayment:
    id: str
    user_id: str
    received_at: str
    amount_cents: int
    reference: str | None = None


@dataclass(frozen=True, slots=True)
class InstitutionPayment:
    id: str
    instrument_id: str
    paid_at: str
    amount_cents: int
    reference: str | None = None


@dataclass(frozen=True, slots=True)
class ReceiptApplication:
    payment_id: str
    receivable_id: str
    amount_cents: int


@dataclass(frozen=True, slots=True)
class FinancialSummary:
    projected_margin_cents: int
    realized_margin_cents: int
    applied_collections_cents: int
    unapplied_collections_cents: int
    recognized_cost_cents: int
    discount_savings_cents: int = 0
    owner_cost_cents: int = field(default=0)
