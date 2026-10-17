"""Action wording must follow existing persistence and draft behavior."""
from pathlib import Path
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QInputDialog, QMessageBox, QPushButton, QTableWidget, QComboBox, QFileDialog

from test_ux_block1 import window, settle, snapshot
from test_product_refunds import repository
from valenza.gui.app import MxnLineEdit
from valenza.gui.person_receipts import ReceiptPreview


def select_order(ui, identity):
    ui.navigation.setCurrentRow(2)
    row = next(row for row in range(ui.orders_table.rowCount()) if ui.orders_table.item(row, 8).text() == identity)
    ui.orders_table.selectRow(row)


def dismiss(dialog, method):
    if method == 'escape':
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
    elif method == 'titlebar':
        dialog.close()
    else:
        next(button for button in dialog.findChildren(QPushButton)
             if button.text() in ('Cerrar y conservar borrador', 'Descartar cambios', 'Cerrar')).click()


@pytest.mark.parametrize('method', ['button', 'escape', 'titlebar'])
def test_new_draft_retained_but_edit_discarded(window, method):
    app, ui, db = window
    before = snapshot(db)
    ui._open_manual_expense()
    assert ui.cancel_manual_button.text() == 'Cerrar y conservar borrador'
    ui.order_merchant.setText('Borrador sintético')
    ui.manual_concepts.item(0, 0).setText('Concepto sin guardar')
    dismiss(ui.manual_dialog, method)
    ui._open_manual_expense()
    assert ui.order_merchant.text() == 'Borrador sintético'
    assert ui.manual_concepts.item(0, 0).text() == 'Concepto sin guardar'
    assert snapshot(db) == before
    ui.manual_dialog.reject()
    ui._clear_order_form()
    select_order(ui, 'normal')
    ui._edit_manual_expense()
    assert ui.cancel_manual_button.text() == 'Descartar cambios'
    assert ui.save_order_button.text() == 'Guardar conceptos y reparto'
    assert 'ya confirmadas se conservan' in ui.manual_action_notice.text()
    ui.manual_concepts.item(0, 0).setText('Edición sin guardar')
    dismiss(ui.manual_dialog, method)
    assert ui.manual_edit_id is None
    assert snapshot(db) == before


def test_manual_success_after_persistence_only_and_error_keeps_draft(window, monkeypatch):
    app, ui, db = window
    before = snapshot(db)
    errors = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args[2]))
    ui._open_manual_expense()
    ui.order_merchant.setText('Gasto sintético')
    ui.order_date.setText('2026-10-15')
    ui.manual_concepts.item(0, 0).setText('Concepto sintético')
    ui.manual_concepts.item(0, 1).setText('100.00')
    ui.order_charged.setText('100.00')
    original = ui.repository.create_order
    def fail(**kwargs):
        raise ValueError('Fallo sintético de guardado')
    monkeypatch.setattr(ui.repository, 'create_order', fail)
    ui.statusBar().showMessage('Operación anterior guardada.')
    ui._save_order()
    assert errors and not ui.statusBar().currentMessage()
    assert ui.manual_dialog.isVisible()
    assert ui.manual_concepts.item(0, 0).text() == 'Concepto sintético'
    assert snapshot(db) == before
    monkeypatch.setattr(ui.repository, 'create_order', original)
    ui._save_order()
    assert ui.statusBar().currentMessage() == 'Gasto guardado.'
    assert not ui.manual_dialog.isVisible()
    assert len(ui.repository.list_orders()) == 3
    new_id = next(row['id'] for row in ui.repository.list_orders() if row['merchant'] == 'Gasto sintético')
    select_order(ui, new_id)
    ui._edit_manual_expense()
    ui.manual_concepts.item(0, 0).setText('Descripción corregida')
    ui._save_order()
    assert ui.statusBar().currentMessage() == 'Conceptos y reparto guardados.'
    assert ui.repository.get_order(new_id)['charged_cents'] == 10000
    assert len(ui.repository.list_orders()) == 3


@pytest.mark.parametrize('method', ['button', 'escape', 'titlebar'])
def test_existing_msi_has_close_without_suggesting_rollback(window, monkeypatch, method):
    app, ui, db = window
    select_order(ui, 'msi')
    before = snapshot(db)
    def inspect(dialog):
        dialog.show(); settle(app)
        assert dialog.save_button.text() == 'Cerrar'
        assert dialog.cancel_button.isHidden()
        assert any('Cerrar no deshace' in label.text() for label in dialog.findChildren(QLabel))
        dismiss(dialog, method)
        return dialog.result()
    monkeypatch.setattr(QDialog, 'exec', inspect)
    ui._msi_dialog()
    assert snapshot(db) == before


def test_msi_immediate_date_and_adjustment_success_failure_and_close(window, monkeypatch):
    app, ui, db = window
    select_order(ui, 'msi')
    order_before = ui.repository.get_order('msi')
    def exercise(dialog):
        dialog.show(); settle(app)
        table = dialog.findChild(QTableWidget)
        table.selectRow(0)
        feedback = dialog.findChild(QLabel, 'actionFeedback')
        edit = next(b for b in dialog.findChildren(QPushButton) if b.text().startswith('Editar fecha'))
        before = snapshot(db)
        monkeypatch.setattr(QInputDialog, 'getText', lambda *args, **kwargs: ('', False))
        edit.click()
        assert snapshot(db) == before and not feedback.text()
        monkeypatch.setattr(QInputDialog, 'getText', lambda *args, **kwargs: ('2026-02-30', True))
        edit.click()
        assert snapshot(db) == before and not feedback.text()
        monkeypatch.setattr(QInputDialog, 'getText', lambda *args, **kwargs: ('2026-10-18', True))
        edit.click()
        assert feedback.text() == 'Fecha de cuota guardada.'
        assert ui.repository.list_installments('card')[0]['due_date'] == '2026-10-18'
        before_adjust = snapshot(db)
        apply = next(b for b in dialog.findChildren(QPushButton) if b.text().startswith('Aplicar ajuste'))
        apply.click()  # A reason is still required; no success on failure.
        assert snapshot(db) == before_adjust and not feedback.text()
        reason = next(f for f in dialog.findChildren(QLineEdit) if f.placeholderText().startswith('Motivo'))
        reason.setText('Ajuste sintético autorizado')
        dialog.findChild(MxnLineEdit).setText('11999.00')
        apply.click()
        assert feedback.text() == 'Ajuste de cuotas previstas guardado.'
        dialog.reject()  # Escape/title-bar closing never rolls back actions already saved.
        return dialog.result()
    monkeypatch.setattr(QDialog, 'exec', exercise)
    ui._msi_dialog()
    assert ui.repository.list_installments('card')[0]['due_date'] == '2026-10-18'
    after = ui.repository.get_order('msi')
    assert after['charged_cents'] == order_before['charged_cents'] == 1200000
    assert after['allocations'] == order_before['allocations']
    assert len(ui.repository.list_orders()) == 2
    assert ui.repository.count('institution_payment') == ui.repository.count('user_payment') == 0


def test_msi_link_cancel_validation_and_save_preserve_one_charge(window, monkeypatch):
    app, ui, db = window
    select_order(ui, 'normal')
    before = snapshot(db)
    def cancel(dialog):
        assert dialog.save_button.text() == 'Vincular plan MSI'
        dialog.reject()
        return dialog.result()
    monkeypatch.setattr(QDialog, 'exec', cancel)
    ui._msi_dialog()
    assert snapshot(db) == before
    def save(dialog):
        dialog.show(); settle(app)
        dialog.save_button.click()
        assert dialog.isVisible() and snapshot(db) == before
        assert 'vinculado' not in ui.statusBar().currentMessage()
        field = next(f for f in dialog.findChildren(QLineEdit) if 'banco' in f.placeholderText())
        field.setText('2026-10-20')
        dialog.save_button.click()
        assert dialog.result() == QDialog.DialogCode.Accepted
        return dialog.result()
    monkeypatch.setattr(QDialog, 'exec', save)
    ui._msi_dialog()
    assert ui.statusBar().currentMessage() == 'Plan MSI vinculado al pedido.'
    assert len(ui.repository.list_orders()) == 2
    assert ui.repository.get_order('normal')['charged_cents'] == 150000
    assert len([i for i in ui.repository.list_installments('card') if i['order_id'] == 'normal']) == 3


def test_subscription_create_edit_cancel_and_success(window, monkeypatch):
    app, ui, db = window
    before = snapshot(db)
    def create(dialog):
        dialog.show(); settle(app)
        assert dialog.save_button.text() == 'Crear suscripción'
        dialog.save_button.click()
        assert dialog.isVisible() and snapshot(db) == before
        assert not ui.statusBar().currentMessage()
        fields = dialog.findChildren(QLineEdit)
        fields[0].setText('Nueva sintética'); fields[1].setText('100.00'); fields[3].setText('100.00')
        dialog.save_button.click()
        assert dialog.result() == QDialog.DialogCode.Accepted
        return dialog.result()
    monkeypatch.setattr(QDialog, 'exec', create)
    ui.statusBar().showMessage('Operación anterior guardada.')
    ui._edit_subscription()
    assert ui.statusBar().currentMessage() == 'Suscripción creada.'
    before_edit = snapshot(db)
    def cancel(dialog):
        assert dialog.cancel_button.text() == 'Descartar cambios'
        dialog.findChildren(QLineEdit)[0].setText('Cambio no guardado')
        dialog.reject()
        return dialog.result()
    monkeypatch.setattr(QDialog, 'exec', cancel)
    ui._edit_subscription('sub')
    assert snapshot(db) == before_edit
    def edit(dialog):
        assert dialog.save_button.text() == 'Guardar suscripción'
        dialog.findChildren(QLineEdit)[0].setText('Nombre corregido')
        dialog.save_button.click()
        return dialog.result()
    monkeypatch.setattr(QDialog, 'exec', edit)
    ui._edit_subscription('sub')
    assert ui.statusBar().currentMessage() == 'Suscripción actualizada.'
    assert len(ui.repository.list_orders()) == 2  # Editing a forecast never posts a charge.


def test_global_receipt_preview_cancel_failure_success_and_bank_independence(window):
    app, ui, db = window
    ui.navigation.setCurrentRow(3)
    panel = ui.person_receipt_panel
    panel.person.setCurrentIndex(panel.person.findData('family'))
    panel.amount.setText('100.00'); panel.reference.setText('Referencia sintética')
    before = snapshot(db)
    accounts = ui.repository.person_receipt_accounts('family')
    preview = ReceiptPreview(panel, accounts, 10000)
    assert preview.confirm.text() == 'Registrar abono global'
    next(b for b in preview.findChildren(QPushButton) if b.text() == 'Volver sin registrar').click()
    assert panel.amount.text() == '100.00' and panel.reference.text() == 'Referencia sintética'
    assert snapshot(db) == before and not panel.feedback.text()
    preview = ReceiptPreview(panel, accounts, 10000)
    preview.table.item(0, 3).setText('99.00')
    preview.commit()
    assert preview.error.text() and not panel.feedback.text() and snapshot(db) == before
    preview.table.item(0, 3).setText('100.00')
    bank_before = ui.repository.list_card_summaries()
    preview.commit()
    assert panel.feedback.text() == 'Abono global registrado.'
    assert ui.repository.count('user_payment') == 1
    assert ui.repository.list_card_summaries() == bank_before


def test_confirmed_charge_survives_failed_concept_save_and_cancel(window, monkeypatch):
    app, ui, db = window
    select_order(ui, 'normal')
    ui._edit_manual_expense()
    original = ui.repository.editable_order_concepts(ui.repository.get_order('normal'))
    ui.manual_concepts.item(0, 0).setText('Concepto aún sin guardar')
    ui.order_charged.setText('1490.00')
    monkeypatch.setattr(QInputDialog, 'getText', lambda *args, **kwargs: ('Corrección sintética confirmada', True))
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    ui.correct_charge_button.click()
    assert ui.repository.get_order('normal')['charged_cents'] == 149000
    assert 'Cargo real guardado' in ui.manual_action_notice.text()
    after_charge = snapshot(db)
    errors = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args[2]))
    def fail(*args, **kwargs):
        raise ValueError('Fallo sintético al guardar conceptos')
    monkeypatch.setattr(ui.repository, 'update_manual_concepts', fail)
    ui._save_order()
    assert errors and ui.manual_dialog.isVisible() and not ui.statusBar().currentMessage()
    assert snapshot(db) == after_charge
    ui.cancel_manual_button.click()
    assert ui.repository.get_order('normal')['charged_cents'] == 149000
    assert ui.repository.editable_order_concepts(ui.repository.get_order('normal')) == original


@pytest.mark.parametrize('link', [False, True])
def test_subscription_charge_reports_actual_action(window, monkeypatch, link):
    app, ui, db = window
    repo = ui.repository
    repo.create_order(order_id='matching', ordered_at='2026-10-20', merchant='Servicio sintético',
        instrument_id='card', original_cents=10000, discount_cents=0, charged_cents=10000,
        allocations=({'user_id':'owner', 'amount_cents':5000}, {'user_id':'family', 'amount_cents':5000}))
    ui.navigation.setCurrentRow(5)
    ui.subscription_table.selectRow(0)
    before = snapshot(db)
    def cancel(dialog):
        dialog.reject(); return dialog.result()
    monkeypatch.setattr(QDialog, 'exec', cancel)
    ui._subscription_charge_dialog()
    assert snapshot(db) == before and not ui.statusBar().currentMessage()
    def save(dialog):
        dialog.show(); settle(app)
        dialog.findChild(QLineEdit).setText('2026-10-20')
        if link:
            choices = dialog.findChild(QComboBox)
            choices.setCurrentIndex(choices.findData('matching'))
            assert dialog.save_button.text() == 'Vincular pedido existente'
        else:
            assert dialog.save_button.text() == 'Registrar cargo real'
        dialog.save_button.click()
        assert dialog.result() == QDialog.DialogCode.Accepted
        return dialog.result()
    monkeypatch.setattr(QDialog, 'exec', save)
    ui._subscription_charge_dialog()
    assert ui.statusBar().currentMessage() == ('Pedido vinculado a la suscripción.' if link else 'Cargo real registrado.')
    assert len(repo.list_orders()) == (3 if link else 4)


def test_comparison_feedback_never_claims_financial_agreement(window, monkeypatch):
    app, ui, db = window
    ui.navigation.setCurrentRow(4); ui.cards_table.selectRow(0)
    before = snapshot(db)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: None)
    ui.bank_query_amount.clear()
    ui._record_bank_query()
    assert snapshot(db) == before and not ui.statusBar().currentMessage()
    ui.bank_query_amount.setText('13500.00')
    ui.bank_closing_date.setText('2026-10-10')
    ui.bank_due_date.setText('2026-10-20')
    bank_before = ui.repository.list_card_summaries()
    ui._record_bank_query()
    assert ui.statusBar().currentMessage() == 'Comparación guardada en el historial.'
    assert ui.repository.list_card_summaries() == bank_before
    ui.bank_scope.setCurrentIndex(ui.bank_scope.findData('card'))
    ui._record_bank_scope()
    assert ui.statusBar().currentMessage() == 'Vínculo informativo guardado.'


def test_import_cancel_validation_and_success_only_after_commit(window, monkeypatch):
    from valenza.ocr.order_import import parse_receipt
    from valenza.gui.pdf_import import ImportPreview
    import valenza.ocr.order_import as importing
    app, ui, db = window
    draft = parse_receipt((Path(__file__).parent/'fixtures_synthetic/mp_products.txt').read_text(encoding='utf-8'))
    draft['fingerprint'] = 'synthetic-block2-import'
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: ('synthetic.pdf', 'PDF'))
    monkeypatch.setattr(importing, 'read_receipt', lambda *args: draft)
    before = snapshot(db)
    def cancel(dialog):
        assert isinstance(dialog, ImportPreview)
        assert dialog.cancel_button.text() == 'Cancelar importación'
        dialog.cancel_button.click()
        return dialog.result()
    monkeypatch.setattr(QDialog, 'exec', cancel)
    ui._import_order_pdf()
    assert snapshot(db) == before and not ui.statusBar().currentMessage()
    def save(dialog):
        errors = []
        monkeypatch.setattr(QMessageBox, 'warning', lambda *args: errors.append(args[2]))
        dialog.show(); settle(app)
        original = dialog.fields['paid'].text()
        dialog.fields['paid'].setText('1.00')
        dialog.save()
        assert errors and snapshot(db) == before and dialog.isVisible()
        assert not ui.statusBar().currentMessage()
        dialog.fields['paid'].setText(original)
        dialog.instrument.setCurrentIndex(dialog.instrument.findData('card'))
        dialog.save()
        assert dialog.result() == QDialog.DialogCode.Accepted, errors
        return dialog.result()
    monkeypatch.setattr(QDialog, 'exec', save)
    ui._import_order_pdf()
    assert ui.statusBar().currentMessage() == 'Pedido importado y guardado.'
    assert len(ui.repository.list_orders()) == 3


@pytest.mark.parametrize('editing', [False, True])
def test_repurchase_cancel_retains_saved_refund_and_existing_repurchase(repository, editing):
    from test_product_refunds import purchase_args, saved_repurchase_assigned_to_owner
    from valenza.gui.app import create_application
    from valenza.gui.pdf_import import RefundRepurchaseDialog
    app = create_application([])
    if editing:
        refund = saved_repurchase_assigned_to_owner(repository)
    else:
        repository.create_order(**purchase_args())
        refund = repository.list_product_refunds('order')[0]
    before = snapshot(repository.database)
    dialog = RefundRepurchaseDialog(repository, refund)
    dialog.show(); settle(app)
    assert dialog.cancel_button.text() == ('Descartar cambios' if editing else 'Cancelar recompra')
    assert dialog.save_button.text() == ('Guardar reparto' if editing else 'Guardar recompra')
    dialog.cancel_button.click()
    assert snapshot(repository.database) == before
