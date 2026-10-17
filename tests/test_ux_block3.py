"""Form and query regressions using encrypted synthetic databases only."""
from pathlib import Path
import pytest
import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtGui import QAccessible
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QHeaderView

from test_ux_block1 import window, settle, snapshot
from valenza.gui.pdf_import import ImportPreview, ProductAssignment
from valenza.gui.person_receipts import ReceiptPreview


MANUAL_FIELDS = ('order_merchant', 'order_date', 'order_institution', 'order_instrument',
    'order_purchase_mode', 'order_installments', 'order_amount_basis', 'order_first_due_date',
    'order_interest', 'order_original', 'order_charged', 'manual_concepts', 'order_allocations_table',
    'order_summary', 'save_order_button', 'cancel_manual_button', 'correct_charge_button')


@pytest.mark.parametrize('mode,basis,shared', [
    ('CASH', 'TOTAL', False), ('CASH', 'TOTAL', True),
    ('MSI', 'TOTAL', False), ('MSI', 'TOTAL', True),
    ('MSI', 'INSTALLMENT', False), ('MSI', 'INSTALLMENT', True)])
def test_complete_capture_keeps_amounts_assignments_and_single_charge(window, mode, basis, shared):
    app, ui, db = window
    before = snapshot(db)
    initial_debt = ui.repository.list_card_summaries()[0]['remaining_cents']
    ui._open_manual_expense()
    ui.manual_dialog.resize(480, 480)
    settle(app)
    assert all(shiboken6.isValid(getattr(ui, field)) for field in MANUAL_FIELDS)
    assert ui.manual_concept_section.y() < 320  # The old three introductory panels pushed it much farther down.
    assert ui.manual_scroll.horizontalScrollBar().maximum() == 0
    ui.order_merchant.setText('Comercio sintético bloque 3')
    ui.order_date.setText('2026-10-15')
    ui.order_purchase_mode.setCurrentIndex(ui.order_purchase_mode.findData(mode))
    ui.order_amount_basis.setCurrentIndex(ui.order_amount_basis.findData(basis))
    if mode == 'MSI':
        ui.order_installments.setValue(3)
        ui.order_first_due_date.setText('2026-10-20')
        ui.order_interest.setText('0.00')
        assert not ui.order_amount_basis.isHidden()
        assert not ui.order_first_due_date.isHidden()
    ui.manual_concepts.item(0, 0).setText('Primer concepto')
    ui.manual_concepts.item(0, 1).setText('100.00')
    first = ui.manual_concepts.cellWidget(0, 2)
    if shared:
        first.divide.setChecked(True)
        first.amounts['owner'].setText('40.00')
        first.amounts['family'].setText('60.00')
    ui._add_manual_concept(dict(description='Segundo concepto', amount_cents=5000,
        allocations={'owner':0 if shared else 5000, 'family':5000 if shared else 0}))
    ui.order_charged.setText('140.00')
    settle(app)
    assert snapshot(db) == before  # Capture, previews and navigation never write.
    assert 'Reparto que se guardará' in ui.order_summary.text()
    ui.manual_review_button.click(); settle(app)
    assert ui.manual_scroll.verticalScrollBar().value() > 0
    assert ui.manual_concepts.item(0, 0).text() == 'Primer concepto'
    assert ui.save_order_button.isEnabled()
    ui.manual_review_button.setFocus()
    QTest.keyClick(ui.manual_review_button, Qt.Key.Key_Tab)
    assert ui.cancel_manual_button.hasFocus()
    QTest.keyClick(ui.cancel_manual_button, Qt.Key.Key_Tab)
    assert ui.save_order_button.hasFocus()
    QTest.keyClick(ui.save_order_button, Qt.Key.Key_Space)
    assert not ui.manual_dialog.isVisible()
    saved = next(o for o in ui.repository.list_orders() if o['merchant'] == 'Comercio sintético bloque 3')
    order = ui.repository.get_order(saved['id'])
    multiplier = 3 if basis == 'INSTALLMENT' else 1
    assert order['original_cents'] == 15000 * multiplier
    assert order['charged_cents'] == 14000 * multiplier
    assert order['discount_cents'] == 1000 * multiplier
    amounts = {a['user_id']: a['amount_cents'] for a in order['allocations']}
    assert amounts.get('owner', 0) == (4000 if shared else 15000) * multiplier
    assert amounts.get('family', 0) == (11000 if shared else 0) * multiplier
    assert ui.repository.list_card_summaries()[0]['remaining_cents'] == initial_debt + 14000 * multiplier
    assert len(ui.repository.list_orders()) == 3
    if mode == 'MSI':
        installments = [i for i in ui.repository.list_installments('card') if i['order_id'] == saved['id']]
        assert len(installments) == 3
        assert [i['due_date'] for i in installments] == ['2026-10-20', '2026-11-20', '2026-12-20']
        assert sum(i['principal_cents'] for i in installments) == 14000 * multiplier


def test_manual_compact_layout_footer_keyboard_and_draft_survive_resize(window, tmp_path):
    app, ui, db = window
    before = snapshot(db)
    ui._open_manual_expense()
    ui.order_merchant.setText('Borrador conservado')
    controls = {name: getattr(ui, name) for name in MANUAL_FIELDS}
    for width, height in ((480, 360), (680, 480), (1000, 760), (480, 480)):
        ui.manual_dialog.resize(width, height); settle(app)
        assert ui.manual_scroll.horizontalScrollBar().maximum() == 0
        for button in (ui.manual_review_button, ui.cancel_manual_button, ui.save_order_button):
            assert ui.manual_dialog.rect().contains(button.geometry())
        assert all(getattr(ui, name) is widget for name, widget in controls.items())
        assert ui.order_merchant.text() == 'Borrador conservado'
    ui.manual_review_button.setFocus()
    QTest.keyClick(ui.manual_review_button, Qt.Key.Key_Space); settle(app)
    assert ui.manual_scroll.verticalScrollBar().value() > 0
    assert ui.manual_dialog.grab().save(str(tmp_path / 'manual-summary.png'))
    ui.manual_dialog.reject(); ui._open_manual_expense()
    assert ui.order_merchant.text() == 'Borrador conservado'
    assert snapshot(db) == before


def test_query_names_full_columns_filters_and_empty_state(window):
    app, ui, db = window
    before = snapshot(db)
    for table in (ui.orders_table, ui.cards_table, ui.collection_items, ui.collection_history,
                  ui.people_table, ui.subscription_table, ui.card_payment_history):
        assert table.accessibleName()
        assert not table.tabKeyNavigation()
    ui.navigation.setCurrentRow(2)
    ui.order_filter.setCurrentIndex(ui.order_filter.findData('CANCELLED')); settle(app)
    assert ui.orders_table.rowCount() == 0 and ui.orders_empty_notice.isVisible()
    ui.order_filter.setCurrentIndex(ui.order_filter.findData('ALL')); settle(app)
    assert ui.orders_table.rowCount() == 2 and not ui.orders_empty_notice.isVisible()
    ui.orders_table.selectRow(0); ui.orders_table.setFocus()
    QTest.keyClick(ui.orders_table, Qt.Key.Key_Tab); settle(app)
    assert not ui.orders_table.hasFocus()
    ui.navigation.setCurrentRow(3)
    ui.collection_filter.setCurrentIndex(ui.collection_filter.findData('UNKNOWN')); settle(app)
    assert ui.collection_items.rowCount() == 0 and ui.collections_empty_notice.isVisible()
    ui.collection_filter.setCurrentIndex(ui.collection_filter.findData('ALL'))
    assert ui.collection_items.rowCount() == 4
    assert snapshot(db) == before


def test_individual_and_global_receipts_keep_applications_and_bank_separate(window):
    app, ui, db = window
    ui.navigation.setCurrentRow(3)
    row = next(i for i in range(ui.collection_items.rowCount())
        if ui.collection_items.item(i, 7).text() == 'order:normal:family')
    ui.collection_items.selectRow(row)
    assert 'Familia sintética' in ui.collection_selected_details.text()
    assert 'Compra normal sintética' in ui.collection_selected_details.text()
    bank = ui.repository.list_card_summaries()
    ui.collection_amount.setText('100.00'); ui.collection_received_date.setText('2026-10-15')
    ui.collection_reference.setText('Abono individual sintético')
    ui.record_collection_button.click()
    assert ui.repository.count('user_payment') == 1
    panel = ui.person_receipt_panel
    panel.person.setCurrentIndex(panel.person.findData('family'))
    panel.amount.setText('50.00'); panel.received_date.setText('2026-10-15')
    before = snapshot(db)
    preview = ReceiptPreview(panel, ui.repository.person_receipt_accounts('family'), 5000)
    assert preview.table.horizontalHeaderItem(1).text() == 'Pendiente antes'
    assert preview.table.horizontalHeaderItem(4).text() == 'Pendiente después'
    assert 'sep 2026' in preview.table.item(0, 0).text()
    assert snapshot(db) == before
    preview.commit()
    assert ui.repository.count('user_payment') == 2
    assert ui.repository.list_card_summaries() == bank


def test_import_and_shared_component_keep_fields_and_allocations(window, tmp_path):
    from valenza.ocr.order_import import parse_receipt
    app, ui, db = window
    draft = parse_receipt((Path(__file__).parent / 'fixtures_synthetic/mp_products.txt').read_text(encoding='utf-8'))
    draft['fingerprint'] = 'synthetic-block3-review'
    before = snapshot(db)
    dialog = ImportPreview(ui.repository, draft, ui)
    dialog.resize(680, 480); dialog.show(); settle(app)
    assert set(dialog.fields) >= {'date', 'number', 'payment', 'discount', 'refund', 'charged', 'paid'}
    assert all(edit.accessibleName() for edit in dialog.fields.values())
    first = dialog.table.cellWidget(0, 3)
    first.divide.setChecked(True)
    for person, field in first.amounts.items():
        assert QAccessible.queryAccessibleInterface(field).text(QAccessible.Text.Name)
    original = first.original()
    first.amounts['owner'].setText(f'{original / 100:.2f}')
    first.amounts['family'].setText('0.00')
    allocations = first.shares()
    for width in (680, 1100, 680):
        dialog.resize(width, 480); settle(app)
        assert first.shares() == allocations
        assert dialog.scroll_area.horizontalScrollBar().maximum() == 0
    dialog.details_toggle.setChecked(True); settle(app)
    assert dialog.details.isVisible()
    assert dialog.grab().save(str(tmp_path / 'import-details.png'))
    dialog.cancel_button.click()
    assert snapshot(db) == before


def test_many_records_remain_available_with_table_scrolling(window):
    app, ui, db = window
    for i in range(22):
        ui.repository.create_order(order_id=f'many-{i}', ordered_at='2026-10-15', merchant=f'Comercio sintético {i:02d}',
            instrument_id='card', original_cents=1000, discount_cents=0, charged_cents=1000,
            allocations=({'user_id':'owner', 'amount_cents':1000},))
    before = snapshot(db)
    ui.resize(680, 480); ui.navigation.setCurrentRow(2); settle(app)
    assert ui.orders_table.rowCount() == 24
    assert ui.orders_table.verticalScrollBar().maximum() > 0
    assert ui.orders_table.horizontalScrollBar().maximum() > 0
    assert ui.orders_scroll.horizontalScrollBar().maximum() == 0
    ui.orders_table.selectRow(23); ui._show_order_detail()
    assert ui.order_detail.toPlainText()
    assert snapshot(db) == before


def test_live_person_labels_do_not_reset_shared_draft(window):
    app, ui, db = window
    ui._open_manual_expense()
    ui.manual_concepts.item(0, 1).setText('100.00')
    split = ui.manual_concepts.cellWidget(0, 2)
    split.divide.setChecked(True)
    split.amounts['owner'].setText('40.00'); split.amounts['family'].setText('60.00')
    before = snapshot(db)
    shares = split.shares()
    # Refresh presentation metadata only: no change to the persisted owner or shares.
    people = [dict(person, name='Nombre actualizado' if person['id']=='family' else person['name'])
              for person in ui.repository.list_people()]
    split.refresh_people(people)
    assert split.divide.isChecked() and split.shares() == shares
    assert 'Nombre actualizado' in split.split_fields.layout().labelForField(split.amounts['family']).text()
    assert 'propietario' in split.split_fields.layout().labelForField(split.amounts['owner']).text()
    assert snapshot(db) == before


def test_subscription_display_dates_and_card_form_labels_are_readonly(window, monkeypatch):
    from PySide6.QtWidgets import QDialog
    app, ui, db = window
    before = snapshot(db)
    ui.navigation.setCurrentRow(5); ui.subscription_table.selectRow(0)
    assert '20 oct 2026' in ui.subscription_summary.text()
    assert '20 oct 2026' in ui.subscription_detail.text()
    def inspect(dialog):
        edits = dialog.findChildren(QLineEdit)
        assert all(edit.accessibleName() for edit in edits)
        dialog.reject(); return dialog.result()
    monkeypatch.setattr(QDialog, 'exec', inspect)
    ui._edit_subscription('sub')
    for name in ('card_institution', 'card_instrument', 'card_payment_amount', 'card_payment_date',
                 'card_payment_reference', 'card_apply_payment', 'card_apply_installment',
                 'card_apply_amount', 'card_calendar_effective', 'card_closing_day', 'card_due_day',
                 'bank_period_picker', 'bank_query_date', 'collection_reference', 'collection_received_date'):
        assert getattr(ui, name).accessibleName(), name
    assert snapshot(db) == before
