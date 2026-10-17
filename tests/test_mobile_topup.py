from pathlib import Path

import pytest

from valenza.ocr.order_import import parse_receipt, read_receipt, validate
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository


FIXTURE = Path(__file__).parent / 'fixtures_synthetic' / 'mp_topup.txt'


@pytest.mark.parametrize('company', ['Telcel', 'Movistar', 'AT&T'])
def test_topup_layout_and_exact_amounts(company):
    draft = parse_receipt(FIXTURE.read_text(encoding='utf-8').replace('Telcel', company))
    assert draft['kind'] == 'MOBILE_TOPUP' and draft['company'] == company
    assert draft['date'] == '2026-09-10' and draft['time'] == '08:19:34'
    assert draft['number'] == 'DEMO-TOPUP-001'
    assert draft['payment'] == 'Mastercard terminada en 0000'
    assert draft['products'] == [dict(description='Recarga ' + company, quantity=1, unit=20000)]
    assert validate(draft) == 20000
    assert (draft['charged'], draft['paid'], draft['discount'], draft['refund']) == (20000, 20000, 0, 0)


def test_anonymous_native_topup_pdf(tmp_path):
    import pymupdf
    path = tmp_path / 'synthetic-topup.pdf'
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((40, 40), FIXTURE.read_text(encoding='utf-8'), fontsize=12)
        document.save(path)
    assert validate(read_receipt(path)) == 20000


def test_inconsistent_topup_amount_is_rejected():
    with pytest.raises(ValueError, match='no coinciden'):
        parse_receipt(FIXTURE.read_text(encoding='utf-8').replace('$ 200.00', '$ 199.99', 1))


@pytest.mark.parametrize('key,value', [('discount', 100), ('refund', 100), ('time', '25:00:00')])
def test_topup_does_not_inherit_product_adjustments(key, value):
    draft = parse_receipt(FIXTURE.read_text(encoding='utf-8'))
    draft[key] = value
    with pytest.raises(ValueError):
        validate(draft)


@pytest.mark.parametrize('person', ['owner', 'family'])
def test_topup_preview_confirmation_duplicate_and_single_bank_charge(person, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox, QLabel
    from PySide6.QtGui import QFont, QFontDatabase
    from valenza.gui.app import MainWindow, create_application
    from valenza.gui.pdf_import import ImportPreview
    app = create_application([])
    font_id = QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    if font_id >= 0:
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    database = LocalDatabase.open(':memory:', 'synthetic', allow_synthetic_in_memory=True)
    database.migrate()
    repo = FinanceRepository(database)
    repo.add_person('owner', 'Yo', is_owner=True)
    repo.add_person('family', 'Familiar ficticio')
    repo.add_institution('bank', 'Banco ficticio distinto de Nu')
    repo.add_instrument('card', 'bank', 'Mastercard ficticia', 'CREDIT_CARD')
    draft = parse_receipt(FIXTURE.read_text(encoding='utf-8'))
    draft['fingerprint'] = 'synthetic-topup-only'
    errors = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda parent, title, text: errors.append(text))
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.No)
    dialog = ImportPreview(repo, draft)
    assert not repo.list_orders() and dialog.instrument.currentData() is None
    assert dialog.refund_toggle.isHidden()
    assert dialog.fields['discount'].isReadOnly() and dialog.fields['refund'].isReadOnly()
    dialog.save()
    assert errors and not repo.list_orders()
    errors.clear()
    dialog.instrument.setCurrentIndex(dialog.instrument.findData('card'))
    assignment = dialog.table.cellWidget(0, 3)
    assignment.person.setCurrentIndex(assignment.person.findData(person))
    dialog.details_toggle.setChecked(True)
    dialog.fields['time'].setText('08:20:00')
    dialog.resize(700, 450)
    dialog.show()
    app.processEvents()
    dialog.scroll_area.verticalScrollBar().setValue(dialog.scroll_area.verticalScrollBar().maximum())
    app.processEvents()
    assert dialog.save_button.isVisible() and dialog.save_button.mapTo(dialog, dialog.save_button.rect().bottomRight()).y() < dialog.height()
    dialog.grab().save(str(tmp_path / 'topup-preview.png'))
    dialog.save()
    assert not errors and len(repo.list_orders()) == 1
    saved = repo.get_order(repo.list_orders()[0]['id'])
    assert saved['instrument_id'] == 'card'
    assert saved['import_evidence']['time'] == '08:20:00'
    assert len(saved['import_evidence']['products']) == 1 and not saved['product_refunds']
    summary = repo.dashboard_summary()
    assert summary['institutional_balance_cents'] == 20000
    assert summary['personal_pending_cents'] == (20000 if person == 'owner' else 0)
    assert summary['receivables_cents'] == (20000 if person == 'family' else 0)
    assert summary['discount_benefit_cents'] == 0
    duplicate = ImportPreview(repo, draft)
    duplicate.instrument.setCurrentIndex(1)
    duplicate.save()
    assert len(repo.list_orders()) == 1
    window = MainWindow(database=database)
    window.resize(820, 520)
    window.show()
    app.processEvents()
    assert window.dashboard_discount.findChild(QLabel, 'summaryAmount').text() == '••••'
    window.dashboard_privacy.setChecked(True)
    assert '$0.00 MXN' in window.dashboard_discount.findChild(QLabel, 'summaryAmount').text()
    window.grab().save(str(tmp_path / 'topup-home-small.png'))
    window._show_page(2)
    window.orders_table.selectRow(0)
    app.processEvents()
    assert 'Servicio: Recarga de celular' in window.order_detail.toPlainText()
    assert 'Compañía: Telcel' in window.order_detail.toPlainText()
    assert all(f'{n}.' in window.order_detail.toPlainText() for n in range(1, 5))
    window.close()
    duplicate.close()
    dialog.close()
    database.close()
