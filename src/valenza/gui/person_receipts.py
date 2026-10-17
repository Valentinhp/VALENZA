"""Compact person account and explicit global receipt preview."""
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QComboBox,
 QLineEdit,QPushButton,QCheckBox,QTableWidget,QTableWidgetItem,QHeaderView,QFrame)
from valenza.gui.warm_finance import apply_warm_surface,warm_section,format_money,date_label
from valenza.persistence.database import DATABASE_ERRORS
from valenza.gui.errors import user_error
from valenza.gui.design_system import FlowLayout


def cents(text):
 try:
  value=Decimal(text.strip())
  if not value.is_finite() or value<0 or value*100 != (value*100).to_integral_value(): raise ValueError()
  return int(value*100)
 except (InvalidOperation,ValueError):
  raise ValueError('Introduce un importe positivo con hasta dos decimales.')


class PersonReceiptPanel(QFrame):
 def __init__(self,repository,changed,parent=None):
  super().__init__(parent)
  self.repository,self.changed=repository,changed
  self.setObjectName('summaryCard');self._preview_active=False
  body=QVBoxLayout(self);body.setContentsMargins(12,8,12,8)
  header=QHBoxLayout();title=QLabel('Cuenta por persona');title.setObjectName('sectionTitle');header.addWidget(title)
  self.person=QComboBox();self.person.setMinimumContentsLength(14);self.person.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
  self.person.setAccessibleName('Persona para consultar y registrar abonos globales')
  header.addWidget(self.person,1);body.addLayout(header)
  self.summary=QLabel();self.summary.setWordWrap(True);body.addWidget(self.summary)
  form=QGridLayout();self.amount=QLineEdit();self.amount.setPlaceholderText('Cuánto recibiste (MXN)')
  self.received_date=QLineEdit(date.today().isoformat());self.reference=QLineEdit();self.reference.setPlaceholderText('Referencia opcional')
  self.form=form
  self.form_labels=(QLabel('Abono global (MXN)'),QLabel('Fecha del abono'),QLabel('Referencia opcional'))
  for label,field,name in zip(self.form_labels,(self.amount,self.received_date,self.reference),('Importe del abono global en MXN','Fecha del abono global','Referencia del abono global')):
   label.setBuddy(field);field.setAccessibleName(name)
  body.addLayout(form)
  self.future=QCheckBox('Incluir MSI futuros');self.undated=QCheckBox('Incluir MSI sin fecha')
  permissions=FlowLayout();permissions.addWidget(self.future);permissions.addWidget(self.undated);body.addLayout(permissions)
  actions=FlowLayout();self.register=QPushButton('Revisar abono global');self.register.setObjectName('primaryAction')
  self.current=QPushButton('Revisar liquidación actual');self.all=QPushButton('Revisar liquidación total')
  for button in (self.register,self.current,self.all):actions.addWidget(button)
  body.addLayout(actions)
  self.error=QLabel();self.error.setWordWrap(True);self.error.setStyleSheet('color:#a75340');body.addWidget(self.error)
  self.feedback=QLabel();self.feedback.setObjectName('actionFeedback');self.feedback.setWordWrap(True);self.feedback.hide();body.addWidget(self.feedback)
  self.person.currentIndexChanged.connect(self.select_person)
  self.register.clicked.connect(self.open_preview)
  self.current.clicked.connect(lambda:self.liquidate(False));self.all.clicked.connect(lambda:self.liquidate(True))
  self.refresh()
  self._reflow_fields()
  chain=(self.person,self.amount,self.received_date,self.reference,self.future,self.undated,self.register,self.current,self.all)
  for previous,following in zip(chain,chain[1:]):QWidget.setTabOrder(previous,following)

 def _reflow_fields(self):
  narrow=self.width()<620
  for label,field in zip(self.form_labels,(self.amount,self.received_date,self.reference)):
   self.form.removeWidget(label);self.form.removeWidget(field)
  for index,(label,field) in enumerate(zip(self.form_labels,(self.amount,self.received_date,self.reference))):
   row=index if narrow else index//2
   column=0 if narrow else (index%2)*2
   self.form.addWidget(label,row,column);self.form.addWidget(field,row,column+1,1,1 if narrow or index<2 else 3)
  self.form.setColumnStretch(1,1)
  self.form.setColumnStretch(3,0 if narrow else 1)

 def resizeEvent(self,event):
  super().resizeEvent(event)
  self._reflow_fields()

 def select_person(self):
  self.amount.clear();self.reference.clear();self.future.setChecked(False);self.undated.setChecked(False);self.error.clear()
  self.feedback.clear();self.feedback.hide()
  self.refresh_summary()

 def refresh(self):
  selected=self.person.currentData()
  with QSignalBlocker(self.person):
   self.person.clear()
   for person in self.repository.list_people():
    if person['active']:self.person.addItem(str(person['name'])+(' (Yo)' if person['is_owner'] else ''),person['id'])
   index=self.person.findData(selected)
   if index>=0:self.person.setCurrentIndex(index)
  self.refresh_summary()

 def refresh_summary(self):
  user=self.person.currentData();summary=next((p for p in self.repository.people_debt_summary() if p['user_id']==user),None)
  self.accounts=self.repository.person_receipt_accounts(user)
  current=sum(a['current_cents'] for a in self.accounts);future=sum(a['future_cents'] for a in self.accounts);undated=sum(a['undated_cents'] for a in self.accounts)
  if not summary:self.summary.setText('Selecciona una persona activa.');return
  self.summary.setText(f"Asignado: {format_money(summary['assigned_cents'])} · Abonado: {format_money(summary['paid_cents'])}\n"
   f"Pendiente total: {format_money(summary['remaining_cents'])} · Deuda actual: {format_money(current)} · MSI futuros: {format_money(future)} · Sin fecha: {format_money(undated)}\n"
   'MSI futuros incluidos en el total. Revisa aparte los históricos sin clasificar.')
  self.register.setEnabled(bool(self.accounts));self.current.setEnabled(current>0);self.all.setEnabled(bool(self.accounts))

 def liquidate(self,everything):
  self.future.setChecked(everything);self.undated.setChecked(everything)
  accounts=self.repository.person_receipt_accounts(self.person.currentData(),include_future=everything,include_undated=everything)
  total=sum(a['eligible_cents'] for a in accounts)
  self.amount.setText(f'{Decimal(total)/100:.2f}');self.open_preview()

 def open_preview(self):
  if self._preview_active:return
  self.feedback.clear();self.feedback.hide()
  try:
   total=cents(self.amount.text())
   if total<=0:raise ValueError('El abono debe ser mayor que cero.')
   accounts=self.repository.person_receipt_accounts(self.person.currentData(),include_future=self.future.isChecked(),include_undated=self.undated.isChecked())
   accounts=[a for a in accounts if a['eligible_cents']>0]
   if total>sum(a['eligible_cents'] for a in accounts):raise ValueError('El abono supera la deuda elegible. Revisa el importe o autoriza MSI futuros / sin fecha.')
   self.error.clear();self._preview_active=True
   self.preview=ReceiptPreview(self,accounts,total)
   self.preview.exec()
  except (ValueError,RuntimeError,*DATABASE_ERRORS) as error:self.error.setText(user_error(error))
  finally:self._preview_active=False


class ReceiptPreview(QDialog):
 def __init__(self,panel,accounts,total):
  super().__init__(panel);apply_warm_surface(self,'warmReceiptPreview')
  self.panel,self.accounts,self.total=panel,accounts,total;self.identity=str(uuid4());self._saving=False
  self.setWindowTitle('Revisar abono global');body=QVBoxLayout(self)
  title=QLabel(f'{panel.person.currentText()} · Abono recibido: {format_money(total)}');title.setWordWrap(True);body.addWidget(title)
  title.setMinimumHeight(title.fontMetrics().height()+6)
  note=QLabel('Importes en MXN. Edita la columna Abono para ajustar el reparto. Futuros: '+('autorizados' if panel.future.isChecked() else 'excluidos')+'; sin fecha: '+('autorizados' if panel.undated.isChecked() else 'excluidos')+'.')
  note.setWordWrap(True);body.addWidget(note)
  note.setMinimumHeight(note.fontMetrics().height()*3+6)
  self.table=QTableWidget(len(accounts),5);self.table.setHorizontalHeaderLabels(['Pedido / fecha','Pendiente antes','Se puede cubrir','Abono a aplicar','Pendiente después'])
  self.table.setAccessibleName('Distribución del abono global: edita únicamente Abono a aplicar')
  self.table.setAlternatingRowColors(True);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
  self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
  remaining=total
  for row,account in enumerate(accounts):
   applied=min(remaining,account['eligible_cents']);remaining-=applied
   values=[f"{account['source_name']} · {date_label(account['source_date']) or 'Sin fecha'}",format_money(account['remaining_cents']).removesuffix(' MXN'),format_money(account['eligible_cents']).removesuffix(' MXN'),f'{Decimal(applied)/100:.2f}',format_money(account['remaining_cents']-applied).removesuffix(' MXN')]
   for column,value in enumerate(values):
    item=QTableWidgetItem(value)
    if column!=3:item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if column:item.setTextAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
    self.table.setItem(row,column,item)
   self.table.item(row,0).setToolTip(values[0]+'\n'+str(account.get('order_id') or account.get('purchase_id')))
  self.table.setFixedHeight(self.table.horizontalHeader().height()+4+min(7,max(1,len(accounts)))*32+self.table.horizontalScrollBar().sizeHint().height());body.addWidget(self.table)
  self.error=QLabel();self.error.setWordWrap(True);body.addWidget(self.error)
  self.table.itemChanged.connect(self.update_remaining)
  actions=QHBoxLayout();cancel=QPushButton('Volver sin registrar');cancel.clicked.connect(self.reject)
  self.confirm=QPushButton('Registrar abono global');self.confirm.setObjectName('primaryAction');self.confirm.clicked.connect(self.commit)
  actions.addStretch();actions.addWidget(cancel);actions.addWidget(self.confirm);body.addLayout(actions)
  self.resize(min(820,self.screen().availableGeometry().width()-40),self.table.height()+180)

 def update_remaining(self,item):
  if item.column()!=3:return
  try:
   value=cents(item.text());account=self.accounts[item.row()]
   self.table.item(item.row(),4).setText(format_money(account['remaining_cents']-value).removesuffix(' MXN'))
  except ValueError:self.table.item(item.row(),4).setText('Revisar importe')

 def commit(self):
  if self._saving:return
  self._saving=True;self.confirm.setEnabled(False)
  try:
   applications={a['receivable_id']:cents(self.table.item(i,3).text()) for i,a in enumerate(self.accounts)}
   self.panel.repository.record_global_receipt(payment_id=self.identity,user_id=self.panel.person.currentData(),amount_cents=self.total,
    received_at=self.panel.received_date.text().strip(),reference=self.panel.reference.text().strip() or None,
    applications=applications,expected_balances={a['receivable_id']:a['remaining_cents'] for a in self.accounts},
    include_future=self.panel.future.isChecked(),include_undated=self.panel.undated.isChecked())
   self.panel.amount.clear();self.panel.reference.clear();self.panel.changed();self.accept()
   self.panel.feedback.setText('Abono global registrado.');self.panel.feedback.show()
  except (ValueError,RuntimeError,*DATABASE_ERRORS) as error:self.error.setText(user_error(error))
  finally:self._saving=False;self.confirm.setEnabled(True)
