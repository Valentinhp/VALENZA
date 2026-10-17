from datetime import date
import copy
import pytest
from PySide6.QtCore import Qt
from test_payment_preparation import prepared_repo,msi_preparation_order,snapshot
from valenza.gui.cash_review import CashReviewDialog
from valenza.gui.cash_review_items import cash_review_items
from valenza.gui.app import create_application
from valenza.gui.person_receipts import cents


@pytest.mark.parametrize('products',[True,False])
def test_current_month_msi_reference_and_products_preserve_every_cent(prepared_repo,products):
    repo=prepared_repo;msi_preparation_order(repo,with_products=products)
    before=snapshot(repo);changes=repo.database.connection.total_changes
    totals={'owner':0,'family':0}
    ids=set()
    for month in (9,10,11):
        items=[i for i in cash_review_items(repo,'card',as_of=date(2026,month,1)) if i.get('is_msi')]
        assert len(items)==2
        for item in items:
            assert item['installment_due'][:7]==f'2026-{month:02}'
            assert item['sale_cents'] in (1666,1667)
            assert item['sale_cents']<item['total_sale_cents']
            assert item['receivable_id'] not in ids;ids.add(item['receivable_id'])
            totals[item['user_id']]+=item['sale_cents']
            if products:assert sum(p['amount_cents'] for p in item['products'])==item['sale_cents']
    assert totals=={'owner':5000,'family':5001}
    assert not any(i.get('is_msi') for i in cash_review_items(repo,'card',as_of=date(2026,12,1)))
    assert snapshot(repo)==before and repo.database.connection.total_changes==changes


def test_current_installment_checkbox_and_bulk_never_select_future_principal(prepared_repo,monkeypatch):
    import valenza.gui.cash_review as module
    msi_preparation_order(prepared_repo)
    monkeypatch.setattr(module,'cash_review_items',lambda repo,card_id,**kw:cash_review_items(repo,card_id,as_of=date(2026,10,1)))
    create_application([]);dialog=CashReviewDialog(prepared_repo)
    before=snapshot(prepared_repo);changes=prepared_repo.database.connection.total_changes
    rows=[r for r in dialog.rows if r['share'].get('is_msi')]
    assert len(rows)==2
    row=next(r for r in rows if r['share']['user_id']=='family')
    assert 'Mensualidad 2/3' in row['item'].text(0)
    row['checked'].setChecked(True)
    assert row['field'].text()=='16.67'
    assert sum(e['amount_cents'] for e in dialog.snapshot()['manual_counts'])==1667
    for item in dialog.product_marks.values():item.setCheckState(0,Qt.CheckState.Checked)
    assert sum(e['amount_cents'] for e in dialog.snapshot()['manual_counts'])==1667
    dialog.mark_all_button.click()
    assert sum(cents(r['field'].text()) for r in rows)==3334
    assert snapshot(prepared_repo)==before and prepared_repo.database.connection.total_changes==changes
    dialog.dirty=False;dialog.close()


def test_paid_msi_still_has_monthly_reference_and_allows_independent_partial(prepared_repo):
    msi_preparation_order(prepared_repo)
    prepared_repo.record_receipt(payment_id='all-paid',receivable_id='order:monthly:family',
        amount_cents=5001,received_at='2026-10-01')
    item=next(i for i in cash_review_items(prepared_repo,'card',as_of=date(2026,10,1)) if i.get('is_msi') and i['user_id']=='family')
    assert item['sale_cents']==1667 and item['remaining_cents']==0


def test_two_installments_same_month_have_distinct_keys(prepared_repo):
    msi_preparation_order(prepared_repo,dates=('2026-10-01','2026-10-25','2026-11-25'))
    items=[i for i in cash_review_items(prepared_repo,'card',as_of=date(2026,10,1)) if i.get('is_msi') and i['user_id']=='family']
    assert [i['installment_number'] for i in items]==[1,2]
    assert len({i['receivable_id'] for i in items})==2


def test_old_whole_msi_cut_is_not_loaded_as_monthly_amount(prepared_repo,monkeypatch):
    from valenza.gui.preparation_record import FORMAT
    import valenza.gui.cash_review as module
    msi_preparation_order(prepared_repo)
    original=next(i for i in prepared_repo.list_collection_items() if i['order_id']=='monthly' and i['user_id']=='family')
    record=dict(format=FORMAT,name='Old whole MSI',date='2026-10-01',saved_at='2026-10-01T10:00:00',
        card_id='card',card_label='Synthetic',target_cents=10000,own_cents=0,
        rows=[dict(item=original,contributions=[dict(amount_cents=5001,included=True)])])
    untouched=copy.deepcopy(record)
    create_application([]);dialog=CashReviewDialog(prepared_repo)
    before=snapshot(prepared_repo);changes=prepared_repo.database.connection.total_changes
    dialog.show_old_cut(record)
    assert len(dialog.rows)==1 and dialog.rows[0]['reference']==1667
    assert dialog.rows[0]['field'].text()=='0.00' and not dialog.rows[0]['checked'].isChecked()
    dialog.rows[0]['checked'].setChecked(True)
    assert dialog.rows[0]['field'].text()=='16.67'
    assert dialog.snapshot()['manual_counts'][0]['amount_cents']==1667
    assert record==untouched and snapshot(prepared_repo)==before
    assert prepared_repo.database.connection.total_changes==changes
    dialog.dirty=False;dialog.close()


def test_reopen_keeps_saved_quota_but_new_count_uses_current_month(prepared_repo,monkeypatch):
    import valenza.gui.cash_review as module
    from PySide6.QtWidgets import QMessageBox
    msi_preparation_order(prepared_repo)
    class Clock(date):
        month_now=10
        @classmethod
        def today(cls):return cls(2026,cls.month_now,17)
    monkeypatch.setattr(module,'date',Clock)
    create_application([]);dialog=CashReviewDialog(prepared_repo)
    row=next(r for r in dialog.rows if r['share'].get('is_msi') and r['share']['user_id']=='family')
    october_key=row['share']['receivable_id']
    row['checked'].setChecked(True);dialog.save_review();dialog.close()
    Clock.month_now=11
    again=CashReviewDialog(prepared_repo)
    assert again.review_period=='2026-10'
    row=next(r for r in again.rows if r['share'].get('is_msi') and r['share']['user_id']=='family')
    assert row['share']['receivable_id']==october_key and row['checked'].isChecked()
    before=snapshot(prepared_repo)
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
    again.new_count()
    assert again.review_period=='2026-11'
    row=next(r for r in again.rows if r['share'].get('is_msi') and r['share']['user_id']=='family')
    assert row['share']['receivable_id']!=october_key
    assert not row['checked'].isChecked() and row['reference']==1667
    assert snapshot(prepared_repo)==before
    again.dirty=False;again.close()


def test_undated_installments_never_fall_back_to_whole_plan(prepared_repo):
    msi_preparation_order(prepared_repo,dates=(None,'2026-10-15','2026-11-15'))
    items=[i for i in cash_review_items(prepared_repo,'card',as_of=date(2026,10,1)) if i.get('is_msi') and i['user_id']=='family']
    assert len(items)==2
    unknown=next(i for i in items if i.get('msi_dates_missing'))
    current=next(i for i in items if not i.get('msi_dates_missing'))
    assert unknown['sale_cents']==0 and current['sale_cents']==1667
    assert current['installment_number']==2


def test_old_whole_order_mark_is_not_transferred_to_current_quota(prepared_repo,monkeypatch):
    from valenza.persistence import cash_review as store
    import valenza.gui.cash_review as module
    msi_preparation_order(prepared_repo)
    store.save(prepared_repo,dict(format=store.FORMAT,card_id='card',physical_cents=10000,extra_cents=0,entries=[],
        manual_counts=[dict(receivable_id='order:monthly:family',amount_cents=5001,label='Whole MSI')]),0)
    monkeypatch.setattr(module,'cash_review_items',lambda repo,card_id,**kw:cash_review_items(repo,card_id,as_of=date(2026,10,1)))
    before=snapshot(prepared_repo)
    create_application([]);dialog=CashReviewDialog(prepared_repo)
    row=next(r for r in dialog.rows if r['share'].get('is_msi') and r['share']['user_id']=='family')
    assert row['field'].text()=='0.00' and row['reference']==1667
    assert 'marcas anteriores' in dialog.status.text()
    assert snapshot(prepared_repo)==before
    dialog.close()
