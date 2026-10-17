from datetime import date

import pytest
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QLabel

from test_product_refunds import repository
from test_bank_reconciliation import financial_snapshot
from test_bank_period_experience import purchase, twelve_dates, calendar
from valenza.gui.app import MainWindow, create_application
from valenza.gui.home_month_summary import home_month_summary


def summary(repo, period='2026-10'):
    as_of=date.fromisoformat(period+'-01')
    return home_month_summary(repo,repo.list_bank_comparisons(as_of=as_of),as_of)


def test_home_normal_october_plus_msi_without_changing_bank_forecast(repository):
    calendar(repository)
    purchase(repository, dates=twelve_dates())
    purchase(repository,key='normal',amount=150000,purchased='2026-09-05')
    before=financial_snapshot(repository)
    comparisons=repository.list_bank_comparisons(as_of=date(2026,10,1))
    assert comparisons[0]['current_month_cents']==250000
    result=summary(repository)
    assert result['current_cents']==250000
    assert result['debt_cents']==1350000
    assert result['future_cents']==1100000
    assert comparisons[0]['calculated_cents']==1350000
    assert financial_snapshot(repository)==before


def test_home_original_residual_independent_of_cards_due_forecast(repository):
    calendar(repository)
    purchase(repository,key='normal',amount=150000,purchased='2026-10-25')
    before=financial_snapshot(repository)
    assert repository.list_bank_comparisons(as_of=date(2026,10,1))[0]['current_month_cents']==0
    assert summary(repository)['current_cents']==150000
    assert summary(repository,'2026-12')['current_cents']==150000
    assert summary(repository,'2026-12')['overdue_cents']==0
    assert financial_snapshot(repository)==before


@pytest.mark.parametrize('applied,expected',[(False,200000),(True,200000)])
def test_partial_bank_payment_only_reduces_month_with_recorded_application(repository,applied,expected):
    calendar(repository)
    purchase(repository,dates=twelve_dates())
    purchase(repository,key='normal',amount=150000,purchased='2026-09-05')
    repository.record_institution_payment(payment_id='partial',instrument_id='card',amount_cents=50000,paid_at='2026-10-15')
    if applied:
        repository.apply_institution_payment_to_installment(payment_id='partial',installment_id='plan:msi-1',amount_cents=50000)
    before=financial_snapshot(repository)
    result=summary(repository)
    assert result['current_cents']==expected and result['future_cents']==1100000
    assert repository.list_bank_comparisons()[0]['calculated_cents']==1300000
    assert financial_snapshot(repository)==before


def test_actual_charges_previous_and_future_periods_no_import_double_count(repository):
    calendar(repository)
    purchase(repository,dates=twelve_dates())
    purchase(repository,key='normal',amount=150000,purchased='2026-09-05')
    for key,kind,amount,posted in [('fee','COMMISSION',10000,'2026-09-05'),('interest','INTEREST',2000,'2026-09-10'),
                                   ('future','ADJUSTMENT',3000,'2026-10-01'),('import','CHARGE',150000,'2026-09-05')]:
        repository.add_institution_movement(movement_id=key,instrument_id='card',kind=kind,amount_cents=amount,
                                            posted_at=posted,description='Cargo sintético')
    before=financial_snapshot(repository)
    october=summary(repository)
    assert october['current_cents']==265000  # Original residual includes all recorded net bank charges.
    assert october['future_cents']==1100000
    november=summary(repository,'2026-11')
    assert november['current_cents']==265000
    assert november['overdue_cents']==100000
    assert financial_snapshot(repository)==before


def test_home_indicator_and_breakdown_match_example(repository):
    calendar(repository)
    purchase(repository,dates=twelve_dates())
    purchase(repository,key='normal',amount=150000,purchased='2026-09-05')
    before=financial_snapshot(repository)
    app=create_application([])
    window=MainWindow(database=repository.database,test_mode=True)
    window.dashboard_period_picker.setDate(QDate(2026,10,1))
    assert window.dashboard_debt.findChild(QLabel,'summaryAmount').text()=='$2,500.00 MXN'
    assert window.dashboard_msi.findChild(QLabel,'summaryAmount').text()=='$13,500.00 MXN'
    text=window.dashboard_month_accounts.text()
    assert '$2,500.00 MXN' in text
    assert 'No sustituye el pago informado por el banco' in window.dashboard_period_note.text()
    assert 'MSI futuros separados: $11,000.00 MXN' in window.dashboard_monthly_installments.text()
    assert window.dashboard_month_commitments==250000
    assert financial_snapshot(repository)==before
    window.close(); app.processEvents()


def test_shared_line_reads_sources_once_and_ignores_noncredit_orders(repository):
    calendar(repository)
    purchase(repository,dates=twelve_dates())
    purchase(repository,key='normal',amount=150000,purchased='2026-09-05')
    repository.add_instrument('second','bank','Adicional sintética','CREDIT_CARD')
    repository.set_bank_reconciliation_scope('second','card')
    repository.create_order(order_id='cash',ordered_at='2026-10-05',merchant='Wallet sintética',instrument_id='wallet',
                            original_cents=90000,charged_cents=90000,discount_cents=0,
                            allocations=({'user_id':'owner','amount_cents':90000},))
    before=financial_snapshot(repository)
    assert summary(repository)['current_cents']==250000
    assert financial_snapshot(repository)==before
