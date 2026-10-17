"""Contextual editing; never reuse the new-receipt form for an existing receipt."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QLabel,QLineEdit,QPushButton,QHBoxLayout
from valenza.gui.warm_finance import apply_warm_surface
from valenza.gui.warm_finance import date_label

class ReceiptEditDialog(QDialog):
    def __init__(self,item,global_receipt=False,parent=None):
        super().__init__(parent);self.setWindowTitle('Editar abono seleccionado')
        apply_warm_surface(self,'receiptEdit');root=QVBoxLayout(self)
        title=QLabel(f"{item['user_name']} · {item['source_name']}\nAbono del {date_label(str(item['received_at'])[:10])} · Referencia: {item['reference'] or 'Sin referencia'}\nEditar modifica este mismo abono; no crea otro.")
        title.setWordWrap(True);root.addWidget(title)
        form=QFormLayout();root.addLayout(form)
        self.amount=QLineEdit(f"{item['amount_cents']/100:.2f}")
        self.received_at=QLineEdit(str(item['received_at'])[:10]);self.reference=QLineEdit(item['reference'] or '')
        for label,field in (('Importe (MXN)',self.amount),('Fecha AAAA-MM-DD',self.received_at),('Referencia',self.reference)):
            field.setAccessibleName(label);form.addRow(label,field)
        if global_receipt:
            self.amount.setReadOnly(True)
            note=QLabel('Abono global: puedes editar fecha y referencia. Para cambiar importe o reparto, anula el abono completo y registra el correcto.')
            note.setWordWrap(True);root.addWidget(note)
        actions=QHBoxLayout();cancel=QPushButton('Cancelar');cancel.clicked.connect(self.reject)
        save=QPushButton('Guardar cambios');save.clicked.connect(self.accept)
        actions.addWidget(cancel);actions.addWidget(save);root.addLayout(actions)
