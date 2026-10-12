from datetime import date
import pytest
from PySide6.QtWidgets import QLabel
import valenza.persistence.repository as repository_module
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository
from valenza.gui.app import MainWindow, create_application


@pytest.fixture
def monthly_repo(monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026,10,11)
    monkeypatch.setattr(repository_module,'date',FixedDate)
    db=LocalDatabase.open(':memory:','synthetic',allow_synthetic_in_memory=True)
    db.migrate()
    repo=FinanceRepository(db)
    repo.add_person('owner','Yo',is_owner=True)
    repo.add_person('joaquin','JOAQUÍN')
    repo.add_institution('nu','NuBank sintético')
    repo.add_instrument('card','nu','Tarjeta sintética','CREDIT_CARD')
    yield repo
    db.close()


def create_plan(repo,dates=('2026-10-11','2026-11-11','2026-12-11')):
    repo.create_order(order_id='plant',ordered_at='2026-10-11',merchant='MERCADO LIBRE',instrument_id='card',
        original_cents=142398,charged_cents=142398,discount_cents=0,
        allocations=({'user_id':'owner','amount_cents':0},{'user_id':'joaquin','amount_cents':142398}),
        purchase_mode='MSI',financing_specs=dates)


def test_cards_and_home_month_sum_one_installment_not_three(monthly_repo):
    app=create_application([])
    repo=monthly_repo
    create_plan(repo)
    card=repo.list_card_summaries()[0]
    assert card['remaining_cents']==142398
    assert card['scheduled_month_cents']==47466
    assert card['scheduled_future_cents']==94932
    assert card['scheduled_overdue_cents']==card['scheduled_undated_cents']==0
    # Explicit dates are shown as forecasts even without a confirmed bank calendar.
    assert card['pending_confirmation_cents']==142398
    before=repo.database.connection.total_changes
    window=MainWindow(database=repo.database)
    window._show_page(MainWindow.PAGES.index('Tarjetas'))
    window.cards_table.selectRow(0)
    assert window.cards_table.item(0,4).text()=='$1,423.98 MXN'
    assert window.cards_table.item(0,5).text()=='$474.66 MXN'
    assert window.cards_table.item(0,6).text()=='$949.32 MXN'
    assert 'este mes: $474.66 MXN' in window.card_detail.text()
    assert 'MSI por pagar hasta hoy: Por confirmar' in window.card_detail.text()
    assert 'MSI por pagar hasta hoy: $0.00' not in window.card_detail.text()
    window._show_page(MainWindow.PAGES.index('Inicio'))
    assert 'este mes: $474.66 MXN' in window.dashboard_monthly_installments.text()
    assert 'Meses futuros' not in window.dashboard_monthly_installments.text()
    assert 'Meses anteriores' not in window.dashboard_monthly_installments.text()
    assert 'Sin fecha' not in window.dashboard_monthly_installments.text()
    assert '$474.66 MXN' in window.dashboard_cards_total.text()
    assert window.dashboard_cards.item(0, 1).text() == '$474.66 MXN'
    assert window.dashboard_debt.findChild(QLabel, 'summaryAmount').text() == '$474.66 MXN'
    assert repo.database.connection.total_changes==before
    assert len(repo.list_orders())==1
    window.close()
    app.processEvents()


def test_family_receipt_does_not_pay_bank_but_applied_bank_payment_reduces_month(monthly_repo):
    repo=monthly_repo
    create_plan(repo)
    repo.record_receipt(payment_id='family',receivable_id='order:plant:joaquin',amount_cents=47466,received_at='2026-10-11')
    family_month = repo.collection_monthly_summaries()['order:plant:joaquin']
    assert family_month['current_cents'] == 0
    assert family_month['future_cents'] == family_month['total_cents'] == 94932
    assert repo.dashboard_summary()['scheduled_month_cents']==47466
    assert repo.dashboard_summary()['institutional_balance_cents']==142398
    repo.record_institution_payment(payment_id='bank-payment',instrument_id='card',paid_at='2026-10-11',amount_cents=47466)
    repo.apply_institution_payment_to_installment(payment_id='bank-payment',installment_id='plan:plant-1',amount_cents=47466)
    summary=repo.dashboard_summary()
    assert summary['scheduled_month_cents']==0
    assert summary['scheduled_future_cents']==summary['institutional_balance_cents']==94932


def test_missing_dates_are_not_assigned_to_current_month(monthly_repo):
    create_plan(monthly_repo,dates=(None,None,None))
    summary=monthly_repo.dashboard_summary()
    assert summary['scheduled_month_cents']==summary['scheduled_future_cents']==0
    assert summary['scheduled_undated_cents']==142398
    family_month = monthly_repo.collection_monthly_summaries()['order:plant:joaquin']
    assert family_month['current_cents'] == family_month['future_cents'] == 0
    assert family_month['undated_cents'] == family_month['total_cents'] == 142398


def test_future_first_due_date_does_not_charge_this_month(monthly_repo):
    create_plan(monthly_repo,dates=('2026-11-11','2026-12-11','2027-01-11'))
    summary=monthly_repo.dashboard_summary()
    assert summary['scheduled_month_cents']==0
    assert summary['scheduled_future_cents']==summary['institutional_balance_cents']==142398


def test_sum_two_plans_keeps_month_and_total_separate(monthly_repo):
    create_plan(monthly_repo)
    monthly_repo.create_order(order_id='second', ordered_at='2026-10-11',
        merchant='Otro plan sintético', instrument_id='card', original_cents=30000,
        charged_cents=30000, discount_cents=0,
        allocations=({'user_id':'owner','amount_cents':0}, {'user_id':'joaquin','amount_cents':30000}),
        purchase_mode='MSI', financing_specs=('2026-10-11','2026-11-11','2026-12-11'))
    summary = monthly_repo.dashboard_summary()
    assert summary['scheduled_month_cents'] == 57466
    assert summary['scheduled_future_cents'] == 114932
    assert summary['institutional_balance_cents'] == summary['receivables_cents'] == 172398
    collections = monthly_repo.collection_monthly_summaries().values()
    assert sum(item['current_cents'] for item in collections) == 57466
    assert sum(item['future_cents'] for item in collections) == 114932
    assert sum(item['total_cents'] for item in collections) == 172398


def test_month_rollover_separates_unpaid_previous_month(monkeypatch,monthly_repo):
    create_plan(monthly_repo)
    class NovemberDate(date):
        @classmethod
        def today(cls):
            return cls(2026,11,11)
    monkeypatch.setattr(repository_module,'date',NovemberDate)
    summary=monthly_repo.dashboard_summary()
    assert summary['scheduled_month_cents']==47466
    assert summary['scheduled_overdue_cents']==47466
    assert summary['scheduled_future_cents']==47466
    assert summary['institutional_balance_cents']==142398
