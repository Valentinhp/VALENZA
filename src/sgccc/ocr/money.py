from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re


_AMOUNT = re.compile(
    r"(?<![\d/])(?:[$€]\s*)?([+-]?\d[\d,]*(?:\.\d{1,2})?)(?![\d/])"
)


def parse_amount_cents(value: str) -> int | None:
    """Parsea MXN sin float; devuelve None si la entrada es ambigua o invalida."""
    cleaned = value.strip().replace("$", "").replace(" ", "")
    if not re.fullmatch(r"[+-]?\d[\d,]*(?:\.\d{1,2})?", cleaned):
        return None
    try:
        decimal_value = Decimal(cleaned.replace(",", ""))
    except InvalidOperation:
        return None
    return int((decimal_value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def find_amounts(text: str) -> list[int]:
    amounts: list[int] = []
    for match in _AMOUNT.finditer(text):
        parsed = parse_amount_cents(match.group(1))
        if parsed is not None:
            amounts.append(parsed)
    return amounts
