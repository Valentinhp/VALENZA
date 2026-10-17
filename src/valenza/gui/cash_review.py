"""Simple partial cash counting. Bank payments remain global and independent."""
import json
import os
import tempfile
from pathlib import Path
from datetime import date
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QLineEdit,
    QPushButton,QTreeWidget,QTreeWidgetItem,QWidget,QFileDialog,QTextEdit,QMessageBox,QProgressBar,QInputDialog,QMenu)
from valenza.persistence import cash_review as store
from valenza.persistence.database import DATABASE_ERRORS
from valenza.gui.person_receipts import cents
from valenza.gui.warm_finance import apply_warm_surface,format_money
from valenza.gui.preparation_record import load_record,record_total
from valenza.gui.design_system import FlowLayout
from valenza.gui.cash_review_items import cash_review_items


class CashReviewDialog(QDialog):
    def __init__(self, repository, parent=None):
        super().__init__(parent)
        self.repository=repository;self.rows=[];self.revision=0;self.loaded=None;self.dirty=False
        self.setWindowTitle('Contar y revisar dinero');self.resize(900,650)
        apply_warm_surface(self,'cashReview')
        root=QVBoxLayout(self)
        notice=QLabel('Tu conteo independiente: marca pedidos completos o escribe parciales, aunque no tengan abonos registrados. '
            'Solo guarda tus cuentas; no registra cobros, pagos a Nu ni cambia deudas.')
        notice.setWordWrap(True);root.addWidget(notice)
        self.card=QComboBox()
        for i in repository.list_all_instruments():
            if i['instrument_type'] in ('CREDIT_CARD','CREDIT_LINE'):
                self.card.addItem(i['alias'],i['id'])
        root.addWidget(self.card)
        amounts=QHBoxLayout()
        self.physical=QLineEdit('0.00');self.physical.setAccessibleName('Dinero físico contado en MXN')
        self.extra=QLineEdit('0.00');self.extra.setAccessibleName('Dinero propio u otro efectivo no incluido en los pedidos de este conteo')
        self.physical_label=QLabel('Dinero físico')
        amounts.addWidget(self.physical_label);amounts.addWidget(self.physical)
        amounts.addWidget(QLabel('Propio / otro'));amounts.addWidget(self.extra)
        self.extra.setToolTip('Dinero propio u otro que no hayas incluido ya en este conteo por pedidos.')
        root.addLayout(amounts)
        self.summary=QLabel();self.summary.setWordWrap(True);root.addWidget(self.summary)
        self.progress=QProgressBar();self.progress.setRange(0,100)
        self.progress.setAccessibleName('Avance al identificar el efectivo contado')
        self.progress.setToolTip('Compara lo contado con el dinero físico o el objetivo del corte. Si no indicas dinero físico, muestra el avance frente al total de pedidos.')
        root.addWidget(self.progress)
        selection_actions=FlowLayout()
        self.mark_all_button=QPushButton('Marcar todo')
        self.mark_selection_button=QPushButton('Marcar selección')
        self.partial_selection_button=QPushButton('Marcar parcial de la selección')
        self.clear_selection_button=QPushButton('Desmarcar selección')
        self.mark_all_button.clicked.connect(lambda:self.apply_selection(self.rows))
        self.mark_selection_button.clicked.connect(lambda:self.apply_selection(self.selected_rows()))
        self.partial_selection_button.clicked.connect(self.partial_selection)
        self.clear_selection_button.clicked.connect(lambda:self.apply_selection(self.selected_rows(),0))
        for button in (self.mark_all_button,self.mark_selection_button,self.partial_selection_button,self.clear_selection_button):
            button.setToolTip('Selecciona personas o pedidos. Usa su importe como referencia o indica un parcial libre. No crea abonos ni pagos.')
            selection_actions.addWidget(button)
        root.addLayout(selection_actions)
        self.tree=QTreeWidget();self.tree.setColumnCount(4)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.itemSelectionChanged.connect(self.update_selection_actions)
        self.tree.setHeaderLabels(['Persona / pedido / detalle','Importe de referencia','Por cobrar','Mi conteo (MXN)'])
        self.tree.headerItem().setToolTip(2,'Solo referencia del registro de deudas: tus marcas no cambian este pendiente.')
        self.tree.setColumnWidth(0,330);root.addWidget(self.tree,1)
        self.error=QLabel();self.error.setWordWrap(True);root.addWidget(self.error)
        self.status=QLabel();self.status.setWordWrap(True);root.addWidget(self.status)
        actions=FlowLayout()
        self.save_button=QPushButton('Guardar corte');self.save_button.clicked.connect(self.save_cut)
        self.save_button.setToolTip('Elige dónde guardar un archivo JSON con los importes y todas tus casillas. Cada guardado permite crear otro archivo.')
        self.discard_stale=QPushButton('Revisar marcas desactualizadas');self.discard_stale.clicked.connect(self.clear_stale)
        self.old_button=QPushButton('Abrir corte');self.old_button.clicked.connect(self.open_old_cut)
        self.old_button.setToolTip('Abre un archivo JSON y recupera sus importes, casillas y avance.')
        self.history_button=QPushButton('Conteos guardados');self.history_button.clicked.connect(self.show_history)
        self.history_button.setToolTip('Recupera versiones guardadas en esta base de datos. Los archivos JSON se abren con Abrir corte.')
        self.new_button=QPushButton('Nuevo conteo');self.new_button.clicked.connect(self.new_count)
        self.save_local_button=QPushButton('Guardar en la app');self.save_local_button.clicked.connect(self.save_review)
        self.save_local_button.setToolTip('Guarda una versión que puedes consultar y abrir en Conteos guardados, sin crear un archivo.')
        self.new_button.setToolTip('Empieza desde cero: borra las marcas e importes de esta ventana. Tus archivos guardados se conservan.')
        close=QPushButton('Cerrar');close.clicked.connect(self.reject)
        for b in (self.save_button,self.save_local_button,self.discard_stale,self.new_button,self.old_button,self.history_button,close):actions.addWidget(b)
        root.addLayout(actions)
        self.card.currentIndexChanged.connect(self.change_card)
        self.physical.textChanged.connect(self.recalculate);self.extra.textChanged.connect(self.recalculate)
        self.tree.itemChanged.connect(self.recalculate)
        self.load_card()

    def change_card(self,index):
        if self.dirty:
            answer=QMessageBox.question(self,'Cambios sin guardar','¿Descartar los cambios de esta revisión?',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:
                with QSignalBlocker(self.card):self.card.setCurrentIndex(self.card.findData(self.card_id))
                return
        self.load_card()

    def load_card(self,data_override=None):
        self.loading=True;self.product_marks={}
        self.resumed_cut=None;self.physical_label.setText('Dinero físico')
        self.card_id=self.card.currentData();self.tree.clear();self.rows=[]
        self.sources=store.receipt_sources(self.repository,self.card_id)
        self.revision,self.loaded=store.latest(self.repository,self.card_id)
        if data_override is not None:self.loaded=data_override
        data=self.loaded or dict(format=store.FORMAT,card_id=self.card_id,physical_cents=0,extra_cents=0,entries=[])
        self.review_period=data.get('review_period',date.today().strftime('%Y-%m'))
        self.setWindowTitle('Contar y revisar dinero · MSI de '+self.review_period)
        if data.get('resumed_cut') is not None:
            self.show_old_cut(data['resumed_cut'],saved_data=data)
            self.dirty=data_override is not None
            return
        self.stale=[]
        saved={e['receivable_id']:e['amount_cents'] for e in data.get('manual_counts',[])}
        modes={e['receivable_id']:e.get('selection_mode','LEGACY') for e in data.get('manual_counts',[])}
        if 'manual_counts' not in data:
            for entry in data['entries']:
                _,receivable_id=json.loads(entry['key'])
                saved[receivable_id]=saved.get(receivable_id,0)+entry['amount_cents']
        for field,key in ((self.physical,'physical_cents'),(self.extra,'extra_cents')):
            with QSignalBlocker(field):field.setText(f"{data[key]/100:.2f}")
        people={};shares=cash_review_items(self.repository,self.card_id,as_of=date.fromisoformat(self.review_period+'-01'))
        for s in shares:
            if s['user_id'] not in people:
                people[s['user_id']]=QTreeWidgetItem(self.tree,[s['user_name']])
            apps=[v for v in self.sources.values() if v['receivable_id']==s.get('original_receivable_id',s['receivable_id'])]
            available=sum(v['amount_cents'] for v in apps if not v['inconsistent'])
            item=QTreeWidgetItem(people[s['user_id']],[s['source_name'],format_money(available),format_money(max(0,s['remaining_cents']))])
            item.setToolTip(0,s['source_name'])
            controls=QWidget();line=QHBoxLayout(controls);line.setContentsMargins(0,0,0,0)
            from PySide6.QtWidgets import QCheckBox
            checked=QCheckBox();checked.setAccessibleName('Contabilizar recibido de '+s['source_name'])
            field=QLineEdit();field.setPlaceholderText('Parcial');field.setAccessibleName('Importe parcial contabilizado de '+s['source_name'])
            value=saved.get(s['receivable_id'],0)
            field.setText(f'{value/100:.2f}');checked.setChecked(value>0)
            checked.setToolTip('Marcar el importe de referencia en tu conteo; no registra un abono.')
            field.setToolTip('Importe libre de tu conteo. No está limitado por los abonos registrados.')
            line.addWidget(checked);line.addWidget(field);self.tree.setItemWidget(item,3,controls)
            row=dict(item=item,share=s,apps=apps,available=available,reference=max(0,s['sale_cents']),field=field,checked=checked,
                selection_mode=modes.get(s['receivable_id'],'LEGACY' if value else 'PARTIAL'))
            self.rows.append(row)
            checked.toggled.connect(lambda on,r=row:self.toggle_row(r,on))
            field.textChanged.connect(lambda text,r=row:self.partial_changed(r))
            for source in apps:
                QTreeWidgetItem(item,[f"Abono {source['received_at']} · {source['payment_id'][:8]}",format_money(source['amount_cents'])])
            if s.get('order_id'):
                order=self.repository.get_order(s['order_id'])
                products=(s.get('products',[]) if s.get('is_msi') else
                    order['manual_concepts'] or (order['import_evidence'] or {}).get('products',[]))
                plan=[]
                if not s.get('is_msi') and order.get('financing_plan') and order['installments']:
                    from valenza.gui.payment_preparation import product_installment_schedule
                    all_products=[]
                    for p in products:
                        shares=p.get('allocations',{})
                        if isinstance(shares,list):shares={a['user_id']:a['amount_cents'] for a in shares}
                        all_products.append(dict(description=p['description'],amount_cents=shares.get(s['user_id'],0)))
                    if sum(p['amount_cents'] for p in all_products)==s['sale_cents']:
                        plan=product_installment_schedule(all_products,len(order['installments']))
                for index,product in enumerate(products):
                    allocations=product.get('allocations',{})
                    if isinstance(allocations,list):allocations={a['user_id']:a['amount_cents'] for a in allocations}
                    amount=product['amount_cents'] if s.get('is_msi') else allocations.get(s['user_id'],0)
                    if amount:
                        product_item=QTreeWidgetItem(item,[product['description']+
                            (' · parte de esta mensualidad (no suma)' if s.get('is_msi') else ' · participación (no suma al conteo)'),format_money(amount)])
                        key=json.dumps([s['receivable_id'],index,product['description'],amount],ensure_ascii=False)
                        self.product_marks[key]=product_item
                        product_item.setFlags(product_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        product_item.setCheckState(0,Qt.CheckState.Checked if key in data.get('checked_products',[]) else Qt.CheckState.Unchecked)
                        product_item.setToolTip(0,'Producto revisado: esta marca no suma dinero. El parcial del pedido controla la contabilización.')
                        for number,quota in enumerate(plan,1):
                            QTreeWidgetItem(product_item,[f'Mensualidad {number}/{len(plan)} · referencia, no suma',format_money(quota[index]['amount_cents'])])
            item.setExpanded(False)
        for person in people.values():person.setExpanded(True)
        self.loading=False;self.recalculate();self.dirty=data_override is not None
        self.update_selection_actions()
        obsolete=any(s.get('original_receivable_id') in saved for s in shares if s.get('is_msi'))
        self.status.setText('Los MSI muestran solo las cuotas de '+self.review_period+'. '
            +('Las marcas anteriores del pedido completo siguen en Historial; revisa y marca la cuota del mes.' if obsolete else
              'Revisión recuperada; el historial no se suma.' if self.loaded else 'Guarda para conservar tus marcas.'))

    def partial_changed(self,row,manual=True):
        if manual:row['selection_mode']='PARTIAL'
        try:active=cents(row['field'].text())>0
        except ValueError:active=False
        with QSignalBlocker(row['checked']):row['checked'].setChecked(active)
        self.recalculate()

    def toggle_row(self,row,on):
        row['selection_mode']='FULL' if on else 'PARTIAL'
        with QSignalBlocker(row['field']):
            row['field'].setText(f"{row['reference']/100:.2f}" if on else '0.00')
        self.partial_changed(row,manual=False)

    def selected_rows(self):
        selected=self.tree.selectedItems()
        rows=[]
        for row in self.rows:
            item=row['item']
            while item is not None:
                if item in selected:
                    rows.append(row);break
                item=item.parent()
        return sorted(rows,key=lambda row:(self.tree.indexOfTopLevelItem(row['item'].parent()),
                                          row['item'].parent().indexOfChild(row['item'])))

    def update_selection_actions(self):
        if getattr(self,'loading',False):return
        selected=self.selected_rows()
        active=bool(selected)
        self.mark_selection_button.setEnabled(active)
        self.partial_selection_button.setEnabled(active)
        self.clear_selection_button.setEnabled(active)
        self.mark_all_button.setEnabled(bool(self.rows))

    def apply_selection(self,rows,amount=None):
        if not rows:return
        remaining=amount
        self.loading=True
        try:
            for index,row in enumerate(rows):
                row['selection_mode']='FULL' if amount is None else 'PARTIAL'
                value=row['reference'] if remaining is None else remaining if index==len(rows)-1 else min(remaining,row['reference'])
                if remaining is not None:remaining-=value
                with QSignalBlocker(row['field']):row['field'].setText(f'{value/100:.2f}')
                with QSignalBlocker(row['checked']):row['checked'].setChecked(value>0)
        finally:self.loading=False
        self.recalculate()

    def partial_selection(self):
        rows=self.selected_rows()
        if not rows:return
        text,accepted=QInputDialog.getText(self,'Contabilizar un parcial',
            'Importe de tu conteo para esta selección (MXN), independiente de los abonos.\n'
            'Reemplaza las marcas seleccionadas; no se suma dos veces.\n'
            'Se reparte en orden; el último pedido conserva cualquier importe adicional.')
        if not accepted:return
        try:amount=cents(text)
        except ValueError as error:self.error.setText(str(error));return
        self.apply_selection(rows,amount)

    def snapshot(self):
        manual=[]
        for row in self.rows:
            amount=cents(row['field'].text())
            if amount:manual.append(dict(receivable_id=row['share']['receivable_id'],amount_cents=amount,
                label=row['share']['user_name']+' · '+row['share']['source_name'],selection_mode=row.get('selection_mode','LEGACY')))
        data=dict(format=store.FORMAT,card_id=self.card_id,
            review_period=self.review_period,
            physical_cents=cents(self.physical.text()),extra_cents=cents(self.extra.text()),entries=[],manual_counts=manual,
            checked_products=[key for key,item in self.product_marks.items() if item.checkState(0)==Qt.CheckState.Checked])
        if self.resumed_cut is not None:data['resumed_cut']=self.resumed_cut
        return store.validate_snapshot(data)

    def recalculate(self,*_):
        if not hasattr(self,'sources') or getattr(self,'loading',False):return
        self.dirty=True
        try:
            data=self.snapshot();counted=sum(e['amount_cents'] for e in data['manual_counts'])
            received=sum(s['amount_cents'] for s in {s['key']:s for r in self.rows for s in r['apps'] if not s['inconsistent']}.values())
            pending=sum(max(0,r['share']['remaining_cents']) for r in self.rows)
            identified=counted+data['extra_cents']
            diff=data['physical_cents']-counted-data['extra_cents']
            difference=(('Falta para el objetivo: ' if diff>=0 else 'Sobre el objetivo: ')+format_money(abs(diff))
                if self.resumed_cut is not None else
                'Diferencia de efectivo: '+format_money(diff)+' '+('(sobra frente a lo contabilizado)' if diff>0 else
                '(falta frente a lo contabilizado)' if diff<0 else '(cuadra lo contabilizado)'))
            self.summary.setText(f'Contabilizado: {format_money(counted)} · Abonos registrados (referencia): {format_money(received)}\n'
                f'Por cobrar: {format_money(pending)} · Propio / otro: {format_money(data["extra_cents"])} · '
                f'Total identificado: {format_money(identified)}\n'
                f'{self.physical_label.text()}: {format_money(data["physical_cents"])} · '
                +difference)
            target=data['physical_cents'] or sum(r['reference'] for r in self.rows)
            self.progress.setValue(min(100,identified*100//target) if target else 0)
            self.progress.setFormat(('Reunido para el objetivo: %p%' if self.resumed_cut is not None else 'Efectivo identificado: %p%')
                if data['physical_cents'] else 'Conteo frente al total de pedidos: %p%')
            self.progress.setEnabled(True)
            for row in self.rows:
                with QSignalBlocker(self.tree):
                    row['item'].setText(1,format_money(row['reference']))
                    row['item'].setToolTip(1,'Importe del pedido como referencia. Abonos registrados: '+format_money(row['available'])+'. Tu conteo no modifica ninguno de esos importes.')
            self.error.setText('Hay marcas de abonos editados o anulados. Revísalas antes de guardar.' if self.stale else '')
            self.save_button.setEnabled(not self.stale and self.card_id is not None)
        except ValueError as e:
            self.summary.setText('Completa o corrige los importes para actualizar el desglose. No se han guardado cambios.')
            self.progress.setValue(0);self.progress.setFormat('Revisa los importes');self.progress.setEnabled(False)
            self.error.setText(str(e));self.save_button.setEnabled(False)
        self.discard_stale.setVisible(bool(self.stale))

    def save_review(self):
        try:
            if self.stale:raise ValueError('Revisa las marcas desactualizadas.')
            self.revision=store.save(self.repository,self.snapshot(),self.revision)
            self.loaded=self.snapshot();self.dirty=False;self.status.setText('Conteo guardado en esta app. Puedes consultarlo y abrirlo en Conteos guardados. Para crear un JSON usa Guardar corte.')
        except (ValueError,*DATABASE_ERRORS) as e:self.error.setText(str(e))

    def save_cut(self):
        try:
            if self.stale:raise ValueError('Revisa las marcas desactualizadas.')
            data=self.snapshot()
            path,_=QFileDialog.getSaveFileName(self,'Guardar corte',
                'corte-'+date.today().isoformat()+'.json','Corte (*.json)')
            if not path:return
            if not path.lower().endswith('.json'):path+='.json'
            destination=Path(path)
            temporary=None
            try:
                with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=destination.parent,
                        suffix='.tmp',delete=False) as output:
                    temporary=output.name
                    json.dump(data,output,ensure_ascii=False,indent=2)
                os.replace(temporary,destination)
            finally:
                if temporary and os.path.exists(temporary):os.unlink(temporary)
            self.loaded=data;self.dirty=False
            self.status.setText('Corte guardado en: '+str(destination.resolve()))
            try:self.revision=store.save(self.repository,data,self.revision)
            except (ValueError,*DATABASE_ERRORS):
                self.status.setText(self.status.text()+' · El archivo está guardado; no se pudo crear la copia en esta app.')
        except (OSError,ValueError) as error:self.error.setText(str(error))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'tree'):
            width=self.tree.viewport().width()
            for column,fraction in ((0,.32),(1,.30),(2,.16)):
                self.tree.setColumnWidth(column,int(width*fraction))

    def new_count(self):
        if QMessageBox.question(self,'Nuevo conteo','¿Desmarcar el conteo actual? El historial guardado se conserva y no cambia ningún abono ni pago.',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        self.load_card(data_override=dict(format=store.FORMAT,card_id=self.card_id,
            review_period=date.today().strftime('%Y-%m'),physical_cents=0,extra_cents=0,entries=[],manual_counts=[],checked_products=[]))
        self.status.setText('Conteo nuevo: importes y casillas en cero. Usa Guardar corte para crear su archivo JSON.')

    def clear_stale(self):
        if QMessageBox.question(self,'Revisar cambios','¿Retirar las marcas de abonos que cambiaron? El historial anterior se conserva.',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes:
            self.stale=[];self.recalculate()

    def show_text(self,title,text):
        dialog=QDialog(self);dialog.setWindowTitle(title);dialog.resize(750,500)
        layout=QVBoxLayout(dialog);view=QTextEdit();view.setReadOnly(True);view.setPlainText(text);layout.addWidget(view)
        close=QPushButton('Cerrar');close.clicked.connect(dialog.accept);layout.addWidget(close);dialog.exec()

    def show_history(self):
        lines=[]
        labels={r['id']:r['label'] for r in self.repository.database.connection.execute(
            """SELECT r.id,p.name||' · '||COALESCE(o.merchant,pu.merchant,'Origen por verificar') AS label
               FROM receivable r JOIN person p ON p.id=r.user_id
               LEFT JOIN order_record o ON o.id=r.order_id LEFT JOIN purchase pu ON pu.id=r.purchase_id""")}
        for item in store.history(self.repository,self.card_id):
            data=json.loads(item['new_value']);counted=sum(e['amount_cents'] for e in data.get('manual_counts',data['entries']))
            lines.append(f"{item['occurred_at']} · revisión {item['revision']}\nMi conteo {format_money(counted)} · efectivo {format_money(data['physical_cents'])} · propio/otro {format_money(data['extra_cents'])}")
            for entry in data.get('manual_counts',[]):
                lines.append(f"  {entry['label']} · conteo independiente: {format_money(entry['amount_cents'])}")
            for entry in data['entries']:
                payment,receivable=json.loads(entry['key'])
                lines.append(f"  {labels.get(receivable,receivable)} · abono {payment} · {format_money(entry['amount_cents'])}")
            lines.append('')
        self.history_text='\n'.join(lines) or 'Sin revisiones guardadas.'
        self.history_menu=QMenu(self)
        self.history_menu.setToolTipsVisible(True)
        for revision in store.history(self.repository,self.card_id):
            data=json.loads(revision['new_value'])
            total=sum(e['amount_cents'] for e in data.get('manual_counts',data['entries']))
            name=data.get('resumed_cut',{}).get('name','Mi revisión')
            action=self.history_menu.addAction(f"{name} · {revision['occurred_at']} · {format_money(total)}")
            action.setData(data)
            action.setToolTip('Retomar en esta ventana. El historial no se suma al conteo.')
            action.triggered.connect(lambda checked=False,d=data:self.resume_review(d))
        if not self.history_menu.actions():self.history_menu.addAction('Sin revisiones guardadas').setEnabled(False)
        from valenza.gui.cash_review_history import CashReviewHistoryDialog
        self.history_dialog=CashReviewHistoryDialog(self)
        self.history_dialog.show()

    def open_old_cut(self):
        path,_=QFileDialog.getOpenFileName(self,'Abrir corte','','Corte (*.json)')
        if not path:return
        try:
            if Path(path).stat().st_size>10_000_000:raise ValueError('El archivo del corte es demasiado grande.')
            with open(path,encoding='utf-8-sig') as source:record=json.load(source)
            if isinstance(record,dict) and record.get('format')==store.FORMAT:
                self.resume_review(record)
            else:
                self.show_old_cut(load_record(path))
            self.dirty=False
            self.status.setText('Corte abierto: '+str(path)+' · Continúa el conteo y usa Guardar corte para crear un archivo con los cambios.')
        except (OSError,ValueError,KeyError,TypeError) as e:self.error.setText(str(e))

    def show_old_cut(self,record,saved_data=None):
        # Restore the saved checklist in this window, without touching ledgers.
        from valenza.gui.preparation_record import validate_record
        validate_record(record)
        from valenza.persistence.subscription_fees import refresh_resumed_cut
        record,saved_data=refresh_resumed_cut(self.repository,record,saved_data)
        index=self.card.findData(record['card_id'])
        if index<0:raise ValueError('La tarjeta del corte no existe en esta base.')
        monthly=cash_review_items(self.repository,record['card_id'],as_of=date.fromisoformat(record['date']))
        replacements={}
        msi_orders={row['order_id'] for row in self.repository.database.connection.execute('SELECT order_id FROM financing_plan')}
        for item in monthly:
            if item.get('is_msi'):replacements.setdefault(item['original_receivable_id'],[]).append(item)
        converted=False;cut_rows=[]
        for old_row in record['rows']:
            item=old_row['item'];base=item.get('original_receivable_id',item['receivable_id'])
            if not item.get('installment_id') and (base in replacements or item.get('is_msi') or item.get('order_id') in msi_orders):
                # A whole-plan mark cannot be assigned to a monthly quota by assumption.
                converted=True
                cut_rows.extend(dict(item=dict(quota),contributions=[dict(amount_cents=p['amount_cents'],included=False)
                    for p in quota.get('products',[])]) for quota in replacements.get(base,[]))
            else:cut_rows.append(old_row)
        if converted:record=dict(record,rows=cut_rows)
        self.loading=True
        with QSignalBlocker(self.card):self.card.setCurrentIndex(index)
        self.card_id=record['card_id'];self.revision,_=store.latest(self.repository,self.card_id)
        self.review_period=record['date'][:7]
        self.setWindowTitle('Contar y revisar dinero · Corte '+self.review_period)
        self.resumed_cut=record;self.stale=[];self.product_marks={}
        self.tree.clear();self.rows=[]
        self.sources={}
        physical=saved_data['physical_cents'] if saved_data is not None else record['target_cents']
        extra=saved_data['extra_cents'] if saved_data is not None else record['own_cents']
        for field,value in ((self.physical,physical),(self.extra,extra)):
            with QSignalBlocker(field):field.setText(f'{value/100:.2f}')
        self.physical_label.setText('Objetivo del corte')
        saved={e['receivable_id']:e['amount_cents'] for e in saved_data['manual_counts']} if saved_data is not None else None
        people={}
        from PySide6.QtWidgets import QCheckBox
        for cut_row in record['rows']:
            share=dict(cut_row['item'])
            if share['user_id'] not in people:people[share['user_id']]=QTreeWidgetItem(self.tree,[share['user_name']])
            item=QTreeWidgetItem(people[share['user_id']],[share['source_name'],'',format_money(max(0,share['remaining_cents']))])
            amount=(saved.get(share['receivable_id'],0) if saved is not None else
                sum(c['amount_cents'] for c in cut_row['contributions'] if c['included']))
            controls=QWidget();line=QHBoxLayout(controls);line.setContentsMargins(0,0,0,0)
            checked=QCheckBox();checked.setChecked(amount>0);checked.setAccessibleName('Marcar '+share['source_name'])
            field=QLineEdit(f'{amount/100:.2f}');field.setAccessibleName('Parcial de '+share['source_name'])
            line.addWidget(checked);line.addWidget(field);self.tree.setItemWidget(item,3,controls)
            modes={e['receivable_id']:e.get('selection_mode','LEGACY') for e in saved_data['manual_counts']} if saved_data is not None else {}
            row=dict(item=item,share=share,apps=[],available=share['paid_cents'],reference=max(0,share['sale_cents']),checked=checked,field=field,
                selection_mode=modes.get(share['receivable_id'],'LEGACY' if amount else 'PARTIAL'))
            self.rows.append(row)
            checked.toggled.connect(lambda on,r=row:self.toggle_row(r,on))
            field.textChanged.connect(lambda text,r=row:self.partial_changed(r))
            for number,contribution in enumerate(cut_row['contributions']):
                products=share.get('products',[])
                name=products[number]['description'] if products else f'Aportación {number+1}'
                child=QTreeWidgetItem(item,[name,format_money(contribution['amount_cents'])])
                key=json.dumps(['cut',share['receivable_id'],number])
                self.product_marks[key]=child
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                included=key in saved_data.get('checked_products',[]) if saved_data is not None else contribution['included']
                child.setCheckState(0,Qt.CheckState.Checked if included else Qt.CheckState.Unchecked)
                child.setToolTip(0,'Marca de revisión; el importe de Mi conteo controla el total, sin sumarlo dos veces.')
            item.setExpanded(True)
        for person in people.values():person.setExpanded(True)
        self.loading=False;self.recalculate();self.update_selection_actions()
        self.status.setText('Retomando '+record['name']+' · '+record['date']+'. '+
            ('Los MSI completos se separaron por mensualidad; revisa sus marcas. El corte original no se modificó.' if converted else
             'Puedes continuar aquí; guardar conserva una nueva revisión.'))

    def resume_review(self,data):
        store.validate_snapshot(data)
        index=self.card.findData(data['card_id'])
        if index<0:raise ValueError('La tarjeta de la revisión no existe en esta base.')
        with QSignalBlocker(self.card):self.card.setCurrentIndex(index)
        self.load_card(data_override=data)
        self.status.setText('Revisión anterior retomada. Continúa aquí y guarda para conservar los cambios.')

    def reject(self):
        if self.dirty and QMessageBox.question(self,'Cambios sin guardar','¿Cerrar sin guardar la revisión?',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        self.dirty=False
        super().reject()

    def closeEvent(self,event):
        self.reject()
        if self.dirty:event.ignore()
        else:event.accept()
