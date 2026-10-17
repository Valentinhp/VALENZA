"""Reproducible native Qt visual review with encrypted synthetic fixtures only.

Run with the audit sitecustomize guard on PYTHONPATH. Never invokes app.main.
"""
import ctypes
import json
import os
from pathlib import Path
import sys
import tempfile
from html import escape
from datetime import datetime

if sys.platform == 'win32':
    ctypes.windll.kernel32.SetErrorMode(0x8003)
    os.environ['QT_QPA_PLATFORM'] = 'windows'

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'private/codex/auditoria-integral-20261016'
OUT = ROOT / 'artifacts/tarjetas-interfaz'
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / 'tests'))
from test_home_polish import synthetic, seed
from test_bank_reconciliation import financial_snapshot
from test_cards_refund_ui import settle, assert_siblings_fit, assert_combo_text_fits
from valenza.gui.app import MainWindow
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QPushButton, QWidget, QMessageBox

original_open = LocalDatabase.open.__func__


def safe_open(cls, path, *args, **kwargs):
    if not Path(path).resolve().is_relative_to(AUDIT):
        raise RuntimeError('Only isolated audit database paths are permitted')
    return original_open(cls, path, *args, **kwargs)


LocalDatabase.open = classmethod(safe_open)
fixture = synthetic.__wrapped__(Path(tempfile.mkdtemp(prefix='native-evidence-', dir=AUDIT)))
app, repo = next(fixture)
seed(repo)
repo.record_bank_balance('card1', 25000, datetime.now().astimezone().isoformat(timespec='seconds'))
before = financial_snapshot(repo)
changes = repo.database.connection.total_changes
window = MainWindow(database=repo.database, test_mode=True)
window.setWindowTitle('Valenza - revision visual - SOLO SINTETICOS')
window.show()
window.navigation.setCurrentRow(4)
row = next(r for r in range(window.cards_table.rowCount()) if window.cards_table.item(r,12).text() == 'card1')
window.cards_table.selectRow(row)
captured = []


def capture(name, target):
    settle(app)
    window.cards_scroll.ensureWidgetVisible(target)
    settle(app)
    assert window.cards_scroll.horizontalScrollBar().maximum() == 0
    assert window.grab().save(str(OUT / (name + '.png')))
    captured.append(dict(name=name, size=window.size().toTuple(), maximized=window.isMaximized()))


def check_panel(panel):
    assert_siblings_fit(panel)
    for child in panel.findChildren(QWidget):
        if child.isVisible() and child.layout() is not None:
            assert_siblings_fit(child)


def run_review():
    global window
    try:
        for size_name, size in [('pequena', (680,600)), ('normal', (1100,760)), ('maximizada', None)]:
            if size:
                window.showNormal(); window.resize(*size)
            else:
                window.showMaximized()
            settle(app)
            for toggle, _ in window.card_panels.values():
                toggle.setChecked(False)
            capture(size_name + '-resumen', window.cards_table)
            toggle, bank = window.card_panels['bank']; toggle.setChecked(True)
            for kind in ('NO_INTEREST', 'TOTAL', 'OTHER'):
                window.bank_query_type.setCurrentIndex(window.bank_query_type.findData(kind))
                window.bank_query_amount.setText('123.45')
                settle(app); check_panel(bank)
                assert_combo_text_fits(window.bank_query_type)
                capture(size_name + '-formulario-' + kind.lower(), window.bank_form_widget)
            window.bank_query_type.setCurrentIndex(window.bank_query_type.findData('NO_INTEREST'))
            for name, target in [('Opciones avanzadas', window.bank_query_date),
                                 ('Tarjetas de una misma línea', window.bank_scope_save),
                                 ('Ver desglose bancario', window.bank_breakdown),
                                 ('Ver historial de consultas', window.bank_history)]:
                button = next(b for b in bank.findChildren(QPushButton) if b.text() == name)
                button.setChecked(True)
                if target is window.bank_history:
                    window.bank_history.selectRow(0)
                settle(app); check_panel(bank)
                slug = {window.bank_query_date:'opciones', window.bank_scope_save:'linea',
                        window.bank_breakdown:'desglose', window.bank_history:'historial'}[target]
                capture(size_name + '-' + slug, target)
                if target is window.bank_history:
                    capture(size_name + '-detalle-historial', window.bank_history_detail)
                button.setChecked(False)
            for key in ('payments', 'msi', 'admin'):
                toggle.setChecked(False)
                section_toggle, panel = window.card_panels[key]
                section_toggle.setChecked(True)
                for button in panel.findChildren(QPushButton):
                    if button.isCheckable():
                        button.setChecked(True)
                settle(app); check_panel(panel)
                capture(size_name + '-' + key, panel)
                section_toggle.setChecked(False)
            # Empty history and no selection, without deleting any fixture data.
            window.cards_table.clearSelection()
            window._select_card()
            toggle.setChecked(True)
            window.bank_history_toggle.setChecked(True)
            capture(size_name + '-sin-seleccion', window.bank_query_save)
            capture(size_name + '-historial-vacio', window.bank_history)
            window.bank_history_toggle.setChecked(False)
            window.cards_table.selectRow(row)
        # Actual validation dialog, not a fabricated error label.
        window.bank_closing_date.clear(); window.bank_due_date.clear()
        window.bank_query_amount.setText('123.45')
        def capture_error():
            dialog = next(w for w in app.topLevelWidgets() if isinstance(w, QMessageBox) and w.isVisible())
            assert dialog.grab().save(str(OUT / 'validacion-fechas.png'))
            dialog.accept()
        QTimer.singleShot(250, capture_error)
        window.bank_query_save.click()
        assert financial_snapshot(repo) == before
        assert repo.database.connection.total_changes == changes
        assert repo.database.integrity_report()['ok']
        window.close()
        empty_db = LocalDatabase.open(Path(tempfile.mkdtemp(prefix='native-empty-', dir=AUDIT)) / 'empty.db', 'synthetic-only')
        empty_db.migrate()
        empty_repo = FinanceRepository(empty_db)
        empty_before = financial_snapshot(empty_repo)
        empty_changes = empty_db.connection.total_changes
        window = MainWindow(database=empty_db, test_mode=True)
        window.setWindowTitle('Valenza - estado vacio - SOLO SINTETICOS')
        window.show(); window.navigation.setCurrentRow(4)
        for size_name, size in [('pequena', (680,600)), ('normal', (1100,760)), ('maximizada', None)]:
            if size:
                window.showNormal(); window.resize(*size)
            else:
                window.showMaximized()
            for section_toggle, panel in window.card_panels.values():
                section_toggle.setChecked(True)
            settle(app)
            capture(size_name + '-sin-tarjetas', window.cards_empty_notice)
        assert financial_snapshot(empty_repo) == empty_before
        assert empty_db.connection.total_changes == empty_changes
        (OUT / 'revision.json').write_text(json.dumps(dict(platform=app.platformName(),
            captures=captured, financial_snapshot_unchanged=True, writes=0,
            encrypted=True), ensure_ascii=False, indent=2), encoding='utf-8')
        cards = ''.join('<figure><a href="' + escape(path.name) + '"><img loading="lazy" src="' +
                        escape(path.name) + '" alt="' + escape(path.stem) + '"></a><figcaption>' +
                        escape(path.stem.replace('-', ' ')) + '</figcaption></figure>'
                        for path in sorted(OUT.glob('*.png')))
        (OUT / 'index.html').write_text('''<!doctype html><html lang="es"><meta charset="utf-8">
<title>Tarjetas — evidencia visual</title><style>
body{font:16px Segoe UI,sans-serif;background:#f8f4ee;color:#292724;margin:24px}
main{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:20px}
figure{margin:0;padding:12px;border:1px solid #ddcfc0;border-radius:12px;background:#fffcf8}
img{width:100%;height:300px;object-fit:contain}figcaption{margin-top:8px}
</style><h1>Tarjetas: revisión visual</h1><p>46 capturas de ventanas nativas de Qt en Windows.
Datos exclusivamente sintéticos; cero movimientos creados durante la revisión.
Abre cada imagen para verla a tamaño completo.</p><main>''' + cards + '</main></html>', encoding='utf-8')
        print('NATIVE_REVIEW_OK', len(captured) + 1, flush=True)
    except BaseException:
        import traceback
        traceback.print_exc()
        app.exit(1)
        return
    window.close()
    app.quit()


QTimer.singleShot(400, run_review)
result = app.exec()
try:
    next(fixture)
except StopIteration:
    pass
sys.exit(result)
