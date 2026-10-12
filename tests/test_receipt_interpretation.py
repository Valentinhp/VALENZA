"""Representative local layouts. All generated document contents are synthetic."""
from pathlib import Path

import pytest

from valenza.ocr.order_import import document_money, parse_receipt, read_receipt, validate


def receipt(*, discount='-$ 20.25', refund=None, paid='$ 189.75', charged=None):
    lines = ['Mercado Pago', 'Comprobante de compra', 'Fecha: 21/09/2026',
             'Comercio: Comercio sintético', 'Referencia: SYNTHETIC-001',
             'Medio de pago: Tarjeta sintética',
             'Artículo A | 2 | $ 80.25 | $ 160.50',
             'Artículo B | 3 | $ 16.50 | $ 49.50']
    if discount is not None:
        lines.append('Descuento: ' + discount)
    if refund is not None:
        lines.append('Devolución parcial: ' + refund)
    if charged is not None:
        lines.append('Cargo bancario: ' + charged)
    if paid is not None:
        lines.append('Total pagado: ' + paid)
    return '\n'.join(lines)


@pytest.mark.parametrize('token,expected', [
    ('$ 1,234.56 MXN', 123456), ('$1.234,56', 123456),
    ('$ 1 234,56', 123456), ('$ 1\u202f234.56', 123456),
    ('$ 1234⁵⁶', 123456), ('$ 9.5', 950), ('$ 9', 900),
    ('$ 0.01', 1), ('$ 1,234', 123400), ('$ 12,34', 1234),
])
def test_document_money_exact_formats(token, expected):
    assert document_money(token) == expected


@pytest.mark.parametrize('token', ['$1.234', '$12,3', '$1,23,456', '$ 1 23.45',
                                     '$12.3456', '$-1.25', 'NaN', '23/09/2026', '$10 25'])
def test_document_money_does_not_guess(token):
    with pytest.raises(ValueError):
        document_money(token)


@pytest.mark.parametrize('discount', ['$ -20.25', '-$20.25', '($20.25)', '$20,25', '$20²⁵', '$ −20.25'])
def test_discount_signs_and_formats(discount):
    draft = parse_receipt(receipt(discount=discount))
    assert validate(draft) == 21000
    assert draft['discount'] == 2025
    assert draft['charged'] == draft['paid'] == 18975
    assert draft['refund'] == 0
    assert draft['provenance']['discount'] == 'explícito'
    assert draft['provenance']['charged'].startswith('calculado')
    assert draft['merchant'] == 'Comercio sintético'
    assert draft['number'] == 'SYNTHETIC-001'


def test_purchase_without_discount_or_refund():
    draft = parse_receipt(receipt(discount=None, paid='$210.00'))
    assert validate(draft) == 21000
    assert draft['provenance']['discount'] == 'no indicado'
    assert draft['charged'] == draft['paid'] == 21000


@pytest.mark.parametrize('paid', ['$ 159.75', '$ 189.75'])
def test_refund_distinguishes_original_charge_and_net(paid):
    draft = parse_receipt(receipt(refund='-$30.00', paid=paid, charged='$189.75'))
    assert validate(draft) == 21000
    assert (draft['discount'], draft['charged'], draft['refund'], draft['paid']) == (2025, 18975, 3000, 15975)
    assert draft['source_amounts']['paid'][0]['raw'] == paid
    assert draft['provenance']['charged'] == 'explícito'


def test_distinct_totals_before_and_after_refund():
    draft = parse_receipt(receipt(refund='$30.00') + '\nTotal: $159.75')
    assert validate(draft) == 21000
    assert draft['charged'] == 18975 and draft['paid'] == 15975
    assert draft['provenance']['paid'].startswith('calculado')


@pytest.mark.parametrize('text', [
    receipt(discount='$20.250'),
    receipt(paid='$189.74'),
    receipt(paid=None),
    receipt(charged='$190.00'),
    receipt() + '\nDescuento: $21.00',
    receipt() + '\nTotal: $195.00',
    receipt().replace('$ 160.50', '$160.51'),
    receipt().replace('A | 2', 'A | 0'),
    receipt().replace('$ 80.25', '$80.255'),
])
def test_inconsistent_or_ambiguous_documents_cannot_validate(text):
    draft = parse_receipt(text, review=True)
    assert draft['warnings']
    with pytest.raises(ValueError):
        validate(draft)
    # Reviewing alone cannot override broken equations or a wrong row subtotal.
    draft['review_confirmed'] = True
    with pytest.raises(ValueError):
        validate(draft)


def test_multiline_labelled_products_and_numeric_identifiers():
    text = '\n'.join(['Mercado Pago', 'Comprobante de compra', 'Fecha: 21/09/2026',
                      'Número de comprobante: 9876543210',
                      'Cable 2026 modelo 123', 'para teléfono', 'Cantidad:', '2',
                      'Precio unitario:', '$12,50', 'Cuaderno tamaño 36x25',
                      'Cantidad: 3', 'Precio unitario: $5.00', 'Total pagado: $40.00'])
    draft = parse_receipt(text)
    assert validate(draft) == 4000
    assert draft['products'] == [
        dict(description='Cable 2026 modelo 123 para teléfono', quantity=2, unit=1250),
        dict(description='Cuaderno tamaño 36x25', quantity=3, unit=500)]


def test_unpriced_wallet_product_is_shown_for_review(tmp_path):
    fitz = pytest.importorskip('pymupdf')
    text = '\n'.join(['Comprobante de pago', '21/septiembre/2026 a las 09:20.',
                      'Compraste producto a Varios', 'Total', '$25.00',
                      'Concepto', 'Artículo sin precio', 'Usuario', 'Persona sintética',
                      'Medio de Pago', 'Tarjeta sintética'])
    path = tmp_path / 'incomplete.pdf'
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((30, 30), text)
        document.save(path)
    draft = read_receipt(path)
    assert draft['products'][0]['unit'] is None
    assert draft['products'][0]['description'] == 'Artículo sin precio'
    assert 'products' in draft['review_fields']
    with pytest.raises(ValueError):
        validate(draft)


def test_existing_pdf_resources_are_read_automatically():
    fixtures = Path(__file__).parent / 'fixtures_synthetic'
    files = list(fixtures.glob('*.pdf'))
    assert files
    for path in files:
        if path.name.startswith('nu_'):
            with pytest.raises(ValueError, match='Mercado Pago'):
                read_receipt(path)
            continue
        draft = read_receipt(path)
        assert draft['fingerprint'] and draft['extraction'] == 'texto nativo'
        if path.name == 'mp_products.pdf':
            assert validate(draft) == 30000
        else:
            # The older OCR fixture lacks explicit unit prices; do not invent them.
            assert draft['products'] == []
            with pytest.raises(ValueError):
                validate(draft)


def test_extraction_failure_is_not_reported_as_bad_products(monkeypatch):
    def fail(_):
        raise RuntimeError('No se pudo leer el PDF local')
    monkeypatch.setattr('valenza.ocr.order_import.read_pdf_text', fail)
    with pytest.raises(RuntimeError, match='No se pudo leer'):
        read_receipt(Path('unused.pdf'))


def test_wallet_summary_below_multiline_products():
    text = '\n'.join(['Comprobante de pago', '21/septiembre/2026 a las 09:20.',
                      'Compraste producto a Comercio sintético', 'Concepto',
                      'Cable modelo 2026', 'para teléfono', '$ 12,50 × 2 Unidades',
                      'Cuaderno', '$5.00 x 3 Unidades', 'Productos (2)', '$40.00',
                      'Descuento: -$5.00', 'Total: $35.00',
                      'Usuario: Persona sintética', 'Medio de Pago: Tarjeta sintética'])
    draft = parse_receipt(text)
    assert validate(draft) == 4000
    assert draft['products'][0]['description'] == 'Cable modelo 2026 para teléfono'
    assert draft['discount'] == 500 and draft['charged'] == draft['paid'] == 3500


def test_real_pdf_discount_with_raised_cents_and_separate_dollar_span(tmp_path):
    fitz = pytest.importorskip('pymupdf')
    path = tmp_path / 'discount-spans.pdf'
    with fitz.open() as document:
        page = document.new_page()
        lines = ['Comprobante de pago', '21/septiembre/2026 a las 09:20.',
                 'Compraste producto a Comercio sintetico', 'Descuento',
                 '$ -20.25', 'Total', '$ 189.75', 'Concepto',
                 'Cable modelo 2026', 'para telefono', '$ 80.25 x 2 Unidades',
                 'Cuaderno', '$ 16.50 x 3 Unidades', 'Usuario', 'Persona sintetica',
                 'Medio de Pago', 'Tarjeta sintetica']
        for index, line in enumerate(lines):
            y = 30 + index * 24
            if line in ('$ -20.25', '$ 189.75'):
                pesos, cents = line.rsplit('.', 1)
                page.insert_text((30, y), '$ ', fontsize=12)
                x = 30 + fitz.get_text_length('$ ', fontsize=12)
                page.insert_text((x, y), pesos[2:], fontsize=12)
                x += fitz.get_text_length(pesos[2:], fontsize=12)
                page.insert_text((x, y - 5), cents, fontsize=8)
            else:
                page.insert_text((30, y), line, fontsize=12)
        document.save(path)
    draft = read_receipt(path)
    assert validate(draft) == 21000
    assert draft['discount'] == 2025 and draft['charged'] == draft['paid'] == 18975


def test_missing_reference_does_not_use_a_section_label_as_identity():
    text = receipt().replace('Referencia: SYNTHETIC-001', 'Comprobante\nConcepto desconocido')
    assert parse_receipt(text)['number'] == ''


def test_total_below_label_does_not_take_the_preceding_refund_amount():
    text = receipt(refund='$30.00', paid='$159.75').replace(
        'Devolución parcial: $30.00\nTotal pagado: $159.75',
        'Devolución parcial\n$30.00\nTotal pagado\n$159.75')
    draft = parse_receipt(text)
    assert validate(draft) == 21000
    assert draft['refund'] == 3000 and draft['paid'] == 15975


def test_short_native_text_is_not_misclassified_as_missing_ocr(tmp_path, monkeypatch):
    fitz = pytest.importorskip('pymupdf')
    path = tmp_path / 'unknown-short.pdf'
    with fitz.open() as document:
        document.new_page().insert_text((30, 30), 'Mercado Pago')
        document.save(path)
    monkeypatch.setattr('valenza.ocr.order_import.shutil.which', lambda _: None)
    with pytest.raises(ValueError, match='comprobantes de Mercado Pago'):
        read_receipt(path)
