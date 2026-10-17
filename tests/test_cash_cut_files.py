import json

from test_global_receipts import repo
from valenza.gui.app import create_application
from valenza.gui.cash_review import CashReviewDialog
from valenza.gui.cash_review import QFileDialog


def test_json_roundtrip_and_progress_without_physical(repo, tmp_path, monkeypatch):
    app = create_application([])
    dialog = CashReviewDialog(repo)
    row = next(row for row in dialog.rows if row['reference'] > 0)
    row['checked'].setChecked(True)
    assert dialog.progress.value() > 0
    dialog.extra.setText('1.00')
    expected = dialog.snapshot()
    progress = dialog.progress.value()
    path = tmp_path / 'mi-corte.json'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(path), ''))
    dialog.save_button.click()
    assert json.loads(path.read_text(encoding='utf-8')) == expected
    assert str(path) in dialog.status.text()
    second_path = tmp_path / 'otro-corte.json'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(second_path), ''))
    dialog.save_cut()
    assert second_path.exists() and path.exists()
    row['checked'].setChecked(False)
    dialog.extra.setText('0')
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(path), ''))
    dialog.old_button.click()
    assert dialog.snapshot() == expected
    assert dialog.progress.value() == progress
    assert not dialog.dirty
    dialog.close()
    app.processEvents()


def test_cancel_save_keeps_unsaved_count(repo, monkeypatch):
    app = create_application([])
    dialog = CashReviewDialog(repo)
    dialog.extra.setText('2')
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: ('', ''))
    dialog.save_cut()
    assert dialog.dirty
    dialog.dirty = False
    dialog.close()
    app.processEvents()


def test_browse_open_and_export_saved_counts(repo, tmp_path, monkeypatch):
    from valenza.gui.cash_review_history import QFileDialog as HistoryFiles
    app=create_application([])
    dialog=CashReviewDialog(repo)
    dialog.extra.setText('12.34')
    dialog.save_review()
    first=dialog.snapshot()
    dialog.extra.setText('56.78')
    dialog.save_review()
    dialog.show_history()
    browser=dialog.history_dialog
    assert browser.list.topLevelItemCount()==2
    assert '56.78' in browser.details.toPlainText()
    browser.list.setCurrentItem(browser.list.topLevelItem(1))
    assert '12.34' in browser.details.toPlainText()
    path=tmp_path/'old-count.json'
    monkeypatch.setattr(HistoryFiles,'getSaveFileName',lambda *args:(str(path),''))
    browser.export_button.click()
    assert json.loads(path.read_text(encoding='utf-8'))==first
    assert dialog.extra.text()=='56.78'
    browser.open_button.click()
    assert dialog.snapshot()==first and not dialog.dirty
    dialog.close();app.processEvents()
