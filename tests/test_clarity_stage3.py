from PySide6.QtWidgets import QDialog, QLabel
from test_ux_block1 import window, snapshot, settle


def prepare_receipt(ui):
    ui.repository.record_receipt(payment_id='private-technical-id',receivable_id='order:normal:family',
        amount_cents=1200,received_at='2026-10-17',reference='Transferencia de prueba')
    ui._refresh_collections()


def test_consult_is_readonly_preserves_draft_and_return_selection(window):
    app,ui,db=window
    prepare_receipt(ui)
    ui.navigation.setCurrentRow(3)
    ui.collection_filter.setCurrentIndex(ui.collection_filter.findData('FAMILY'))
    ui._search_select(ui.collection_items,7,'order:normal:family')
    ui.collection_amount.setText('7.89');ui.collection_reference.setText('Mi borrador')
    draft=[f.text() for f in (ui.collection_amount,ui.collection_received_date,ui.collection_reference)]
    before=snapshot(db);changes=db.connection.total_changes
    ui.collection_history_toggle.setChecked(True)
    ui._search_select(ui.collection_history,6,'private-technical-id')
    assert 'Consultando abono' in ui.collection_mode_notice.text()
    assert 'private-technical-id' not in ui.collection_selected_details.text()
    assert ui.collection_amount.isReadOnly() and not ui.record_collection_button.isEnabled()
    assert ui.collection_capture_form.isHidden()
    assert [f.text() for f in (ui.collection_amount,ui.collection_received_date,ui.collection_reference)]==draft
    ui.collection_return_button.click()
    assert ui.collection_filter.currentData()=='FAMILY'
    assert ui._table_id(ui.collection_items,7)=='order:normal:family'
    assert [f.text() for f in (ui.collection_amount,ui.collection_received_date,ui.collection_reference)]==draft
    assert not ui.collection_amount.isReadOnly()
    assert not ui.collection_capture_form.isHidden()
    assert snapshot(db)==before and db.connection.total_changes==changes


def test_edit_changes_original_receipt_only(window,monkeypatch):
    app,ui,db=window
    prepare_receipt(ui);ui.navigation.setCurrentRow(3)
    ui.collection_history_toggle.setChecked(True)
    ui._search_select(ui.collection_history,6,'private-technical-id')
    count=db.connection.execute('SELECT COUNT(*) FROM user_payment').fetchone()[0]
    def edit(dialog):
        assert all('private-technical-id' not in label.text() for label in dialog.findChildren(QLabel))
        dialog.reference.setText('Referencia corregida');dialog.accept()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog,'exec',edit)
    ui._edit_selected_receipt()
    assert db.connection.execute('SELECT COUNT(*) FROM user_payment').fetchone()[0]==count
    row=db.connection.execute('SELECT reference,amount_cents FROM user_payment WHERE id=?',('private-technical-id',)).fetchone()
    assert tuple(row)==('Referencia corregida',1200)


def test_result_uses_human_descriptions_not_internal_ids(window):
    app,ui,db=window
    ui.dashboard_privacy.setChecked(True);ui.dashboard_result_toggle.setChecked(True)
    text=ui.dashboard_result_details.toPlainText()
    assert 'Compra normal sintética' in text and 'Operación' in text
    assert ' · normal' not in text


def test_search_refreshes_participations_when_already_in_collections(window):
    app,ui,db=window
    ui.navigation.setCurrentRow(3)
    ui.repository.create_purchase(purchase_id='new-history',purchased_at='2026-09-10',merchant='Compra histórica nueva',
        instrument_id='card',products=({'id':'history-product','description':'Artículo','quantity':1,'unit_price_cents':2000},),
        allocations=({'product_id':'history-product','user_id':'family','method':'UNITS','basis':1},))
    before=snapshot(db);changes=db.connection.total_changes
    ui._open_search_result(dict(kind='purchase',id='new-history'))
    identity=ui._table_id(ui.collection_items,7)
    entry=next(e for e in ui.repository.list_collection_items() if e['receivable_id']==identity)
    assert entry['source_id']=='new-history'
    assert 'Compra histórica nueva' in ui.collection_mode_notice.text()
    assert snapshot(db)==before and db.connection.total_changes==changes
