"""Stage-one search on encrypted synthetic databases only."""
from pathlib import Path
import copy

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtCore import QElapsedTimer

def wait_for(condition, timeout_ms=2000):
    timer=QElapsedTimer();timer.start()
    while not condition() and timer.elapsed()<timeout_ms:
        QTest.qWait(10)
    assert condition(), 'La búsqueda no completó la condición dentro del plazo.'

from test_product_refunds import repository, create_discount_comparison_case
from test_home_initial_restore import tables
from valenza.gui.app import MainWindow, create_application


@pytest.fixture
def searchable(repository):
    assert repository.database.encrypted
    repository.add_person('lucia', 'Lucía Búsqueda')
    repository.add_instrument('search-card', 'bank', 'Tarjeta Búsqueda', 'CREDIT_CARD')
    repository.create_order(order_id='search-order', ordered_at='2026-10-15', merchant='Café Búsqueda',
        instrument_id='search-card', original_cents=100000, discount_cents=0, charged_cents=100000,
        allocations=({'user_id': 'owner', 'amount_cents': 60000}, {'user_id': 'mama', 'amount_cents': 40000}),
        concepts=[dict(description='Auriculares inalámbricos', amount_cents=100000, allocations={'owner': 60000, 'mama': 40000})])
    repository.create_purchase(purchase_id='search-purchase', purchased_at='2026-09-10', merchant='Mercado Búsqueda',
        instrument_id='search-card', products=({'id': 'search-product', 'description': 'Adaptador clásico', 'quantity': 1, 'unit_price_cents': 2000},),
        allocations=({'product_id': 'search-product', 'user_id': 'owner', 'method': 'UNITS', 'basis': 1},))
    repository.record_institution_payment(payment_id='search-bank', instrument_id='search-card',
        paid_at='2026-10-15', amount_cents=5000, reference='Búsqueda SPEI-001')
    repository.record_receipt(payment_id='search-receipt', receivable_id='order:search-order:mama',
        received_at='2026-10-15', amount_cents=1000, reference='Búsqueda ABONO-001')
    repository.create_order(order_id='search-cancelled', ordered_at='2026-10-01', merchant='Búsqueda anulada',
        instrument_id='search-card', original_cents=1000, discount_cents=0, charged_cents=1000,
        allocations=({'user_id': 'owner', 'amount_cents': 1000},))
    repository.cancel_order('search-cancelled', reason='Prueba sintética')
    return repository


def test_partial_accented_multi_category_search_is_readonly_and_contains_no_amounts(searchable):
    before = tables(searchable)
    changes = searchable.database.connection.total_changes
    response = searchable.search_records('BUSQUEDA')
    assert not response['timed_out']
    assert {row['kind'] for row in response['results']} == {'person', 'card', 'order', 'purchase', 'bank_payment', 'receipt'}
    assert all('cents' not in key and 'amount' not in key for row in response['results'] for key in row)
    assert any(row['id'] == 'search-order' for row in searchable.search_records('auric inalam')['results'])
    assert any(row['id'] == 'search-purchase' for row in searchable.search_records('ADAPTADOR')['results'])
    assert any(row['id'] == 'search-bank' for row in searchable.search_records('spei-001')['results'])
    assert any(row['id'] == 'search-receipt' for row in searchable.search_records('abono-001')['results'])
    assert any(row['id'] == 'lucia' for row in searchable.search_records('luci')['results'])
    assert not searchable.search_records('%%')['results']
    assert not searchable.search_records('__')['results']
    assert not searchable.search_records("' OR 1=1 --")['results']
    assert not searchable.search_records('imposible-sintetico')['results']
    assert not searchable.search_records('x')['results']
    assert tables(searchable) == before and searchable.database.connection.total_changes == changes


def test_only_effective_concepts_and_imported_descriptions_are_searched(searchable):
    original = searchable.get_order('search-order')['manual_concepts']
    edited = copy.deepcopy(original); edited[0]['description'] = 'Audífonos actuales'
    searchable.update_manual_concepts('search-order', edited, expected_concepts=original)
    create_discount_comparison_case(searchable)
    before = tables(searchable)
    assert not searchable.search_records('auriculares')['results']
    assert any(r['id'] == 'search-order' for r in searchable.search_records('audifonos')['results'])
    assert any(r['id'] == 'order' for r in searchable.search_records('producto ficticio')['results'])
    assert tables(searchable) == before


def test_many_results_are_limited_and_budget_handler_is_removed(searchable):
    conn = searchable.database.connection
    with searchable.database.transaction() as connection:
        connection.executemany('INSERT INTO person(id,name) VALUES (?,?)',
            [(f'mass-{i}', f'Masivo sintético {i:04d}') for i in range(1500)])
    before = tables(searchable)
    trace = []
    conn.set_trace_callback(trace.append)
    try:
        response = searchable.search_records('masivo', budget_ms=2000)
    finally:
        conn.set_trace_callback(None)
    assert len(response['results']) == 5 and response['limited']
    assert all(sql.lstrip().upper().startswith(('SELECT', 'WITH')) for sql in trace)
    assert len(trace) == 6
    assert searchable.search_records('sin-coincidencia', budget_ms=0)['timed_out']
    assert conn.execute('SELECT COUNT(*) FROM person').fetchone()[0] == 1503
    assert any(r['id'] == 'search-order' for r in searchable.search_records('auric')['results'])
    assert tables(searchable) == before


def find(dialog, kind, identity=None):
    for i in range(dialog.results.count()):
        result = dialog.results.item(i).data(Qt.ItemDataRole.UserRole)
        if result and result['kind'] == kind and (identity is None or result['id'] == identity):
            dialog.results.setCurrentRow(i)
            return result
    raise AssertionError(f'Missing search result: {kind}')


def test_shortcut_button_debounce_keyboard_empty_privacy_and_query_clearing(searchable, monkeypatch):
    app = create_application([])
    window = MainWindow(database=searchable.database, test_mode=True)
    window.show(); window.activateWindow(); app.processEvents()
    before = tables(searchable)
    calls = []
    original = window.repository.search_records
    def counted(query, **kwargs):
        calls.append(query)
        return original(query, **kwargs)
    monkeypatch.setattr(window.repository, 'search_records', counted)
    try:
        for page in ('Inicio', 'Pedidos', 'Tarjetas', 'Cobros', 'Usuarios', 'Suscripciones', 'Configuración'):
            window.navigation.setCurrentRow(window.PAGES.index(page)); app.processEvents()
            # The offscreen plugin does not reactivate the owner after a modal closes.
            # WindowShortcut requires the same active-window precondition as native Qt.
            window.activateWindow(); app.processEvents()
            window.navigation.setFocus()
            QTest.keyClick(window.navigation, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier)
            app.processEvents()
            dialog = window._search_dialog
            assert dialog is not None and dialog.isVisible()
            assert dialog.input.hasFocus()
            QTest.keyClick(dialog.input, Qt.Key.Key_Escape); app.processEvents()
            assert window._search_dialog is None
        window.search_button.click(); app.processEvents()
        dialog = window._search_dialog
        QTest.keyClicks(dialog.input, 'busqueda')
        assert not calls
        assert dialog.timer.interval()==180
        wait_for(lambda: calls == ['busqueda'])
        assert calls == ['busqueda']
        rows = [dialog.results.item(i).text() for i in range(dialog.results.count())]
        assert len(rows) > 6 and all('$' not in text and 'MXN' not in text for text in rows)
        assert not window.dashboard_privacy.isChecked()
        first = dialog.results.currentRow()
        QTest.keyClick(dialog.input, Qt.Key.Key_Down)
        assert dialog.results.currentRow() != first
        QTest.keyClick(dialog.input, Qt.Key.Key_Up)
        assert dialog.results.currentRow() == first
        out = Path('artifacts/search'); out.mkdir(parents=True, exist_ok=True)
        dialog.grab().save(str(out/'results.png'))
        dialog.input.setText('nada-que-exista'); wait_for(lambda: 'Sin coincidencias' in dialog.status.text())
        assert 'Sin coincidencias' in dialog.status.text()
        dialog.grab().save(str(out/'empty.png'))
        dialog.input.setText('busqueda')
        QTest.keyClick(dialog.input, Qt.Key.Key_Escape); app.processEvents()
        window.search_button.click(); app.processEvents()
        assert not window._search_dialog.input.text() and not window._search_dialog.results.count()
        window._search_dialog.reject(); app.processEvents()
        window.dashboard_privacy.setChecked(True)
        window.search_button.click(); app.processEvents()
        revealed = window._search_dialog
        revealed.input.setText('busqueda'); wait_for(lambda: not revealed.timer.isActive())
        assert all('$' not in revealed.results.item(i).text() for i in range(revealed.results.count()))
        revealed.reject(); app.processEvents()
        assert tables(searchable) == before
    finally:
        window.close(); app.processEvents()


@pytest.mark.parametrize('kind,identity,page,table_name,column', [
    ('order', 'search-order', 'Pedidos', 'orders_table', 8),
    ('order', 'search-cancelled', 'Pedidos', 'orders_table', 8),
    ('person', 'lucia', 'Usuarios', 'people_table', 0),
    ('card', 'search-card', 'Tarjetas', 'cards_table', 12),
    ('bank_payment', 'search-bank', 'Tarjetas', 'card_payment_history', 4),
    ('receipt', 'search-receipt', 'Cobros', 'collection_history', 6),
])
def test_enter_opens_exact_record_readonly(searchable, kind, identity, page, table_name, column):
    app = create_application([])
    window = MainWindow(database=searchable.database, test_mode=True)
    window.show(); app.processEvents()
    before = tables(searchable)
    changes = searchable.database.connection.total_changes
    try:
        window.search_button.click(); app.processEvents()
        dialog = window._search_dialog
        dialog.input.setText('busqueda'); QTest.qWait(230)
        find(dialog, kind, identity)
        QTest.keyClick(dialog.input, Qt.Key.Key_Return); app.processEvents()
        assert window.pages.currentIndex() == window.PAGES.index(page)
        assert window._table_id(getattr(window, table_name), column) == identity
        assert tables(searchable) == before
        assert searchable.database.connection.total_changes == changes
    finally:
        window.close(); app.processEvents()


def test_purchase_opens_participation_and_missing_record_keeps_selection(searchable):
    app = create_application([])
    window = MainWindow(database=searchable.database, test_mode=True)
    before = tables(searchable)
    try:
        window.navigation.setCurrentRow(window.PAGES.index('Cobros'))
        window.collection_filter.setCurrentIndex(window.collection_filter.findData('FAMILY'))
        window._search_select(window.collection_items,7,'order:search-order:mama')
        window.collection_amount.setText('7.89')
        window.collection_reference.setText('Borrador anterior a buscar')
        purchase = next(r for r in searchable.search_records('busqueda')['results'] if r['kind'] == 'purchase')
        window._open_search_result(purchase)
        assert window.pages.currentIndex() == window.PAGES.index('Cobros')
        selected=window._table_id(window.collection_items, 7)
        assert selected is not None
        entry=next(e for e in searchable.list_collection_items() if e['receivable_id']==selected)
        assert entry['source_id']=='search-purchase'
        assert 'Mercado Búsqueda' in window.collection_mode_notice.text()
        window.collection_return_button.click()
        assert window.collection_filter.currentData()=='FAMILY'
        assert window._table_id(window.collection_items,7)=='order:search-order:mama'
        assert window.collection_amount.text()=='7.89'
        assert window.collection_reference.text()=='Borrador anterior a buscar'
        page = window.pages.currentIndex()
        window._open_search_result(dict(kind='order', id='no-existe'))
        assert window.pages.currentIndex() == page
        assert 'ya no está disponible' in window.statusBar().currentMessage()
        assert tables(searchable) == before
    finally:
        window.close(); app.processEvents()


def test_click_navigation_and_enter_during_debounce_use_the_current_query(searchable):
    app = create_application([])
    window = MainWindow(database=searchable.database, test_mode=True)
    window.show(); app.processEvents()
    before = tables(searchable)
    try:
        window.search_button.click(); app.processEvents()
        dialog = window._search_dialog
        dialog.input.setText('busqueda'); QTest.qWait(230)
        find(dialog, 'bank_payment', 'search-bank')
        item = dialog.results.currentItem()
        dialog.results.scrollToItem(item); app.processEvents()
        QTest.mouseClick(dialog.results.viewport(), Qt.MouseButton.LeftButton,
                        pos=dialog.results.visualItemRect(item).center())
        app.processEvents()
        assert window._table_id(window.card_payment_history, 4) == 'search-bank'
        window.search_button.click(); app.processEvents()
        dialog = window._search_dialog
        dialog.input.setText('adaptador'); QTest.qWait(230)
        assert dialog.results.currentItem().data(Qt.ItemDataRole.UserRole)['kind'] == 'purchase'
        dialog.input.setText('auric')
        QTest.keyClick(dialog.input, Qt.Key.Key_Return); app.processEvents()
        assert window.pages.currentIndex() == window.PAGES.index('Pedidos')
        assert window._table_id(window.orders_table, 8) == 'search-order'
        assert tables(searchable) == before
    finally:
        window.close(); app.processEvents()
