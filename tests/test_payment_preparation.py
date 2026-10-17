"""Only encrypted synthetic data; preparation must perform zero database writes."""
import pytest
from PySide6.QtWidgets import QDialog
from valenza.gui.app import create_application, MainWindow
from valenza.gui.payment_preparation import PaymentPreparationDialog, preparation_items
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository


@pytest.fixture
def prepared_repo(tmp_path):
    db = LocalDatabase.open(tmp_path / 'preparation-synthetic.db', 'synthetic-only')
    assert db.encrypted
    db.migrate()
    repo = FinanceRepository(db)
    repo.add_person('owner', 'Yo sintético', is_owner=True)
    repo.add_person('family', 'J sintético')
    repo.add_institution('bank', 'Nu sintético')
    for card in ('card', 'other'):
        repo.add_instrument(card, 'bank', card, 'CREDIT_CARD')
    for key, amount, paid, card in (
        ('unpaid', 10000, 0, 'card'), ('partial', 65487, 30000, 'card'),
        ('paid', 20000, 20000, 'card'), ('different', 1000, 1000, 'other'),
    ):
        repo.create_order(order_id=key, ordered_at='2026-10-01', merchant=key,
                          instrument_id=card, original_cents=amount, charged_cents=amount,
                          discount_cents=0, allocations=({'user_id': 'family', 'amount_cents': amount},
                                                       {'user_id': 'owner', 'amount_cents': 0}))
        if paid:
            repo.record_receipt(payment_id='receipt-' + key, receivable_id=f'order:{key}:family',
                                amount_cents=paid, received_at='2026-10-02')
    yield repo
    db.close()


def snapshot(repo):
    c = repo.database.connection
    return {r[0]: [tuple(x) for x in c.execute('SELECT * FROM "' + r[0] + '" ORDER BY rowid')]
            for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def open_dialog(repo):
    app = create_application([])
    dialog = PaymentPreparationDialog(repo)
    dialog.card.setCurrentIndex(dialog.card.findData('card'))
    dialog.show()
    app.processEvents()
    return app, dialog


def row(dialog, key):
    return next(r for r in dialog.rows if r['item']['order_id'] == key)


def test_partial_contributions_and_totals_are_exact_without_writes(prepared_repo, tmp_path):
    repo = prepared_repo
    before = snapshot(repo)
    changes = repo.database.connection.total_changes
    app, dialog = open_dialog(repo)
    assert len(dialog.rows) == 3
    unpaid = row(dialog, 'unpaid')
    assert unpaid['item']['paid_cents'] == 0
    assert unpaid['contributions'][0][0].isEnabled()
    assert unpaid['contributions'][0][1].isEnabled()
    partial = row(dialog, 'partial')
    assert partial['item']['remaining_cents'] == 35487
    first, amount, _ = partial['contributions'][0]
    amount.setText('200.00')
    first.setChecked(True)
    dialog.add_contribution(partial)
    second, extra, _ = partial['contributions'][1]
    extra.setText('100.00')
    second.setChecked(True)
    dialog.target.setText('654.87')
    assert dialog.total_cents == 30000
    assert '$354.87' in dialog.summary.text()
    second.setChecked(False)
    assert dialog.total_cents == 20000
    extra.setText('50.01')
    second.setChecked(True)
    assert dialog.total_cents == 25001
    dialog.own.setText('500.00')
    assert dialog.total_cents == 75001
    assert '$95.14' in dialog.summary.text()
    assert dialog.progress.value() == 100
    dialog.target.setText('1000.00')
    assert '$249.99' in dialog.summary.text()
    paid = row(dialog, 'paid')
    paid['contributions'][0][1].setText('200.00')
    paid['contributions'][0][0].setChecked(True)
    assert paid['item']['remaining_cents'] == 0
    assert dialog.total_cents == 95001
    from PySide6.QtWidgets import QPushButton
    next(b for b in dialog.findChildren(QPushButton) if 'J sintético' in b.text()).click()
    next(b for b in dialog.findChildren(QPushButton) if b.text().startswith('partial ·')).click()
    app.processEvents()
    dialog.grab().save(str(tmp_path / 'preparation.png'))
    dialog.reject()
    assert dialog.total_cents == 0 and not dialog.rows
    reopened = PaymentPreparationDialog(repo)
    assert reopened.total_cents == 0 and reopened.target.text() == ''
    reopened.reject()
    assert snapshot(repo) == before
    assert repo.database.connection.total_changes == changes


def test_free_calculation_invalid_amounts_and_card_changes(prepared_repo):
    app, dialog = open_dialog(prepared_repo)
    partial = row(dialog, 'partial')
    checked, amount, _ = partial['contributions'][0]
    dialog.target.setText('100.00')
    checked.setChecked(True)
    for invalid in ('-1', 'NaN', '1.001', 'abc'):
        amount.setText(invalid)
        assert not dialog.continue_button.isEnabled()
        assert dialog.total_cents == 0
    amount.setText('300.00')
    dialog.add_contribution(partial)
    other = partial['contributions'][1]
    other[1].setText('354.87')  # Calculator allows amounts above receipts, without creating receipts.
    other[0].setChecked(True)
    assert dialog.continue_button.isEnabled()
    assert dialog.total_cents == 65487
    other[2].click()
    assert dialog.continue_button.isEnabled()
    assert dialog.total_cents == 30000
    dialog.card.setCurrentIndex(dialog.card.findData('other'))
    assert len(dialog.rows) == 1 and dialog.total_cents == 0
    assert dialog.own.text() == '0.00' and dialog.target.text() == ''
    dialog.close()
    assert dialog.total_cents == 0


def test_home_entry_only_navigates_to_existing_payment_flow(prepared_repo, monkeypatch):
    app = create_application([])
    repo = prepared_repo
    before = snapshot(repo)
    window = MainWindow(database=repo.database, test_mode=True)
    assert window.prepare_payment_button.isEnabled()
    assert window.prepare_payment_button.text() == 'Revisar efectivo'
    def accept_without_payment(dialog):
        dialog.card.setCurrentIndex(dialog.card.findData('card'))
        return QDialog.DialogCode.Accepted
    from valenza.gui.cash_review import CashReviewDialog
    monkeypatch.setattr(CashReviewDialog, 'exec', accept_without_payment)
    window.prepare_payment_button.click()
    assert window.card_instrument.currentData() == 'card'
    assert snapshot(repo) == before
    window.close()


def test_item_identity_not_merchant_name(prepared_repo):
    items = preparation_items(prepared_repo, 'card')
    assert {r['order_id'] for r in items} == {'unpaid', 'partial', 'paid'}
    assert len({r['receivable_id'] for r in items}) == 3


def test_order_checkbox_fills_pending_and_preserves_partial_edits(prepared_repo):
    before = snapshot(prepared_repo)
    app, dialog = open_dialog(prepared_repo)
    partial = row(dialog, 'partial')
    partial['quick'].click()
    assert dialog.total_cents == 35487
    assert partial['contributions'][0][1].text() == '354.87'
    partial['quick'].click()
    assert dialog.total_cents == 0
    partial['contributions'][0][1].setText('200.00')
    partial['quick'].click()
    assert dialog.total_cents == 20000
    unpaid = row(dialog, 'unpaid')
    unpaid['quick'].click()
    assert dialog.total_cents == 30000
    dialog.add_contribution(partial)
    partial['contributions'][1][1].setText('50.00')
    partial['contributions'][1][0].setChecked(True)
    partial['quick'].click()
    assert dialog.total_cents == 10000
    assert not any(c.isChecked() for c, _, _ in partial['contributions'])
    dialog.close()
    assert snapshot(prepared_repo) == before


def test_save_reopen_independent_snapshot_without_accounting_writes(prepared_repo, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from valenza.gui.preparation_record import load_record, record_total
    repo = prepared_repo
    before = snapshot(repo)
    changes = repo.database.connection.total_changes
    app, dialog = open_dialog(repo)
    unpaid = row(dialog, 'unpaid')
    unpaid['contributions'][0][1].setText('654.87')
    unpaid['contributions'][0][0].setChecked(True)
    dialog.add_contribution(unpaid)
    unpaid['contributions'][1][1].setText('200.00')
    # Unchecked contribution must survive reopening without entering the total.
    dialog.target.setText('1000.00')
    dialog.own.setText('200.13')
    dialog.record_name.setText('Cáliz de octubre')
    path = tmp_path / 'corte-sintetico.json'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(path), ''))
    dialog.save_button.click()
    record = load_record(path)
    assert record['name'] == 'Cáliz de octubre'
    assert record['card_id'] == 'card'
    assert record_total(record) == 85500
    assert snapshot(repo) == before and repo.database.connection.total_changes == changes
    dialog.reject()
    reopened = PaymentPreparationDialog(repo)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(path), ''))
    reopened.open_cut()
    assert reopened.total_cents == 85500
    restored = row(reopened, 'unpaid')
    assert restored['item']['paid_cents'] == 0
    assert len(restored['contributions']) == 2
    assert not restored['contributions'][1][0].isChecked()
    assert restored['contributions'][1][1].text() == '200.00'
    restored['contributions'][1][0].setChecked(True)
    assert reopened.total_cents == 105500
    reopened.save_cut()
    assert record_total(load_record(path)) == 105500
    reopened.close()
    assert snapshot(repo) == before and repo.database.connection.total_changes == changes


def test_record_validation_and_cancelled_file_dialogs(prepared_repo, tmp_path, monkeypatch):
    import json
    from PySide6.QtWidgets import QFileDialog
    from valenza.gui.preparation_record import load_record
    app, dialog = open_dialog(prepared_repo)
    dialog.target.setText('1500.00')
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: ('', ''))
    dialog.save_cut()
    assert dialog.target.text() == '1500.00'
    bad = tmp_path / 'invalid.json'
    bad.write_text('{"format":"not-valenza"}', encoding='utf-8')
    with pytest.raises(ValueError):
        load_record(bad)
    record = dialog.cut_record()
    record['rows'].append(record['rows'][0])
    bad.write_text(json.dumps(record), encoding='utf-8')
    with pytest.raises(ValueError, match='duplicados'):
        load_record(bad)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(bad), ''))
    dialog.open_cut()
    assert 'No se pudo abrir' in dialog.error.text()
    assert dialog.target.text() == '1500.00' and len(dialog.rows) == 3
    dialog.close()


def product_order(repo):
    repo.create_order(order_id='products', ordered_at='2026-10-01', merchant='Pedido con productos',
                      instrument_id='card', original_cents=30000, charged_cents=30000, discount_cents=0,
                      allocations=({'user_id': 'owner', 'amount_cents': 3000},
                                   {'user_id': 'family', 'amount_cents': 27000}),
                      concepts=[dict(description='Compartido', amount_cents=10000,
                                     allocations={'owner': 3000, 'family': 7000}),
                                dict(description='Solo familiar', amount_cents=20000,
                                     allocations={'owner': 0, 'family': 20000})])
    repo.record_receipt(payment_id='product-receipt', receivable_id='order:products:family',
                        amount_cents=5000, received_at='2026-10-02')


def test_product_selection_partial_parent_and_no_double_count(prepared_repo, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton
    product_order(prepared_repo)
    before = snapshot(prepared_repo)
    changes = prepared_repo.database.connection.total_changes
    app, dialog = open_dialog(prepared_repo)
    products = row(dialog, 'products')
    assert [p['amount_cents'] for p in products['item']['products']] == [7000, 20000]
    assert len(products['contributions']) == 2
    products['quick'].click()
    assert dialog.total_cents == 27000  # Products only; parent and receipt are never added/subtracted again.
    products['contributions'][1][0].setChecked(False)
    assert dialog.total_cents == 7000
    assert products['quick'].checkState() == Qt.CheckState.PartiallyChecked
    products['contributions'][0][1].setText('35.01')
    assert dialog.total_cents == 3501
    products['contributions'][0][1].setText('70.01')
    assert dialog.error.text() and dialog.total_cents == 0
    products['contributions'][0][1].setText('35.01')
    products['quick'].click()  # Partial -> all; preserves edited partial amount.
    assert dialog.total_cents == 23501
    products['quick'].click()
    assert dialog.total_cents == 0
    next(b for b in dialog.findChildren(QPushButton) if 'J sintético' in b.text()).click()
    next(b for b in dialog.findChildren(QPushButton) if b.text().startswith('Pedido con productos ·')).click()
    app.processEvents()
    dialog.scroll.ensureWidgetVisible(products['contributions'][0][0])
    app.processEvents()
    dialog.grab().save(str(tmp_path / 'products-checklist.png'))
    dialog.close()
    assert snapshot(prepared_repo) == before
    assert prepared_repo.database.connection.total_changes == changes


def test_product_snapshot_roundtrip_and_validation(prepared_repo, tmp_path, monkeypatch):
    import copy
    from PySide6.QtWidgets import QFileDialog
    from valenza.gui.preparation_record import save_record, load_record, record_total, validate_record
    product_order(prepared_repo)
    before = snapshot(prepared_repo)
    app, dialog = open_dialog(prepared_repo)
    products = row(dialog, 'products')
    products['contributions'][1][0].setChecked(True)
    products['contributions'][1][1].setText('150.13')
    dialog.target.setText('300.00')
    path = tmp_path / 'product-cut.json'
    save_record(path, dialog.cut_record())
    assert record_total(load_record(path)) == 15013
    dialog.close()
    opened = PaymentPreparationDialog(prepared_repo)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(path), ''))
    opened.open_cut()
    restored = row(opened, 'products')
    assert len(restored['contributions']) == 2
    assert restored['item']['products'][1]['description'] == 'Solo familiar'
    assert not restored['contributions'][0][0].isChecked()
    assert restored['contributions'][1][1].text() == '150.13'
    assert opened.total_cents == 15013
    record = copy.deepcopy(load_record(path))
    saved = next(r for r in record['rows'] if r['item'].get('products'))
    saved['contributions'].pop()
    with pytest.raises(ValueError, match='desglose'):
        validate_record(record)
    opened.close()
    assert snapshot(prepared_repo) == before


def test_mismatched_product_totals_block_mark_all(prepared_repo):
    product_order(prepared_repo)
    app, dialog = open_dialog(prepared_repo)
    items = preparation_items(prepared_repo, 'card')
    item = next(i for i in items if i['order_id'] == 'products')
    item['sale_cents'] -= 1000  # Synthetic adjustment without product-level evidence.
    dialog.render_items(items)
    products = row(dialog, 'products')
    assert products['mismatch'] and not products['quick'].isEnabled()
    products['contributions'][0][0].setChecked(True)
    assert dialog.total_cents == 7000
    dialog.close()


def test_historical_products_keep_person_share_and_quantity(prepared_repo):
    repo = prepared_repo
    repo.create_purchase(purchase_id='historical', purchased_at='2026-10-01', merchant='Histórica',
                         instrument_id='card',
                         products=({'id': 'historical-product', 'description': 'Artículo histórico',
                                    'quantity': 3, 'unit_price_cents': 1000},),
                         allocations=({'product_id': 'historical-product', 'user_id': 'owner',
                                       'method': 'UNITS', 'basis': 1},
                                      {'product_id': 'historical-product', 'user_id': 'family',
                                       'method': 'UNITS', 'basis': 2}))
    before = snapshot(repo)
    items = preparation_items(repo, 'card')
    historical = next(i for i in items if i.get('purchase_id') == 'historical')
    assert historical['products'] == [dict(product_id='historical-product', description='Artículo histórico',
                                         quantity=3, amount_cents=2000)]
    assert snapshot(repo) == before


@pytest.mark.parametrize('list_allocations', [False, True])
def test_imported_product_projection_uses_saved_allocations(prepared_repo, monkeypatch, list_allocations):
    product_order(prepared_repo)
    original = prepared_repo.get_order
    def imported(order_id):
        order = original(order_id)
        if order_id == 'products':
            products = order.pop('manual_concepts')
            for product in products:
                product['quantity'] = 2
                if list_allocations:
                    product['allocations'] = [dict(user_id=k, amount_cents=v)
                                              for k, v in product['allocations'].items()]
            order['manual_concepts'] = None
            order['import_evidence'] = dict(products=products)
        return order
    monkeypatch.setattr(prepared_repo, 'get_order', imported)
    products = next(i for i in preparation_items(prepared_repo, 'card') if i['order_id'] == 'products')['products']
    assert [p['amount_cents'] for p in products] == [7000, 20000]
    assert [p['quantity'] for p in products] == [2, 2]


def test_owner_participation_products_and_extra_money_are_separate(prepared_repo):
    product_order(prepared_repo)
    before = snapshot(prepared_repo)
    changes = prepared_repo.database.connection.total_changes
    app, dialog = open_dialog(prepared_repo)
    personal = [r for r in dialog.rows if r['item']['user_id'] == 'owner']
    assert len(personal) == 1
    own_order = personal[0]
    assert own_order['item']['participant_role'] == 'PERSONAL'
    assert own_order['item']['sale_cents'] == 3000
    assert [p['amount_cents'] for p in own_order['item']['products']] == [3000]
    own_order['quick'].click()
    assert dialog.total_cents == 3000
    dialog.own.setText('10.00')
    assert dialog.total_cents == 4000
    own_order['quick'].click()
    assert dialog.total_cents == 1000
    dialog.close()
    assert snapshot(prepared_repo) == before
    assert prepared_repo.database.connection.total_changes == changes


def msi_preparation_order(repo, *, with_products=True, dates=('2026-09-15', '2026-10-15', '2026-11-15')):
    repo.create_order(order_id='monthly', ordered_at='2026-08-01', merchant='MSI sintético', instrument_id='card',
                      original_cents=10001, charged_cents=10001, discount_cents=0,
                      allocations=({'user_id': 'owner', 'amount_cents': 5000},
                                   {'user_id': 'family', 'amount_cents': 5001}),
                      purchase_mode='MSI', financing_specs=dates,
                      concepts=[dict(description='Producto A', amount_cents=5000,
                                     allocations={'owner': 3000, 'family': 2000}),
                                dict(description='Producto B', amount_cents=5001,
                                     allocations={'owner': 2000, 'family': 3001})] if with_products else None)


@pytest.mark.parametrize('with_products', [True, False])
def test_msi_preparation_only_current_month_and_no_financial_writes(prepared_repo, with_products):
    from datetime import date
    repo = prepared_repo
    msi_preparation_order(repo, with_products=with_products)
    before = snapshot(repo)
    changes = repo.database.connection.total_changes
    totals = {'owner': 0, 'family': 0}
    for month in (9, 10, 11):
        items = [i for i in preparation_items(repo, 'card', as_of=date(2026, month, 1)) if i['order_id'] == 'monthly']
        assert len(items) == 2
        for item in items:
            assert item['sale_cents'] in (1666, 1667)
            assert item['sale_cents'] == item['remaining_cents']
            assert item['total_sale_cents'] in (5000, 5001)
            totals[item['user_id']] += item['sale_cents']
            if with_products:
                assert sum(p['amount_cents'] for p in item['products']) == item['sale_cents']
    assert totals == {'owner': 5000, 'family': 5001}
    for when in (date(2026, 8, 1), date(2026, 12, 1)):
        assert not any(i['order_id'] == 'monthly' for i in preparation_items(repo, 'card', as_of=when))
    assert snapshot(repo) == before and repo.database.connection.total_changes == changes


def test_msi_receipts_reduce_month_once_and_product_cut_roundtrips(prepared_repo, monkeypatch, tmp_path):
    from datetime import date
    import valenza.gui.payment_preparation as module
    from valenza.gui.preparation_record import save_record, load_record, record_total
    from PySide6.QtWidgets import QFileDialog
    class October(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 16)
    monkeypatch.setattr(module, 'date', October)
    repo = prepared_repo
    msi_preparation_order(repo)
    repo.record_receipt(payment_id='monthly-paid', receivable_id='order:monthly:family', amount_cents=2000,
                        received_at='2026-10-01')
    before = snapshot(repo)
    app, dialog = open_dialog(repo)
    monthly = row(dialog, 'monthly')
    assert monthly['item']['remaining_cents'] == 1334
    assert sum(p['amount_cents'] for p in monthly['item']['products']) == 1334
    monthly['quick'].click()
    assert dialog.total_cents == 1334
    from PySide6.QtWidgets import QPushButton
    next(b for b in dialog.findChildren(QPushButton) if 'J sintético' in b.text()).click()
    next(b for b in dialog.findChildren(QPushButton) if b.text().startswith('MSI sintético ·')).click()
    dialog.scroll.ensureWidgetVisible(monthly['contributions'][0][0])
    app.processEvents()
    dialog.grab().save(str(tmp_path / 'monthly-checklist.png'))
    dialog.target.setText('100.00')
    path = tmp_path / 'monthly.json'
    save_record(path, dialog.cut_record())
    dialog.close()
    reopened = PaymentPreparationDialog(repo)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(path), ''))
    reopened.open_cut()
    assert reopened.total_cents == record_total(load_record(path)) == 1334
    assert row(reopened, 'monthly')['item']['preparation_period'] == '2026-10'
    reopened.close()
    assert snapshot(repo) == before


def test_msi_missing_dates_never_uses_whole_principal(prepared_repo):
    from datetime import date
    msi_preparation_order(prepared_repo, dates=(None, None, None))
    items = [i for i in preparation_items(prepared_repo, 'card', as_of=date(2026,10,1)) if i['order_id'] == 'monthly']
    assert len(items) == 2
    assert all(i['msi_dates_missing'] and i['remaining_cents'] == 0 for i in items)


def test_msi_no_products_checkbox_uses_monthly_amount_and_caps_total(prepared_repo):
    from datetime import date
    msi_preparation_order(prepared_repo, with_products=False)
    app, dialog = open_dialog(prepared_repo)
    dialog.render_items(preparation_items(prepared_repo, 'card', as_of=date(2026,10,1)))
    monthly = row(dialog, 'monthly')
    monthly['quick'].click()
    assert dialog.total_cents == 1667
    dialog.add_contribution(monthly)
    monthly['contributions'][1][1].setText('1.00')
    monthly['contributions'][1][0].setChecked(True)
    assert dialog.error.text() and dialog.total_cents == 0
    dialog.close()


def test_each_msi_installment_has_own_identity_and_checkbox(prepared_repo):
    from datetime import date
    msi_preparation_order(prepared_repo, with_products=False,
                          dates=('2026-10-01', '2026-10-25', '2026-11-25'))
    before = snapshot(prepared_repo)
    items = preparation_items(prepared_repo, 'card', as_of=date(2026,10,1))
    family = [i for i in items if i['order_id'] == 'monthly' and i['user_id'] == 'family']
    assert [i['installment_number'] for i in family] == [1, 2]
    assert len({i['receivable_id'] for i in family}) == 2
    assert all(i['remaining_cents'] == 1667 for i in family)
    assert all('Mensualidad' in i['source_name'] for i in family)
    app, dialog = open_dialog(prepared_repo)
    dialog.render_items(family)
    dialog.rows[0]['quick'].click()
    assert dialog.total_cents == 1667
    dialog.rows[1]['quick'].click()
    assert dialog.total_cents == 3334
    dialog.rows[0]['quick'].click()
    assert dialog.total_cents == 1667
    dialog.close()
    assert snapshot(prepared_repo) == before


def test_old_cut_full_msi_is_replaced_by_unchecked_monthly_rows(prepared_repo, monkeypatch, tmp_path):
    from datetime import date
    from PySide6.QtWidgets import QFileDialog
    from valenza.gui.preparation_record import save_record, load_record
    import valenza.gui.payment_preparation as module
    class October(date):
        @classmethod
        def today(cls): return cls(2026,10,16)
    monkeypatch.setattr(module, 'date', October)
    msi_preparation_order(prepared_repo)
    before = snapshot(prepared_repo)
    app, dialog = open_dialog(prepared_repo)
    dialog.target.setText('1000.00')
    record = dialog.cut_record()
    record.pop('msi_basis')
    record['rows'] = [r for r in record['rows'] if r['item'].get('order_id') != 'monthly']
    full = next(i for i in prepared_repo.list_collection_items() if i['order_id'] == 'monthly' and i['user_id'] == 'family')
    record['rows'].append(dict(item=full, contributions=[dict(amount_cents=5001, included=True)]))
    path = tmp_path / 'old-full-msi.json'
    save_record(path, record)
    original_bytes = path.read_bytes()
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(path), ''))
    dialog.open_cut()
    monthly = row(dialog, 'monthly')
    assert monthly['item']['remaining_cents'] == 1667
    assert monthly['item']['installment_number'] == 2
    assert dialog.total_cents == 0
    assert 'separados' in dialog.record_status.text()
    monthly['quick'].click()
    assert dialog.total_cents == 1667
    assert dialog.cut_record()['msi_basis'] == 'installment-rows-v2'
    assert path.read_bytes() == original_bytes
    assert load_record(path)['rows'][-1]['item']['sale_cents'] == 5001
    dialog.close()
    assert snapshot(prepared_repo) == before


def test_msi_marked_without_readable_plan_never_falls_back_to_full_price(prepared_repo, monkeypatch):
    from datetime import date
    msi_preparation_order(prepared_repo)
    original = prepared_repo.get_order
    def missing_plan(order_id):
        order = original(order_id)
        if order_id == 'monthly':
            order['financing_plan'] = None
            order['installments'] = []
        return order
    monkeypatch.setattr(prepared_repo, 'get_order', missing_plan)
    items = [i for i in preparation_items(prepared_repo, 'card', as_of=date(2026,10,1)) if i['order_id'] == 'monthly']
    assert items and all(i['remaining_cents'] == 0 and i['msi_dates_missing'] for i in items)
