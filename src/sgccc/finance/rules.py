from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from .models import (
    Allocation,
    AllocationMethod,
    BonusEvent,
    BonusStatus,
    FinancialSummary,
    FinancingPlan,
    InitialBalance,
    InstitutionMovement,
    Installment,
    InstallmentPeriodAssignment,
    InstrumentCalendar,
    MatchSuggestion,
    PaymentInstrumentType,
    PeriodCorrectionEvent,
    ProductLine,
    Purchase,
    ReceivableAdjustmentEvent,
    ReceivableAdjustmentKind,
    ReconciliationStatus,
    RefundEvent,
    ReceiptApplication,
    Receivable,
    UserPayment,
)


def _require_nonnegative(value: int, label: str) -> None:
    if value < 0:
        raise ValueError(f"{label} no puede ser negativo")


def validate_line_allocations(line: ProductLine, allocations: tuple[Allocation, ...]) -> None:
    if not allocations:
        raise ValueError("Una linea debe tener al menos una asignacion")
    if any(item.line_id != line.id for item in allocations):
        raise ValueError("La asignacion referencia otra linea")
    for allocation in allocations:
        _require_nonnegative(allocation.share_cents, "La asignacion")
        if allocation.method is AllocationMethod.UNITS and allocation.quantity is None:
            raise ValueError("Una asignacion por unidades requiere cantidad")
    if sum(item.share_cents for item in allocations) != line.gross_cents:
        raise ValueError("Las asignaciones no cuadran con el total de la linea")
    quantities = [item.quantity for item in allocations if item.quantity is not None]
    if quantities and sum(quantities) != line.quantity:
        raise ValueError("Las cantidades asignadas no cuadran con la linea")


def allocate_line_shares(
    line: ProductLine,
    assignments: tuple[tuple[str, AllocationMethod, int], ...],
) -> tuple[Allocation, ...]:
    """Calcula repartos deterministas por unidades o puntos porcentuales."""
    if not assignments:
        raise ValueError("Una linea debe tener al menos una asignacion")
    if len({user_id for user_id, _, _ in assignments}) != len(assignments):
        raise ValueError("Una persona no puede repetirse en la misma linea")
    total_basis = sum(value for _, _, value in assignments)
    if any(value <= 0 for _, _, value in assignments):
        raise ValueError("El reparto debe ser positivo")
    methods = {method for _, method, _ in assignments}
    if len(methods) != 1:
        raise ValueError("Una linea no puede mezclar unidades y proporciones")
    method = methods.pop()
    expected = line.quantity if method is AllocationMethod.UNITS else 10000
    if total_basis != expected:
        raise ValueError("El reparto no cuadra con la cantidad o proporción total")
    remaining = line.gross_cents
    allocations: list[Allocation] = []
    for index, (user_id, _, basis) in enumerate(assignments):
        share = remaining if index == len(assignments) - 1 else _round_ratio(
            line.gross_cents, basis, expected
        )
        remaining -= share
        allocations.append(
            Allocation(
                line_id=line.id,
                user_id=user_id,
                method=method,
                quantity=basis if method is AllocationMethod.UNITS else None,
                share_cents=share,
                percentage_basis=basis if method is AllocationMethod.PERCENT else None,
            )
        )
    result = tuple(allocations)
    validate_line_allocations(line, result)
    return result


def _round_ratio(amount: int, numerator: int, denominator: int) -> int:
    return int(
        (Decimal(amount) * Decimal(numerator) / Decimal(denominator)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def prorate_discount(
    discount_cents: int,
    eligible_shares: dict[str, int],
) -> dict[str, int]:
    """Distribuye centavos proporcionalmente y asigna el residual de forma estable."""
    _require_nonnegative(discount_cents, "El descuento")
    total = sum(eligible_shares.values())
    if discount_cents > total:
        raise ValueError("El descuento excede el bruto elegible")
    if total == 0 and discount_cents:
        raise ValueError("No hay importe elegible para distribuir el descuento")
    result: dict[str, int] = {}
    remaining = discount_cents
    ordered = sorted(eligible_shares.items())
    for index, (key, share) in enumerate(ordered):
        value = (
            remaining
            if index == len(ordered) - 1
            else _round_ratio(discount_cents, share, total)
        )
        result[key] = value
        remaining -= value
    return result


def build_financing_plan(
    *,
    plan_id: str,
    purchase_id: str,
    instrument_id: str,
    principal_cents: int,
    interest_cents: int,
    installment_specs: tuple[tuple[str, int], ...],
) -> FinancingPlan:
    _require_nonnegative(principal_cents, "El principal")
    _require_nonnegative(interest_cents, "El interes")
    if not installment_specs:
        raise ValueError("El plan requiere mensualidades")
    principal_each, residual = divmod(principal_cents, len(installment_specs))
    interest_each, interest_residual = divmod(interest_cents, len(installment_specs))
    installments = tuple(
        Installment(
            id=f"{plan_id}-{number}",
            number=number,
            due_date=due_date,
            principal_cents=principal_each + (1 if number <= residual else 0),
            interest_cents=interest_each + (1 if number <= interest_residual else 0),
        )
        for number, (due_date, _) in enumerate(installment_specs, start=1)
    )
    if sum(item.principal_cents for item in installments) != principal_cents:
        raise AssertionError("Error interno de redondeo de principal")
    if sum(item.interest_cents for item in installments) != interest_cents:
        raise AssertionError("Error interno de redondeo de interes")
    return FinancingPlan(
        id=plan_id,
        purchase_id=purchase_id,
        instrument_id=instrument_id,
        principal_cents=principal_cents,
        interest_cents=interest_cents,
        installments=installments,
    )


def validate_financing_instrument(instrument_type: PaymentInstrumentType) -> None:
    if instrument_type is PaymentInstrumentType.WALLET_BALANCE:
        raise ValueError("El saldo wallet no origina deuda de credito")


def validate_institution_movement(movement: InstitutionMovement) -> None:
    _require_nonnegative(movement.amount_cents, "El movimiento institucional")
    if not movement.description.strip():
        raise ValueError("El movimiento institucional requiere descripcion")


def validate_no_duplicate_movements(
    movements: tuple[InstitutionMovement, ...],
) -> None:
    seen_ids: set[str] = set()
    seen_refs: set[tuple[str, str]] = set()
    for movement in movements:
        validate_institution_movement(movement)
        if movement.id in seen_ids:
            raise ValueError("Movimiento institucional duplicado")
        seen_ids.add(movement.id)
        if movement.external_ref is not None:
            key = (movement.instrument_id, movement.external_ref)
            if key in seen_refs:
                raise ValueError("Referencia institucional duplicada")
            seen_refs.add(key)


def validate_user_payment(payment: UserPayment) -> None:
    _require_nonnegative(payment.amount_cents, "El cobro")
    if not payment.user_id.strip():
        raise ValueError("El cobro requiere usuario")


def propose_initial_balance_overlap(
    opening: InitialBalance,
    movements: tuple[InstitutionMovement, ...],
) -> MatchSuggestion | None:
    """Solo propone una coincidencia; nunca suma ni vincula movimientos."""
    candidates = [
        movement
        for movement in movements
        if movement.instrument_id == opening.instrument_id
        and movement.posted_at <= opening.effective_date
        and movement.amount_cents == opening.amount_cents
    ]
    if not candidates:
        return None
    candidate = sorted(candidates, key=lambda item: item.id)[0]
    return MatchSuggestion(
        id=f"opening-match:{opening.id}:{candidate.id}",
        source_a_id=opening.id,
        source_b_id=candidate.id,
        evidence=("instrument_id", "effective_date", "amount_cents"),
        status=ReconciliationStatus.PROPOSED,
    )


def accept_match_suggestion(
    suggestion: MatchSuggestion,
    *,
    actor: str,
    occurred_at: str,
) -> MatchSuggestion:
    if suggestion.status is not ReconciliationStatus.PROPOSED:
        raise ValueError("Solo se puede aceptar una sugerencia propuesta")
    return MatchSuggestion(
        id=suggestion.id,
        source_a_id=suggestion.source_a_id,
        source_b_id=suggestion.source_b_id,
        evidence=suggestion.evidence,
        confidence=suggestion.confidence,
        status=ReconciliationStatus.ACCEPTED,
        approved_by=actor,
        approved_at=occurred_at,
    )


def assign_installment_period(
    *,
    installment_id: str,
    instrument_id: str,
    calendar: InstrumentCalendar | None,
    period_key: str | None,
    source: str,
) -> InstallmentPeriodAssignment:
    requires_review = calendar is None or period_key is None
    if calendar is not None and calendar.instrument_id != instrument_id:
        raise ValueError("El calendario no pertenece al instrumento")
    return InstallmentPeriodAssignment(
        id=f"period:{installment_id}",
        installment_id=installment_id,
        calendar_id=calendar.id if calendar else None,
        period_key=period_key,
        source=source,
        calendar_revision=calendar.revision if calendar else None,
        requires_review=requires_review,
        status=(
            ReconciliationStatus.PROPOSED
            if requires_review
            else ReconciliationStatus.ACCEPTED
        ),
    )


def correct_installment_period(
    assignment: InstallmentPeriodAssignment,
    *,
    new_period_key: str | None,
    new_due_date: str | None,
    reason: str,
    actor: str,
    occurred_at: str,
    evidence_id: str | None = None,
) -> PeriodCorrectionEvent:
    if not reason.strip() or not actor.strip():
        raise ValueError("Una correccion requiere motivo y autor")
    return PeriodCorrectionEvent(
        id=f"correction:{assignment.id}:{occurred_at}",
        assignment_id=assignment.id,
        old_period_key=assignment.period_key,
        new_period_key=new_period_key,
        old_due_date=None,
        new_due_date=new_due_date,
        reason=reason,
        actor=actor,
        occurred_at=occurred_at,
        evidence_id=evidence_id,
    )


def validate_refund_event(event: RefundEvent) -> None:
    for value, label in (
        (event.requested_cents, "El reembolso solicitado"),
        (event.approved_cents, "El reembolso aprobado"),
        (event.applied_to_institution_cents, "El reembolso institucional"),
        (event.paid_to_user_cents, "El reembolso al usuario"),
    ):
        if value is not None:
            _require_nonnegative(value, label)
    if event.approved_cents is not None and event.approved_cents > event.requested_cents:
        raise ValueError("El reembolso aprobado excede el solicitado")
    applied = (event.applied_to_institution_cents or 0) + (event.paid_to_user_cents or 0)
    if event.approved_cents is not None and applied > event.approved_cents:
        raise ValueError("Los destinos exceden el reembolso aprobado")


def confirmed_bonus_effect(events: tuple[BonusEvent, ...]) -> int:
    """Devuelve solo el efecto neto confirmado; pendientes no reducen costo."""
    by_id = {event.id: event for event in events}
    effect = 0
    for event in events:
        _require_nonnegative(event.amount_cents, "La bonificacion")
        if event.status is BonusStatus.CONFIRMED:
            effect += event.amount_cents
        elif event.status is BonusStatus.REVERTED:
            original = by_id.get(event.reversal_of or "")
            if original is None or original.status is not BonusStatus.CONFIRMED:
                raise ValueError("La reversa debe referenciar una bonificacion confirmada")
            effect -= event.amount_cents
    return effect


def validate_receivable_adjustment(event: ReceivableAdjustmentEvent) -> None:
    _require_nonnegative(event.amount_cents, "El ajuste de cuenta por cobrar")
    if not event.reason.strip() or not event.actor.strip():
        raise ValueError("El ajuste requiere motivo y autor")


def summarize_receivable_adjustments(
    *,
    original_sale_cents: int,
    applied_collections_cents: int,
    events: tuple[ReceivableAdjustmentEvent, ...],
) -> dict[str, int]:
    """Resume eventos manuales; no borra ni recrea la cuenta original."""
    _require_nonnegative(original_sale_cents, "La venta original")
    _require_nonnegative(applied_collections_cents, "Los cobros aplicados")
    totals = {
        ReceivableAdjustmentKind.WRITE_OFF.value: 0,
        ReceivableAdjustmentKind.FORGIVENESS.value: 0,
        ReceivableAdjustmentKind.RECOVERY.value: 0,
    }
    for event in events:
        validate_receivable_adjustment(event)
        totals[event.kind.value] += event.amount_cents
    extinguished = min(
        original_sale_cents,
        applied_collections_cents
        + totals[ReceivableAdjustmentKind.WRITE_OFF.value]
        + totals[ReceivableAdjustmentKind.FORGIVENESS.value],
    )
    totals["outstanding_cents"] = original_sale_cents - extinguished
    totals["recovery_cash_cents"] = totals[ReceivableAdjustmentKind.RECOVERY.value]
    return totals


def propose_proportional_payment(
    payment: UserPayment,
    receivables: tuple[Receivable, ...],
) -> dict[str, int]:
    """Propone reparto determinista; no confirma ni reconoce utilidad."""
    validate_user_payment(payment)
    eligible = sorted(
        (
            (receivable.id, max(receivable.sale_cents, 0))
            for receivable in receivables
            if receivable.user_id == payment.user_id
        ),
        key=lambda item: item[0],
    )
    total = sum(amount for _, amount in eligible)
    target = min(payment.amount_cents, total)
    if target == 0 or total == 0:
        return {key: 0 for key, _ in eligible}
    result = {
        key: (target * amount) // total
        for key, amount in eligible
    }
    remainder = target - sum(result.values())
    for key, _ in sorted(
        eligible,
        key=lambda item: (-((target * item[1]) % total), item[0]),
    )[:remainder]:
        result[key] += 1
    return result


def internal_cost_by_user(
    *,
    allocations: tuple[Allocation, ...],
    discount_cents: int,
    eligible_user_ids: set[str] | None = None,
) -> dict[str, int]:
    """Calcula costo interno; no modifica el precio cobrado al tercero."""
    gross_by_user: dict[str, int] = {}
    for allocation in allocations:
        gross_by_user[allocation.user_id] = (
            gross_by_user.get(allocation.user_id, 0) + allocation.share_cents
        )
    eligible = (
        gross_by_user
        if eligible_user_ids is None
        else {
            user_id: amount
            for user_id, amount in gross_by_user.items()
            if user_id in eligible_user_ids
        }
    )
    discount_by_user = prorate_discount(discount_cents, eligible)
    return {
        user_id: amount - discount_by_user.get(user_id, 0)
        for user_id, amount in gross_by_user.items()
    }


def validate_receipt_applications(
    payment: UserPayment,
    applications: tuple[ReceiptApplication, ...],
) -> None:
    if any(item.payment_id != payment.id for item in applications):
        raise ValueError("La aplicacion referencia otro cobro")
    if any(item.amount_cents < 0 for item in applications):
        raise ValueError("Una aplicacion no puede ser negativa")
    if sum(item.amount_cents for item in applications) > payment.amount_cents:
        raise ValueError("Las aplicaciones exceden el cobro recibido")


def summarize_receipts(
    *,
    receivable: Receivable,
    payments: tuple[UserPayment, ...],
    applications: tuple[ReceiptApplication, ...],
) -> FinancialSummary:
    for payment in payments:
        validate_receipt_applications(
            payment,
            tuple(item for item in applications if item.payment_id == payment.id),
        )
    applied = sum(
        item.amount_cents
        for item in applications
        if item.receivable_id == receivable.id
    )
    received = sum(payment.amount_cents for payment in payments)
    assigned_total = sum(item.amount_cents for item in applications)
    limited = min(applied, receivable.sale_cents)
    if receivable.sale_cents <= 0:
        return FinancialSummary(
            projected_margin_cents=receivable.sale_cents - receivable.attributable_cost_cents,
            realized_margin_cents=0,
            applied_collections_cents=limited,
            unapplied_collections_cents=received - assigned_total,
            recognized_cost_cents=0,
        )
    recognized_cost = _round_ratio(
        receivable.attributable_cost_cents, limited, receivable.sale_cents
    )
    return FinancialSummary(
        projected_margin_cents=receivable.sale_cents - receivable.attributable_cost_cents,
        realized_margin_cents=limited - recognized_cost,
        applied_collections_cents=limited,
        unapplied_collections_cents=received - assigned_total,
        recognized_cost_cents=recognized_cost,
    )
