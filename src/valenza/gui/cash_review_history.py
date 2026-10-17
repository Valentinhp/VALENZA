"""Browse saved cash counts without changing the current checklist."""
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTreeWidget,
    QTreeWidgetItem,QTextEdit,QPushButton,QFileDialog,QMessageBox)
from valenza.persistence import cash_review as store
from valenza.gui.warm_finance import apply_warm_surface,format_money


class CashReviewHistoryDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner=owner
        self.setWindowTitle('Conteos guardados · '+owner.card.currentText())
        self.resize(800,600)
        apply_warm_surface(self,'cashReviewHistory')
        layout=QVBoxLayout(self)
        notice=QLabel('Versiones guardadas en esta app para esta tarjeta. Selecciona una para consultar sus detalles. '
            'Abrir conteo recupera sus marcas; Exportar JSON crea un archivo sin cambiar tu conteo actual.')
        notice.setWordWrap(True);layout.addWidget(notice)
        self.list=QTreeWidget();self.list.setHeaderLabels(['Fecha y hora','Mes','Contado','Dinero físico / objetivo'])
        layout.addWidget(self.list,1)
        self.details=QTextEdit();self.details.setReadOnly(True)
        self.details.setAccessibleName('Detalle del conteo guardado');layout.addWidget(self.details,1)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        actions=QHBoxLayout();layout.addLayout(actions)
        self.open_button=QPushButton('Abrir conteo');self.open_button.clicked.connect(self.open_count)
        self.export_button=QPushButton('Exportar JSON');self.export_button.clicked.connect(self.export_count)
        close=QPushButton('Cerrar');close.clicked.connect(self.close)
        for button in (self.open_button,self.export_button,close):actions.addWidget(button)
        for revision in store.history(owner.repository,owner.card_id):
            data=json.loads(revision['new_value'])
            total=sum(e['amount_cents'] for e in data.get('manual_counts',data['entries']))
            stamp=datetime.fromisoformat(revision['occurred_at']).astimezone().strftime('%d/%m/%Y %H:%M:%S')
            item=QTreeWidgetItem(self.list,[stamp,data.get('review_period',''),format_money(total),format_money(data['physical_cents'])])
            item.setData(0,Qt.ItemDataRole.UserRole,data)
        self.list.currentItemChanged.connect(self.preview)
        self.list.itemDoubleClicked.connect(lambda *_:self.open_count())
        if self.list.topLevelItemCount():self.list.setCurrentItem(self.list.topLevelItem(0))
        else:
            self.details.setPlainText('Todavía no hay conteos guardados para esta tarjeta. Usa Guardar en la app o Guardar corte para conservar el primero.')
            self.open_button.setEnabled(False);self.export_button.setEnabled(False)
        self.list.resizeColumnToContents(0)

    def selected(self):
        item=self.list.currentItem()
        return item.data(0,Qt.ItemDataRole.UserRole) if item else None

    def preview(self,*_):
        data=self.selected()
        if data is None:return
        lines=['Dinero físico / objetivo: '+format_money(data['physical_cents']),
            'Propio / otro: '+format_money(data['extra_cents']),
            'Productos marcados: '+str(len(data.get('checked_products',[]))), '', 'Pedidos incluidos:']
        for entry in data.get('manual_counts',[]):
            lines.append(entry['label']+' · '+format_money(entry['amount_cents']))
        for entry in data['entries']:
            lines.append('Abono '+entry['key']+' · '+format_money(entry['amount_cents']))
        self.details.setPlainText('\n'.join(lines))

    def open_count(self):
        data=self.selected()
        if data is None:return
        if self.owner.dirty and QMessageBox.question(self,'Abrir conteo',
                'Hay cambios sin guardar en el conteo actual. ¿Descartarlos y abrir el conteo seleccionado?',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        try:
            self.owner.resume_review(data)
            self.owner.dirty=False
            self.owner.status.setText('Conteo guardado abierto. Puedes continuar y guardar una nueva versión o un archivo JSON.')
            self.close()
        except (ValueError,KeyError,TypeError) as error:self.status.setText(str(error))

    def export_count(self):
        data=self.selected()
        if data is None:return
        path,_=QFileDialog.getSaveFileName(self,'Exportar conteo guardado','corte-guardado.json','Corte (*.json)')
        if not path:return
        if not path.lower().endswith('.json'):path+='.json'
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=Path(path).parent,delete=False) as output:
                temporary=output.name
                json.dump(data,output,ensure_ascii=False,indent=2)
            os.replace(temporary,path)
            self.status.setText('Archivo guardado en: '+str(Path(path).resolve()))
        except OSError as error:self.status.setText(str(error))
        finally:
            if temporary and os.path.exists(temporary):os.unlink(temporary)
