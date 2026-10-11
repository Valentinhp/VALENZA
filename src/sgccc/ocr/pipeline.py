from __future__ import annotations

import hashlib
import re
from datetime import date

from .money import find_amounts
from .models import DocumentKind, MovementKind, ProposedDocument, ProposedMovement


_DATE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iso_date(match: re.Match[str]) -> str | None:
    try:
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1))).isoformat()
    except ValueError:
        return None


def analyze_text(text: str, *, source_platform: str, source_kind: str) -> ProposedDocument:
    """Analiza texto ya extraido y solo produce datos propuestos."""
    normalized = text.replace("\r\n", "\n")
    lowered = normalized.casefold()
    dates = list(_DATE.finditer(normalized))
    warnings: list[str] = []

    if source_platform.casefold() == "mercado_pago" or (
        "mercado pago" in lowered and "comprobante" in lowered
    ):
        document_type = DocumentKind.MP_RECEIPT
        platform = "mercado_pago"
        instrument = (
            "WALLET_BALANCE"
            if "dinero en mercado pago" in lowered
            else None
        )
        amounts = find_amounts(normalized)
        amount = amounts[-1] if amounts else None
        if amount is None:
            warnings.append("No se identifico un importe verificable")
        if instrument is None:
            warnings.append("Medio de pago no identificado; requiere revision")
        movement = ProposedMovement(
            movement_date=_iso_date(dates[0]) if dates else None,
            description_raw="Comprobante de pago",
            amount_cents=amount,
            movement_type=MovementKind.CHARGE if amount is not None else MovementKind.UNKNOWN,
            payment_instrument=instrument,
            region="document",
            warnings=tuple(warnings),
        )
        return ProposedDocument(
            source_platform=platform,
            source_kind=source_kind,
            document_fingerprint=_fingerprint(normalized),
            document_type=document_type,
            movements=(movement,),
            warnings=tuple(warnings),
        )

    if "nu" in lowered and ("resumen de transacciones" in lowered or "gastos actuales" in lowered):
        document_type = DocumentKind.NU_TRANSACTIONS_SCREEN
        platform = "nu"
        summary_amounts = find_amounts(normalized)
        movements: list[ProposedMovement] = []
        for index, line in enumerate(normalized.splitlines(), start=1):
            line_dates = list(_DATE.finditer(line))
            line_amounts = find_amounts(line)
            if not line_dates or not line_amounts:
                continue
            movements.append(
                ProposedMovement(
                    movement_date=_iso_date(line_dates[0]),
                    description_raw=line,
                    amount_cents=line_amounts[-1],
                    movement_type=MovementKind.UNKNOWN,
                    region=f"line:{index}",
                    warnings=("Signo no verificable desde esta captura",),
                )
            )
        if not movements:
            warnings.append("No se identificaron filas de movimientos")
        if "captura" in lowered or "selector" in lowered:
            warnings.append("La captura puede ser parcial; no representa necesariamente el saldo total")
        return ProposedDocument(
            source_platform=platform,
            source_kind=source_kind,
            document_fingerprint=_fingerprint(normalized),
            document_type=document_type,
            movements=tuple(movements),
            summary={"amounts_detected_cents": summary_amounts},
            warnings=tuple(warnings),
            is_partial_capture=True,
        )

    return ProposedDocument(
        source_platform="unknown",
        source_kind=source_kind,
        document_fingerprint=_fingerprint(normalized),
        document_type=DocumentKind.UNKNOWN,
        warnings=("Tipo de documento no identificado",),
    )
