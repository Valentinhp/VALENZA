"""Native crashes must fail a child process, never take down the test runner."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


CHILD = r'''
import ctypes
import sys
from pathlib import Path
if sys.platform == 'win32':
    # Do not leave Windows application-error dialogs after a native test crash.
    ctypes.windll.kernel32.SetErrorMode(0x8003)
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton
import shiboken6
from valenza.gui.app import MainWindow, create_application
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository

def snapshot(db):
    names = db.connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return {name: [tuple(row) for row in db.connection.execute('SELECT * FROM "'+name+'" ORDER BY rowid')]
            for (name,) in names}

def settle():
    for _ in range(5):
        app.processEvents()

app = create_application([])
for font in ('segoeui.ttf', 'seguisb.ttf', 'georgia.ttf'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
scenario = sys.argv[1]
for cycle in range(3):
    path = Path.cwd() / f'synthetic-lifecycle-{cycle}.db'
    db = LocalDatabase.open(path, 'synthetic-only')
    assert db.encrypted
    db.migrate()
    repo = FinanceRepository(db)
    repo.add_person('owner', 'Synthetic owner', is_owner=True)
    repo.add_person('family', 'Synthetic family')
    repo.add_institution('bank', 'Synthetic bank')
    repo.add_instrument('card', 'bank', 'Synthetic card', 'CREDIT_CARD')
    repo.create_order(order_id='normal', ordered_at='2026-09-05', merchant='Synthetic store',
        instrument_id='card', original_cents=150000, discount_cents=0, charged_cents=150000,
        allocations=({'user_id':'owner', 'amount_cents':50000}, {'user_id':'family', 'amount_cents':100000}))
    before = snapshot(db)
    changes = db.connection.total_changes
    ui = MainWindow(database=db, test_mode=True)
    ui.show()
    settle()
    assert not ui.grab().isNull()  # This is where the native access violation occurred.
    if scenario == 'render':
        for size in ((680,480), (1100,760), (820,600)):
            ui.resize(*size)
            for page in range(7):
                ui.navigation.setCurrentRow(page)
                settle()
                assert not ui.grab().isNull()
        ui.navigation.setCurrentRow(4)
        for toggle, content in ui.card_panels.values():
            toggle.setChecked(True)
            for button in content.findChildren(QPushButton):
                if button.isCheckable():
                    button.setChecked(True)
            settle()
            assert not ui.grab().isNull()
            toggle.setChecked(False)
    elif scenario == 'dialogs':
        ui._open_manual_expense()
        settle()
        ui.manual_dialog.reject()
        ui._open_search()
        search = ui._search_dialog
        search.input.setText('Synthetic')
        search.reject()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        settle()
        assert not shiboken6.isValid(search)
        assert ui._search_dialog is None
    elif scenario == 'pending_search':
        ui._open_search()
        ui._search_dialog.input.setText('Synthetic')
        assert ui._search_dialog.timer.isActive()
    assert snapshot(db) == before
    assert db.connection.total_changes == changes
    ui.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    settle()
    QTest.qWait(220)  # A deferred search must not run against the closed window/database.
    assert not shiboken6.isValid(ui)
    reopened = LocalDatabase.open(path, 'synthetic-only')
    assert snapshot(reopened) == before
    assert reopened.integrity_report()['ok']
    reopened.close()
print('LIFECYCLE_OK', scenario, flush=True)
'''


@pytest.mark.parametrize('platform', ['offscreen', 'windows'] if sys.platform == 'win32' else ['offscreen'])
@pytest.mark.parametrize('scenario', ['render', 'dialogs', 'pending_search'])
def test_encrypted_window_lifecycle_in_isolated_process(tmp_path, platform, scenario):
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = platform
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
    result = subprocess.run([sys.executable, '-B', '-X', 'faulthandler', '-c', CHILD, scenario],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=45)
    (tmp_path / 'lifecycle.log').write_text(result.stdout + '\n' + result.stderr, encoding='utf-8')
    assert result.returncode == 0, f'exit={result.returncode}\n{result.stdout}\n{result.stderr}'
    assert 'LIFECYCLE_OK' in result.stdout
    assert 'Traceback' not in result.stderr
    assert 'Internal C++ object' not in result.stderr
