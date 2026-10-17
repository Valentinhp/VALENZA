"""Manual bank observations remain independent of financial operations."""
from datetime import datetime
from sqlcipher3 import dbapi2 as sqlite3
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from test_bank_reconciliation import repository, order, financial_snapshot
from test_home_polish import synthetic, seed, MainWindow
from valenza.persistence.repository import FinanceRepository


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


@pytest.mark.parametrize('delta', [0, 1, -1, 100, -100])
def test_exact_cent_and_duplicate_snapshot(repository, delta):
    order(repository, 'synthetic')
    before = financial_snapshot(repository)
    stamp = now()
    for _ in range(2):
        repository.record_bank_balance('card', 5000 + delta, stamp)
    history = repository.list_bank_reconciliation_history('card')
    assert len(history) == 1 and history[0]['difference_cents'] == delta
    assert financial_snapshot(repository) == before


@pytest.mark.parametrize('closing,due', [('bad','2026-10-20'), ('2026-02-30','2026-03-01'),
    ('2026-10-20','2026-10-10'), ('2026-10-10',None), (None,'2026-10-20')])
def test_invalid_statement_dates_are_atomic(repository, closing, due):
    before = repository.database.connection.total_changes
    with pytest.raises(ValueError):
        repository.record_bank_balance('card', 150000, now(), balance_type='NO_INTEREST', closing_date=closing, due_date=due)
    assert repository.database.connection.total_changes == before


def test_unknown_scope_never_confirms_equal_balance(repository):
    repository.record_bank_balance('card', 0, now(), total_confirmed=False)
    saved = repository.list_bank_reconciliation_history()[0]
    assert saved['difference_cents'] is None and not saved['comparable']
    assert any('Alcance sin confirmar' in w for w in saved['warnings'])


def test_official_dates_encrypted_restore_and_later_payment(repository, tmp_path):
    order(repository, 'synthetic')
    before = financial_snapshot(repository)
    repository.record_bank_balance('card', 1500, now(), balance_type='NO_INTEREST',
        closing_date='2026-10-10', due_date='2026-10-20')
    saved = repository.list_bank_reconciliation_history()[0]
    assert saved['amount_cents'] == 1500 and saved['closing_date'] == '2026-10-10'
    assert saved['due_date'] == '2026-10-20' and saved['difference_cents'] is None
    assert saved['orientative_difference_cents'] is None
    assert financial_snapshot(repository) == before
    backup = tmp_path / 'encrypted-observations.db'
    db = repository.database
    db.create_backup(backup); db.verify_backup(backup)
    assert backup.read_bytes()[:16] != b'SQLite format 3\x00'
    repository.record_institution_payment(payment_id='global', instrument_id='card', amount_cents=125, paid_at='2026-10-16')
    assert repository.list_bank_reconciliation_history()[0] == saved
    db.restore_backup(backup, tmp_path / 'safety.db')
    restored = FinanceRepository(db)
    assert financial_snapshot(restored) == before
    assert restored.list_bank_reconciliation_history()[0] == saved


def test_failed_insert_leaves_no_partial_snapshot(repository):
    db = repository.database
    db.connection.execute("CREATE TEMP TRIGGER fail_observation BEFORE INSERT ON audit_event WHEN NEW.action='BANK_BALANCE_QUERIED' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
    before = financial_snapshot(repository)
    with pytest.raises(sqlite3.DatabaseError):
        repository.record_bank_balance('card', 0, now())
    assert not repository.list_bank_reconciliation_history()
    assert financial_snapshot(repository) == before


def test_manual_ui_sizes_dates_and_keyboard(synthetic, tmp_path, monkeypatch):
    app, repo = synthetic; seed(repo)
    before = financial_snapshot(repo)
    window = MainWindow(database=repo.database, test_mode=True)
    monkeypatch.setattr(window, '_show_information', lambda *_: None)
    window.show(); window._show_page(4)
    window.cards_table.selectRow(0)
    window.card_panels['bank'][0].setChecked(True)
    window.bank_query_type.setCurrentIndex(window.bank_query_type.findData('NO_INTEREST'))
    for width in (680, 900, 1920):
        window.resize(width, 850)
        for _ in range(8): app.processEvents()
        window.cards_scroll.ensureWidgetVisible(window.bank_query_save)
        for _ in range(8): app.processEvents()
        assert window.cards_scroll.horizontalScrollBar().maximum() == 0
        form = window.bank_form_widget
        assert window.bank_query_save.geometry().bottom() < form.height()
        assert form.geometry().bottom() < window.bank_query_feedback.geometry().top(), [
            (w.height(), w.minimumHeight(), w.maximumHeight(), w.sizeHint().height(), w.layout().spacing() if w.layout() else None)
            for w in (form, window.card_panels['bank'][1], window.card_panels['bank'][1].parentWidget())]
        assert window.card_panels['bank'][1].height() < 3000
        for field in (window.bank_query_amount, window.bank_closing_date, window.bank_due_date):
            assert field.height() >= field.minimumSizeHint().height()
        (tmp_path / f'geometry-{width}.txt').write_text(str([
            (type(w).__name__, w.geometry().getRect(), w.minimumHeight()) for w in
            (window.card_panels['bank'][1], window.bank_nu_help, window.bank_query_amount,
             window.bank_closing_date, window.bank_due_date, window.bank_query_save)]))
        window.grab().save(str(tmp_path / f'manual-{width}.png'))
        window.card_panels['bank'][1].grab().save(str(tmp_path / f'form-{width}.png'))
    window.bank_closing_date.setFocus()
    QTest.keyClick(window.bank_closing_date, Qt.Key.Key_Tab)
    assert window.bank_due_date.hasFocus()
    QTest.keyClick(window.bank_due_date, Qt.Key.Key_Backtab)
    assert window.bank_closing_date.hasFocus()
    window.bank_query_amount.setText('15.00')
    window.bank_closing_date.setText('2026-10-10'); window.bank_due_date.setText('2026-10-20')
    window.bank_query_save.click()
    assert len(repo.list_bank_reconciliation_history()) == 1
    assert repo.list_bank_reconciliation_history()[0]['due_date'] == '2026-10-20'
    assert financial_snapshot(repo) == before
    window.close()
