from pathlib import Path
import os
import pytest
from valenza.ocr.order_import import parse_receipt, read_receipt, validate, money
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository

FIXTURE = Path(__file__).parent / 'fixtures_synthetic' / 'mp_products.txt'
OPENPDF = FIXTURE.with_name('mp_openpdf.txt')


def test_original_eight_product_receipt():
    """Private original stays outside the repository; opt in with its path."""
    explicit_path = os.environ.get('VALENZA_RECEIPT_TEST_PDF')
    if not explicit_path:
        pytest.skip('Private receipt test requires an explicitly supplied VALENZA_RECEIPT_TEST_PDF')
    source = Path(explicit_path)
    if not source.is_file():
        pytest.skip('Set VALENZA_RECEIPT_TEST_PDF to the private original PDF')
    draft = read_receipt(Path(source))
    assert (draft['date'], draft['time'], draft['merchant']) == ('2026-09-23', '13:34', 'Varios')
    assert draft['payment'].startswith('NuBank')
    assert [p['quantity'] for p in draft['products']] == [1] * 8
    assert [p['unit'] for p in draft['products']] == [14616, 11283, 6281, 17342, 12908, 19900, 8559, 54900]
    assert [p['description'] for p in draft['products']] == [
        'Mochila Impermeable Para Estudiantes De Escuela Primaria, Mochila Para Niñas, Mochila Para Lentejuelas De Mariposa',
        'Cable Usb 1m Ugreen 60126 Con Entrada Usb Salida Tipo C Negro',
        'Rollo Listones Para Decoración,cinta Estampación Escuela',
        'Papel Picado Colores Día De Muertos Decoración 100pz 36x25cm',
        'Mochila Para Niñas Unicornio Mochila Escolar Impermeable Mochila Infantil Adolescentes Con 6-12 Años',
        'Funda Cubreasiento Premium Malla Mesh Doble Italika At135x Negro',
        '2 Piezas Mica Cristal Templado 9d Para Samsung A36/a56',
        'Tenis Deportivo Para Caminar Next & Co 6181 Rojo Para Mujer',
    ]
    assert validate(draft) == draft['paid'] == draft['charged'] == 145789
    assert draft['discount'] == draft['refund'] == 0


def test_openpdf_without_product_summary_still_validates_total():
    text = OPENPDF.read_text(encoding='utf-8').replace('Productos (5)\n$ 602.87\n', '')
    assert validate(parse_receipt(text)) == 60287
    with pytest.raises(ValueError, match='No cuadra'):
        parse_receipt(text.replace('$ 356.01', '$ 356.02'))
    with pytest.raises(ValueError):
        parse_receipt(text.replace('$ 149 x 1 Unidad', '$ 149 x 0 Unidad'))


def test_password_protected_and_damaged_pdf(tmp_path):
    fitz = pytest.importorskip('pymupdf')
    protected = tmp_path / 'protected.pdf'
    with fitz.open() as document:
        document.new_page()
        document.save(protected, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw='test', owner_pw='owner')
    with pytest.raises(ValueError, match='contraseña'):
        read_receipt(protected)
    damaged = tmp_path / 'damaged.pdf'
    damaged.write_bytes(b'not a PDF')
    with pytest.raises(RuntimeError, match='No se pudo leer'):
        read_receipt(damaged)


def test_openpdf_layout_without_brand_and_multiline_products():
    draft = parse_receipt(OPENPDF.read_text(encoding='utf-8'))
    assert draft['date'] == '2026-10-03'
    assert draft['number'] == 'DEMO-OPENPDF-001'
    assert draft['payment'] == 'Tarjeta ficticia terminada en 0000'
    assert len(draft['products']) == 5
    assert [p['unit'] for p in draft['products']] == [14900, 2000, 7905, 14703, 20779]
    assert draft['products'][0]['description'] == 'Producto ficticio A con descripción en dos líneas'
    assert (draft['discount'], draft['refund'], draft['charged'], draft['paid']) == (6029, 18657, 54258, 35601)
    assert validate(draft) == 60287
    assert all('refund' not in p for p in draft['products'])


def test_openpdf_superscript_cents_are_read_from_pdf(tmp_path):
    fitz = pytest.importorskip('pymupdf')
    path = tmp_path / 'anonymous-openpdf.pdf'
    with fitz.open() as document:
        page = document.new_page(width=612, height=1200)
        for index, line in enumerate(OPENPDF.read_text(encoding='utf-8').splitlines()):
            y = 30 + index * 24
            if line.startswith('$ ') and ' x ' not in line:
                pesos, cents = line.rsplit('.', 1)
                page.insert_text((30, y), pesos, fontsize=12)
                x = 30 + fitz.get_text_length(pesos, fontsize=12)
                page.insert_text((x, y - 5), cents, fontsize=8)
            else:
                page.insert_text((30, y), line, fontsize=12)
        document.save(path)
    with fitz.open(path) as document:
        # Reproduce la concatenación que provocaba importes cien veces mayores.
        assert '$ 35601' in document[0].get_text()
        assert 'mercado pago' not in document[0].get_text().casefold()
    assert validate(read_receipt(path)) == 60287


@pytest.mark.parametrize('old,new', [('Productos (5)', 'Productos (4)'),
                                     ('$ 602.87', '$ 602.88'), ('$ 356.01', '$ 356.02')])
def test_openpdf_inconsistent_amounts_and_counts_are_rejected(old, new):
    with pytest.raises(ValueError):
        parse_receipt(OPENPDF.read_text(encoding='utf-8').replace(old, new))


def test_unrelated_payment_receipt_is_still_rejected():
    with pytest.raises(ValueError, match='Esta versión admite'):
        parse_receipt('Comprobante de pago\nTotal\n$ 10.00')


def test_exact_cents_and_separate_refund():
    draft = parse_receipt(FIXTURE.read_text(encoding='utf-8'))
    assert validate(draft) == 30000
    assert draft['products'][0]['unit'] == 12535
    assert (draft['discount'], draft['refund'], draft['charged'], draft['paid']) == (2000, 3000, 28000, 25000)
    assert draft['number'] == 'DEMO-MP-001'
    assert not any('refund' in product for product in draft['products'])
    draft['paid'] += 1
    with pytest.raises(ValueError, match='No cuadra'):
        validate(draft)


@pytest.mark.parametrize('value', ['1.001', '1,23', '-1', 'NaN', '12,34.00'])
def test_ambiguous_money_rejected(value):
    with pytest.raises(ValueError):
        money(value)


def test_native_pdf_and_no_ocr(tmp_path, monkeypatch):
    fitz = pytest.importorskip('pymupdf')
    path = tmp_path / 'receipt.pdf'
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((40, 40), FIXTURE.read_text(encoding='utf-8'))
        document.save(path)
    assert validate(read_receipt(path)) == 30000
    blank = tmp_path / 'blank.pdf'
    with fitz.open() as document:
        document.new_page()
        document.save(blank)
    monkeypatch.setattr('valenza.ocr.order_import.shutil.which', lambda _: None)
    with pytest.raises(ValueError, match='Se necesita OCR'):
        read_receipt(blank)


def test_confirmed_save_and_duplicate_guard(tmp_path):
    database = LocalDatabase.open(tmp_path / 'import.db', 'synthetic-password')
    database.migrate()
    repository = FinanceRepository(database)
    owner = repository.create_person('Yo ficticio', is_owner=True)
    repository.ensure_demo_catalog()
    draft = parse_receipt(FIXTURE.read_text(encoding='utf-8'))
    draft['fingerprint'] = 'synthetic-fingerprint'
    assert repository.list_orders() == []
    arguments = dict(ordered_at=draft['date'], merchant='Comercio ficticio',
        instrument_id=repository.list_instruments()[0]['id'], original_cents=30000,
        discount_cents=2000, charged_cents=28000,
        allocations=(dict(user_id=owner, amount_cents=30000),), import_evidence=draft)
    repository.create_order(order_id='first', **arguments)
    with pytest.raises(ValueError, match='duplicado'):
        repository.create_order(order_id='second', **arguments)
    assert len(repository.list_orders()) == 1
    repository.create_order(order_id='second', allow_duplicate=True, **arguments)
    assert len(repository.list_orders()) == 2
    database.close()
