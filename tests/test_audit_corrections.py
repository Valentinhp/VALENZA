"""Approved audit corrections, using only encrypted synthetic fixtures."""
import random
from valenza.gui.payment_preparation import product_installment_schedule
from test_global_receipts import repo

def test_product_schedule_preserves_both_margins_including_zero_months():
    rng=random.Random(64602)
    for count in (3,6,12):
        for amounts in ([2,2],[1,0],[0,0],[10001,3999,1],*[ [rng.randrange(10000) for _ in range(5)] for _ in range(40)]):
            products=[dict(product_id=str(i),description=str(i),amount_cents=v) for i,v in enumerate(amounts)]
            plan=product_installment_schedule(products,count)
            each,residual=divmod(sum(amounts),count)
            assert [sum(p['amount_cents'] for p in row) for row in plan]==[each+(i<residual) for i in range(count)]
            assert [sum(row[i]['amount_cents'] for row in plan) for i in range(len(amounts))]==list(amounts)
            assert all(p['amount_cents']>=0 for row in plan for p in row)
            assert all(p['total_share_cents']==amounts[i] for row in plan for i,p in enumerate(row))
            assert product_installment_schedule(products,count)==plan

def test_tab_order_has_no_warnings_and_keyboard_reaches_footer(repo):
    from PySide6.QtCore import Qt,qInstallMessageHandler
    from PySide6.QtTest import QTest
    from valenza.gui.app import create_application,MainWindow
    app=create_application([]);messages=[]
    previous=qInstallMessageHandler(lambda kind,context,text:messages.append(text) if 'setTabOrder' in text else None)
    try:window=MainWindow(database=repo.database,test_mode=True)
    finally:qInstallMessageHandler(previous)
    assert not messages
    window.show();window._open_manual_expense();app.processEvents()
    window.save_order_button.setEnabled(True)  # Test the enabled footer focus chain, without submitting.
    window.manual_dialog.activateWindow();window.manual_review_button.setFocus();app.processEvents()
    QTest.keyClick(window.manual_review_button,Qt.Key.Key_Tab);app.processEvents()
    assert window.cancel_manual_button.hasFocus()
    QTest.keyClick(window.cancel_manual_button,Qt.Key.Key_Tab);app.processEvents()
    assert window.save_order_button.hasFocus()
    QTest.keyClick(window.save_order_button,Qt.Key.Key_Backtab);app.processEvents()
    assert window.cancel_manual_button.hasFocus()
    window.manual_dialog.reject();window.close()
