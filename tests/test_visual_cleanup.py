"""Read-only UI checks against a synthetic, encrypted database."""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QLocale
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from test_product_refunds import repository
from test_home_initial_restore import seed, tables
from valenza.gui.app import MainWindow, create_application
from valenza.gui.warm_finance import date_label, RecordedDateDelegate


def test_visual_cleanup_preserves_money_history_and_keyboard_access(repository):
    seed(repository)
    repository.record_bank_balance('card', 250000,
        datetime.now().astimezone().isoformat(timespec='seconds'),
        balance_type='NO_INTEREST', period='2026-10')
    before = tables(repository)
    changes = repository.database.connection.total_changes
    app = create_application([])
    window = MainWindow(database=repository.database, test_mode=True)
    window.resize(1100, 760)
    window.show()
    window.dashboard_period_picker.setDate(QDate(2026, 10, 1))
    output = Path('artifacts/visual-cleanup')
    output.mkdir(parents=True, exist_ok=True)
    try:
        assert window.dashboard_debt.findChild(QLabel, 'summaryAmount').text() == '$2,500.00 MXN'
        assert window.dashboard_msi.findChild(QLabel, 'summaryAmount').text() == '$13,500.00 MXN'
        assert 'original' not in window.dashboard_period_note.text()
        assert not window.dashboard_privacy.isChecked()
        assert '$' not in window.dashboard_discount.findChild(QLabel, 'summaryAmount').text()
        for index, page in enumerate(window.PAGES):
            window._show_page(index)
            if page == 'Tarjetas':
                row = next(r for r in range(window.cards_table.rowCount()) if window.cards_table.item(r, 12).text() == 'card')
                window.cards_table.selectRow(row)
                window.card_panels['bank'][0].setChecked(True)
                assert window.card_detail_scroll.isHidden()
                assert 'calendario' in window.card_period_notice.text().lower()
                assert 'Total incompleto' in window.bank_query_comparison.text()
                assert len(window.bank_query_comparison.text().splitlines()) <= 5
                window.card_detail_toggle.setFocus()
                QTest.keyClick(window.card_detail_toggle, Qt.Key.Key_Space)
                assert window.card_detail_scroll.isVisible()
                QTest.keyClick(window.card_detail_toggle, Qt.Key.Key_Space)
                assert window.card_detail_scroll.isHidden()
                assert 'Programación vigente' in window.bank_breakdown.text() or 'Parte identificada' in window.bank_breakdown.text()
                assert 'plan:msi-' not in window.bank_breakdown.text()
            app.processEvents()
            window.grab().save(str(output / f'{index:02d}.png'))
        # Original ISO values remain available for sorting and selection.
        assert window.orders_table.item(0, 1).text().startswith('2026-')
        assert isinstance(window.orders_table.itemDelegateForColumn(1), RecordedDateDelegate)
        assert tables(repository) == before
        assert repository.database.connection.total_changes == changes
    finally:
        window.close()
        app.processEvents()


def test_recorded_dates_display_in_spanish_without_timezone_conversion():
    app = create_application([])
    delegate = RecordedDateDelegate()
    original = '2026-12-31T23:30:00-06:00'
    assert delegate.displayText(original, QLocale()) == '31 dic 2026 · 23:30'
    assert date_label('2027-01-01') == '1 ene 2027'
    assert date_label('Sin consulta') == 'Sin consulta'
    assert date_label(None) == ''
    app.processEvents()


def test_storage_error_hides_sql_and_keeps_non_sensitive_log(caplog):
    from valenza.gui.errors import user_error
    from valenza.persistence.database import DATABASE_ERRORS
    error = DATABASE_ERRORS[0]('internal SQL synthetic-secret')
    assert 'vuelve a intentarlo' in user_error(error)
    assert 'synthetic-secret' not in caplog.text
    assert type(error).__name__ in caplog.text
    assert user_error(ValueError('Revisa el importe.')) == 'Revisa el importe.'
