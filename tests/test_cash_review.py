"""Partial counting is separate from all bank and receivable ledgers."""
import copy
import pytest
from test_global_receipts import repo,record
from valenza.persistence import cash_review as store
from valenza.gui.cash_review import CashReviewDialog
from valenza.gui.app import create_application

def financial(repo):
    tables=['user_payment','receipt_application','institution_payment','installment_payment_application',
            'receivable','order_record','financing_plan','installment']
    return {name:[tuple(r) for r in repo.database.connection.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in tables}

def data(repo,amount=12500):
    sources=store.receipt_sources(repo,'card')
    source=next(iter(sources.values()))
    return dict(format=store.FORMAT,card_id='card',physical_cents=amount,extra_cents=0,
        entries=[dict(key=source['key'],fingerprint=source['fingerprint'],amount_cents=amount)])

def test_partial_save_idempotence_history_and_no_financial_changes(repo):
    record(repo,amount=15000)
    before=financial(repo);summary=repo.dashboard_summary()
    first=data(repo,3500)
    revision=store.save(repo,first,0)
    assert store.save(repo,first,revision)==revision
    second=copy.deepcopy(first);second['entries'][0]['amount_cents']=5000
    next_revision=store.save(repo,second,revision)
    assert next_revision>revision and len(store.history(repo,'card'))==2
    assert store.latest(repo,'card')==(next_revision,second)
    assert financial(repo)==before and repo.dashboard_summary()==summary

def test_duplicates_stale_window_and_over_count_are_blocked_atomically(repo):
    record(repo,amount=15000)
    first=data(repo,1000);revision=store.save(repo,first,0)
    before=financial(repo);changes=repo.database.connection.total_changes
    for bad in (dict(first,entries=first['entries']*2),
                dict(first,entries=[dict(first['entries'][0],amount_cents=15001)])):
        with pytest.raises(ValueError):store.save(repo,bad,revision)
    with pytest.raises(ValueError,match='otra ventana'):store.save(repo,first,0)
    assert repo.database.connection.total_changes==changes and financial(repo)==before

@pytest.mark.parametrize('change',['edit','cancel'])
def test_changed_receipt_requires_explicit_review_without_repair(repo,change):
    record(repo,amount=15000)
    first=data(repo,1000);revision=store.save(repo,first,0)
    if change=='cancel':repo.cancel_user_payment('global',reason='Synthetic cancel')
    else:repo.update_user_payment('global',received_at='2026-10-13',amount_cents=15000,reference='Changed')
    assert store.stale_entries(first,store.receipt_sources(repo,'card'))
    before=financial(repo)
    with pytest.raises(ValueError,match='anulados'):store.save(repo,first,revision)
    assert financial(repo)==before and store.latest(repo,'card')[1]==first

def test_global_applications_are_distinct_but_never_count_payment_twice(repo):
    record(repo,amount=25000)
    sources=store.receipt_sources(repo,'card')
    assert len(sources)==2 and sum(s['amount_cents'] for s in sources.values())==25000
    state=dict(format=store.FORMAT,card_id='card',physical_cents=25000,extra_cents=0,
        entries=[dict(key=s['key'],fingerprint=s['fingerprint'],amount_cents=s['amount_cents']) for s in sources.values()])
    store.save(repo,state,0)
    assert sum(e['amount_cents'] for e in store.latest(repo,'card')[1]['entries'])==25000

def test_dialog_partial_without_whole_order_paid_msi_visible_and_reload(repo):
    app=create_application([])
    repo.record_receipt(payment_id='full-msi',receivable_id='order:msi:mama',amount_cents=30000,received_at='2026-10-12')
    before=financial(repo)
    dialog=CashReviewDialog(repo)
    row=next(r for r in dialog.rows if r['share']['order_id']=='msi')
    assert row['available']==30000 and row['share']['remaining_cents']==0
    row['field'].setText('17.25')
    assert row['checked'].isChecked()
    assert sum(e['amount_cents'] for e in dialog.snapshot()['manual_counts'])==1725
    dialog.physical.setText('17.25');dialog.save_review()
    assert 'cuadra' in dialog.summary.text()
    dialog.close()
    again=CashReviewDialog(repo)
    row=next(r for r in again.rows if r['share']['order_id']=='msi')
    assert row['field'].text()=='17.25'
    assert financial(repo)==before
    again.close();app.processEvents()

def test_corrupt_overallocated_receipt_is_never_available(repo):
    record(repo,amount=15000)
    repo.database.connection.execute("UPDATE user_payment SET amount_cents=1 WHERE id='global'")
    assert all(s['inconsistent'] for s in store.receipt_sources(repo,'card').values())
    with pytest.raises(ValueError):store.save(repo,data(repo,1),0)

def test_encrypted_reopen_preserves_revision_and_schema(repo):
    from pathlib import Path
    from valenza.persistence.database import LocalDatabase
    from valenza.persistence.repository import FinanceRepository
    record(repo,amount=15000)
    first=data(repo,1234);revision=store.save(repo,first,0)
    schema=[tuple(r) for r in repo.database.connection.execute("SELECT name,sql FROM sqlite_master ORDER BY name")]
    path=Path(repo.database.connection.execute('PRAGMA database_list').fetchone()[2])
    repo.database.close()
    db=LocalDatabase.open(path,'synthetic-only')
    try:
        assert db.encrypted and db.integrity_report()['ok']
        assert store.latest(FinanceRepository(db),'card')==(revision,first)
        assert [tuple(r) for r in db.connection.execute("SELECT name,sql FROM sqlite_master ORDER BY name")]==schema
    finally:db.close()

def test_product_checks_and_partial_do_not_double_count_and_render(repo,tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFontDatabase
    app=create_application([])
    for font in ('segoeui.ttf','seguisb.ttf','georgia.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
    repo.create_order(order_id='products',ordered_at='2026-10-01',merchant='Productos sintéticos',
        instrument_id='card',original_cents=4,charged_cents=4,discount_cents=0,
        allocations=({'user_id':'owner','amount_cents':0},{'user_id':'mama','amount_cents':4}),
        purchase_mode='MSI',financing_specs=('2026-10-15','2026-11-15','2026-12-15'),
        concepts=[dict(description=name,amount_cents=2,allocations={'mama':2,'owner':0}) for name in ('A','B')])
    repo.record_receipt(payment_id='products-cash',receivable_id='order:products:mama',amount_cents=4,received_at='2026-10-12')
    before=financial(repo);dialog=CashReviewDialog(repo)
    for item in dialog.product_marks.values():item.setCheckState(0,Qt.CheckState.Checked)
    row=next(r for r in dialog.rows if r['share']['order_id']=='products')
    row['field'].setText('0.03');dialog.physical.setText('0.03')
    state=dialog.snapshot()
    assert sum(e['amount_cents'] for e in state['manual_counts'])==3
    assert len(state['checked_products'])==2
    dialog.save_review();dialog.show()
    for width,height in ((900,650),(680,480)):
        dialog.resize(width,height);app.processEvents()
        assert dialog.width()==width
        assert dialog.grab().save(str(tmp_path/f'cash-review-{width}.png'))
        for button in (dialog.save_button,dialog.old_button,dialog.history_button):
            assert dialog.rect().contains(button.mapTo(dialog,button.rect().bottomRight()))
    dialog.close()
    again=CashReviewDialog(repo)
    assert all(i.checkState(0)==Qt.CheckState.Checked for i in again.product_marks.values())
    assert financial(repo)==before
    again.close()

def test_history_and_legacy_cut_are_human_readable_and_never_recount(repo,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from valenza.gui.preparation_record import FORMAT,save_record
    record(repo,amount=15000)
    revision=store.save(repo,data(repo,1234),0)
    path=tmp_path/'legacy.json'
    save_record(path,dict(format=FORMAT,name='Octubre sintético',date='2026-10-16',saved_at='2026-10-16T12:00:00',
        card_id='card',card_label='Tarjeta sintética',target_cents=10000,own_cents=500,
        rows=[dict(item=dict(receivable_id='order:old:mama',user_id='mama',user_name='Familiar sintético',
            source_name='Pedido anterior',source_date='2026-10-01',sale_cents=20000,paid_cents=15000,remaining_cents=5000),
            contributions=[dict(amount_cents=1234,included=True)])]))
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *args:(str(path),'JSON'))
    captured=[];create_application([]);dialog=CashReviewDialog(repo)
    monkeypatch.setattr(dialog,'show_text',lambda title,text:captured.append((title,text)))
    old_cuts=[]
    monkeypatch.setattr(dialog,'show_old_cut',old_cuts.append)
    before=repo.database.connection.total_changes;financial_before=financial(repo)
    dialog.open_old_cut();dialog.show_history()
    assert old_cuts[0]['rows'][0]['item']['source_name']=='Pedido anterior'
    assert old_cuts[0]['rows'][0]['contributions']==[dict(amount_cents=1234,included=True)]
    assert 'Pedido sintético old' in dialog.history_text and 'global' in dialog.history_text
    dialog.history_menu.close()
    assert sum(e['amount_cents'] for e in dialog.snapshot()['manual_counts'])==1234
    assert store.latest(repo,'card')[0]==revision
    assert repo.database.connection.total_changes==before and financial(repo)==financial_before
    dialog.close()


def test_cash_progress_and_breakdown_update_immediately_without_saving(repo):
    record(repo,amount=15000)
    create_application([]);dialog=CashReviewDialog(repo)
    before=financial(repo);changes=repo.database.connection.total_changes
    row=next(r for r in dialog.rows if r['available']==15000)
    dialog.physical.setText('200.00')
    row['field'].setText('50.00')
    assert dialog.progress.value()==25
    assert 'Contabilizado: $50.00 MXN' in dialog.summary.text()
    assert 'Abonos registrados (referencia): $150.00 MXN' in dialog.summary.text()
    dialog.extra.setText('25.00')
    assert dialog.progress.value()==37
    assert 'Total identificado: $75.00 MXN' in dialog.summary.text()
    row['checked'].setChecked(False)
    assert dialog.progress.value()==12
    row['checked'].setChecked(True)
    assert dialog.progress.value()==100
    dialog.extra.setText('0.00')
    assert dialog.progress.value()==100 and 'cuadra' in dialog.summary.text()
    row['field'].clear()
    assert not dialog.progress.isEnabled() and dialog.progress.value()==0
    assert 'Completa o corrige' in dialog.summary.text() and not dialog.save_button.isEnabled()
    row['field'].setText('151.00')
    assert dialog.progress.isEnabled()
    row['field'].setText('1.001')
    assert not dialog.progress.isEnabled()
    row['field'].setText('150.00')
    assert dialog.progress.isEnabled() and dialog.progress.value()==75
    assert financial(repo)==before and repo.database.connection.total_changes==changes
    dialog.dirty=False;dialog.close()


def test_bulk_and_partial_selection_never_duplicate_or_invent_cash(repo,monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    record(repo,amount=25000)
    create_application([]);dialog=CashReviewDialog(repo)
    before=financial(repo);changes=repo.database.connection.total_changes
    dialog.physical.setText('250.00')
    empty=next(row for row in dialog.rows if not row['available'])
    assert empty['checked'].isEnabled() and empty['field'].isEnabled()
    empty['checked'].setChecked(True)
    assert empty['checked'].isChecked()
    dialog.mark_all_button.click()
    assert sum(e['amount_cents'] for e in dialog.snapshot()['manual_counts'])==40000
    assert dialog.progress.value()==100
    parent=dialog.rows[0]['item'].parent()
    parent.setSelected(True)
    for row in dialog.rows:row['item'].setSelected(True)
    assert len(dialog.selected_rows())==len(dialog.rows)
    monkeypatch.setattr(QInputDialog,'getText',lambda *args:('125.50',True))
    dialog.partial_selection_button.click()
    assert sum(e['amount_cents'] for e in dialog.snapshot()['manual_counts'])==12550
    assert dialog.progress.value()==50
    dialog.partial_selection_button.click()
    assert sum(e['amount_cents'] for e in dialog.snapshot()['manual_counts'])==12550
    previous=dialog.snapshot()
    monkeypatch.setattr(QInputDialog,'getText',lambda *args:('250.01',True))
    dialog.partial_selection_button.click()
    assert sum(e['amount_cents'] for e in dialog.snapshot()['manual_counts'])==25001
    previous=dialog.snapshot()
    monkeypatch.setattr(QInputDialog,'getText',lambda *args:('-1',True))
    dialog.partial_selection_button.click()
    assert dialog.snapshot()==previous
    monkeypatch.setattr(QInputDialog,'getText',lambda *args:('999',False))
    dialog.partial_selection_button.click()
    assert dialog.snapshot()==previous
    dialog.clear_selection_button.click()
    assert not dialog.snapshot()['manual_counts'] and dialog.progress.value()==0
    dialog.mark_selection_button.click()
    assert sum(e['amount_cents'] for e in dialog.snapshot()['manual_counts'])==40000
    assert financial(repo)==before and repo.database.connection.total_changes==changes
    dialog.dirty=False;dialog.close()


def test_old_cut_resumes_inline_and_saved_changes_survive_reopen(repo,monkeypatch,tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog,QFileDialog
    from valenza.gui.preparation_record import FORMAT,save_record
    create_application([]);dialog=CashReviewDialog(repo)
    before=financial(repo);changes=repo.database.connection.total_changes
    record_data=dict(format=FORMAT,name='Corte sintético',date='2026-10-17',saved_at='2026-10-17T10:00:00',
        card_id='card',card_label='Tarjeta sintética',target_cents=10000,own_cents=500,
        rows=[dict(item=dict(receivable_id='historical-row',user_id='mama',user_name='Persona sintética',
        source_name='Pedido del corte',source_date='2026-10-01',sale_cents=5000,paid_cents=0,remaining_cents=5000),
        contributions=[dict(amount_cents=2000,included=True),dict(amount_cents=3000,included=False)])])
    path=tmp_path/'cut.json';save_record(path,record_data)
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *args:(str(path),'JSON'))
    monkeypatch.setattr(QDialog,'exec',lambda *args:pytest.fail('No secondary dialog is allowed'))
    dialog.open_old_cut()
    assert dialog.physical.text()=='100.00' and dialog.extra.text()=='5.00'
    assert dialog.physical_label.text()=='Objetivo del corte'
    assert dialog.rows[0]['field'].text()=='20.00' and dialog.rows[0]['checked'].isChecked()
    assert dialog.progress.value()==25
    marks=list(dialog.product_marks.values())
    assert marks[0].checkState(0)==Qt.CheckState.Checked and marks[1].checkState(0)==Qt.CheckState.Unchecked
    assert financial(repo)==before and repo.database.connection.total_changes==changes
    dialog.rows[0]['field'].setText('30.00');marks[1].setCheckState(0,Qt.CheckState.Checked)
    dialog.save_review();dialog.close()
    again=CashReviewDialog(repo)
    assert again.rows[0]['share']['source_name']=='Pedido del corte'
    assert again.rows[0]['field'].text()=='30.00'
    assert again.physical.text()=='100.00' and again.progress.value()==35
    assert all(item.checkState(0)==Qt.CheckState.Checked for item in again.product_marks.values())
    assert financial(repo)==before
    again.show();create_application([]).processEvents()
    again.grab().save(str(tmp_path/'resumed-cut-inline.png'))
    again.close()


def test_history_resumes_selected_revision_inline_and_saves_new_revision(repo):
    create_application([]);dialog=CashReviewDialog(repo)
    row=next(r for r in dialog.rows if r['share']['order_id']=='old')
    dialog.physical.setText('100.00');row['field'].setText('20.00');dialog.save_review()
    row['field'].setText('40.00');dialog.save_review()
    before=financial(repo);changes=repo.database.connection.total_changes
    dialog.show_history()
    dialog.history_menu.actions()[-1].trigger();dialog.history_menu.close()
    row=next(r for r in dialog.rows if r['share']['order_id']=='old')
    assert row['field'].text()=='20.00' and dialog.progress.value()==20
    assert repo.database.connection.total_changes==changes
    row['field'].setText('25.00');dialog.save_review()
    assert len(store.history(repo,'card'))==3 and financial(repo)==before
    dialog.close()


def test_independent_count_without_receipts_saves_reopens_and_does_not_pay_anything(repo):
    create_application([])
    before=financial(repo);balances=repo.dashboard_summary()
    dialog=CashReviewDialog(repo)
    row=next(r for r in dialog.rows if r['share']['order_id']=='old')
    assert row['available']==0 and row['field'].isEnabled() and row['checked'].isEnabled()
    dialog.physical.setText('1000.00')
    row['checked'].setChecked(True)
    assert row['field'].text()=='200.00' and dialog.progress.value()==20
    row['field'].setText('1000.00')
    assert dialog.progress.value()==100
    dialog.save_review()
    state=store.latest(repo,'card')[1]
    assert state['entries']==[] and state['manual_counts'][0]['amount_cents']==100000
    dialog.close()
    again=CashReviewDialog(repo)
    loaded=next(r for r in again.rows if r['share']['order_id']=='old')
    assert loaded['field'].text()=='1000.00' and loaded['checked'].isChecked()
    assert again.progress.value()==100
    assert financial(repo)==before and repo.dashboard_summary()==balances
    captured=[];again.show_text=lambda title,text:captured.append(text)
    again.show_history()
    assert 'conteo independiente: $1,000.00 MXN' in again.history_text
    again.history_menu.close()
    again.close()


def test_manual_count_validation_rejects_duplicates_and_mixed_receipt_counting(repo):
    record(repo,amount=15000)
    source=data(repo,1000)
    manual=dict(receivable_id='order:old:mama',amount_cents=50000,label='Mi cuenta independiente')
    with pytest.raises(ValueError):store.save(repo,dict(source,manual_counts=[manual]),0)
    with pytest.raises(ValueError):store.save(repo,dict(source,entries=[],manual_counts=[manual,manual]),0)
    before=financial(repo)
    revision=store.save(repo,dict(source,entries=[],manual_counts=[manual]),0)
    repo.cancel_user_payment('global',reason='Synthetic cancellation')
    after=financial(repo)
    assert store.save(repo,dict(source,entries=[],manual_counts=[manual]),revision)==revision
    assert financial(repo)==after

def test_new_count_is_an_explicit_reset_without_reusing_or_destroying_history(repo,monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    record(repo,amount=15000)
    first=data(repo,5000);revision=store.save(repo,first,0)
    create_application([]);dialog=CashReviewDialog(repo)
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
    before=financial(repo);changes=repo.database.connection.total_changes
    dialog.new_count()
    assert not dialog.snapshot()['manual_counts'] and dialog.snapshot()['physical_cents']==0
    assert repo.database.connection.total_changes==changes
    assert store.latest(repo,'card')==(revision,first)
    row=next(r for r in dialog.rows if r['share']['order_id']=='old')
    assert '$200.00 MXN' in row['item'].text(1)
    dialog.save_review()
    assert len(store.history(repo,'card'))==2 and financial(repo)==before
    assert not store.latest(repo,'card')[1]['entries']
    dialog.close()
