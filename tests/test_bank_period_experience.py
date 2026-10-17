from datetime import date, datetime
import json

import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from test_product_refunds import repository
from test_bank_reconciliation import financial_snapshot
from valenza.gui.app import MainWindow, create_application
from valenza.persistence.bank_periods import period_forecast, normal_due


def purchase(repo, key='msi', amount=1200000, purchased='2026-09-20', dates=None):
    repo.create_order(order_id=key, ordered_at=purchased, merchant='Compra sintética '+key,
                      instrument_id='card', original_cents=amount, charged_cents=amount, discount_cents=0,
                      allocations=({'user_id':'owner', 'amount_cents':amount},),
                      **(dict(purchase_mode='MSI', financing_specs=dates) if dates else {}))


def twelve_dates(start=10):
    return tuple(date(2026+(start+i-1)//12, (start+i-1)%12+1, 15).isoformat() for i in range(12))


def calendar(repo):
    repo.save_instrument_calendar(calendar_id='calendar', instrument_id='card',
                                  effective_from='2026-01-01', closing_day=20, due_day=10)


@pytest.mark.parametrize('period,current,future,previous', [
    ('2026-09',0,1200000,0), ('2026-10',100000,1100000,0),
    ('2026-12',100000,900000,200000), ('2027-01',100000,800000,300000)])
def test_twelve_msi_periods_never_duplicate_principal(repository, period, current, future, previous):
    calendar(repository)
    purchase(repository, dates=twelve_dates())
    before = financial_snapshot(repository)
    result = repository.list_bank_comparisons(as_of=date.fromisoformat(period+'-01'))[0]
    forecast = result['monthly_forecast']
    assert result['calculated_cents'] == 1200000
    assert result['current_month_cents'] == forecast['current_cents'] == current
    assert forecast['future_cents'] == future
    assert forecast['confirmed_overdue_cents'] == previous
    assert forecast['previous_unconfirmed_cents'] == 0
    assert sum(forecast[k] for k in ('current_cents','future_cents','overdue_cents','undated_cents')) == 1200000
    assert financial_snapshot(repository) == before


def test_unconfirmed_previous_and_partial_payments_do_not_fake_monthly_net(repository):
    purchase(repository, dates=twelve_dates())
    repository.record_institution_payment(payment_id='partial', instrument_id='card',
                                          amount_cents=50000, paid_at='2026-10-15')
    before = financial_snapshot(repository)
    account = repository.list_bank_comparisons(as_of=date(2026,10,1))[0]
    # Former total-minus-future formula gave 50000, without knowing which month was paid.
    assert account['calculated_cents']-account['monthly_forecast']['future_cents'] == 50000
    assert account['current_month_cents'] == 100000
    assert account['monthly_forecast']['unassigned_payments_cents'] == 50000
    assert financial_snapshot(repository) == before
    repository.apply_institution_payment_to_installment(payment_id='partial', installment_id='plan:msi-1', amount_cents=50000)
    forecast = period_forecast(repository, ['card'], date(2026,10,1))
    assert forecast['current_cents']==100000 and forecast['future_cents']==1100000
    assert forecast['pending_identified_cents']==50000 and forecast['payments_applied_cents']==50000
    assert forecast['unassigned_payments_cents']==0
    november = period_forecast(repository, ['card'], date(2026,11,1))
    assert november['confirmed_overdue_cents']==0 and november['previous_unconfirmed_cents']==50000


def test_normal_orders_use_purchase_calendar_not_residual_total(repository):
    calendar(repository)
    purchase(repository, dates=twelve_dates())
    purchase(repository, key='normal-current', amount=20000, purchased='2026-09-01')
    purchase(repository, key='normal-old', amount=30000, purchased='2026-08-01')
    purchase(repository, key='normal-future', amount=40000, purchased='2026-10-21')
    account = repository.list_bank_comparisons(as_of=date(2026,10,1))[0]
    forecast = account['monthly_forecast']
    assert account['calculated_cents']==1290000
    assert forecast['current_cents']==120000
    assert forecast['future_cents']==1140000
    assert forecast['previous_unconfirmed_cents']==30000
    # Before, the old normal purchase was silently charged to this month too.
    assert account['calculated_cents']-1100000==190000
    assert account['current_month_cents']==120000
    purchase(repository, key='msi-second', amount=20000, dates=('2026-10-15','2026-11-15'))
    assert period_forecast(repository, ['card'], date(2026,10,1))['current_cents']==130000
    assert normal_due(repository.database.connection, 'card', '2026-12-21')=='2027-02-10'


def test_missing_calendar_never_assigns_normal_purchase_to_this_month(repository):
    purchase(repository, key='normal', amount=20000)
    forecast = period_forecast(repository, ['card'], date(2026,10,1))
    assert forecast['current_cents']==forecast['future_cents']==0
    assert forecast['undated_cents']==20000 and forecast['warnings']
    from valenza.gui.bank_reconciliation import scheduled_text
    assert scheduled_text(forecast,lambda value:str(value))=='Por configurar'


@pytest.mark.parametrize('kind', ['NO_INTEREST','MINIMUM','OTHER','MONTHLY','STATEMENT'])
def test_monthly_query_saves_concept_period_and_immutable_forecast(repository, kind):
    purchase(repository, dates=twelve_dates())
    before = financial_snapshot(repository)
    repository.record_bank_balance('card',100000,datetime.now().astimezone().isoformat(),
                                   balance_type=kind,period='2026-10',balance_label='Saldo personalizado')
    query = repository.list_bank_reconciliation_history()[0]
    assert query['period']=='2026-10' and query['monthly_forecast']['current_cents']==100000
    assert query['balance_type']==kind and not query['comparable'] and query['difference_cents'] is None
    assert financial_snapshot(repository)==before
    saved = json.dumps(query, sort_keys=True)
    repository.record_institution_payment(payment_id='later', instrument_id='card', amount_cents=100000, paid_at='2026-10-15')
    assert json.dumps(repository.list_bank_reconciliation_history()[0],sort_keys=True)==saved


def test_other_requires_identification_and_period_must_be_valid(repository):
    for args in (dict(balance_type='OTHER'),dict(period='2026-13')):
        changes=repository.database.connection.total_changes
        with pytest.raises(ValueError):
            repository.record_bank_balance('card',0,datetime.now().astimezone().isoformat(),**args)
        assert repository.database.connection.total_changes==changes


def test_guided_month_ui_privacy_keyboard_and_period_selection(repository, tmp_path):
    purchase(repository, dates=twelve_dates())
    app=create_application([])
    before=financial_snapshot(repository)
    window=MainWindow(database=repository.database,test_mode=True)
    window.resize(900,700); window.show(); app.processEvents()
    window.dashboard_period_picker.setDate(QDate(2026,10,1))
    amount=lambda widget:widget.findChild(QLabel,'summaryAmount').text()
    assert amount(window.dashboard_debt)=='$1,000.00 MXN'
    assert amount(window.dashboard_msi)=='$12,000.00 MXN'
    assert '$11,000.00 MXN' in window.dashboard_monthly_installments.text()
    assert window.dashboard_period_picker.date().toString('yyyy-MM') == '2026-10'
    window.grab().save(str(tmp_path/'inicio.png'))
    window.dashboard_result_toggle.setFocus(); QTest.keyClick(window.dashboard_result_toggle,Qt.Key.Key_Space)
    assert '$' not in window.dashboard_result_details.toPlainText()
    window._show_page(window.PAGES.index('Tarjetas'))
    window.cards_table.selectRow(0); window.card_panels['bank'][0].setChecked(True)
    assert window.bank_query_type.currentData()=='NO_INTEREST'
    window.bank_query_type.setFocus()
    QTest.keyClick(window.bank_query_type,Qt.Key.Key_Tab)
    assert window.bank_query_amount.hasFocus()
    window.bank_query_amount.setText('1000.00')
    assert 'Referencia oficial introducida manualmente' in window.bank_query_feedback.text()
    assert 'Los saldos coinciden' not in window.bank_query_feedback.text()
    app.processEvents()
    window.cards_scroll.ensureWidgetVisible(window.bank_query_save)
    window.grab().save(str(tmp_path/'comprobar.png'))
    window.bank_closing_date.setText('2026-10-10')
    window.bank_due_date.setText('2026-10-20')
    window.bank_query_save.setFocus(); QTest.keyClick(window.bank_query_save,Qt.Key.Key_Space)
    assert repository.list_bank_reconciliation_history()[0]['period']=='2026-10'
    assert financial_snapshot(repository)==before
    window.bank_query_type.setCurrentIndex(window.bank_query_type.findData('TOTAL'))
    window.bank_total_confirmed.setChecked(True)
    today=date.today()
    window.bank_period_picker.setDate(QDate(today.year,today.month,1))
    window.bank_query_amount.setText('12000.00')
    assert 'Los saldos coinciden' in window.bank_query_feedback.text()
    window.bank_period_picker.setDate(QDate(2027,1,1))
    assert window.dashboard_period_picker.date()==QDate(2027,1,1)
    assert '$8,000.00 MXN' in window.bank_breakdown.text()
    assert 'Ene 2027' in window.bank_query_comparison.text()
    assert 'Programado antes de pagos: $1,000.00 MXN' in window.bank_query_comparison.text()
    window.close()
