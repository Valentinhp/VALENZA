from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase

from valenza.gui.app import MainWindow, create_application
from valenza.gui.pdf_import import ImportPreview
from valenza.ocr.order_import import parse_receipt, validate
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository


@pytest.fixture
def design_repo():
    app = create_application([])
    font = QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    if font >= 0:
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(font)[0], 10))
    db = LocalDatabase.open(':memory:', 'synthetic', allow_synthetic_in_memory=True)
    db.migrate()
    repo = FinanceRepository(db)
    repo.add_person('owner', 'Yo', is_owner=True)
    repo.add_person('ana', 'Ana')
    repo.add_person('luis', 'Luis')
    repo.add_institution('bank', 'Banco sintético')
    repo.add_instrument('card', 'bank', 'Tarjeta sintética', 'CREDIT_CARD')
    yield app, repo
    db.close()


def capture(path, widget, app):
    app.processEvents()
    assert widget.grab().save(str(path))


@pytest.mark.parametrize('count,size', [(0, (900, 700)), (3, (1536, 1024)), (18, (900, 700))])
def test_orders_surface_is_read_only_and_compact(design_repo, count, size, tmp_path):
    app, repo = design_repo
    for index in range(count):
        repo.create_order(order_id=str(index), ordered_at=date.today().isoformat(), merchant=f'Comercio sintético {index+1}',
            instrument_id='card', original_cents=12500, charged_cents=11500, discount_cents=1000,
            allocations=({'user_id': 'owner', 'amount_cents': 5000}, {'user_id': 'ana', 'amount_cents': 7500}),
            concepts=[dict(description='Material de oficina', amount_cents=12500, allocations={'owner': 5000, 'ana': 7500})])
    before = repo.dashboard_summary()
    changes = repo.database.connection.total_changes
    window = MainWindow(database=repo.database, test_mode=True)
    window.resize(*size)
    window.show()
    window.navigation.setCurrentRow(window.PAGES.index('Pedidos'))
    app.processEvents()
    if count:
        window.orders_table.selectRow(0)
        assert window.edit_order_button.isEnabled() and window.edit_concepts_button.isEnabled()
        assert window.orders_table.item(0, 2).text() == '$125.00 MXN'
        assert window.orders_table.item(0, 2).textAlignment() & Qt.AlignmentFlag.AlignRight
        assert '1. Compra original y descuento' in window.order_detail.toPlainText()
        assert '$115.00 MXN' in window.order_detail.toPlainText()
    else:
        assert not window.edit_order_button.isEnabled()
    assert window.orders_table.height() < 380
    assert window.orders_table.verticalScrollBar().maximum() > 0 if count > 7 else window.orders_table.verticalScrollBar().maximum() == 0
    window.order_filter.setCurrentIndex(window.order_filter.findData('ALL'))
    capture(tmp_path / 'pedidos-principal.png', window, app)
    assert repo.dashboard_summary() == before and repo.database.connection.total_changes == changes
    window.close()


@pytest.mark.parametrize('mode', ['CASH', 'MSI'])
def test_manual_warm_sections_footer_and_draft_survive(design_repo, mode, tmp_path):
    app, repo = design_repo
    before = repo.dashboard_summary()
    changes = repo.database.connection.total_changes
    window = MainWindow(database=repo.database, test_mode=True)
    window.show()
    window._open_manual_expense()
    window.manual_concepts.removeRow(0)
    window._add_manual_concept(dict(description='Equipo de trabajo compartido', amount_cents=47466,
                                   allocations={'owner': 17466, 'ana': 30000}))
    window.order_merchant.setText('Comercio sintético')
    window.order_charged.setText('474.66')
    window.order_purchase_mode.setCurrentIndex(window.order_purchase_mode.findData(mode))
    if mode == 'MSI':
        window.order_installments.setValue(3)
        window.order_first_due_date.setText(date.today().isoformat())
        window.order_amount_basis.setCurrentIndex(window.order_amount_basis.findData('INSTALLMENT'))
        assert '$1,423.98 MXN' in window.order_summary.text()
    else:
        assert '$474.66 MXN' in window.order_summary.text()
    original = deepcopy(window._read_manual_concepts())
    for width, height in [(760, 520), (620, 480), (1000, 1030)]:
        window.manual_dialog.resize(width, height)
        app.processEvents()
        for button in (window.save_order_button, window.cancel_manual_button):
            assert window.manual_dialog.rect().contains(button.rect().translated(button.mapTo(window.manual_dialog, button.rect().topLeft())))
            assert not window.manual_scroll.isAncestorOf(button)
        assert window._read_manual_concepts() == original
    window.manual_dialog.resize(1000, max(1030, window.manual_scroll.widget().sizeHint().height()+110))
    capture(tmp_path / f'nuevo-gasto-{mode.lower()}.png', window.manual_dialog, app)
    capture(tmp_path / f'formulario-{mode.lower()}-completo.png', window.manual_scroll.widget(), app)
    assert repo.dashboard_summary() == before and repo.database.connection.total_changes == changes
    window.manual_dialog.reject()
    window.close()


@pytest.mark.parametrize('single', [True, False])
def test_pdf_review_compact_summary_and_fixed_footer(design_repo, single, tmp_path):
    app, repo = design_repo
    draft = parse_receipt((Path(__file__).parent / 'fixtures_synthetic/mp_openpdf.txt').read_text(encoding='utf-8'))
    if single:
        draft['products'] = [dict(description='Servicio de mantenimiento · comprobante sintético', quantity=1, unit=25000)]
        draft.update(discount=2000, refund=0, charged=23000, paid=23000, warnings=[], review_fields=[],
                     declared_count=1, declared_subtotal=25000,
                     provenance={}, source_amounts={}, fingerprint='synthetic-one-product')
    assert validate(draft) == sum(p['unit'] * p['quantity'] for p in draft['products'])
    original = deepcopy(draft)
    before = repo.dashboard_summary()
    changes = repo.database.connection.total_changes
    dialog = ImportPreview(repo, draft)
    dialog.instrument.setCurrentIndex(dialog.instrument.findData('card'))
    dialog.assign_all('ana')
    dialog.resize(1200, 780 if not single else 600)
    dialog.show()
    app.processEvents()
    assert 'Diferencia: $0.00' in dialog.assignment_totals.text()
    assert 'diferencia cero' in dialog.assignment_totals.status.text()
    if single:
        assert dialog.table.height() < 150
    dialog.details_toggle.click()
    dialog.details_toggle.click()
    capture(tmp_path / ('pdf-un-concepto.png' if single else 'pdf-varios-conceptos.png'), dialog, app)
    for width, height in [(960, 480), (640, 480)]:
        dialog.resize(width, height)
        app.processEvents()
        for button in (dialog.cancel_button, dialog.save_button):
            assert not dialog.scroll_area.isAncestorOf(button)
            assert dialog.rect().contains(button.rect().translated(button.mapTo(dialog, button.rect().topLeft())))
    assert draft == original
    assert repo.dashboard_summary() == before and repo.database.connection.total_changes == changes
    dialog.reject()
