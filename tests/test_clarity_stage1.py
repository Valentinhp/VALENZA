from PySide6.QtWidgets import QMessageBox, QFileDialog
from test_ux_block1 import window, snapshot


def test_subscription_cancel_is_explicitly_local(window, monkeypatch):
    app, ui, db = window
    ui.navigation.setCurrentRow(5)
    assert 'recargos anteriores' in ui.subscription_detail.text()
    ui.subscription_table.selectRow(0)
    before = snapshot(db)
    prompts=[]
    def decline(*args):
        prompts.append(args[2])
        return QMessageBox.StandardButton.No
    monkeypatch.setattr(QMessageBox,'question',decline)
    ui._subscription_status(True)
    assert 'NO cancela el servicio' in prompts[0]
    assert snapshot(db)==before


def test_persistent_feedback_and_error_clear(window, monkeypatch):
    app, ui, db = window
    ui.navigation.setCurrentRow(2)
    ui._show_information('Gasto guardado.',location='Pedidos: Comercio sintético · 17 oct 2026')
    ui.statusBar().clearMessage()
    assert 'Comercio sintético' in ui.action_feedback.text()
    assert 'Dónde encontrarlo' in ui.action_feedback.text()
    monkeypatch.setattr(QMessageBox,'critical',lambda *args:None)
    ui._show_error('Fallo de prueba')
    assert not ui.action_feedback.text()


def test_pdf_success_has_path_and_cancel_has_no_success(window,tmp_path,monkeypatch):
    app, ui, db = window
    path=tmp_path/'persona.pdf'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(path),''))
    ui._export_family_pdf('family')
    assert path.exists()
    assert str(path.resolve()) in ui.action_feedback.text()
    ui.action_feedback.clear()
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:('',''))
    ui._export_family_pdf('family')
    assert not ui.action_feedback.text()
