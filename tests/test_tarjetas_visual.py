"""Synthetic Tarjetas presentation and action checks."""
from pathlib import Path
import os
import pytest
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QLabel, QListWidget, QPushButton, QMessageBox
from valenza.gui.app import MainWindow, create_application, format_money
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository

@pytest.mark.parametrize('count', [0, 1, 10])
def test_cards_layout_readonly(tmp_path, count):
    app = create_application([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    db = LocalDatabase.open(tmp_path/'synthetic.db','synthetic-only')
    db.migrate()
    repo = FinanceRepository(db)
    repo.add_person('owner','Yo sintético',is_owner=True)
    repo.add_institution('bank','Banco sintético')
    for i in range(count):
        repo.add_instrument(f'card-{i}','bank',f'Tarjeta sintética {i+1}','CREDIT_CARD')
        repo.create_order(order_id=f'order-{i}', ordered_at='2026-10-12', merchant='Comercio sintético',
            instrument_id=f'card-{i}', original_cents=30000, discount_cents=0,charged_cents=30000,
            allocations=({'user_id':'owner','amount_cents':30000},), purchase_mode='MSI',
            financing_specs=('2026-10-20','2026-11-20','2026-12-20'))
        repo.record_institution_payment(payment_id=f'payment-{i}',instrument_id=f'card-{i}',
            amount_cents=5000, paid_at='2026-10-12',reference='Transferencia sintética')
        repo.record_bank_balance(f'card-{i}',25500,'2026-10-12')
    before = (repo.list_card_summaries(include_inactive=True),repo.list_bank_comparisons(),repo.dashboard_summary())
    window = MainWindow(database=db)
    window.resize(round(1360/app.devicePixelRatio()),round(960/app.devicePixelRatio()))
    window.findChild(QListWidget,'navigation').setCurrentRow(4)
    window.show(); app.processEvents()
    changes = db.connection.total_changes
    assert window.cards_table.rowCount() == count
    assert window.cards_empty_notice.isVisible() == (count == 0)
    assert window.cards_table.height() < 300
    if count:
        window.cards_table.selectRow(0)
        assert window.card_summary_cards[0].findChild(QLabel,'summaryAmount').text() == '$250.00 MXN'
        # An old bank reference stays in history, separate from today's debt.
        assert window.bank_history.item(0, 2).text() == '$255.00 MXN'
        assert window.card_apply_payment.count() == 1
        assert window.card_apply_installment.count() == 3
        window.card_detail_toggle.click(); app.processEvents()
        assert window.card_detail_scroll.verticalScrollBar().maximum() > 0
    out = Path(os.environ.get('VALENZA_VISUAL_OUTPUT', 'output/tarjetas')); out.mkdir(parents=True,exist_ok=True)
    if count == 1:
        window.grab().save(str(out/'01-principal.png'))
    for key,(toggle,content) in window.card_panels.items():
        toggle.setChecked(True)
        if key == 'admin':
            for button in content.findChildren(QPushButton):
                if button.isCheckable(): button.setChecked(True)
        app.processEvents()
        assert content.isVisible()
        assert window.cards_scroll.horizontalScrollBar().maximum() == 0
        if count == 1:
            content.parentWidget().grab().save(str(out/f'{key}.png'))
        toggle.setChecked(False)
    window.cards_columns_toggle.setChecked(True)
    assert not window.cards_table.isColumnHidden(13)
    assert window.cards_table.isColumnHidden(12)
    window.cards_columns_toggle.setChecked(False)
    assert db.connection.total_changes == changes
    assert (repo.list_card_summaries(include_inactive=True),repo.list_bank_comparisons(),repo.dashboard_summary()) == before
    window.close(); db.close()

def test_card_buttons_preserve_operation_types(tmp_path, monkeypatch):
    app = create_application([])
    monkeypatch.setattr(MainWindow,'_show_information',lambda *args: None)
    monkeypatch.setattr(MainWindow,'_show_error',lambda self,text: pytest.fail(text))
    monkeypatch.setattr(QMessageBox,'question',lambda *args: QMessageBox.StandardButton.Yes)
    db = LocalDatabase.open(tmp_path/'actions.db','synthetic-only'); db.migrate()
    repo = FinanceRepository(db)
    repo.add_person('owner','Owner synthetic',is_owner=True)
    repo.add_institution('bank','Bank synthetic')
    repo.add_instrument('card','bank','Card synthetic','CREDIT_CARD')
    repo.create_order(order_id='msi',ordered_at='2026-10-12',merchant='Synthetic store',instrument_id='card',
        original_cents=30000, discount_cents=0,charged_cents=30000,
        allocations=({'user_id':'owner','amount_cents':30000},),purchase_mode='MSI',
        financing_specs=('2026-10-20','2026-11-20','2026-12-20'))
    window = MainWindow(database=db)
    window._show_page(4); window.cards_table.selectRow(0)
    def button(text):
        return next(b for b in window.pages.widget(4).findChildren(QPushButton) if b.text() == text)
    summary = repo.dashboard_summary()
    window.bank_query_amount.setText('305.00')
    window.bank_closing_date.setText('2026-10-10')
    window.bank_due_date.setText('2026-10-20')
    window.bank_query_save.click()
    after_query = repo.dashboard_summary()
    assert {k:v for k,v in after_query.items() if k != 'bank_comparisons'} == {
        k:v for k,v in summary.items() if k != 'bank_comparisons'}
    assert repo.list_bank_comparisons()[0]['reported_cents'] == 30500
    assert repo.count('institution_payment') == 0
    window.card_payment_amount.setText('50.00')
    window.card_payment_reference.setText('Synthetic reference')
    window.record_card_button.click()
    assert repo.list_card_summaries()[0]['remaining_cents'] == 25000
    window.cards_table.selectRow(0)
    window.card_payment_history.selectRow(0)
    window.card_payment_amount.setText('60.00')
    window.edit_payment_button.click()
    assert repo.list_card_summaries()[0]['remaining_cents'] == 24000
    window.cards_table.selectRow(0)
    window.card_apply_amount.setText('10.00')
    assert window.apply_card_button.isEnabled()
    window.apply_card_button.click()
    assert repo.list_installments('card')[0]['remaining_cents'] == 9000
    window.cards_table.selectRow(0)
    window.card_payment_history.selectRow(0)
    window.cancel_payment_button.click()
    assert repo.list_card_summaries()[0]['remaining_cents'] == 30000
    assert repo.list_installments('card')[0]['remaining_cents'] == 10000
    assert repo.count('user_payment') == 0
    window.cards_table.selectRow(0)
    window.card_closing_day.setText('10'); window.card_due_day.setText('25')
    button('Guardar fechas').click()
    assert repo.list_card_summaries()[0]['closing_day'] == 10
    window.admin_card_name.setText('Updated synthetic card')
    window.admin_card_last_four.setText('4321')
    button('Guardar cuenta').click()
    assert repo.instrument_profile('card')['last_four'] == '4321'
    assert repo.list_all_instruments()[0]['id'] == 'card'
    button('Activar/desactivar').click() # institution toggle
    assert not repo.list_all_institutions()[0]['active']
    window.admin_institution.setCurrentIndex(window.admin_institution.findData('bank'))
    button('Activar/desactivar').click()
    assert repo.list_all_institutions()[0]['active']
    window.admin_institution_name.setText('New synthetic bank')
    button('Agregar institución').click()
    assert len(repo.list_all_institutions()) == 2
    window.admin_institution.setCurrentIndex(window.admin_institution.findData('bank'))
    window.admin_institution_name.setText('Updated synthetic bank')
    button('Guardar nombre').click()
    assert next(i for i in repo.list_all_institutions() if i['id']=='bank')['name'] == 'Updated synthetic bank'
    button('Preparar nueva cuenta').click()
    window.admin_card_institution.setCurrentIndex(window.admin_card_institution.findData('bank'))
    window.admin_card_name.setText('New synthetic card')
    button('Agregar cuenta').click()
    assert len(repo.list_all_instruments()) == 2
    assert next(c for c in repo.list_card_summaries() if c['instrument_id']=='card')['remaining_cents'] == 30000
    row = next(r for r in range(window.cards_table.rowCount()) if window.cards_table.item(r,12).text()=='card')
    window.cards_table.selectRow(row)
    account_toggle = [b for b in window.pages.widget(4).findChildren(QPushButton) if b.text()=='Activar/desactivar'][-1]
    account_toggle.click()
    assert not next(c for c in repo.list_all_instruments() if c['id']=='card')['active']
    account_toggle.click()
    assert next(c for c in repo.list_all_instruments() if c['id']=='card')['active']
    assert len(repo.list_institution_payments('card')) == 1
    window.close(); db.close()
