from datetime import date, datetime
import json

import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from test_product_refunds import repository, purchase_args, repurchase_proposal
from test_bank_period_experience import calendar, purchase, twelve_dates
from test_bank_reconciliation import financial_snapshot
from valenza.gui.app import MainWindow, create_application, format_money
from valenza.gui.home_month_summary import home_month_summary
from valenza.gui.bank_reconciliation import query_text, monthly_comparison_text, official_period_query


def forecast(repo, period='2026-10'):
    return repo.list_bank_comparisons(as_of=date.fromisoformat(period+'-01'))[0]['monthly_forecast']


def seed(repo):
    calendar(repo)
    purchase(repo, dates=twelve_dates())
    purchase(repo,key='normal',amount=150000,purchased='2026-09-05')


@pytest.mark.parametrize('paid_at', ['2026-09-15','2026-10-25'])
def test_scheduled_not_reduced_by_payments_before_or_after_cut(repository,paid_at):
    seed(repository)
    repository.record_institution_payment(payment_id='bank',instrument_id='card',amount_cents=40000,paid_at=paid_at)
    repository.apply_institution_payment_to_installment(payment_id='bank',installment_id='plan:msi-1',amount_cents=40000)
    before=financial_snapshot(repository)
    f=forecast(repository)
    assert f['scheduled_cents']==250000  # Before: 210000 after partial application.
    assert f['payments_applied_cents']==40000 and f['pending_identified_cents']==210000
    assert f['msi_future_cents']==1100000
    september=forecast(repository,'2026-09')
    assert september['current_cents']==0 and september['msi_future_cents']==1200000
    assert september['future_pending_cents']==1310000  # MSI 1160000 + normal 150000, known now.
    assert financial_snapshot(repository)==before


def test_missing_calendar_no_invented_month_and_unassigned_payment_incomplete(repository):
    purchase(repository,dates=twelve_dates())
    purchase(repository,key='normal',amount=150000,purchased='2026-09-05')
    repository.record_institution_payment(payment_id='bank',instrument_id='card',amount_cents=40000,paid_at='2026-10-15')
    f=forecast(repository)
    assert f['scheduled_cents']==100000 and f['undated_cents']==150000
    assert f['payments_applied_cents']==0 and f['pending_identified_cents']==100000
    assert not f['pending_complete'] and f['unassigned_payments_cents']==40000
    assert any('configurar' in w for w in f['warnings'])


@pytest.mark.parametrize('destination',['card','wallet'])
def test_discount_and_refund_only_change_own_bank_total_not_scheduled(repository,destination):
    calendar(repository)
    repository.create_order(**purchase_args(destination=destination))
    before=financial_snapshot(repository)
    f=forecast(repository,'2026-11')
    assert f['scheduled_cents']==54258 and f['breakdown']['NORMAL']==54258
    assert f['credits_applied_cents']==0  # No monthly credit application exists; do not invent it.
    assert f['pending_identified_cents']==54258
    assert f['pending_complete']==(destination=='wallet')
    card=next(c for c in repository.list_card_summaries() if c['instrument_id']=='card')
    assert card['remaining_cents']==(35601 if destination=='card' else 54258)
    assert financial_snapshot(repository)==before


def test_pending_refund_and_wallet_repurchase_preserve_financial_sources(repository):
    calendar(repository)
    repository.create_order(**purchase_args(status='PENDING',destination='wallet'))
    f=forecast(repository,'2026-11')
    assert f['scheduled_cents']==54258 and f['credits_applied_cents']==0
    # Separate isolated case for accredited Wallet replacement.
    refund=repository.list_product_refunds('order')[0]
    repository.confirm_product_refund(refund['id'],accredited_at='2026-10-10')
    repository.register_refund_repurchase(refund['id'],repurchase_proposal())
    before=financial_snapshot(repository)
    assert forecast(repository,'2026-11')['scheduled_cents']==54258
    assert next(c for c in repository.list_card_summaries() if c['instrument_id']=='wallet')['wallet_balance_cents']==5658
    assert financial_snapshot(repository)==before


def test_year_rollover_and_interest_not_duplicated(repository):
    calendar(repository)
    purchase(repository,dates=twelve_dates(start=13))
    purchase(repository,key='normal',amount=150000,purchased='2026-12-05')
    assert forecast(repository,'2026-12')['scheduled_cents']==0
    assert forecast(repository,'2027-01')['scheduled_cents']==250000
    assert forecast(repository,'2027-01')['msi_future_cents']==1100000
    assert forecast(repository,'2027-02')['confirmed_overdue_cents']==100000


def test_financing_interest_once_and_dated_extra_fee(repository):
    calendar(repository)
    repository.create_order(order_id='interest',ordered_at='2026-09-05',merchant='Sintético',instrument_id='card',
                            original_cents=120000,discount_cents=0,charged_cents=120000,
                            allocations=({'user_id':'owner','amount_cents':120000},),purchase_mode='MSI',
                            financing_specs=twelve_dates(),interest_cents=1200)
    repository.add_institution_movement('fee','card','2026-09-05','COMMISSION',1000,'Comisión sintética')
    f=forecast(repository)
    assert f['scheduled_cents']==11100 and f['breakdown']==dict(NORMAL=0,MSI=10100,OTHER=1000)
    assert repository.list_bank_comparisons()[0]['calculated_cents']==122200


def test_old_schema2_snapshot_not_recalculated_and_new_official_snapshot_frozen(repository):
    seed(repository)
    now=datetime.now().astimezone().isoformat(timespec='seconds')
    old=dict(schema=2,account_id='card',members=['card'],amount_cents=210000,calculated_cents=1310000,
             difference_cents=None,consulted_at=now,recorded_at=now,balance_type='NO_INTEREST',comparable=False,
             warnings=['Fotografía sintética anterior'],components=[],currency='MXN',period='2026-10',balance_label='',
             monthly_forecast=dict(current_cents=210000))
    with repository.database.transaction() as conn:
        repository._insert_person_audit(conn,'card','BANK_BALANCE_QUERIED','synthetic',None,old,entity_type='instrument')
    original_raw=[tuple(r) for r in repository.database.connection.execute("SELECT * FROM audit_event WHERE action='BANK_BALANCE_QUERIED'")]
    old_view=repository.list_bank_reconciliation_history()[0]
    old_text=query_text(old_view,format_money)
    assert 'Calendario Valenza al guardar: $2,100.00 MXN' in old_text
    repository.record_bank_balance('card',240000,now,balance_type='NO_INTEREST',period='2026-10')
    saved=next(q for q in repository.list_bank_reconciliation_history() if q['schema']==4)
    assert saved['orientative_difference_cents'] is None and saved['difference_cents'] is None
    assert saved['monthly_forecast']['scheduled_cents']==250000
    frozen=json.dumps(saved,sort_keys=True)
    repository.record_institution_payment(payment_id='later',instrument_id='card',amount_cents=10000,paid_at='2026-11-01')
    assert json.dumps(next(q for q in repository.list_bank_reconciliation_history() if q['schema']==4),sort_keys=True)==frozen
    assert query_text(next(q for q in repository.list_bank_reconciliation_history() if q['schema']==2),format_money)==old_text
    raw=[tuple(r) for r in repository.database.connection.execute("SELECT * FROM audit_event WHERE action='BANK_BALANCE_QUERIED' ORDER BY rowid LIMIT 1")]
    assert raw==original_raw


def test_minimum_not_compared_and_official_same_period_scope_only(repository):
    seed(repository)
    f=forecast(repository)
    minimum=monthly_comparison_text(f,5000,'MINIMUM',format_money)
    assert 'No se calcula una diferencia' in minimum and '$2,500' not in minimum
    oriented=monthly_comparison_text(f,250000,'NO_INTEREST',format_money)
    assert 'Referencia oficial introducida manualmente' in oriented and 'Los saldos coinciden' not in oriented
    now=datetime.now().astimezone().isoformat(timespec='seconds')
    repository.record_bank_balance('card',240000,now,balance_type='NO_INTEREST',period='2026-10')
    history=repository.list_bank_reconciliation_history()
    account=repository.list_bank_comparisons()[0]
    assert official_period_query(history,account,'2026-10')['amount_cents']==240000
    assert official_period_query(history,account,'2026-11') is None
    changed=dict(account,members=['card','different'])
    assert official_period_query(history,changed,'2026-10') is None


def test_home_original_and_cards_forecast_keep_manual_bank_reference(repository,tmp_path):
    seed(repository)
    now=datetime.now().astimezone().isoformat(timespec='seconds')
    repository.record_bank_balance('card',240000,now,balance_type='NO_INTEREST',period='2026-10')
    before=financial_snapshot(repository)
    app=create_application([])
    window=MainWindow(database=repository.database,test_mode=True)
    window.resize(900,700); window.show(); app.processEvents()
    window.dashboard_period_picker.setDate(QDate(2026,10,1))
    assert window.dashboard_debt.findChild(QLabel,'summaryAmount').text()=='$2,500.00 MXN'
    assert 'Lo que pide el banco: $2,400.00 MXN' in window.dashboard_month_accounts.text()
    assert 'Pago para no generar intereses' in window.dashboard_month_accounts.text()
    window.grab().save(str(tmp_path/'inicio-previsto.png'))
    window._show_page(window.PAGES.index('Tarjetas'))
    row=next(r for r in range(window.cards_table.rowCount()) if window.cards_table.item(r,12).text()=='card')
    window.cards_table.selectRow(row); window.card_panels['bank'][0].setChecked(True)
    assert window.card_summary_cards[1].findChild(QLabel,'summaryAmount').text()=='$2,500.00 MXN'
    window.bank_query_amount.setText('2400.00')
    assert 'Referencia oficial introducida manualmente' in window.bank_query_feedback.text()
    window.bank_query_type.setFocus(); QTest.keyClick(window.bank_query_type,Qt.Key.Key_Tab)
    assert window.bank_query_amount.hasFocus()
    window.bank_query_type.setCurrentIndex(window.bank_query_type.findData('MINIMUM'))
    assert 'No se calcula una diferencia' in window.bank_query_feedback.text()
    window.bank_period_picker.setDate(QDate(2026,11,1))
    assert 'Lo que pide el banco' not in window.dashboard_month_accounts.text()
    assert window.dashboard_debt.findChild(QLabel,'summaryAmount').text()=='$2,500.00 MXN'
    assert window.card_summary_cards[1].findChild(QLabel,'summaryAmount').text()=='$1,000.00 MXN'
    assert financial_snapshot(repository)==before
    window.close(); app.processEvents()


def test_cards_partial_forecast_preserved_while_home_initial_total_is_restored(repository):
    # Without any configured calendar, only MSI can be dated.
    purchase(repository,dates=twelve_dates())
    purchase(repository,key='normal',amount=150000,purchased='2026-09-05')
    before=financial_snapshot(repository)
    f=forecast(repository)
    assert f['scheduled_cents']==100000 and f['undated_cents']==150000
    app=create_application([])
    window=MainWindow(database=repository.database,test_mode=True)
    window.dashboard_period_picker.setDate(QDate(2026,10,1))
    assert window.dashboard_debt.findChild(QLabel,'summaryAmount').text()=='$2,500.00 MXN'
    assert 'No sustituye el pago informado por el banco' in window.dashboard_period_note.text()
    window._show_page(window.PAGES.index('Tarjetas'))
    row=next(r for r in range(window.cards_table.rowCount()) if window.cards_table.item(r,12).text()=='card')
    window.cards_table.selectRow(row)
    assert window.card_summary_cards[1].findChild(QLabel,'summaryAmount').text()=='Total sin determinar'
    assert financial_snapshot(repository)==before
    window.close(); app.processEvents()


def test_current_configured_rules_estimate_older_normal_purchase_without_reconfirmation(repository):
    purchase(repository,dates=twelve_dates())
    purchase(repository,key='normal',amount=150000,purchased='2026-09-05')
    repository.save_instrument_calendar(calendar_id='late-calendar',instrument_id='card',
        effective_from='2026-10-01',closing_day=20,due_day=10)
    before=financial_snapshot(repository)
    f=forecast(repository)
    assert f['scheduled_cents']==250000
    assert f['undated_cents']==0
    assert f['breakdown']==dict(NORMAL=150000,MSI=100000,OTHER=0)
    assert financial_snapshot(repository)==before
    assert repository.database.connection.execute("SELECT effective_from FROM instrument_calendar WHERE id='late-calendar'").fetchone()[0]=='2026-10-01'
