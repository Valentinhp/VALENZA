from PySide6.QtCore import QDate
from PySide6.QtWidgets import QLabel
from test_ux_block1 import window, snapshot, settle
from valenza.gui.clarity_text import MONTHLY_BASES_EXPLANATION


def test_month_changes_projection_not_current_balances_and_never_writes(window):
    app,ui,db=window
    before=snapshot(db)
    balances=lambda: [w.findChild(QLabel,'summaryAmount').text() for w in
        (ui.dashboard_personal,ui.dashboard_receivables,ui.dashboard_msi)]
    original=balances()
    for month in (9,10,11):
        ui.dashboard_period_picker.setDate(QDate(2026,month,1));settle(app)
        assert balances()==original
        assert MONTHLY_BASES_EXPLANATION in ui.dashboard_monthly_installments.text()
        assert 'actuales' in ui.dashboard_balance_scope.text()
    assert snapshot(db)==before


def test_both_breakdowns_explain_distinct_bases_without_exposing_private_result(window):
    app,ui,db=window
    ui.navigation.setCurrentRow(4);ui.cards_table.selectRow(0);settle(app)
    assert MONTHLY_BASES_EXPLANATION in ui.card_detail.text()
    ui.navigation.setCurrentRow(0)
    ui.dashboard_privacy.setChecked(False)
    ui.dashboard_result_toggle.setChecked(True);settle(app)
    assert 'ocultos' in ui.dashboard_result_details.toPlainText()
    assert 'Costo efectivo:' not in ui.dashboard_result_details.toPlainText()
