"""Synthetic presentation checks for Cobros; never opens an existing database."""
from pathlib import Path
import pytest
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QLabel, QListWidget
from valenza.gui.app import MainWindow, create_application, format_money
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository

@pytest.mark.parametrize('count', [0, 2, 24])
def test_cobros_layout_preserves_finance(tmp_path, count):
    app = create_application([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    db = LocalDatabase.open(tmp_path / 'synthetic.db', 'synthetic-only')
    db.migrate()
    repo = FinanceRepository(db)
    owner = repo.create_person('Yo sintético', is_owner=True)
    family = repo.create_person('Familia sintética')
    repo.ensure_demo_catalog()
    instrument = str(repo.list_instruments()[0]['id'])
    for i in range(count):
        repo.create_order(order_id=f'synthetic-{i}', ordered_at='2026-10-12',
            merchant=f'Comercio sintético {i+1}', instrument_id=instrument,
            original_cents=15000, discount_cents=0, charged_cents=15000,
            allocations=({'user_id':owner, 'amount_cents':5000},
                         {'user_id':family, 'amount_cents':10000}))
        repo.record_receipt(payment_id=f'receipt-{i}', receivable_id=f'order:synthetic-{i}:{family}',
            amount_cents=2500, received_at='2026-10-12', reference='Transferencia sintética')
    before = (repo.dashboard_summary(), repo.list_collection_items(), repo.list_receipt_history())
    window = MainWindow(database=db)
    window.resize(round(1360 / app.devicePixelRatio()), round(940 / app.devicePixelRatio()))
    window.findChild(QListWidget, 'navigation').setCurrentRow(window.PAGES.index('Cobros'))
    window.show()
    app.processEvents()
    changes = db.connection.total_changes
    assert window.collection_items.rowCount() == count*2
    assert window.collection_items.height() < 360
    assert window.collection_personal_card.findChild(QLabel,'summaryAmount').text() == format_money(count*5000)
    assert window.collection_family_card.findChild(QLabel,'summaryAmount').text() == format_money(count*7500)
    out = Path('output/cobros'); out.mkdir(parents=True,exist_ok=True)
    def capture(name, widget=None):
        app.processEvents()
        (widget or window).grab().save(str(out / f'{name}.png'))
    if count == 2:
        capture('01-movimientos')
    if count:
        window.collection_items.selectRow(0)
        assert window.record_collection_button.isEnabled()
        assert window.family_pdf_button.isEnabled()
        assert 'Pendiente' in window.collection_selected_details.text()
        if count == 2: capture('02-seleccion')
        window.collection_details_toggle.setChecked(True)
        window.collection_reference.setText('Referencia de prueba')
        window.collection_received_date.setText('2026-10-12')
        assert window.collection_details.isVisible()
        if count == 2: capture('03-abono')
        window.other_operations_toggle.setChecked(True)
        app.processEvents()
        assert window.other_operations.isVisible()
        assert window.collections_scroll.horizontalScrollBar().maximum() == 0
        if count == 2: capture('04-extras', window.other_operations.parentWidget())
        window.collection_history_toggle.setChecked(True)
        assert window.collection_history.rowCount() == count
        assert window.collection_history.height() < 360
        window.collection_history.selectRow(0)
        assert window.edit_receipt_button.isEnabled()
        assert window.cancel_receipt_button.isEnabled()
        if count == 2: capture('05-historial', window.collection_history.parentWidget())
        window.collection_filter.setCurrentIndex(1)
        assert window.collection_items.rowCount() == count
        window.collection_filter.setCurrentIndex(2)
        assert window.collection_items.rowCount() == count
        window.collection_history_toggle.setChecked(False)
        assert window.collection_history.isHidden()
    else:
        assert not window.record_collection_button.isEnabled()
    assert db.connection.total_changes == changes
    assert (repo.dashboard_summary(), repo.list_collection_items(), repo.list_receipt_history()) == before
    window.close()
    db.close()

def test_explicit_collection_actions(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    app = create_application([])
    monkeypatch.setattr(MainWindow, '_show_information', lambda *args: None)
    monkeypatch.setattr(MainWindow, '_show_error', lambda self, text: pytest.fail(text))
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    db = LocalDatabase.open(tmp_path / 'actions.db', 'synthetic-only')
    db.migrate()
    repo = FinanceRepository(db)
    owner = repo.create_person('Owner synthetic', is_owner=True)
    person = repo.create_person('Family synthetic')
    repo.ensure_demo_catalog()
    repo.create_order(order_id='actions', ordered_at='2026-10-12', merchant='Synthetic store',
        instrument_id=str(repo.list_instruments()[0]['id']), original_cents=10000,
        discount_cents=0, charged_cents=10000,
        allocations=({'user_id':owner,'amount_cents':0},{'user_id':person,'amount_cents':10000}))
    window = MainWindow(database=db)
    window._show_page(3)
    window.collection_items.selectRow(0)
    window.collection_amount.setText('10.00')
    window.collection_reference.setText('Synthetic reference')
    window.record_collection_button.click()
    assert repo.list_collection_items()[0]['remaining_cents'] == 9000
    assert repo.list_receipt_history()[0]['reference'] == 'Synthetic reference'
    window.collection_history_toggle.setChecked(True)
    window.collection_history.selectRow(0)
    window.collection_amount.setText('15.00')
    from valenza.gui.receipt_editor import ReceiptEditDialog
    from PySide6.QtWidgets import QDialog
    def edit_receipt(dialog):
        dialog.amount.setText('15.00')
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(ReceiptEditDialog,'exec',edit_receipt)
    window.edit_receipt_button.click()
    assert repo.list_collection_items()[0]['remaining_cents'] == 8500
    window.collection_history.selectRow(0)
    window.cancel_receipt_button.click()
    assert repo.list_collection_items()[0]['remaining_cents'] == 10000
    window.other_operations_toggle.setChecked(True)
    window.extra_person.setCurrentIndex(window.extra_person.findData(person))
    window.extra_amount.setText('5.00')
    window.extra_description.setText('Synthetic extra')
    assert window.record_extra_button.isEnabled()
    window.record_extra_button.click()
    window.fee_amount.setText('2.00')
    window.fee_description.setText('Synthetic fee')
    assert window.record_fee_button.isEnabled()
    window.record_fee_button.click()
    assert repo.list_collection_items()[0]['remaining_cents'] == 10000
    assert repo.count('institution_payment') == 0
    window.close()
    db.close()
