from pathlib import Path

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QLineEdit

from valenza.gui.app import create_application, open_database_with_prompt
from valenza.gui.unlock import UnlockDialog
from valenza.persistence.database import LocalDatabase


@pytest.fixture
def application():
    app = create_application([])
    font = QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    if font >= 0:
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(font)[0], 10))
    return app


def test_password_visibility_focus_and_cancel(application, tmp_path):
    dialog = UnlockDialog()
    dialog.show()
    application.processEvents()
    assert dialog.password.hasFocus()
    assert dialog.password.echoMode() == QLineEdit.EchoMode.Password
    dialog.password.setText('synthetic-test-only')
    dialog.password.setCursorPosition(4)
    dialog.visibility.click()
    assert dialog.password.echoMode() == QLineEdit.EchoMode.Normal
    assert dialog.password.hasFocus() and dialog.password.cursorPosition() == 4
    dialog.visibility.click()
    assert dialog.password.echoMode() == QLineEdit.EchoMode.Password
    dialog.password.clear()
    assert dialog.grab().save(str(tmp_path / 'desbloqueo.png'))
    dialog.show_error()
    application.processEvents()
    assert dialog.error.isVisible() and dialog.password.hasFocus()
    assert dialog.grab().save(str(tmp_path / 'desbloqueo-error.png'))
    for button in (dialog.cancel_button, dialog.unlock_button, dialog.visibility):
        assert dialog.rect().contains(button.rect().translated(button.mapTo(dialog, button.rect().topLeft())))
    QTest.keyClick(dialog.password, Qt.Key.Key_Escape)
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert not dialog.password.text()


def test_synthetic_encrypted_unlock_and_wrong_password_retry(application, tmp_path, monkeypatch):
    path = tmp_path / 'synthetic-encrypted.db'
    db = LocalDatabase.open(path, 'synthetic-test-only')
    db.migrate()
    db.close()
    original = path.read_bytes()
    import valenza.gui.app as module
    actual_exec = UnlockDialog.exec
    attempts = []
    def exercise(dialog):
        index = len(attempts)
        attempts.append(index)
        if index:
            assert not dialog.error.isHidden()
        def enter():
            dialog.password.setText('synthetic-wrong' if index == 0 else 'synthetic-test-only')
            QTest.keyClick(dialog.password, Qt.Key.Key_Return)
        QTimer.singleShot(0, enter)
        return actual_exec(dialog)
    monkeypatch.setattr(module.UnlockDialog, 'exec', exercise)
    opened = open_database_with_prompt(application, path)
    assert opened is not None and len(attempts) == 2
    assert opened.integrity_report()['ok']
    opened.close()
    assert path.read_bytes() == original


def test_cancel_unlock_does_not_open_database(application, tmp_path, monkeypatch):
    import valenza.gui.app as module
    actual_exec = UnlockDialog.exec
    def cancel(dialog):
        QTimer.singleShot(0, dialog.reject)
        return actual_exec(dialog)
    monkeypatch.setattr(module.UnlockDialog, 'exec', cancel)
    monkeypatch.setattr(module.LocalDatabase, 'open', lambda *args: pytest.fail('Database opened during cancellation'))
    path = tmp_path / 'synthetic-never-created.db'
    assert open_database_with_prompt(application, path) is None
    assert not path.exists()
