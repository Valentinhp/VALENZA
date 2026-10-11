from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DocumentKind(StrEnum):
    MP_RECEIPT = "MP_RECEIPT"
    NU_TRANSACTIONS_SCREEN = "NU_TRANSACTIONS_SCREEN"
    UNKNOWN = "UNKNOWN"


class MovementKind(StrEnum):
    CHARGE = "charge"
    CREDIT = "credit"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ProposedMovement:
    movement_date: str | None
    description_raw: str | None
    amount_cents: int | None
    movement_type: MovementKind
    payment_instrument: str | None = None
    page: int | None = None
    region: str | None = None
    warnings: tuple[str, ...] = ()
    status: str = "proposed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "movement_date": self.movement_date,
            "description_raw": self.description_raw,
            "amount_cents": self.amount_cents,
            "movement_type": self.movement_type.value,
            "payment_instrument": self.payment_instrument,
            "page": self.page,
            "region": self.region,
            "warnings": list(self.warnings),
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class ProposedDocument:
    source_platform: str
    source_kind: str
    document_fingerprint: str
    document_type: DocumentKind
    movements: tuple[ProposedMovement, ...] = ()
    summary: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    is_partial_capture: bool = False
    review_status: str = "proposed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_platform": self.source_platform,
            "source_kind": self.source_kind,
            "document_fingerprint": self.document_fingerprint,
            "document_type": self.document_type.value,
            "summary": self.summary,
            "transactions": [movement.as_dict() for movement in self.movements],
            "warnings": list(self.warnings),
            "is_partial_capture": self.is_partial_capture,
            "review_status": self.review_status,
        }
