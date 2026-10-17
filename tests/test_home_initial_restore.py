"""Regression against the exact Home calculation present in Git at session start."""
from datetime import date, datetime
import subprocess
import sys
import types
from pathlib import Path

import pytest
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QLabel

from test_product_refunds import repository
from test_bank_period_experience import purchase, twelve_dates
from valenza.gui.app import MainWindow, create_application
from valenza.gui.home_month_summary import home_month_summary
import valenza.persistence.repository as repository_module


def tables(repo):
    conn=repo.database.connection
    names=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {name:[tuple(row) for row in conn.execute('SELECT * FROM "'+name+'" ORDER BY rowid')] for name in names}


@pytest.fixture
def initial_repository(monkeypatch):
    # Read Git into memory only; no checkout/reset or application data changes.
    root = Path(__file__).resolve().parents[1]
    source=subprocess.run(['git','-c',f'safe.directory={root.as_posix()}',
        'show','4dc28a9:src/valenza/persistence/repository.py'],cwd=root,check=True,capture_output=True).stdout.decode('utf-8')
    module=types.ModuleType('valenza.persistence._initial_home_regression')
    module.__package__='valenza.persistence'
    monkeypatch.setitem(sys.modules,module.__name__,module)
    exec(compile(source,'<initial repository from Git>','exec'),module.__dict__)
    class October(date):
        @classmethod
        def today(cls):
            return cls(2026,10,15)
    monkeypatch.setattr(module,'date',October)
    monkeypatch.setattr(repository_module,'date',October)
    return module.FinanceRepository


def seed(repo):
    assert repo.database.encrypted
    purchase(repo,dates=twelve_dates())
    purchase(repo,key='normal',amount=150000,purchased='2026-09-05')


def restored(repo):
    return home_month_summary(repo,repo.list_bank_comparisons(as_of=date(2026,10,1)),date(2026,10,1))


def test_original_2500_regressed_1000_normal_restored_and_total_unchanged(repository,initial_repository):
    seed(repository)
    original=sum(a['current_month_cents'] for a in initial_repository(repository.database).list_bank_comparisons())
    later=repository.list_bank_comparisons(as_of=date(2026,10,1))[0]
    assert original==250000
    assert later['current_month_cents']==100000  # The newer due forecast excluded the normal purchase.
    assert later['calculated_cents']==1350000
    before=tables(repository)
    changes=repository.database.connection.total_changes
    result=restored(repository)
    assert result['current_cents']==original
    assert result['future_cents']==1100000
    assert tables(repository)==before and repository.database.connection.total_changes==changes
    assert repository.list_bank_comparisons(as_of=date(2026,10,1))==[later]


@pytest.mark.parametrize('application,amount,expected',[
    (None,40000,210000), ('plan:msi-1',40000,210000),
    ('plan:msi-2',40000,250000), (None,1500000,0),
])
def test_payment_handling_identical_to_git_initial(repository,initial_repository,application,amount,expected):
    seed(repository)
    repository.record_institution_payment(payment_id='bank',instrument_id='card',paid_at='2026-10-15',amount_cents=amount)
    if application:
        repository.apply_institution_payment_to_installment(payment_id='bank',installment_id=application,amount_cents=amount)
    before=tables(repository)
    original=sum(a['current_month_cents'] for a in initial_repository(repository.database).list_bank_comparisons())
    assert original==expected
    assert restored(repository)['current_cents']==original
    assert tables(repository)==before


def test_previous_undated_and_per_instrument_clamp_preserved_in_shared_line(repository,initial_repository):
    seed(repository)
    purchase(repository,key='old',amount=6000,purchased='2026-08-01',dates=('2026-09-15',))
    purchase(repository,key='undated',amount=120000,dates=(None,None))
    repository.add_instrument('second','bank','Adicional sintética','CREDIT_CARD')
    repository.create_order(order_id='future',ordered_at='2026-09-05',merchant='MSI futuro sintético',instrument_id='second',
                            original_cents=500000,discount_cents=0,charged_cents=500000,
                            allocations=({'user_id':'owner','amount_cents':500000},),purchase_mode='MSI',financing_specs=('2026-11-15',))
    repository.record_institution_payment(payment_id='second-payment',instrument_id='second',paid_at='2026-10-15',amount_cents=100000)
    repository.set_bank_reconciliation_scope('second','card')
    before=tables(repository)
    original=sum(a['current_month_cents'] for a in initial_repository(repository.database).list_bank_comparisons())
    assert original==250000
    result=restored(repository)
    assert result['current_cents']==original
    assert result['overdue_cents']==6000 and result['undated_cents']==120000
    assert tables(repository)==before


def test_home_uses_original_amount_preserves_cards_privacy_and_query_history(repository,initial_repository):
    seed(repository)
    repository.record_bank_balance('card',240000,datetime.now().astimezone().isoformat(timespec='seconds'),
                                   balance_type='NO_INTEREST',period='2026-10')
    before=tables(repository)
    comparisons=repository.list_bank_comparisons(as_of=date(2026,10,1))
    app=create_application([])
    window=MainWindow(database=repository.database,test_mode=True)
    window.dashboard_period_picker.setDate(QDate(2026,10,1))
    assert window.dashboard_debt.findChild(QLabel,'summaryAmount').text()=='$2,500.00 MXN'
    assert window.dashboard_msi.findChild(QLabel,'summaryAmount').text()=='$13,500.00 MXN'
    assert window.dashboard_month_commitments==250000
    assert 'Lo que pide el banco: $2,400.00 MXN' in window.dashboard_month_accounts.text()
    assert window.dashboard_bar_chart.values[0]==('2026-10',250000)
    assert not window.dashboard_privacy.isChecked()
    window.dashboard_result_toggle.click()
    assert '$' not in window.dashboard_result_details.toPlainText()
    window._show_page(window.PAGES.index('Tarjetas'))
    row=next(r for r in range(window.cards_table.rowCount()) if window.cards_table.item(r,12).text()=='card')
    window.cards_table.selectRow(row)
    assert window.card_summary_cards[1].findChild(QLabel,'summaryAmount').text()=='Total sin determinar'
    assert repository.list_bank_comparisons(as_of=date(2026,10,1))==comparisons
    assert tables(repository)==before
    window.close(); app.processEvents()


@pytest.mark.parametrize('future_payment',[0,40000])
def test_future_chart_only_pending_msi_not_normal_purchases_or_other_charges(repository,initial_repository,future_payment):
    seed(repository)
    repository.save_instrument_calendar(calendar_id='calendar',instrument_id='card',
        effective_from='2026-01-01',closing_day=20,due_day=10)
    purchase(repository,key='large-normal',amount=5000000,purchased='2026-10-05')
    repository.add_institution_movement('fee','card','2026-10-05','COMMISSION',10000,'Comisión sintética')
    if future_payment:
        repository.record_institution_payment(payment_id='future-payment',instrument_id='card',paid_at='2026-10-15',amount_cents=future_payment)
        repository.apply_institution_payment_to_installment(payment_id='future-payment',installment_id='plan:msi-2',amount_cents=future_payment)
    before=tables(repository)
    app=create_application([])
    window=MainWindow(database=repository.database,test_mode=True)
    window.dashboard_period_picker.setDate(QDate(2026,10,1))
    bars=dict(window.dashboard_bar_chart.values)
    assert bars['2026-11']==100000-future_payment
    assert bars['2026-12']==100000
    original=sum(a['current_month_cents'] for a in initial_repository(repository.database).list_bank_comparisons())
    assert bars['2026-10']==window.dashboard_month_commitments==original
    assert tables(repository)==before
    window.close(); app.processEvents()
