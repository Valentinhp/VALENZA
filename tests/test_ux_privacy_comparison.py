from datetime import datetime, timedelta
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel
from test_product_refunds import repository, create_discount_comparison_case
from test_bank_reconciliation import financial_snapshot
from valenza.gui.app import MainWindow, create_application, format_money


def test_private_details_keyboard_and_refresh(repository, tmp_path):
    create_discount_comparison_case(repository)
    before = financial_snapshot(repository)
    app = create_application([])
    window = MainWindow(database=repository.database, test_mode=True)
    window.show(); app.processEvents()
    assert not window.dashboard_privacy.isChecked()
    assert format_money(6029) not in window.dashboard_discount.findChild(QLabel, 'summaryAmount').text()
    window.dashboard_result_toggle.setFocus()
    QTest.keyClick(window.dashboard_result_toggle, Qt.Key.Key_Space)
    assert window.dashboard_result_toggle.isChecked()
    assert '$' not in window.dashboard_result_details.toPlainText()
    assert 'a tu cargo' not in window.dashboard_expected.text()
    assert 'a favor' not in window.dashboard_expected.text()
    window.dashboard_privacy.setFocus()
    QTest.keyClick(window.dashboard_privacy, Qt.Key.Key_Space)
    assert window.dashboard_privacy.isChecked()
    assert '$' in window.dashboard_result_details.toPlainText()
    QTest.keyClick(window.dashboard_privacy, Qt.Key.Key_Space)
    window._refresh_dashboard()
    assert '$' not in window.dashboard_result_details.toPlainText()
    assert '$' not in window.dashboard_net_pending.text()
    window.grab().save(str(tmp_path / 'privacidad.png'))
    assert financial_snapshot(repository) == before
    reopened = MainWindow(database=repository.database, test_mode=True)
    assert not reopened.dashboard_privacy.isChecked()
    reopened.close()
    window.close()


def test_live_comparison_dates_types_keyboard_and_immutable_history(repository, tmp_path):
    create_discount_comparison_case(repository)
    before = financial_snapshot(repository)
    app = create_application([])
    window = MainWindow(database=repository.database, test_mode=True)
    window.show(); window._show_page(4); app.processEvents()
    row = next(r for r in range(window.cards_table.rowCount()) if window.cards_table.item(r,12).text() == 'card')
    window.cards_table.selectRow(row)
    window.card_panels['bank'][0].setChecked(True)
    window.bank_query_type.setCurrentIndex(window.bank_query_type.findData('TOTAL'))
    window.bank_total_confirmed.setChecked(True)
    window.bank_query_amount.setFocus()
    QTest.keyClicks(window.bank_query_amount, '542.58')
    assert 'coinciden' in window.bank_query_feedback.text()
    window.bank_query_save.setFocus()
    QTest.keyClick(window.bank_query_save, Qt.Key.Key_Space)
    saved = repository.list_bank_reconciliation_history()
    assert len(saved) == 1 and saved[0]['difference_cents'] == 0
    window.bank_query_amount.setText('550.00')
    assert 'El banco muestra más' in window.bank_query_feedback.text()
    window.bank_query_amount.setText('500.00')
    assert 'Valenza muestra más' in window.bank_query_feedback.text()
    window.bank_query_type.setCurrentIndex(window.bank_query_type.findData('MONTHLY'))
    assert 'No comparable' in window.bank_query_feedback.text()
    window.bank_query_type.setCurrentIndex(window.bank_query_type.findData('TOTAL'))
    window.bank_date_manual.setChecked(True)
    window.bank_query_date.setText((datetime.now().astimezone()-timedelta(days=1)).isoformat(timespec='seconds'))
    window.bank_query_amount.setText('542.58')
    assert 'No comparable' in window.bank_query_feedback.text()
    window.bank_query_save.click()
    history = repository.list_bank_reconciliation_history()
    old = next(q for q in history if q['id'] != saved[0]['id'])
    assert old['difference_cents'] is None and not old['comparable']
    assert next(q for q in history if q['id'] == saved[0]['id']) == saved[0]
    assert financial_snapshot(repository) == before
    window.cards_scroll.ensureWidgetVisible(window.bank_query_save)
    app.processEvents()
    window.grab().save(str(tmp_path / 'comparacion.png'))
    window.close()
