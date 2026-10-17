import pytest
from PySide6.QtGui import QFont,QFontDatabase
from test_product_refunds import repository,create_discount_comparison_case,purchase_args
from valenza.persistence.database import LocalDatabase,SCHEMA_VERSION
from valenza.persistence.repository import FinanceRepository
from valenza.gui.app import MainWindow,create_application,format_money
from valenza.gui.bank_reconciliation import difference_text

from datetime import datetime
CONSULTED=datetime.now().astimezone().isoformat(timespec='seconds')


def financial_snapshot(repo):
    connection=repo.database.connection
    tables=[r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='audit_event' ORDER BY name")]
    return {name:[tuple(r) for r in connection.execute('SELECT * FROM "'+name+'" ORDER BY rowid')] for name in tables}


def account(repo,key='card'):
    return next(a for a in repo.list_bank_comparisons() if a['account_id']==key)


def order(repo,key,instrument='card',charged=5000):
    repo.create_order(order_id=key,ordered_at='2026-10-13',merchant='Compra sintética '+key,
        instrument_id=instrument,original_cents=charged,discount_cents=0,charged_cents=charged,
        allocations=({'user_id':'owner','amount_cents':charged},))


@pytest.mark.parametrize('delta',[0,1234,-1234])
def test_total_snapshot_and_direction_without_financial_writes(repository,delta):
    create_discount_comparison_case(repository)
    before=financial_snapshot(repository)
    summary=repository.list_card_summaries(include_inactive=True)
    repository.record_bank_balance('card',54258+delta,CONSULTED)
    query=repository.list_bank_reconciliation_history('card')[0]
    assert query['calculated_cents']==54258 and query['difference_cents']==delta
    assert query['consulted_at']==CONSULTED and query['balance_type']=='TOTAL'
    assert query['components'][0]['order_charges_cents']==54258
    assert query['components'][0]['bank_payments_cents']==0
    assert query['comparable']
    assert difference_text(delta,format_money).startswith('Coincide' if not delta else 'El banco muestra más' if delta>0 else 'Valenza muestra más')
    assert financial_snapshot(repository)==before
    assert repository.list_card_summaries(include_inactive=True)==summary


@pytest.mark.parametrize('kind',['STATEMENT','MONTHLY','PENDING','UNKNOWN'])
def test_non_equivalent_balances_do_not_assert_a_difference(repository,kind):
    order(repository,'one')
    repository.record_bank_balance('card',1000,CONSULTED,balance_type=kind)
    query=repository.list_bank_reconciliation_history()[0]
    assert query['calculated_cents']==5000
    assert query['difference_cents'] is None and not query['comparable']
    assert query['warnings'] and query['balance_type']==kind
    assert account(repository)['difference_cents'] is None


def test_independent_accounts_and_shared_line_are_counted_once(repository):
    repo=repository
    repo.add_instrument('line','bank','Línea sintética','CREDIT_LINE')
    repo.add_instrument('second','bank','Tarjeta adicional','CREDIT_CARD')
    order(repo,'line-order','line',6000); order(repo,'card-order','card',4000); order(repo,'second-order','second',3000)
    before=financial_snapshot(repo)
    debt_before=repo.list_card_summaries(include_inactive=True)
    assert len(repo.list_bank_comparisons())==3
    repo.record_bank_balance('card',4000,CONSULTED)
    repo.set_bank_reconciliation_scope('card','line')
    assert len(repo.list_bank_comparisons())==2
    assert account(repo,'line')['members']==['card','line']
    repo.set_bank_reconciliation_scope('second','line')
    assert len(repo.list_bank_comparisons())==1
    shared=account(repo,'line')
    assert shared['calculated_cents']==13000
    assert len(set(shared['members']))==3
    repo.record_bank_balance('second',13500,CONSULTED)
    shared=account(repo,'line')
    assert shared['reported_cents']==13500 and shared['difference_cents']==500
    assert repo.list_bank_reconciliation_history('card')[0]['calculated_cents']==4000
    changes=repo.database.connection.total_changes
    repo.set_bank_reconciliation_scope('second','line')
    assert repo.database.connection.total_changes==changes
    with pytest.raises(ValueError): repo.set_bank_reconciliation_scope('line','card')
    with pytest.raises(ValueError): repo.set_bank_reconciliation_scope('second','wallet')
    repo.add_instrument('different','mp','Otra institución','CREDIT_CARD')
    with pytest.raises(ValueError): repo.set_bank_reconciliation_scope('second','different')
    # New catalog record is outside the financial comparison above.
    assert [c for c in repo.list_card_summaries(include_inactive=True) if c['instrument_id']!='different']==debt_before
    for name,rows in before.items():
        if name not in ('payment_instrument','instrument_calendar'):
            assert financial_snapshot(repo)[name]==rows


def test_shared_line_with_credit_is_explicitly_unreliable(repository):
    repo=repository
    repo.add_instrument('second','bank','Tarjeta adicional','CREDIT_CARD')
    order(repo,'one','card',5000)
    repo.record_institution_payment(payment_id='credit',instrument_id='second',amount_cents=1000,paid_at='2026-10-13')
    repo.set_bank_reconciliation_scope('second','card')
    repo.record_bank_balance('card',4000,CONSULTED)
    query=repo.list_bank_reconciliation_history()[0]
    assert not query['comparable'] and query['difference_cents'] is None
    assert any('saldo a favor' in w for w in query['warnings'])
    assert account(repo)['calculated_cents']==5000  # Existing source retained; no invented cross-card netting.


def test_discount_wallet_repurchase_msi_and_payments_use_bank_source(repository):
    repo=repository
    create_discount_comparison_case(repo)
    repo.link_order_to_msi('order',('2026-11-13','2026-12-13','2027-01-13'))
    initial=account(repo)
    assert initial['calculated_cents']==54258
    repo.record_receipt(payment_id='family',receivable_id='order:order:mama',amount_cents=1000,received_at='2026-10-13')
    assert account(repo)['calculated_cents']==54258
    repo.record_bank_balance('card',54258,CONSULTED)
    query=repo.list_bank_reconciliation_history()[0]
    assert query['components'][0]['future_msi_cents']==54258
    assert query['components'][0]['movements']==[]
    before=financial_snapshot(repo)
    repo.record_bank_balance('card',54258,CONSULTED)
    assert financial_snapshot(repo)==before
    saved=repo.list_bank_reconciliation_history()
    repo.record_institution_payment(payment_id='real-bank-payment',instrument_id='card',amount_cents=3000,paid_at='2026-10-13')
    assert account(repo)['calculated_cents']==51258
    assert account(repo)['snapshot_calculated_cents']==54258
    assert account(repo)['difference_cents']==0
    assert repo.list_bank_reconciliation_history()==saved
    order(repo,'later',charged=700)
    assert account(repo)['calculated_cents']==51958
    assert account(repo)['difference_cents']==0
    assert repo.list_bank_reconciliation_history()==saved


@pytest.mark.parametrize('status,expected',[('PENDING',54258),('ACCREDITED',35601)])
def test_refund_affects_only_its_accredited_bank_destination(repository,status,expected):
    repository.create_order(**purchase_args(status=status,destination='card'))
    comparison=account(repository)
    assert comparison['calculated_cents']==expected
    repository.record_bank_balance('card',expected,CONSULTED)
    assert account(repository)['difference_cents']==0
    assert bool(comparison['warnings'])==(status=='PENDING')


def test_old_queries_migrate_and_reopen_without_fabricated_history(tmp_path):
    path=tmp_path/'synthetic-existing.db'
    db=LocalDatabase.open(path,'synthetic-only'); assert db.encrypted
    db.migrate(target=14)
    repo=FinanceRepository(db)
    repo.add_institution('bank','Banco sintético'); repo.add_instrument('card','bank','Cuenta sintética','CREDIT_CARD')
    with db.transaction() as connection:
        repo._insert_person_audit(connection,'card','BANK_BALANCE_QUERIED','synthetic',None,
            dict(amount_cents=8000,consulted_at='2026-10-12',currency='MXN'),entity_type='instrument')
    old_audit=[tuple(r) for r in db.connection.execute('SELECT * FROM audit_event ORDER BY rowid')]
    db.prepare_migration_backup(tmp_path/'synthetic-backup.db','synthetic-only'); db.migrate()
    assert db.connection.execute('PRAGMA user_version').fetchone()[0]==SCHEMA_VERSION==15
    assert [tuple(r) for r in db.connection.execute('SELECT * FROM audit_event ORDER BY rowid')]==old_audit
    old=repo.list_bank_reconciliation_history()[0]
    assert old['amount_cents']==8000 and old['calculated_cents'] is None and old['difference_cents'] is None
    repo.add_instrument('second','bank','Otra tarjeta de la línea','CREDIT_CARD')
    repo.set_bank_reconciliation_scope('second','card')
    repo.record_bank_balance('card',0,CONSULTED)
    saved=repo.list_bank_reconciliation_history()
    db.close()
    reopened=LocalDatabase.open(path,'synthetic-only'); reopened.migrate()
    reopened_repo=FinanceRepository(reopened)
    assert reopened_repo.list_bank_reconciliation_history()==saved
    assert account(reopened_repo)['members']==['card','second']
    reopened.close()


@pytest.mark.parametrize('key,amount,dated,kind',[
    ('wallet',0,CONSULTED,'TOTAL'),('missing',0,CONSULTED,'TOTAL'),('card',-1,CONSULTED,'TOTAL'),
    ('card',1.2,CONSULTED,'TOTAL'),('card',True,CONSULTED,'TOTAL'),('card',1,'invalid','TOTAL'),('card',1,CONSULTED,'INVALID')])
def test_invalid_consultation_never_writes(repository,key,amount,dated,kind):
    before=repository.database.connection.total_changes
    with pytest.raises(ValueError): repository.record_bank_balance(key,amount,dated,balance_type=kind)
    assert repository.database.connection.total_changes==before


def test_cards_home_history_and_preserved_personal_indicators(repository,tmp_path,monkeypatch):
    repo=repository
    create_discount_comparison_case(repo)
    before=financial_snapshot(repo)
    app=create_application([])
    font=QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    app.setFont(QFont(QFontDatabase.applicationFontFamilies(font)[0],10))
    errors=[]; monkeypatch.setattr(MainWindow,'_show_error',lambda _,message:errors.append(message))
    window=MainWindow(database=repo.database,test_mode=True)
    window.resize(1180,820); window.show(); window._show_page(4); app.processEvents()
    row=next(r for r in range(window.cards_table.rowCount()) if window.cards_table.item(r,12).text()=='card')
    window.cards_table.selectRow(row)
    window.card_panels['bank'][0].setChecked(True)
    window.bank_query_type.setCurrentIndex(window.bank_query_type.findData('TOTAL'))
    window.bank_total_confirmed.setChecked(True)
    window.bank_query_amount.setText('550.00'); window.bank_query_date.setText(CONSULTED)
    assert 'El banco muestra más' in window.bank_query_feedback.text()
    assert '$7.42 MXN' in window.bank_query_feedback.text()
    window.bank_query_save.click(); app.processEvents()
    assert not errors and not window.bank_query_amount.text()
    window.bank_history_toggle.click(); app.processEvents()
    assert window.bank_history.rowCount()==1
    window.bank_history.selectRow(0)
    assert 'al guardar' in window.bank_history_detail.text()
    window.bank_history_toggle.click(); app.processEvents()
    window.cards_scroll.ensureWidgetVisible(window.bank_query_save,0,80); app.processEvents()
    window.grab().save(str(tmp_path/'tarjetas-conciliacion.png'))
    window.bank_query_type.setCurrentIndex(window.bank_query_type.findData('STATEMENT'))
    window.bank_query_amount.setText('550.00')
    window.bank_query_save.click(); app.processEvents()
    assert repository.list_bank_reconciliation_history()[0]['difference_cents'] is None
    window._show_page(0); app.processEvents()
    assert window.dashboard_discount.isVisible() and window.dashboard_expected.isVisible()
    assert window.dashboard_result_toggle.isVisible()
    assert window.dashboard_cards.rowCount()==1
    assert window.dashboard_cards.item(0,1).text()=='$542.58 MXN'
    assert window.dashboard_cards.item(0,4).text()=='No comparable'
    assert window.dashboard_cards.item(0,2).text()=='Al corte: $550.00 MXN'
    assert 'total calculada' in window.dashboard_cards_total.text()
    assert not window.dashboard_cards.isColumnHidden(2)
    window.dashboard_scroll.ensureWidgetVisible(window.dashboard_cards); app.processEvents()
    window.grab().save(str(tmp_path/'inicio-conciliacion.png'))
    assert financial_snapshot(repo)==before
    window.close()
