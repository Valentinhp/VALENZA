import copy
import pytest
from PySide6.QtWidgets import QCheckBox,QDialog,QLabel,QPushButton
from test_subscriptions import repository,subscription
from test_payment_preparation import snapshot
from valenza.persistence.subscription_fees import preview
from valenza.persistence import cash_review as cash_store
from valenza.gui.cash_review import CashReviewDialog
from valenza.gui.app import create_application,MainWindow


def charged(repo,count=1):
    subscription(repo,allocations=[dict(user_id='owner',amount_cents=0),
        dict(user_id='mama',amount_cents=10001,surcharge_cents=500)])
    orders=[]
    for _ in range(count):
        current=repo.list_subscriptions()[0]
        orders.append(repo.record_subscription_charge('sub',cycle_date=current['next_due'],charged_at=current['next_due']))
    return orders


def update(repo,fee=0,**extra):
    current=repo.list_subscriptions()[0]
    subscription(repo,next_due=current['next_due'],expected_revision=current['revision'],
        allocations=[dict(user_id='owner',amount_cents=0),dict(user_id='mama',amount_cents=10001,surcharge_cents=fee)],**extra)


def protected(repo):
    return {name:rows for name,rows in snapshot(repo).items() if name not in {
        'audit_event','subscription','subscription_allocation','subscription_surcharge','receivable'}}


def test_reduces_recorded_fees_and_full_count_preserving_partial_and_bank(repository):
    orders=charged(repository,2);app=create_application([])
    dialog=CashReviewDialog(repository)
    rows={r['share']['order_id']:r for r in dialog.rows}
    rows[orders[0]]['checked'].setChecked(True)
    rows[orders[1]]['field'].setText('12.34')
    dialog.save_review();dialog.close()
    old_revision,old_count=cash_store.latest(repository,'card')
    untouched=protected(repository)
    before=repository.dashboard_summary()
    plan=preview(repository,'sub',{'owner':0,'mama':0})
    assert len(plan['changes'])==2 and len(plan['cash_updates'])==1
    update(repository,reduce_posted_surcharges=True,expected_surcharge_state=plan['token'])
    assert protected(repository)==untouched
    assert repository.dashboard_summary()['receivables_cents']==before['receivables_cents']-1000
    assert repository.dashboard_summary()['institutional_balance_cents']==before['institutional_balance_cents']
    latest_revision,data=cash_store.latest(repository,'card')
    values={e['receivable_id']:e for e in data['manual_counts']}
    assert values[f'order:{orders[0]}:mama']['amount_cents']==10001
    assert values[f'order:{orders[1]}:mama']['amount_cents']==1234
    assert latest_revision>old_revision and len(cash_store.history(repository,'card'))==2
    assert cash_store.history(repository,'card')[-1]['new_value']
    again=CashReviewDialog(repository)
    assert {r['reference'] for r in again.rows}=={10001}
    assert sum(e['amount_cents'] for e in again.snapshot()['manual_counts'])==11235
    again.close()
    after=snapshot(repository);update(repository,reduce_posted_surcharges=True)
    assert repository.database.connection.execute('SELECT COUNT(*) FROM subscription_surcharge').fetchone()[0]==0
    assert after['receivable']==snapshot(repository)['receivable']
    assert len(cash_store.history(repository,'card'))==2


@pytest.mark.parametrize('paid,allowed',[(5000,True),(10001,True),(10501,False)])
def test_receipts_are_never_rewritten_or_silently_lost(repository,paid,allowed):
    order=charged(repository)[0]
    repository.record_receipt(payment_id='receipt',receivable_id=f'order:{order}:mama',amount_cents=paid,received_at='2026-01-31')
    before=snapshot(repository)
    if not allowed:
        with pytest.raises(ValueError,match='excedente'):update(repository,reduce_posted_surcharges=True)
        assert snapshot(repository)==before
    else:
        update(repository,reduce_posted_surcharges=True)
        after=snapshot(repository)
        assert after['user_payment']==before['user_payment'] and after['receipt_application']==before['receipt_application']
        assert repository.list_collection_items()[0]['remaining_cents']==10001-paid


def test_future_only_default_and_increases_never_change_posted_debt(repository):
    charged(repository);before=repository.list_collection_items()
    update(repository)
    assert repository.list_collection_items()==before
    update(repository,fee=700,reduce_posted_surcharges=True)
    assert repository.list_collection_items()==before


def test_stale_preview_and_failure_roll_back_everything(repository,monkeypatch):
    order=charged(repository)[0]
    plan=preview(repository,'sub',{'mama':0})
    repository.record_receipt(payment_id='after-preview',receivable_id=f'order:{order}:mama',amount_cents=1,received_at='2026-01-31')
    before=snapshot(repository)
    with pytest.raises(ValueError,match='cambiaron'):
        update(repository,reduce_posted_surcharges=True,expected_surcharge_state=plan['token'])
    assert snapshot(repository)==before
    original=repository._insert_person_audit
    def fail(*args,**kwargs):
        if args[2]=='SUBSCRIPTION_SAVED':raise ValueError('Synthetic final failure')
        return original(*args,**kwargs)
    monkeypatch.setattr(repository,'_insert_person_audit',fail)
    with pytest.raises(ValueError,match='final failure'):update(repository,reduce_posted_surcharges=True)
    assert snapshot(repository)==before


@pytest.mark.parametrize('mode,expected',[('FULL',10001),('PARTIAL',10501),('LEGACY',10001)])
def test_explicit_partial_is_preserved_even_when_equal_to_old_total(repository,mode,expected):
    order=charged(repository)[0]
    data=dict(format=cash_store.FORMAT,card_id='card',physical_cents=20000,extra_cents=0,entries=[],manual_counts=[
        dict(receivable_id=f'order:{order}:mama',amount_cents=10501,label='Synthetic count',selection_mode=mode)])
    cash_store.save(repository,data,0)
    update(repository,reduce_posted_surcharges=True)
    assert cash_store.latest(repository,'card')[1]['manual_counts'][0]['amount_cents']==expected


def test_subscription_editor_previews_and_applies_previous_fee_removal(repository,monkeypatch):
    charged(repository);app=create_application([])
    window=MainWindow(database=repository.database,test_mode=True)
    monkeypatch.setattr(window,'_show_information',lambda *args:None)
    def edit(dialog):
        option=dialog.findChild(QCheckBox,'updatePostedSubscriptionFees')
        assert option.isChecked()
        fee=next(c for c in dialog.findChildren(QCheckBox) if c.text().startswith('Recargo familiar'))
        fee.setChecked(False);app.processEvents()
        text=dialog.findChild(QLabel,'postedSubscriptionFeePreview').text()
        assert '$5.00 MXN' in text and '1 recargos' in text
        button=next(b for b in dialog.findChildren(QPushButton) if b.text()=='Guardar suscripción')
        assert button.isEnabled();button.click()
        return dialog.result()
    monkeypatch.setattr(QDialog,'exec',edit)
    window._edit_subscription('sub')
    assert repository.list_collection_items()[0]['sale_cents']==10001
    window.close()


def test_recount_resumed_from_old_cut_updates_references_and_keeps_original_history(repository):
    order=charged(repository)[0]
    item=repository.list_collection_items()[0]
    cut=dict(format='valenza-preparation-v1',name='Synthetic prior cut',date='2026-01-31',
        saved_at='2026-01-31T12:00:00',card_id='card',card_label='Synthetic card',target_cents=20000,own_cents=0,
        rows=[dict(item=copy.deepcopy(item),contributions=[dict(amount_cents=10501,included=True)])])
    data=dict(format=cash_store.FORMAT,card_id='card',physical_cents=20000,extra_cents=0,entries=[],resumed_cut=cut,
        manual_counts=[dict(receivable_id=f'order:{order}:mama',amount_cents=10501,label='Synthetic full count',selection_mode='FULL')])
    cash_store.save(repository,data,0)
    update(repository,reduce_posted_surcharges=True)
    assert data['resumed_cut']['rows'][0]['item']['sale_cents']==10501
    latest=cash_store.latest(repository,'card')[1]
    assert latest['resumed_cut']['rows'][0]['item']['sale_cents']==10001
    create_application([]);dialog=CashReviewDialog(repository)
    assert dialog.rows[0]['reference']==10001 and dialog.rows[0]['field'].text()=='100.01'
    dialog.close()


def test_concurrent_receipt_cannot_enter_between_validation_and_fee_update(repository,monkeypatch):
    from pathlib import Path
    from valenza.persistence.database import LocalDatabase,DATABASE_ERRORS
    from valenza.persistence.repository import FinanceRepository
    import valenza.persistence.subscription_fees as module
    order=charged(repository)[0]
    path=Path(repository.database.connection.execute('PRAGMA database_list').fetchone()[2])
    second=LocalDatabase.open(path,'synthetic');second.connection.execute('PRAGMA busy_timeout=0')
    other=FinanceRepository(second);original=module.apply
    def interleave(repo,plan,actor):
        with pytest.raises(DATABASE_ERRORS,match='locked'):
            other.record_receipt(payment_id='concurrent',receivable_id=f'order:{order}:mama',amount_cents=10501,received_at='2026-01-31')
        return original(repo,plan,actor)
    monkeypatch.setattr(module,'apply',interleave)
    try:update(repository,reduce_posted_surcharges=True)
    finally:second.close()
    assert repository.list_collection_items()[0]['sale_cents']==10001
    assert repository.database.connection.execute("SELECT COUNT(*) FROM user_payment WHERE id='concurrent'").fetchone()[0]==0


def test_editor_removes_posted_fee_when_template_was_already_disabled(repository,monkeypatch):
    charged(repository)
    update(repository)  # Future configuration is already zero, posted fee still exists.
    assert repository.list_subscriptions()[0]['allocations'][1]['surcharge_cents']==0
    assert repository.list_collection_items()[0]['sale_cents']==10501
    app=create_application([])
    window=MainWindow(database=repository.database,test_mode=True)
    monkeypatch.setattr(window,'_show_information',lambda *args:None)
    def edit(dialog):
        fees=next(c for c in dialog.findChildren(QCheckBox) if c.text().startswith('Recargo familiar'))
        assert not fees.isChecked()
        assert dialog.findChild(QCheckBox,'updatePostedSubscriptionFees').isChecked()
        assert '$5.00 MXN' in dialog.findChild(QLabel,'postedSubscriptionFeePreview').text()
        next(b for b in dialog.findChildren(QPushButton) if b.objectName()=='primaryAction').click()
        return dialog.result()
    monkeypatch.setattr(QDialog,'exec',edit)
    window._edit_subscription('sub')
    assert repository.list_collection_items()[0]['sale_cents']==10001
    assert repository.database.connection.execute('SELECT COUNT(*) FROM subscription_surcharge').fetchone()[0]==0
    cash=CashReviewDialog(repository)
    row=cash.rows[0]
    assert row['reference']==10001
    row['checked'].setChecked(True)
    assert row['field'].text()=='100.01'
    cash.dirty=False;cash.close();window.close()


@pytest.mark.parametrize('mode,expected', [('FULL',10001),('PARTIAL',10501),('LEGACY',10001),(None,10001)])
def test_old_cut_opened_after_fee_removal_uses_corrected_reference(repository,mode,expected):
    charged(repository)
    item=copy.deepcopy(repository.list_collection_items()[0])
    cut=dict(format='valenza-preparation-v1',name='Old synthetic cut',date='2026-01-31',
        saved_at='2026-01-31T12:00:00',card_id='card',card_label='Synthetic',target_cents=20000,own_cents=0,
        rows=[dict(item=item,contributions=[dict(amount_cents=10501,included=True)])])
    data=dict(format=cash_store.FORMAT,card_id='card',physical_cents=20000,extra_cents=0,entries=[],resumed_cut=cut,
        manual_counts=[dict(receivable_id=item['receivable_id'],amount_cents=10501,label='Count',selection_mode=mode or 'LEGACY')])
    update(repository,reduce_posted_surcharges=True)
    before=snapshot(repository)
    create_application([]);dialog=CashReviewDialog(repository)
    dialog.show_old_cut(cut,saved_data=data if mode else None)
    assert dialog.rows[0]['reference']==10001
    assert dialog.rows[0]['field'].text()==f'{expected/100:.2f}'
    assert cut['rows'][0]['item']['sale_cents']==10501
    assert data['manual_counts'][0]['amount_cents']==10501
    assert snapshot(repository)==before
    dialog.dirty=False;dialog.close()
