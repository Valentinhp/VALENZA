import pytest
from test_product_refunds import repository,purchase_args
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository


DATES=('2026-11-30','2026-12-30','2027-01-30')


def order(repo, instrument='card'):
    repo.create_order(order_id='msi',ordered_at='2026-10-11',merchant='Compra sintética',instrument_id=instrument,
        original_cents=10001,discount_cents=0,charged_cents=10001,
        allocations=({'user_id':'owner','amount_cents':3333},{'user_id':'mama','amount_cents':6668}),
        concepts=[dict(description='Producto sintético',amount_cents=10001,allocations={'owner':3333,'mama':6668})])


def test_link_rounding_family_forecast_and_no_double_debt(repository):
    order(repository)
    before=repository.dashboard_summary()
    repository.link_order_to_msi('msi',DATES)
    after=repository.dashboard_summary()
    assert before['institutional_balance_cents']==after['institutional_balance_cents']==10001
    assert before['receivables_cents']==after['receivables_cents']==6668
    assert len(repository.list_orders())==1
    installments=repository.list_installments('card')
    assert [i['principal_cents'] for i in installments]==[3334,3334,3333]
    planned=repository.upcoming_obligations()
    assert sum(i['amount_cents'] for i in planned)==10001
    assert all(i['included_in_pending'] for i in planned)
    assert [i['amount_cents'] for i in planned if i['user_id']=='mama']==[2223,2223,2222]
    with pytest.raises(ValueError): repository.link_order_to_msi('msi',DATES)
    assert len(repository.list_orders())==1


def test_family_bank_receipts_are_independent_and_partial(repository):
    order(repository); repository.link_order_to_msi('msi',DATES)
    repository.record_receipt(payment_id='family',receivable_id='order:msi:mama',amount_cents=3000,received_at='2026-11-30')
    family=[i for i in repository.upcoming_obligations() if i['user_id']=='mama']
    assert [i['amount_cents'] for i in family]==[1446,2222]
    assert repository.dashboard_summary()['institutional_balance_cents']==10001
    repository.record_institution_payment(payment_id='bank',instrument_id='card',paid_at='2026-11-30',amount_cents=1000)
    repository.apply_institution_payment_to_installment(payment_id='bank',installment_id='plan:msi-1',amount_cents=1000)
    assert repository.dashboard_summary()['receivables_cents']==3668
    assert sum(i['remaining_cents'] for i in repository.list_installments('card'))==9001
    assert repository.dashboard_summary()['institutional_balance_cents']==9001
    with pytest.raises(ValueError):
        repository.apply_institution_payment_to_installment(payment_id='bank',installment_id='plan:msi-2',amount_cents=1)


def test_forecast_adjustment_keeps_real_bank_family_and_payments(repository):
    order(repository); repository.link_order_to_msi('msi',DATES)
    repository.record_institution_payment(payment_id='bank',instrument_id='card',paid_at='2026-11-30',amount_cents=1000)
    repository.apply_institution_payment_to_installment(payment_id='bank',installment_id='plan:msi-1',amount_cents=1000)
    before=repository.dashboard_summary()
    repository.adjust_msi_remaining('msi',5001,'Corrección sintética de previsión')
    items=repository.list_installments('card')
    assert sum(i['remaining_cents'] for i in items)==5001
    assert sum(i['applied_cents'] for i in items)==1000
    after=repository.dashboard_summary()
    assert after['institutional_balance_cents']==before['institutional_balance_cents']==9001
    assert after['receivables_cents']==before['receivables_cents']==6668
    assert repository.database.connection.execute("SELECT COUNT(*) FROM audit_event WHERE action='MSI_FORECAST_ADJUSTED'").fetchone()[0]==1
    with pytest.raises(ValueError): repository.adjust_msi_remaining('msi',9002,'No cabe')
    with pytest.raises(ValueError): repository.adjust_msi_remaining('msi',5000,'')


def test_family_paid_does_not_hide_future_bank_installments(repository):
    order(repository); repository.link_order_to_msi('msi',DATES)
    repository.record_receipt(payment_id='own',receivable_id='order:msi:owner',amount_cents=3333,received_at='2026-11-30')
    repository.record_receipt(payment_id='family',receivable_id='order:msi:mama',amount_cents=6668,received_at='2026-11-30')
    assert repository.upcoming_obligations()==[]
    assert sum(i['amount_cents'] for i in repository.upcoming_bank_installments())==10001
    assert repository.dashboard_summary()['institutional_balance_cents']==10001


def test_zero_forecast_can_be_corrected_without_losing_original_debt(repository):
    order(repository); repository.link_order_to_msi('msi',DATES)
    repository.adjust_msi_remaining('msi',0,'Previsión cancelada provisionalmente')
    assert not repository.upcoming_bank_installments()
    assert repository.dashboard_summary()['institutional_balance_cents']==10001
    repository.adjust_msi_remaining('msi',10001,'Corrección de previsión')
    assert sum(i['amount_cents'] for i in repository.upcoming_bank_installments())==10001
    assert repository.dashboard_summary()['institutional_balance_cents']==10001


def test_imported_refund_wallet_and_msi_remain_separate(repository):
    repository.create_order(**purchase_args(destination='wallet',absorbs='owner'))
    before=repository.dashboard_summary()
    repository.link_order_to_msi('order',DATES)
    repository.adjust_msi_remaining('order',35601,'Previsión revisada; reembolso en billetera')
    after=repository.dashboard_summary()
    assert before['institutional_balance_cents']==after['institutional_balance_cents']==54258
    assert before['receivables_cents']==after['receivables_cents']
    assert before['discount_benefit_cents']==after['discount_benefit_cents']==6029
    assert len(repository.list_orders())==1 and len(repository.list_product_refunds('order'))==1


@pytest.mark.parametrize('dates',[(),('2026-11-30','2026-11-30'),('2026-12-30','2026-11-30'),('2026-02-30',),(None,),('2026-10-10',)])
def test_invalid_msi_link_is_atomic(repository,dates):
    order(repository)
    with pytest.raises(ValueError): repository.link_order_to_msi('msi',dates)
    assert repository.get_order('msi')['purchase_mode']=='CASH'
    assert not repository.list_installments('card')


def test_wallet_cannot_become_msi_and_dates_remain_ordered(repository):
    order(repository,'wallet')
    with pytest.raises(ValueError,match='billetera'): repository.link_order_to_msi('msi',DATES)
    assert repository.get_order('msi')['purchase_mode']=='CASH'
    repository.create_order(order_id='credit',ordered_at='2026-10-11',merchant='Crédito',instrument_id='card',original_cents=100,
        discount_cents=0,charged_cents=100,allocations=({'user_id':'owner','amount_cents':100},))
    repository.link_order_to_msi('credit',DATES)
    with pytest.raises(ValueError):
        repository.correct_installment_due_date(installment_id='plan:credit-2',due_date='2027-02-01')
    repository.correct_installment_due_date(installment_id='plan:credit-2',due_date='2026-12-28')
    assert repository.list_installments('card')[1]['due_date']=='2026-12-28'


def test_msi_ui_link_and_dynamic_small_dialog(repository,monkeypatch,tmp_path):
    from valenza.gui.app import MainWindow,create_application
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFont,QFontDatabase
    from PySide6.QtWidgets import QDialog,QLineEdit,QPushButton
    app=create_application([])
    font=QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    if font>=0: app.setFont(QFont(QFontDatabase.applicationFontFamilies(font)[0],10))
    order(repository)
    window=MainWindow(database=repository.database); window.show(); window._show_page(2); window.orders_table.selectRow(0)
    def link():
        dialog=window.findChildren(QDialog)[-1]; dialog.resize(480,280)
        field=next(f for f in dialog.findChildren(QLineEdit) if 'banco' in f.placeholderText())
        field.setText('2026-11-30')
        save=next(b for b in dialog.findChildren(QPushButton) if b.text()=='Vincular plan MSI')
        assert save.isVisible() and save.mapTo(dialog,save.rect().bottomRight()).y()<dialog.height()
        dialog.grab().save(str(tmp_path/'msi-link-small.png')); save.click()
        if dialog.isVisible(): dialog.reject()
    QTimer.singleShot(0,link); window._msi_dialog()
    assert len(repository.list_installments('card'))==3
    def inspect():
        dialog=window.findChildren(QDialog)[-1]; dialog.resize(480,280); app.processEvents()
        from PySide6.QtWidgets import QScrollArea
        scroll=dialog.findChild(QScrollArea); scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        app.processEvents(); dialog.grab().save(str(tmp_path/'msi-adjust-small.png'))
        close=next(b for b in dialog.findChildren(QPushButton) if b.text()=='Cerrar')
        assert close.isVisible() and close.mapTo(dialog,close.rect().bottomRight()).y()<dialog.height()
        close.click()
    QTimer.singleShot(0,inspect); window._msi_dialog()
    window.close(); app.processEvents()
