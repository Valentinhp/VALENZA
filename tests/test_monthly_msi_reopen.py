from datetime import date

import valenza.persistence.repository as repository_module
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository
from valenza.gui.app import MainWindow, create_application
from tests.test_manual_msi_capture import plant_form
from PySide6.QtWidgets import QMessageBox


def test_manual_msi_persisted_reopened_october_november_december(tmp_path, monkeypatch):
    app = create_application([])
    path = tmp_path / 'synthetic-msi.db'
    db = LocalDatabase.open(path, 'synthetic-test-only')
    db.migrate()
    repo = FinanceRepository(db)
    repo.add_person('valen', 'VALEN', is_owner=True)
    repo.add_person('joaquin', 'JOAQUÍN')
    repo.add_institution('nu', 'NuBank')
    repo.add_instrument('nu-card', 'nu', 'NuBank sintética', 'CREDIT_CARD')
    errors = []
    monkeypatch.setattr(MainWindow, '_show_error', lambda _, message: errors.append(message))
    monkeypatch.setattr(MainWindow, '_show_information', lambda *args: None)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    window = MainWindow(database=db)
    window._open_manual_expense()
    plant_form(window)
    window.order_date.setText('2026-10-01')
    window.order_first_due_date.setText('2026-10-01')
    window.save_order_button.click()
    assert not errors
    assert len(repo.list_orders()) == 1
    window.close()
    db.close()
    app.processEvents()

    for month, future, overdue in ((10,94932,0), (11,47466,47466), (12,0,94932)):
        class FixedDate(date):
            @classmethod
            def today(cls):
                return cls(2026, month, 12)
        monkeypatch.setattr(repository_module, 'date', FixedDate)
        db = LocalDatabase.open(path, 'synthetic-test-only')
        db.migrate()
        repo = FinanceRepository(db)
        window = MainWindow(database=db)
        summary = repo.dashboard_summary()
        assert summary['scheduled_month_cents'] == 47466
        assert summary['scheduled_future_cents'] == future
        assert summary['scheduled_overdue_cents'] == overdue
        assert summary['institutional_balance_cents'] == summary['receivables_cents'] == 142398
        window._show_page(MainWindow.PAGES.index('Inicio'))
        assert 'este mes: $474.66 MXN' in window.dashboard_monthly_installments.text()
        assert 'familiares este mes: $474.66 MXN' in window.dashboard_monthly_installments.text()
        window._show_page(MainWindow.PAGES.index('Tarjetas'))
        assert window.cards_table.item(0,4).text() == '$1,423.98 MXN'
        assert window.cards_table.item(0,5).text() == '$474.66 MXN'
        assert not window.cards_table.isColumnHidden(5)
        assert not window.cards_table.isColumnHidden(6)
        from valenza.gui.app import format_money
        assert window.cards_table.item(0,6).text() == format_money(future)
        monthly = next(value for value in repo.collection_monthly_summaries().values() if value['total_cents'])
        assert (monthly['current_cents'],monthly['future_cents'],monthly['overdue_cents']) == (47466,future,overdue)
        window._show_page(MainWindow.PAGES.index('Cobros'))
        for row in range(window.collection_items.rowCount()):
            if window.collection_items.item(row,0).text() == 'JOAQUÍN':
                window.collection_items.selectRow(row)
                window._select_collection_item()
                assert window.collection_amount.text() == '474.66'
                assert window.collection_items.item(row,5).text() == '$1,423.98 MXN'
                assert window.collection_items.item(row,11).text() == '$474.66 MXN'
                break
        else:
            raise AssertionError('Missing Joaquín collection')
        assert len(repo.list_orders()) == 1
        assert len(repo.list_installments('nu-card')) == 3
        assert repo.family_statement('joaquin')['remaining_cents'] == 142398
        for table in ('institution_payment', 'user_payment'):
            assert db.connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
        assert not db.connection.execute('PRAGMA foreign_key_check').fetchall()
        window.close()
        db.close()
        app.processEvents()
