import json
import pytest
from PySide6.QtWidgets import QMessageBox,QFileDialog
from test_subscriptions import repository,subscription
from test_subscription_fee_reduction import charged
from test_payment_preparation import snapshot
from valenza.persistence.subscription_delete import preview,delete,_clean_review
from valenza.persistence import cash_review as store
from valenza.gui.app import create_application,MainWindow
from valenza.gui.cash_review import CashReviewDialog


def remove(repo,tmp_path):
    plan=preview(repo,'sub')
    return delete(repo,'sub',expected_token=plan['token'],backup_path=tmp_path/'before-delete.db')


def test_deletes_charges_receipts_history_and_counts_with_verified_backup(repository,tmp_path):
    orders=charged(repository,2)
    repository.record_institution_payment(payment_id='bank-global',instrument_id='card',paid_at='2026-01-31',amount_cents=12500)
    repository.record_receipt(payment_id='exclusive',receivable_id=f'order:{orders[0]}:mama',amount_cents=500,received_at='2026-01-31')
    create_application([]);cash=CashReviewDialog(repository)
    cash.apply_selection(cash.rows);cash.save_review();cash.dirty=False;cash.close()
    before=snapshot(repository)
    remove(repository,tmp_path)
    assert repository.list_subscriptions()==[] and repository.list_orders()==[]
    assert repository.list_collection_items()==[]
    for table in ('subscription','subscription_charge','subscription_allocation','subscription_surcharge','receivable','receipt_application','user_payment','order_record','order_allocation'):
        assert not repository.database.connection.execute('SELECT 1 FROM '+table).fetchone()
    for event in repository.database.connection.execute('SELECT * FROM audit_event'):
        assert not any(order in json.dumps(dict(event)) for order in orders)
    assert store.latest(repository,'card')[1]['manual_counts']==[]
    assert repository.database.integrity_report()['ok']
    repository.database.verify_backup(tmp_path/'before-delete.db')
    for table in ('person','payment_instrument','institution','institution_payment','institution_movement'):
        assert snapshot(repository)[table]==before[table]


@pytest.mark.parametrize('status',['ACTIVE','PAUSED','CANCELLED'])
def test_deletes_uncharged_subscription_in_any_status(repository,tmp_path,status):
    subscription(repository)
    if status!='ACTIVE':repository.set_subscription_status('sub',status)
    remove(repository,tmp_path)
    assert not repository.list_subscriptions()


def test_shared_receipt_blocks_atomic_deletion(repository,tmp_path):
    order=charged(repository)[0]
    repository.create_order(order_id='other-order',ordered_at='2026-01-31',merchant='Other synthetic',instrument_id='card',
        original_cents=1000,discount_cents=0,charged_cents=1000,
        allocations=({'user_id':'owner','amount_cents':0},{'user_id':'mama','amount_cents':1000}))
    balances={a['receivable_id']:a['remaining_cents'] for a in repository.person_receipt_accounts('mama')}
    repository.record_global_receipt(payment_id='shared',user_id='mama',amount_cents=1000,received_at='2026-01-31',
        applications={f'order:{order}:mama':500,'order:other-order:mama':500},expected_balances=balances)
    before=snapshot(repository)
    with pytest.raises(ValueError,match='otros pedidos'):remove(repository,tmp_path)
    assert snapshot(repository)==before and not (tmp_path/'before-delete.db').exists()


def test_stale_preview_and_backup_failure_do_not_delete(repository,tmp_path,monkeypatch):
    charged(repository);plan=preview(repository,'sub')
    repository.set_subscription_status('sub','PAUSED');before=snapshot(repository)
    with pytest.raises(ValueError,match='cambiaron'):
        delete(repository,'sub',expected_token=plan['token'],backup_path=tmp_path/'stale.db')
    assert snapshot(repository)==before
    def fail(*args):raise OSError('synthetic backup failure')
    monkeypatch.setattr(repository.database,'create_backup',fail)
    with pytest.raises(OSError):remove(repository,tmp_path)
    assert snapshot(repository)==before


def test_legacy_count_cleanup_preserves_other_entries_and_format():
    data=dict(entries=[dict(key=json.dumps(['p','order:a:u']),amount_cents=2),
                       dict(key=json.dumps(['p','order:b:u']),amount_cents=3)])
    cleaned=_clean_review(data,['a'],['order:a:u'])
    assert 'manual_counts' not in cleaned and len(cleaned['entries'])==1
    assert len(data['entries'])==2


def test_ui_cancel_has_no_effect_and_delete_is_available_for_cancelled(repository,monkeypatch):
    subscription(repository);repository.set_subscription_status('sub','CANCELLED')
    create_application([]);window=MainWindow(database=repository.database,test_mode=True)
    window.subscription_table.selectRow(0);window._subscription_selection()
    assert window.subscription_actions[4].isEnabled()
    before=snapshot(repository)
    monkeypatch.setattr(QMessageBox,'warning',lambda *a:QMessageBox.StandardButton.No)
    window.subscription_actions[4].click()
    assert snapshot(repository)==before
    window.close()


def test_ui_confirmation_executes_delete_with_backup(repository,tmp_path,monkeypatch):
    charged(repository)
    create_application([]);window=MainWindow(database=repository.database,test_mode=True)
    window.subscription_table.selectRow(0)
    monkeypatch.setattr(QMessageBox,'warning',lambda *a:QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:(str(tmp_path/'ui-backup.db'),''))
    messages=[]
    monkeypatch.setattr(window,'_show_information',messages.append)
    window._delete_subscription()
    assert not repository.list_subscriptions() and not repository.list_orders()
    assert messages and (tmp_path/'ui-backup.db').exists()
    window.close()


def test_delete_failure_rolls_back_entire_operation(repository,tmp_path):
    from valenza.persistence.database import DATABASE_ERRORS
    charged(repository)
    repository.database.connection.execute("CREATE TRIGGER synthetic_reject_delete BEFORE DELETE ON subscription BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
    before=snapshot(repository)
    with pytest.raises(DATABASE_ERRORS,match='synthetic failure'):remove(repository,tmp_path)
    assert snapshot(repository)==before
    repository.database.verify_backup(tmp_path/'before-delete.db')


def test_unrelated_subscription_and_its_count_are_preserved(repository,tmp_path):
    charged(repository)
    subscription(repository,subscription_id='other-sub',name='Other synthetic service')
    other=repository.record_subscription_charge('other-sub',cycle_date='2026-01-31',charged_at='2026-01-31')
    create_application([]);cash=CashReviewDialog(repository)
    cash.apply_selection(cash.rows);cash.save_review();cash.dirty=False;cash.close()
    remove(repository,tmp_path)
    assert [s['id'] for s in repository.list_subscriptions()]==['other-sub']
    assert [o['id'] for o in repository.list_orders()]==[other]
    entries=store.latest(repository,'card')[1]['manual_counts']
    assert len(entries)==1 and entries[0]['receivable_id']==f'order:{other}:mama'
