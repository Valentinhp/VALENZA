import pytest
from test_product_refunds import repository
from valenza.persistence.database import LocalDatabase, SCHEMA_VERSION, DatabaseSecurityError
from valenza.persistence.repository import FinanceRepository


def subscription(repo, **changes):
    args = dict(subscription_id='sub',name='Servicio sintético',amount_cents=10001,
                instrument_id='card',next_due='2026-01-31',
                allocations=[dict(user_id='owner',amount_cents=0),dict(user_id='mama',amount_cents=10001)])
    args.update(changes)
    repo.save_subscription(**args)


def test_forecasts_lifecycle_do_not_create_debt(repository):
    subscription(repository)
    assert repository.list_subscriptions()[0]['next_due']=='2026-01-31'
    assert repository.list_orders()==[] and repository.list_collection_items()==[]
    repository.set_subscription_status('sub','PAUSED')
    with pytest.raises(ValueError):
        repository.record_subscription_charge('sub',cycle_date='2026-01-31',charged_at='2026-01-31')
    repository.set_subscription_status('sub','ACTIVE')
    revision=repository.list_subscriptions()[0]['revision']
    subscription(repository,expected_revision=revision,name='Servicio editado')
    with pytest.raises(ValueError):
        subscription(repository,expected_revision=revision,name='Edición antigua')
    repository.set_subscription_status('sub','CANCELLED')
    assert not repository.list_orders()
    with pytest.raises(ValueError): repository.set_subscription_status('sub','ACTIVE')


def test_real_charge_fees_anchor_and_no_duplicates(repository):
    subscription(repository,allocations=[dict(user_id='owner',amount_cents=0),dict(user_id='mama',amount_cents=10001,surcharge_cents=500)])
    order=repository.record_subscription_charge('sub',cycle_date='2026-01-31',charged_at='2026-01-30')
    assert len(repository.list_orders())==1
    assert repository.dashboard_summary()['institutional_balance_cents']==10001
    assert repository.dashboard_summary()['receivables_cents']==10501
    assert repository.dashboard_summary()['discount_benefit_cents']==0
    assert repository.family_statement('mama')['rows'][0]['concepts'][1]['amount_cents']==500
    assert repository.list_subscriptions()[0]['next_due']=='2026-02-28'
    with pytest.raises(ValueError):
        repository.record_subscription_charge('sub',cycle_date='2026-01-31',order_id=order)
    with pytest.raises(ValueError):
        repository.record_subscription_charge('sub',cycle_date='2026-02-28',order_id=order)
    assert len(repository.list_orders())==1
    repository.record_subscription_charge('sub',cycle_date='2026-02-28',charged_at='2026-02-28')
    assert repository.list_subscriptions()[0]['next_due']=='2026-03-31'
    assert repository.list_subscriptions()[0]['family_pending_cents']==21002


def test_link_existing_order_creates_no_second_charge(repository):
    subscription(repository)
    repository.create_order(order_id='existing',ordered_at='2026-01-31',merchant='Servicio',instrument_id='card',original_cents=10001,
        discount_cents=0,charged_cents=10001,allocations=({'user_id':'owner','amount_cents':0},{'user_id':'mama','amount_cents':10001}))
    before=repository.dashboard_summary()
    repository.record_subscription_charge('sub',cycle_date='2026-01-31',order_id='existing')
    after=repository.dashboard_summary()
    assert before['institutional_balance_cents']==after['institutional_balance_cents']==10001
    assert before['receivables_cents']==after['receivables_cents']==10001
    assert len(repository.list_orders())==1 and len(repository.list_collection_items())==1


@pytest.mark.parametrize('changes',[dict(amount_cents=0),dict(next_due='2026-02-30'),dict(instrument_id='missing'),
    dict(allocations=[dict(user_id='owner',amount_cents=10001,surcharge_cents=50)]),
    dict(allocations=[dict(user_id='owner',amount_cents=1),dict(user_id='mama',amount_cents=9999)]),
    dict(allocations=[dict(user_id='owner',amount_cents=10001),dict(user_id='owner',amount_cents=0)])])
def test_invalid_subscription_is_atomic(repository,changes):
    with pytest.raises(ValueError): subscription(repository,**changes)
    assert repository.list_subscriptions()==[] and repository.list_orders()==[]


def test_failed_charge_rolls_back_order_and_cycle(repository,monkeypatch):
    subscription(repository)
    original=repository._insert_person_audit
    def fail(*args,**kwargs):
        if args[2]=='SUBSCRIPTION_CHARGE_LINKED': raise ValueError('synthetic failure')
        return original(*args,**kwargs)
    monkeypatch.setattr(repository,'_insert_person_audit',fail)
    with pytest.raises(ValueError):
        repository.record_subscription_charge('sub',cycle_date='2026-01-31',charged_at='2026-01-31')
    assert not repository.list_orders() and not repository.list_collection_items()
    assert repository.list_subscriptions()[0]['next_due']=='2026-01-31'


def test_edit_future_template_and_manual_description_preserves_posted_fee(repository):
    subscription(repository,allocations=[dict(user_id='owner',amount_cents=0),dict(user_id='mama',amount_cents=10001,surcharge_cents=500)])
    order=repository.record_subscription_charge('sub',cycle_date='2026-01-31',charged_at='2026-01-31')
    revision=repository.list_subscriptions()[0]['revision']
    subscription(repository,expected_revision=revision,amount_cents=20000,next_due='2026-02-28',
        allocations=[dict(user_id='owner',amount_cents=20000),dict(user_id='mama',amount_cents=0)])
    concepts=repository.get_order(order)['manual_concepts']
    concepts[0]['description']='Servicio mes de enero'
    repository.update_manual_concepts(order,concepts)
    assert repository.dashboard_summary()['receivables_cents']==10501
    assert repository.dashboard_summary()['institutional_balance_cents']==10001
    statement=repository.family_statement('mama')
    assert statement['rows'][0]['concept_adjustment_cents']==0
    assert sum(c['amount_cents'] for c in statement['rows'][0]['concepts'])==10501
    assert repository.list_subscriptions()[0]['amount_cents']==20000


def test_encrypted_migration_and_persistence(tmp_path):
    path=tmp_path/'synthetic.db'
    db=LocalDatabase.open(path,'synthetic')
    db.migrate(14)
    with pytest.raises(DatabaseSecurityError): db.migrate()
    db.prepare_migration_backup(tmp_path/'pre15.db','synthetic')
    db.migrate()
    assert db.connection.execute('PRAGMA user_version').fetchone()[0]==SCHEMA_VERSION
    repo=FinanceRepository(db)
    repo.add_person('owner','Yo',is_owner=True); repo.add_person('mama','Persona sintética')
    repo.add_institution('bank','Banco sintético'); repo.add_instrument('card','bank','Cuenta sintética','CREDIT_CARD')
    subscription(repo)
    repo.record_subscription_charge('sub',cycle_date='2026-01-31',charged_at='2026-01-31')
    db.close()
    db=LocalDatabase.open(path,'synthetic'); db.migrate(); repo=FinanceRepository(db)
    assert repo.list_subscriptions()[0]['family_pending_cents']==10001
    assert repo.dashboard_summary()['institutional_balance_cents']==10001
    assert db.integrity_report()['ok']; db.close()


def test_subscription_ui_small_and_save(repository,monkeypatch,tmp_path):
    from valenza.gui.app import MainWindow,create_application
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFont,QFontDatabase
    from PySide6.QtWidgets import QDialog,QLineEdit,QPushButton
    app=create_application([])
    font=QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    if font>=0: app.setFont(QFont(QFontDatabase.applicationFontFamilies(font)[0],10))
    window=MainWindow(database=repository.database)
    window.show(); window.resize(680,480); window._show_page(5); app.processEvents()
    window.grab().save(str(tmp_path/'subscriptions-small.png'))
    def fill():
        dialog=window.findChildren(QDialog)[-1]
        dialog.resize(480,280)
        fields=dialog.findChildren(QLineEdit)
        fields[0].setText('Servicio sintético'); fields[1].setText('100.01')
        fields[3].setText('100.01')
        buttons=dialog.findChildren(QPushButton)
        save=next(b for b in buttons if b.text()=='Guardar')
        assert save.isVisible() and save.mapTo(dialog,save.rect().bottomRight()).y()<dialog.height()
        dialog.grab().save(str(tmp_path/'subscription-dialog-small.png'))
        save.click()
        if dialog.isVisible(): dialog.reject()
    QTimer.singleShot(0,fill); window._edit_subscription()
    assert len(repository.list_subscriptions())==1 and not repository.list_orders()
    window.close(); app.processEvents()
