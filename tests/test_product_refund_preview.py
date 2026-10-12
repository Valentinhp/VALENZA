from pathlib import Path

import pytest

pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog
from valenza.gui.app import create_application, MainWindow
from valenza.gui.pdf_import import ImportPreview
from valenza.ocr.order_import import parse_receipt
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository


@pytest.fixture
def preview(monkeypatch):
    app = create_application([])
    database = LocalDatabase.open(':memory:', 'synthetic', allow_synthetic_in_memory=True)
    database.migrate()
    repo = FinanceRepository(database)
    repo.add_person('owner', 'Yo', is_owner=True)
    repo.add_person('mama', 'MAMÁ')
    repo.add_institution('bank', 'Banco ficticio')
    repo.add_instrument('card', 'bank', 'Tarjeta ficticia', 'CREDIT_CARD')
    repo.add_instrument('wallet', 'bank', 'Mercado Pago ficticio', 'WALLET_BALANCE')
    draft = parse_receipt((Path(__file__).parent / 'fixtures_synthetic' / 'mp_openpdf.txt').read_text(encoding='utf-8'))
    draft['fingerprint'] = 'anonymous-gui-refund'
    dialog = ImportPreview(repo, draft)
    dialog.instrument.setCurrentIndex(dialog.instrument.findData('card'))
    assignment = dialog.table.cellWidget(4, 3)
    assignment.person.setCurrentIndex(assignment.person.findData('mama'))
    dialog.table.selectRow(4)
    errors = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda parent, title, message: errors.append(message))
    yield dialog, repo, errors
    dialog.close()
    database.close()
    app.processEvents()


def configure_refund(dialog, credited=True, destination='card'):
    dialog.refund_toggle.click()
    editor = dialog.refund_editor
    editor.destination.setCurrentIndex(editor.destination.findData(destination))
    if credited:
        editor.status.setCurrentIndex(editor.status.findData('ACCREDITED'))
        editor.accredited_at.setText('2026-10-10')
    return editor


def configure_repurchase(dialog):
    editor = configure_refund(dialog, destination='wallet')
    editor.repurchase.click()
    editor.repurchase_amount.setText('129.99')
    editor.repurchase_date.setText('2026-10-11')
    editor.repurchase_instrument.setCurrentIndex(editor.repurchase_instrument.findData('wallet'))
    editor.apply_surplus.click()
    return editor


def test_personal_difference_family_repurchase_preview_matches_saved_result(preview, tmp_path):
    dialog, repo, errors = preview
    editor = configure_repurchase(dialog)
    editor.allocation.divide.setChecked(True)
    editor.allocation.amounts['owner'].setText('21.22')
    editor.allocation.amounts['mama'].setText('129.99')
    before_changes = repo.database.connection.total_changes
    dialog.update_totals()
    result = dialog.refund_preview_data
    assert result['before'] == {'owner':0,'mama':20779}
    assert result['after'] == {'owner':2122,'mama':12999}
    assert result['applied'] == result['wallet_after'] == 5658
    assert result['existing_applied'] == 0
    assert 'MAMÁ: antes $207.79 → después $129.99' in editor.outcome.toPlainText()
    assert 'Yo: antes $0.00 → después $21.22' in editor.outcome.toPlainText()
    assert repo.database.connection.total_changes == before_changes
    assert repo.list_orders() == []
    dialog.show()
    QApplication.instance().processEvents()
    editor.outcome.grab().save(str(tmp_path / 'participation-preview.png'))
    dialog.save()
    assert not errors
    parent = next(o for o in repo.list_orders() if repo.list_product_refunds(o['id']))
    shares = {s['user_id']:s for s in repo.list_collection_items() if s['order_id']==parent['id']}
    assert shares['mama']['sale_cents'] == result['after']['mama']
    # Other products in this synthetic PDF belong to owner, so compare the change.
    assert shares['owner']['sale_cents'] == parent['owner_cents'] + 2122
    wallet = next(c for c in repo.list_card_summaries() if c['instrument_id']=='wallet')
    assert wallet['wallet_balance_cents'] == result['wallet_after']
    changes = repo.database.connection.total_changes
    dialog.update_totals()
    assert dialog.refund_preview_data['existing_applied'] == 5658
    assert dialog.refund_preview_data['wallet_after'] == 5658
    assert 'ya está registrada' in editor.outcome.toPlainText()
    dialog.save()
    assert errors and 'ya está registrada' in errors[-1]
    assert repo.database.connection.total_changes == changes
    assert len(repo.list_orders()) == 2


def test_surplus_changes_participations_but_does_not_spend_wallet_twice(preview):
    dialog, repo, _ = preview
    editor = configure_repurchase(dialog)
    editor.apply_surplus.setChecked(False)
    assert dialog.refund_preview_data['applied'] == 0
    assert dialog.refund_preview_data['after']['mama'] == 20779
    assert dialog.refund_preview_data['wallet_after'] == 5658
    editor.apply_surplus.setChecked(True)
    assert dialog.refund_preview_data['after']['mama'] == 15121
    assert dialog.refund_preview_data['wallet_after'] == 5658
    assert repo.list_orders() == []


def test_final_resin_animals_case_entire_order_50507_and_no_double_debt(preview):
    dialog, repo, errors = preview
    # Fixture subtotal: 602.87, of which 20.00 belongs to owner and 582.87 to Mama.
    for row in (0, 2, 3):
        assignment = dialog.table.cellWidget(row, 3)
        assignment.person.setCurrentIndex(assignment.person.findData('mama'))
    dialog.table.item(4, 0).setText('150 mini animales de resina')
    editor = configure_repurchase(dialog)
    assert 'Reparto final' in editor.allocation_label.text()
    # Assigning the selector to Yo alone assigns the WHOLE 151.21, not just 21.22.
    editor.allocation.person.setCurrentIndex(editor.allocation.person.findData('owner'))
    assert editor.allocation.shares()['owner'] == 15121
    editor.allocation.divide.setChecked(True)
    editor.allocation.amounts['owner'].setText('21.22')
    editor.allocation.amounts['mama'].setText('129.99')
    changes = repo.database.connection.total_changes
    dialog.update_totals()
    preview_result = dialog.refund_preview_data
    assert preview_result['order_before'] == {'owner':2000, 'mama':58287}
    assert preview_result['order_after'] == {'owner':4122, 'mama':50507}
    assert preview_result['wallet_after'] == preview_result['applied'] == 5658
    text = editor.outcome.toPlainText()
    assert 'otros productos $375.08 + producto revisado $129.99 = $505.07' in text
    assert 'a favor de MAMÁ' in text
    assert 'no es un abono que haya entregado' in text
    assert repo.database.connection.total_changes == changes and repo.list_orders() == []
    dialog.save()
    assert not errors
    mama = repo.family_statement('mama')
    assert (mama['assigned_cents'],mama['paid_cents'],mama['remaining_cents']) == (50507,0,50507)
    assert repo.dashboard_summary()['family_received_cents'] == 0
    assert repo.dashboard_summary()['discount_benefit_cents'] == 6029
    assert repo.family_statement('owner')['assigned_cents'] == 4122
    assert len(repo.list_orders()) == 2  # Original and funded replacement, with no second family debt.
    linked = next(o for o in repo.list_orders() if not repo.list_product_refunds(o['id']))
    assert all(s['sale_cents']==0 for s in repo.list_collection_items() if s['order_id']==linked['id'])
    repo.record_receipt(payment_id='later-mama',receivable_id=mama['rows'][0]['receivable_id'],
                        amount_cents=10000,received_at='2026-10-11')
    assert repo.family_statement('mama')['assigned_cents'] == 50507
    assert repo.family_statement('mama')['remaining_cents'] == 40507


def test_repurchase_preview_and_atomic_save(preview):
    dialog, repo, errors = preview
    editor = configure_repurchase(dialog)
    assert editor.allocation.shares() == {'owner': 0, 'mama': 15121}
    assert 'Aplicado $56.58' in editor.summary.text() and 'Pendiente $151.21' in editor.summary.text()
    assert dialog.table.cellWidget(4, 3).shares()['mama'] == 20779
    assert repo.list_orders() == []
    dialog.save()
    assert not errors
    assert len(repo.list_orders()) == 2
    assert repo.dashboard_summary()['receivables_cents'] == 15121


def test_saved_refund_can_be_extended_without_reimporting(preview):
    from valenza.gui.pdf_import import RefundRepurchaseDialog
    dialog, repo, errors = preview
    configure_refund(dialog, destination='wallet')
    dialog.save()
    original_id = repo.list_orders()[0]['id']
    refund = repo.list_product_refunds(original_id)[0]
    editor_dialog = RefundRepurchaseDialog(repo, refund)
    editor = editor_dialog.editor
    assert editor.amount.text() == '186.57' and not editor.amount.isEnabled()
    editor.repurchase_amount.setText('129.99')
    editor.repurchase_date.setText('2026-10-11')
    editor.apply_surplus.click()
    editor_dialog.save()
    assert not errors
    assert repo.dashboard_summary()['receivables_cents'] == 15121
    assert len(repo.list_orders()) == 2
    assert repo.list_product_refunds(original_id)[0]['repurchase']['applied_cents'] == 5658
    editor_dialog.close()


@pytest.mark.parametrize('width,height', [(760, 560), (640, 360)])
def test_edit_saved_repurchase_from_pedidos_refreshes_collection_and_dashboard(preview, monkeypatch, tmp_path, width, height):
    from PySide6.QtCore import QTimer, QPoint
    from PySide6.QtGui import QFontDatabase, QFont, QPixmap
    from valenza.gui.pdf_import import RefundRepurchaseDialog
    font = Path('C:/Windows/Fonts/segoeui.ttf')
    if font.exists():
        font_id = QFontDatabase.addApplicationFont(str(font))
        QApplication.instance().setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    importer, repo, errors = preview
    editor = configure_repurchase(importer)
    editor.allocation.person.setCurrentIndex(editor.allocation.person.findData('owner'))
    importer.save()
    original_id = next(o['id'] for o in repo.list_orders() if repo.list_product_refunds(o['id']))
    initial_refund = repo.list_product_refunds(original_id)[0]
    original_summary = {r['instrument_id']: r for r in repo.list_card_summaries()}
    window = MainWindow(database=repo.database)
    window.pages.setCurrentIndex(window.PAGES.index('Pedidos'))
    window.show()
    row = next(i for i in range(window.orders_table.rowCount()) if window.orders_table.item(i, 8).text() == original_id)
    window.orders_table.selectRow(row)
    assert window.repurchase_button.text() == 'Editar reparto devolución/recompra'
    monkeypatch.setattr(QInputDialog, 'getItem', lambda parent, title, label, choices, *args: (choices[0], True))
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    failures, visited = [], []

    def edit_modal():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, RefundRepurchaseDialog) and dialog.editing_allocations
            dialog.resize(width, height)
            QApplication.processEvents()
            assert dialog.editor.allocation.shares() == {'owner': 15121, 'mama': 0}
            for control in (dialog.editor.amount, dialog.editor.destination, dialog.editor.repurchase_amount,
                            dialog.editor.repurchase_date, dialog.editor.repurchase_instrument, dialog.editor.apply_surplus):
                assert not control.isEnabled()
            assert 'Diferencia original $21.22 + recompra $129.99 = pendiente a repartir $151.21' in dialog.editor.summary.text()
            dialog.editor.allocation.amounts['owner'].setText('21.22')
            dialog.editor.allocation.amounts['mama'].setText('129.99')
            assert sum(dialog.editor.allocation.shares().values()) == 15121
            dialog.scroll_area.ensureWidgetVisible(dialog.editor.summary)
            QApplication.processEvents()
            image = QPixmap(1366, 768)
            image.fill('#e9edf2')
            dialog.render(image, QPoint(20, 20))
            image.save(str(tmp_path / f'edit-saved-repartition-{width}.png'))
            assert dialog.rect().contains(dialog.save_button.mapTo(dialog, dialog.save_button.rect().bottomRight()))
            dialog.save_button.click()
            assert dialog.result() == dialog.DialogCode.Accepted
            visited.append(True)
        except BaseException as error:
            failures.append(error)
        finally:
            if dialog is not None:
                dialog.reject()

    QTimer.singleShot(0, edit_modal)
    window.repurchase_button.click()
    if failures:
        window.database = None
        window.close()
        raise failures[0]
    assert visited and not errors
    assert len(repo.list_orders()) == 2
    assert repo.list_product_refunds(original_id)[0]['repurchase'] == initial_refund['repurchase']
    assert {r['instrument_id']: r for r in repo.list_card_summaries()} == original_summary
    assert repo.dashboard_summary()['personal_pending_cents'] == 41630
    assert repo.dashboard_summary()['receivables_cents'] == 12999
    from PySide6.QtWidgets import QLabel
    assert '129.99' in window.dashboard_receivables.findChild(QLabel, 'summaryAmount').text()
    assert '416.30' in window.dashboard_personal.findChild(QLabel, 'summaryAmount').text()
    assert any('129.99' in window.collection_items.item(row, column).text()
               for row in range(window.collection_items.rowCount())
               for column in range(window.collection_items.columnCount())
               if window.collection_items.item(row, column) is not None)
    assert '129.99' in window.order_detail.toPlainText()
    window.database = None
    window.close()


@pytest.mark.parametrize('valid,confirmation', [(False, QMessageBox.StandardButton.Yes), (True, QMessageBox.StandardButton.No)])
def test_saved_repartition_requires_exact_sum_and_confirmation(preview, monkeypatch, valid, confirmation):
    from valenza.gui.pdf_import import RefundRepurchaseDialog
    importer, repo, errors = preview
    editor = configure_repurchase(importer)
    editor.allocation.person.setCurrentIndex(editor.allocation.person.findData('owner'))
    importer.save()
    order_id = next(o['id'] for o in repo.list_orders() if repo.list_product_refunds(o['id']))
    refund = repo.list_product_refunds(order_id)[0]
    dialog = RefundRepurchaseDialog(repo, refund)
    dialog.editor.allocation.amounts['owner'].setText('21.22' if valid else '21.21')
    dialog.editor.allocation.amounts['mama'].setText('129.99')
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: confirmation)
    changes = repo.database.connection.total_changes
    dialog.save_button.click()
    assert repo.database.connection.total_changes == changes
    assert {a['user_id']: a['effective_final_cents'] for a in repo.list_product_refunds(order_id)[0]['adjustments']} == {
        'owner': 15121, 'mama': 0}
    if not valid:
        assert errors and '151.21' in errors[-1]
    dialog.close()


@pytest.mark.parametrize('width,height', [(760, 560), (640, 360), (480, 280)])
def test_saved_repurchase_scroll_keeps_footer_and_values(preview, width, height):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QFontDatabase, QFont, QWheelEvent
    from valenza.gui.pdf_import import RefundRepurchaseDialog
    font = Path('C:/Windows/Fonts/segoeui.ttf')
    if font.exists():
        font_id = QFontDatabase.addApplicationFont(str(font))
        QApplication.instance().setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    dialog, repo, errors = preview
    configure_refund(dialog, destination='wallet')
    dialog.save()
    refund = repo.list_product_refunds(repo.list_orders()[0]['id'])[0]
    saved = RefundRepurchaseDialog(repo, refund)
    editor = saved.editor
    editor.repurchase_amount.setText('129.99')
    editor.repurchase_date.setText('2026-10-11')
    editor.apply_surplus.click()
    editor.allocation.divide.click()
    editor.allocation.amounts['mama'].setText('151.21')
    editor.allocation.amounts['owner'].setText('0.00')
    saved.resize(width, height)
    saved.show()
    QApplication.processEvents()
    assert saved.width() == width and saved.height() == height
    assert saved.editor.width() <= saved.scroll_area.viewport().width()
    for button in (saved.save_button, saved.cancel_button):
        assert saved.rect().contains(button.mapTo(saved, button.rect().bottomRight()))
        assert not saved.scroll_area.isAncestorOf(button)
    bar = saved.scroll_area.verticalScrollBar()
    if height < 560:
        assert bar.maximum() > 0
        viewport = saved.scroll_area.viewport()
        wheel = QWheelEvent(QPointF(viewport.rect().center()),
            QPointF(viewport.mapToGlobal(viewport.rect().center())), QPoint(), QPoint(0, -120),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(viewport, wheel)
        QApplication.processEvents()
        assert bar.value() > 0
    saved.scroll_area.ensureWidgetVisible(editor.repurchase_date)
    QApplication.processEvents()
    assert saved.scroll_area.viewport().rect().intersects(
        editor.repurchase_date.rect().translated(editor.repurchase_date.mapTo(saved.scroll_area.viewport(), QPoint())))
    bar.setValue(bar.maximum())
    QApplication.processEvents()
    assert editor.repurchase_amount.text() == '129.99'
    assert editor.repurchase_date.text() == '2026-10-11'
    assert editor.allocation.shares() == {'owner': 0, 'mama': 15121}
    # Click the fixed footer while the form is scrolled: reuse the normal save.
    saved.save_button.click()
    assert not errors
    assert saved.result() == saved.DialogCode.Accepted
    assert repo.dashboard_summary()['receivables_cents'] == 15121
    saved.close()


@pytest.mark.parametrize('width,height', [(760, 560), (640, 360), (480, 280)])
def test_pedidos_modal_dynamic_fields_never_grow_dialog(preview, monkeypatch, tmp_path, width, height):
    from PySide6.QtCore import QTimer, QPoint
    from PySide6.QtGui import QFontDatabase, QFont, QPixmap
    from valenza.gui.pdf_import import RefundRepurchaseDialog
    font = Path('C:/Windows/Fonts/segoeui.ttf')
    if font.exists():
        font_id = QFontDatabase.addApplicationFont(str(font))
        QApplication.instance().setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    importer, repo, errors = preview
    # Enough conditional rows to exceed a 768px display if height propagates.
    for index in range(16):
        repo.add_person(f'extra-{index}', f'Persona ficticia {index + 1}')
    shares = {p['id']: 0 for p in repo.list_people()}
    evidence = dict(importer.draft)
    evidence['products'] = [{**product, 'allocations': {**shares,
        **importer.table.cellWidget(index, 3).shares()}} for index, product in enumerate(evidence['products'])]
    repo.create_order(order_id='dynamic-fixture', ordered_at=evidence['date'], merchant='Comercio ficticio',
        instrument_id='card', original_cents=60287, discount_cents=6029, charged_cents=54258,
        allocations=tuple({'user_id': user, 'amount_cents': 39508 if user == 'owner' else 20779 if user == 'mama' else 0}
                          for user in shares), import_evidence=evidence,
        product_refunds=({'product_index': 4, 'amount_cents': 18657, 'destination_id': 'wallet',
            'status': 'ACCREDITED', 'accredited_at': '2026-10-10',
            'final_allocations': {**shares, 'mama': 2122}},))
    window = MainWindow(database=repo.database)
    window.show()
    window.orders_table.selectRow(0)
    assert window.repurchase_button.isEnabled()
    monkeypatch.setattr(QInputDialog, 'getItem', lambda parent, title, label, choices, *args: (choices[0], True))
    failures, visited = [], []

    def exercise_modal():
        saved = QApplication.activeModalWidget()
        try:
            assert isinstance(saved, RefundRepurchaseDialog)
            saved.resize(width, height)
            QApplication.processEvents()
            stable_height = saved.height()
            assert stable_height == height
            assert saved.maximumHeight() <= saved.screen().availableGeometry().height() - 48
            editor = saved.editor
            editor.repurchase_amount.setText('129.99')
            editor.repurchase_date.setText('2026-10-11')
            editor.apply_surplus.click()
            for _ in range(3):
                editor.allocation.divide.click()
                QApplication.processEvents()
                assert saved.height() == stable_height
                assert saved.editor.width() <= saved.scroll_area.viewport().width()
                assert saved.scroll_area.isAncestorOf(editor.allocation.split_fields)
                assert saved.scroll_area.isAncestorOf(editor.repurchase_fields)
                for button in (saved.cancel_button, saved.save_button):
                    assert not saved.scroll_area.isAncestorOf(button)
                    assert saved.rect().contains(button.mapTo(saved, button.rect().bottomRight()))
            assert editor.allocation.divide.isChecked()
            bar = saved.scroll_area.verticalScrollBar()
            assert bar.maximum() > 0
            # Visit every dynamic amount and purchase field with the real scroll.
            for field in [*editor.allocation.amounts.values(), editor.repurchase_amount,
                          editor.repurchase_date, editor.repurchase_instrument, editor.apply_surplus]:
                saved.scroll_area.ensureWidgetVisible(field)
                QApplication.processEvents()
                assert saved.scroll_area.viewport().rect().contains(
                    field.rect().translated(field.mapTo(saved.scroll_area.viewport(), QPoint())))
                assert saved.height() == stable_height
            bar.setValue(0)
            QApplication.processEvents()
            canvas = QPixmap(1366, 768)
            canvas.fill('#e9edf2')
            saved.render(canvas, QPoint(24, 24))
            canvas.save(str(tmp_path / f'pedidos-dynamic-{width}-top.png'))
            bar.setValue(bar.maximum())
            QApplication.processEvents()
            canvas.fill('#e9edf2')
            saved.render(canvas, QPoint(24, 24))
            canvas.save(str(tmp_path / f'pedidos-dynamic-{width}-bottom.png'))
            saved.resize(width, 10000)
            QApplication.processEvents()
            assert saved.height() <= saved.screen().availableGeometry().height() - 48
            saved.resize(width, stable_height)
            QApplication.processEvents()
            assert editor.repurchase_amount.text() == '129.99'
            assert editor.repurchase_date.text() == '2026-10-11'
            saved.save_button.click()
            assert saved.result() == saved.DialogCode.Accepted
            visited.append(True)
        except BaseException as error:
            failures.append(error)
        finally:
            if saved is not None:
                saved.reject()

    # Invoke the actual Pedidos action and run its modal event loop.
    QTimer.singleShot(0, exercise_modal)
    window.repurchase_button.click()
    window.database = None
    window.close()
    if failures:
        raise failures[0]
    assert visited and not errors
    assert repo.dashboard_summary()['receivables_cents'] == 15121


def test_repurchase_preview_five_rows_and_footer_visible(preview):
    from PySide6.QtGui import QFontDatabase, QFont
    font = Path('C:/Windows/Fonts/segoeui.ttf')
    if font.exists():
        font_id = QFontDatabase.addApplicationFont(str(font))
        QApplication.instance().setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    dialog, _, _ = preview
    configure_repurchase(dialog)
    dialog.show()
    QApplication.processEvents()
    dialog.update_totals()
    QApplication.processEvents()
    assert dialog.width() <= 1366 and dialog.height() <= 720
    assert dialog.table.rowViewportPosition(4) + dialog.table.rowHeight(4) <= dialog.table.viewport().height()
    assert dialog.rect().contains(dialog.save_button.mapTo(dialog, dialog.save_button.rect().bottomRight()))


def test_proposes_existing_pdf_refund_and_preserves_original_assignment(preview):
    dialog, repo, errors = preview
    editor = configure_refund(dialog)
    assert editor.amount.text() == '186.57'
    assert editor.allocation.shares() == {'owner': 0, 'mama': 2122}
    assert dialog.table.cellWidget(4, 3).shares()['mama'] == 20779
    assert 'MAMÁ: $207.79 → $21.22' in dialog.assignment_totals.text()
    assert 'Total después del ajuste: $416.30' in dialog.assignment_totals.text()
    dialog.save()
    assert not errors
    order = repo.get_order(repo.list_orders()[0]['id'])
    assert order['discount_cents'] == 6029 and order['charged_cents'] == 54258
    assert order['product_refunds'][0]['amount_cents'] == 18657


def test_choose_owner_to_absorb_remaining_difference(preview):
    dialog, repo, errors = preview
    editor = configure_refund(dialog, destination='wallet')
    editor.allocation.person.setCurrentIndex(editor.allocation.person.findData('owner'))
    assert 'MAMÁ: $207.79 → $0.00' in dialog.assignment_totals.text()
    dialog.save()
    assert not errors
    assert repo.dashboard_summary()['receivables_cents'] == 0
    assert repo.dashboard_summary()['institutional_balance_cents'] == 54258
    assert next(c for c in repo.list_card_summaries() if c['instrument_id'] == 'wallet')['wallet_balance_cents'] == 18657


def test_divide_remaining_cost_without_changing_original_split(preview):
    dialog, repo, errors = preview
    editor = configure_refund(dialog)
    editor.allocation.divide.setChecked(True)
    editor.allocation.amounts['mama'].setText('10.00')
    editor.allocation.amounts['owner'].setText('11.22')
    dialog.save()
    assert not errors
    people = {p['user_id']: p['remaining_cents'] for p in repo.list_collection_items()}
    assert people == {'owner': 40630, 'mama': 1000}


@pytest.mark.parametrize('invalid', ['missing_destination', 'missing_date', 'wrong_split', 'refund_exceeds_pdf'])
def test_invalid_confirmation_never_saves_partial_records(preview, invalid):
    dialog, repo, errors = preview
    editor = configure_refund(dialog)
    if invalid == 'missing_destination':
        editor.destination.setCurrentIndex(0)
    elif invalid == 'missing_date':
        editor.accredited_at.clear()
    elif invalid == 'wrong_split':
        editor.allocation.divide.setChecked(True)
        editor.allocation.amounts['mama'].setText('21.23')
    else:
        editor.amount.setText('186.58')
    dialog.save()
    assert errors
    assert not repo.list_orders()
    assert not repo.database.connection.execute('SELECT 1 FROM institution_movement').fetchone()


def test_pending_refund_can_be_accredited_from_existing_orders_page(preview, monkeypatch):
    dialog, repo, errors = preview
    editor = configure_refund(dialog, credited=False)
    assert editor.accredited_at.text() == '' and not editor.accredited_at.isEnabled()
    dialog.save()
    assert not errors
    assert repo.dashboard_summary()['receivables_cents'] == 20779
    window = MainWindow(database=repo.database)
    window.orders_table.selectRow(0)
    assert window.accredit_refund_button.isEnabled()
    monkeypatch.setattr(QInputDialog, 'getItem', lambda parent, title, label, choices, *args: (choices[0], True))
    monkeypatch.setattr(QInputDialog, 'getText', lambda *args: ('2026-10-10', True))
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    window.accredit_refund_button.click()
    assert repo.dashboard_summary()['receivables_cents'] == 2122
    assert repo.dashboard_summary()['institutional_balance_cents'] == 35601
    assert not window.accredit_refund_button.isEnabled()
    assert 'Acreditado el 2026-10-10' in window.order_detail.toPlainText()
    window.database = None  # El fixture es propietario de esta conexión sintética.
    window.close()


def test_removing_refund_assignment_or_cancelling_creates_no_refund(preview):
    dialog, repo, _ = preview
    configure_refund(dialog)
    dialog.refund_toggle.click()
    assert dialog.refund_source is None
    dialog.save()
    order = repo.list_orders()[0]
    assert repo.list_product_refunds(order['id']) == []
    assert repo.dashboard_summary()['receivables_cents'] == 20779


@pytest.mark.parametrize('width,height', [(1200, 680), (960, 480)])
def test_pedidos_import_scroll_contains_all_return_options(preview, monkeypatch, tmp_path, width, height):
    from PySide6.QtCore import QTimer, QPoint
    from PySide6.QtGui import QFontDatabase, QFont, QPixmap
    from PySide6.QtWidgets import QFileDialog, QPushButton
    import valenza.ocr.order_import as parser
    font = Path('C:/Windows/Fonts/segoeui.ttf')
    if font.exists():
        font_id = QFontDatabase.addApplicationFont(str(font))
        QApplication.instance().setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    initial, repo, errors = preview
    for index in range(12):
        repo.add_person(f'extra-{index}', f'Persona ficticia {index + 1}')
    window = MainWindow(database=repo.database)
    window.show()
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: ('anonymous.pdf', 'PDF'))
    monkeypatch.setattr(parser, 'read_receipt', lambda path: dict(initial.draft))
    failures, visited = [], []

    def exercise_modal():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, ImportPreview)
            dialog.resize(width, height)
            QApplication.processEvents()
            stable = dialog.size()
            dialog.instrument.setCurrentIndex(dialog.instrument.findData('card'))
            dialog.assign_all('mama')
            first = dialog.table.cellWidget(1, 3)
            first.person.setCurrentIndex(first.person.findData('owner'))
            dialog.table.selectRow(4)
            editor = configure_repurchase(dialog)
            for _ in range(3):
                editor.allocation.divide.click()
                dialog.details_toggle.click()
                QApplication.processEvents()
                assert dialog.size() == stable
            assert editor.allocation.divide.isChecked()
            for widget in (dialog.header, dialog.table, editor, editor.repurchase_fields,
                           editor.allocation.split_fields, dialog.assignment_totals):
                assert dialog.scroll_area.isAncestorOf(widget)
            for button in (dialog.save_button, dialog.cancel_button):
                assert not dialog.scroll_area.isAncestorOf(button)
                assert dialog.rect().contains(button.mapTo(dialog, button.rect().bottomRight()))
            assert dialog.scroll_area.verticalScrollBar().maximum() > 0
            for field in [*editor.allocation.amounts.values(), editor.repurchase_amount, editor.repurchase_date]:
                dialog.scroll_area.ensureWidgetVisible(field)
                QApplication.processEvents()
                assert dialog.scroll_area.viewport().rect().contains(
                    field.rect().translated(field.mapTo(dialog.scroll_area.viewport(), QPoint())))
                assert dialog.size() == stable
            dialog.scroll_area.verticalScrollBar().setValue(dialog.scroll_area.verticalScrollBar().maximum())
            QApplication.processEvents()
            image = QPixmap(1366, 768)
            image.fill('#e9edf2')
            dialog.render(image, QPoint(16, 16))
            image.save(str(tmp_path / f'import-return-scroll-{width}.png'))
            assert editor.repurchase_amount.text() == '129.99'
            assert editor.repurchase_date.text() == '2026-10-11'
            dialog.save_button.click()
            assert not errors and dialog.result() == dialog.DialogCode.Accepted
            visited.append(True)
        except BaseException as error:
            failures.append(error)
        finally:
            if dialog is not None:
                dialog.reject()

    QTimer.singleShot(0, exercise_modal)
    next(b for b in window.findChildren(QPushButton) if b.text() == 'Importar PDF').click()
    window.database = None
    window.close()
    if failures:
        raise failures[0]
    assert visited and len(repo.list_orders()) == 2


def test_return_editor_leaves_five_products_and_footer_visible(preview):
    from PySide6.QtGui import QFontDatabase, QFont
    font = Path('C:/Windows/Fonts/segoeui.ttf')
    if font.exists():
        font_id = QFontDatabase.addApplicationFont(str(font))
        QApplication.instance().setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    dialog, _, _ = preview
    configure_refund(dialog)
    dialog.show()
    QApplication.processEvents()
    dialog.update_totals()
    QApplication.processEvents()
    assert dialog.width() <= 1366 and dialog.height() <= 720
    assert dialog.table.rowViewportPosition(4) + dialog.table.rowHeight(4) <= dialog.table.viewport().height()
    assert dialog.rect().contains(dialog.save_button.mapTo(dialog, dialog.save_button.rect().bottomRight()))
    assert dialog.refund_editor.isVisible()
