"""Capture isolated synthetic clarity workflows; never opens a default database."""
import json
import sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog,QMessageBox

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from test_ux_block1 import window,settle


def main():
    stage=sys.argv[1]
    output=Path(sys.argv[2]).resolve();output.mkdir(parents=True,exist_ok=True)
    fixture=window.__wrapped__(output)
    app,ui,db=next(fixture)
    assert db.encrypted
    geometry=app.primaryScreen().availableGeometry()
    assert geometry.width()>=1920 and geometry.height()>=1080
    sizes=[]
    for width,height in ((680,480),(1100,760),(1360,900)):
        ui.showNormal();ui.resize(width,height);settle(app)
        assert ui.size().toTuple()==(width,height)
        sizes.append(ui.size().toTuple())
        for index in (0,2,3,4,5):
            ui.navigation.setCurrentRow(index)
            if index==4:
                ui.cards_table.selectRow(0)
                ui.card_panels['bank'][0].setChecked(True)
                ui.bank_breakdown_toggle.setChecked(True)
            if index==0:ui.dashboard_summary_toggle.setChecked(True)
            settle(app)
            ui.grab().save(str(output/f'{index}-{width}.png'))
    ui.showMaximized();settle(app)
    ui.grab().save(str(output/'maximized.png'))
    ui.showNormal();ui.resize(1100,760);ui.navigation.setCurrentRow(5)
    def capture_editor(filename='subscription-editor.png'):
        dialog=next(d for d in ui.findChildren(QDialog) if d.isVisible())
        settle(app);dialog.grab().save(str(output/filename));dialog.reject()
    QTimer.singleShot(0,capture_editor);ui._edit_subscription('sub')
    ui.subscription_table.selectRow(0)
    def cancel_prompt():
        question=next(w for w in app.topLevelWidgets() if isinstance(w,QMessageBox) and w.isVisible())
        question.grab().save(str(output/'cancel-local-confirmation.png'))
        question.done(QMessageBox.StandardButton.No)
    QTimer.singleShot(0,cancel_prompt);ui._subscription_status(True)
    if stage=='3':
        ui.repository.record_receipt(payment_id='synthetic-receipt',receivable_id='order:normal:family',
            amount_cents=1200,received_at='2026-10-17',reference='Transferencia de prueba')
        ui.navigation.setCurrentRow(3);ui._refresh_collections()
        ui.collection_history_toggle.setChecked(True)
        ui._search_select(ui.collection_history,6,'synthetic-receipt')
        ui.collections_scroll.ensureWidgetVisible(ui.collection_mode_notice);settle(app)
        ui.grab().save(str(output/'receipt-consultation.png'))
        QTimer.singleShot(0,lambda:capture_editor('receipt-editor.png'));ui._edit_selected_receipt()
        ui.collection_return_button.click();settle(app)
        ui.grab().save(str(output/'receipt-draft-restored.png'))
        ui.repository.create_purchase(purchase_id='synthetic-history',purchased_at='2026-09-10',merchant='Compra histórica sintética',
            instrument_id='card',products=({'id':'historic-product','description':'Artículo histórico','quantity':1,'unit_price_cents':2000},),
            allocations=({'product_id':'historic-product','user_id':'family','method':'UNITS','basis':1},))
        ui._open_search_result(dict(kind='purchase',id='synthetic-history'))
        settle(app);ui.grab().save(str(output/'search-historical-selection.png'))
    ui.navigation.setCurrentRow(2);ui._open_manual_expense()
    ui.order_merchant.setText('Comercio de claridad sintético')
    ui.order_date.setText('2026-10-17')
    ui.manual_concepts.item(0,0).setText('Artículo sintético')
    ui.manual_concepts.item(0,1).setText('100.00');ui.order_charged.setText('100.00')
    ui._save_order();settle(app)
    ui.grab().save(str(output/'saved-feedback.png'))
    (output/'geometry.json').write_text(json.dumps(dict(stage=stage,screen=[geometry.width(),geometry.height()],sizes=sizes),indent=2))
    ui.close();settle(app);db.close()


if __name__=='__main__':main()
