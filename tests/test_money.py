from sgccc.ocr.money import find_amounts, parse_amount_cents


def test_parse_amount_uses_integer_cents():
    assert parse_amount_cents("$1,299.99") == 129999
    assert parse_amount_cents("129.9") == 12990


def test_ambiguous_amount_is_not_invented():
    assert parse_amount_cents("12999") == 1299900
    assert parse_amount_cents("129.999") is None


def test_find_amounts_preserves_repeated_values():
    assert find_amounts("CFE 08/10/2026 $100.00\nCFE 08/10/2026 $100.00") == [10000, 10000]
