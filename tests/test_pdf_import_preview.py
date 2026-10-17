from pathlib import Path

import pytest

pytest.importorskip('PySide6')
from PySide6.QtWidgets import QMessageBox
from valenza.gui.app import create_application
from valenza.gui.pdf_import import ImportPreview
from valenza.ocr.order_import import parse_receipt
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository


@pytest.fixture
def preview(monkeypatch):
    app = create_application([])
    database = LocalDatabase.open(':memory:', 'synthetic', allow_synthetic_in_memory=True)
    database.migrate()
    repository = FinanceRepository(database)
    repository.add_person('owner', 'Propietario ficticio', is_owner=True)
    repository.add_person('friend', 'Persona ficticia')
    repository.ensure_demo_catalog()
    draft = parse_receipt((Path(__file__).parent / 'fixtures_synthetic' / 'mp_products.txt').read_text(encoding='utf-8'))
    draft['fingerprint'] = 'synthetic-preview'
    dialog = ImportPreview(repository, draft)
    dialog.instrument.setCurrentIndex(1)
    errors = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda parent, title, message: errors.append(message))
    yield dialog, repository, errors
    dialog.close()
    database.close()
    app.processEvents()


def assignment(dialog, row=0):
    return dialog.table.cellWidget(row, 3)


def select(widget, person):
    widget.person.setCurrentIndex(widget.person.findData(person))


def test_shared_summary_does_not_claim_owner_and_reduces_zero_fields(preview):
    dialog,repo,errors=preview
    row=assignment(dialog);row.divide.setChecked(True)
    row.amounts['owner'].setText('100.00');row.amounts['friend'].setText('150.70')
    assert row.shared_summary.text()=='Compartido · 2 personas'
    assert row.person.isHidden()
    assert row.shares()=={'owner':10000,'friend':15070}
    row.amounts['friend'].setText('0.00')
    assert row.amounts['friend'].isHidden()
    row.add_person.setCurrentIndex(row.add_person.findData('friend'))
    assert not row.amounts['friend'].isHidden()


def test_import_msi_single_order_preserves_amounts_and_dates(preview):
    dialog,repo,errors=preview
    dialog.msi_enabled.setChecked(True);dialog.msi_count.setValue(3)
    dialog.msi_first_due.setText('2026-01-31')
    dialog.save()
    assert not errors and len(repo.list_orders())==1
    order=repo.get_order(repo.list_orders()[0]['id'])
    assert order['purchase_mode']=='MSI'
    assert [i['due_date'] for i in order['installments']]==['2026-01-31','2026-02-28','2026-03-31']
    assert sum(i['principal_cents'] for i in order['installments'])==order['charged_cents']
    assert repo.count('institution_payment')==repo.count('user_payment')==0


def test_import_msi_invalid_first_date_has_no_partial_records(preview):
    dialog,repo,errors=preview
    dialog.msi_enabled.setChecked(True);dialog.msi_first_due.setText('2026-02-31')
    before=repo.database.connection.total_changes
    dialog.save()
    assert errors and not repo.list_orders() and repo.database.connection.total_changes==before


def test_preview_and_cancel_do_not_record_orders(preview):
    dialog, repository, _ = preview
    assert repository.list_orders() == []
    assert 'Total calculado: $250.00' in dialog.assignment_totals.text()
    assert 'Diferencia: $0.00' in dialog.assignment_totals.text()
    dialog.fields['paid'].setText('250.01')
    assert 'Diferencia: $-0.01' in dialog.assignment_totals.text()
    dialog.reject()
    assert repository.list_orders() == []


def test_database_failure_keeps_preview_and_rolls_back(preview):
    dialog, repository, errors = preview
    repository.database.connection.execute(
        "CREATE TRIGGER reject_import BEFORE INSERT ON audit_event "
        "BEGIN SELECT RAISE(ABORT, 'synthetic import failure'); END")
    dialog.save()
    assert errors and 'No se pudo guardar' in errors[0]
    assert repository.list_orders() == []
    for table in ('order_allocation', 'receivable', 'institution_movement'):
        assert repository.database.connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0


def test_ambiguous_discount_requires_correction_and_review(preview):
    previous, repository, errors = preview
    previous.close()
    text = (Path(__file__).parent / 'fixtures_synthetic' / 'mp_products.txt').read_text(encoding='utf-8')
    draft = parse_receipt(text.replace('Descuento: $20.00', 'Descuento: $20.000'), review=True)
    dialog = ImportPreview(repository, draft)
    dialog.instrument.setCurrentIndex(1)
    assert dialog.review_confirmation.isVisibleTo(dialog)
    assert dialog.fields['discount'].text() == ''
    assert repository.list_orders() == []
    dialog.save()
    assert errors and repository.list_orders() == []
    dialog.fields['discount'].setText('20.00')
    errors.clear()
    dialog.save()
    assert errors and repository.list_orders() == []
    dialog.review_confirmation.setChecked(True)
    errors.clear()
    dialog.save()
    assert not errors
    order = repository.get_order(repository.list_orders()[0]['id'])
    assert order['charged_cents'] == 28000
    assert order['import_evidence']['review_corrections']['discount'] == {'original': None, 'confirmed': 2000}
    dialog.close()


def test_unpriced_product_preview_does_not_invent_values(preview):
    previous, repository, errors = preview
    previous.close()
    draft = dict(date='2026-09-21', number='', payment='', products=[
        dict(description='Producto sin precio', quantity=None, unit=None)],
        discount=0, refund=0, charged=None, paid=2500,
        warnings=['Revisa el producto'], review_fields=['products'])
    dialog = ImportPreview(repository, draft)
    assert dialog.table.item(0, 1).text() == dialog.table.item(0, 2).text() == ''
    dialog.instrument.setCurrentIndex(1)
    dialog.review_confirmation.setChecked(True)
    dialog.save()
    assert errors and repository.list_orders() == []
    dialog.close()


def test_defaults_to_owner_and_saves_existing_financial_values(preview):
    dialog, repository, errors = preview
    assert assignment(dialog).shares() == {'owner': 25070, 'friend': 0}
    assert assignment(dialog, 1).shares() == {'owner': 4930, 'friend': 0}
    assert 'Yo: $300.00' in dialog.assignment_totals.text()
    assert 'Total asignado: $300.00' in dialog.assignment_totals.text()
    dialog.save()
    assert not errors
    order = repository.get_order(repository.list_orders()[0]['id'])
    assert (order['original_cents'], order['discount_cents'], order['charged_cents']) == (30000, 2000, 28000)
    assert order['import_evidence']['refund'] == 3000
    assert order['import_evidence']['paid'] == 25000
    assert order['import_evidence']['products'][0]['allocations']['owner'] == 25070


def test_selector_assigns_full_value_and_tracks_edits(preview):
    dialog, _, _ = preview
    select(assignment(dialog), 'friend')
    assert assignment(dialog).shares() == {'owner': 0, 'friend': 25070}
    assert 'Persona ficticia: $250.70' in dialog.assignment_totals.text()
    dialog.table.item(0, 1).setText('3')
    dialog.table.item(0, 2).setText('125.36')
    assert assignment(dialog).shares()['friend'] == 37608
    assert 'Total asignado: $425.38' in dialog.assignment_totals.text()


def test_split_exact_cents_and_save(preview):
    dialog, repository, errors = preview
    row = assignment(dialog)
    row.divide.setChecked(True)
    assert not row.split_fields.isHidden()
    assert row.amounts['owner'].text() == '250.70'
    row.amounts['owner'].setText('125.35')
    row.amounts['friend'].setText('125.35')
    assert 'Yo: $174.65' in dialog.assignment_totals.text()
    dialog.save()
    assert not errors
    order = repository.get_order(repository.list_orders()[0]['id'])
    assert order['import_evidence']['products'][0]['allocations'] == {'owner': 12535, 'friend': 12535}


def test_inexact_split_blocks_save_even_when_overall_total_matches(preview):
    dialog, repository, errors = preview
    first, second = assignment(dialog), assignment(dialog, 1)
    first.divide.setChecked(True)
    second.divide.setChecked(True)
    first.amounts['owner'].setText('250.69')
    second.amounts['owner'].setText('49.31')
    assert 'Total asignado: $300.00' in dialog.assignment_totals.text()
    assert 'no cuadra' in dialog.assignment_totals.text()
    dialog.save()
    assert errors and 'producto 1' in errors[-1]
    assert not repository.list_orders()


def test_bulk_assignments_replace_splits(preview):
    dialog, _, _ = preview
    assignment(dialog).divide.setChecked(True)
    assignment(dialog).amounts['owner'].setText('1.00')
    dialog.bulk_person.setCurrentIndex(dialog.bulk_person.findData('friend'))
    assert dialog.all_for_person.text() == 'Todo para Persona ficticia'
    dialog.all_for_person.click()
    assert assignment(dialog).shares()['friend'] == 25070
    assert assignment(dialog, 1).shares()['friend'] == 4930
    assert not assignment(dialog).divide.isChecked()
    assert 'Persona ficticia: $300.00' in dialog.assignment_totals.text()
    dialog.all_for_me.click()
    assert assignment(dialog).shares()['owner'] == 25070
    assert 'Yo: $300.00' in dialog.assignment_totals.text()


def test_changing_person_leaves_manual_split(preview):
    dialog, _, _ = preview
    row = assignment(dialog)
    row.divide.setChecked(True)
    row.amounts['owner'].setText('20.00')
    select(row, 'friend')
    assert not row.divide.isChecked()
    assert row.split_fields.isHidden()
    assert row.shares()['friend'] == 25070


def test_row_removal_and_addition_keep_assignments_attached(preview):
    dialog, repository, _ = preview
    select(assignment(dialog, 1), 'friend')
    dialog.table.selectRow(0)
    dialog.remove_row()
    assert assignment(dialog).shares()['friend'] == 4930
    dialog.add_row(dict(description='Nuevo ficticio', quantity=2, unit=101))
    assert assignment(dialog, 1).shares()['owner'] == 202
    assert 'Total asignado: $51.32' in dialog.assignment_totals.text()
    dialog.reject()
    assert not repository.list_orders()


def test_invalid_manual_amount_blocks_save(preview):
    dialog, repository, errors = preview
    assignment(dialog).divide.setChecked(True)
    assignment(dialog).amounts['owner'].setText('250.701')
    dialog.save()
    assert errors
    assert not repository.list_orders()


def test_five_products_and_fixed_footer_fit_laptop_resolution(preview):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QHeaderView
    dialog, _, _ = preview
    while dialog.table.rowCount():
        dialog.table.removeRow(0)
    draft = parse_receipt((Path(__file__).parent / 'fixtures_synthetic' / 'mp_openpdf.txt').read_text(encoding='utf-8'))
    for product in draft['products']:
        dialog.add_row(product)
    dialog.resize(1200, 680)
    dialog.show()
    QApplication.processEvents()
    dialog.update_totals()
    QApplication.processEvents()
    assert dialog.width() <= 1366 and dialog.height() <= 720
    assert dialog.details.isHidden()
    assert dialog.table.height() <= dialog.table.horizontalHeader().height() + sum(
        dialog.table.rowHeight(row) for row in range(dialog.table.rowCount())) + 30
    assert dialog.table.rowViewportPosition(4) + dialog.table.rowHeight(4) <= dialog.table.viewport().height()
    assert dialog.table.horizontalHeader().sectionResizeMode(0) == QHeaderView.ResizeMode.Interactive
    assert dialog.table.textElideMode() == Qt.TextElideMode.ElideNone
    assert dialog.table.columnWidth(0) > 400
    for button in (dialog.cancel_button, dialog.save_button):
        assert button.isVisible()
        assert dialog.rect().contains(button.mapTo(dialog, button.rect().bottomRight()))
    assert dialog.all_for_me.y() == dialog.bulk_person.y() == dialog.all_for_person.y()
    dialog.details_toggle.click()
    QApplication.processEvents()
    assert not dialog.details.isHidden()
    assert dialog.table.height() >= dialog.table.minimumHeight()
    assert dialog.rect().contains(dialog.save_button.mapTo(dialog, dialog.save_button.rect().bottomRight()))
