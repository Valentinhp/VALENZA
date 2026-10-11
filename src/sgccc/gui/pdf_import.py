from __future__ import annotations

from uuid import uuid4
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLineEdit, QLabel,
                              QSizePolicy, QHeaderView,
                              QLayout,
                              QTableWidget, QTableWidgetItem, QPushButton, QComboBox, QCheckBox, QMessageBox, QScrollArea)
from sgccc.ocr.order_import import money, validate


def pesos(cents):
    return f'{cents // 100}.{cents % 100:02d}'


class ProductAssignment(QWidget):
    changed = Signal()

    def __init__(self, people, original, parent=None):
        super().__init__(parent)
        self.original = original
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        controls = QHBoxLayout()
        self.person = QComboBox()
        for person in people:
            self.person.addItem('Yo' if person['is_owner'] else str(person['name']), str(person['id']))
        self.person.setCurrentIndex(next((i for i, p in enumerate(people) if p['is_owner']), -1))
        controls.addWidget(self.person, 1)
        self.divide = QPushButton('Dividir')
        self.divide.setCheckable(True)
        controls.addWidget(self.divide)
        layout.addLayout(controls)
        self.split_fields = QWidget()
        form = QFormLayout(self.split_fields)
        self.amounts = {}
        for person in people:
            edit = QLineEdit('0.00')
            self.amounts[str(person['id'])] = edit
            form.addRow('Yo' if person['is_owner'] else str(person['name']), edit)
            edit.textChanged.connect(lambda _text: self.changed.emit())
        self.split_fields.hide()
        layout.addWidget(self.split_fields)
        self.person.currentIndexChanged.connect(self._select_person)
        self.divide.toggled.connect(self._toggle_split)

    def _select_person(self):
        self.divide.setChecked(False)
        self.changed.emit()

    def _toggle_split(self, divided):
        if divided:
            try:
                original = self.original()
            except ValueError:
                original = 0
            for person, edit in self.amounts.items():
                edit.setText(pesos(original if person == self.person.currentData() else 0))
        self.split_fields.setVisible(divided)
        self.divide.setText('Asignar a una persona' if divided else 'Dividir')
        self.changed.emit()

    def shares(self):
        if self.divide.isChecked():
            return {person: money(edit.text()) for person, edit in self.amounts.items()}
        selected = self.person.currentData()
        if selected is None:
            raise ValueError('Configura Yo o selecciona una persona para cada producto.')
        return {person: self.original() if person == selected else 0 for person in self.amounts}

    def refresh_people(self, people):
        """Update a live draft without replacing its selection or split text."""
        from PySide6.QtCore import QSignalBlocker
        selected = self.person.currentData()
        with QSignalBlocker(self.person):
            for person in people:
                person_id = str(person['id'])
                label = 'Yo' if person['is_owner'] else str(person['name'])
                index = self.person.findData(person_id)
                if index < 0:
                    self.person.addItem(label, person_id)
                    edit = QLineEdit('0.00')
                    self.amounts[person_id] = edit
                    self.split_fields.layout().addRow(label, edit)
                    edit.textChanged.connect(lambda _text: self.changed.emit())
                else:
                    self.person.setItemText(index, label)
            self.person.setCurrentIndex(self.person.findData(selected))


class ProductRefundEditor(QWidget):
    changed = Signal()

    def __init__(self, people, instruments, original, parent=None):
        super().__init__(parent)
        self.original = original
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        form = QGridLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(3)
        self.product_name = QLabel()
        self.product_name.setWordWrap(True)
        self.product_name.setMaximumHeight(42)
        self.amount = QLineEdit()
        self.amount.setMaximumWidth(100)
        self.status = QComboBox()
        self.status.addItem('Pendiente', 'PENDING')
        self.status.addItem('Acreditado', 'ACCREDITED')
        self.destination = QComboBox()
        self.destination.addItem('Confirma el destino real', None)
        for instrument in instruments:
            kind = {'WALLET_BALANCE': 'Billetera', 'CREDIT_CARD': 'Tarjeta',
                    'CREDIT_LINE': 'Crédito', 'OTHER': 'Otro'}[instrument['instrument_type']]
            self.destination.addItem(f"{instrument['alias']} ({kind})", instrument['id'])
        self.accredited_at = QLineEdit()
        self.accredited_at.setPlaceholderText('AAAA-MM-DD')
        self.accredited_at.setMaximumWidth(125)
        self.accredited_at.setEnabled(False)
        self.allocation = ProductAssignment(people, self.net_cost, self)
        self.repurchase = QPushButton('Lo compré de nuevo')
        self.repurchase.setCheckable(True)
        self.repurchase_fields = QWidget()
        purchase_layout = QHBoxLayout(self.repurchase_fields)
        purchase_layout.setContentsMargins(0, 0, 0, 0)
        self.repurchase_amount = QLineEdit()
        self.repurchase_amount.setMaximumWidth(100)
        self.repurchase_date = QLineEdit()
        self.repurchase_date.setPlaceholderText('AAAA-MM-DD')
        self.repurchase_date.setMaximumWidth(125)
        self.repurchase_instrument = QComboBox()
        self.repurchase_instrument.addItem('Confirma el medio de pago', None)
        for instrument in instruments:
            self.repurchase_instrument.addItem(instrument['alias'], instrument['id'])
        self.apply_surplus = QCheckBox('Aplicar sobrante a compra original')
        for widget in (QLabel('Recompra $'), self.repurchase_amount, QLabel('Fecha'),
                       self.repurchase_date, self.repurchase_instrument, self.apply_surplus):
            purchase_layout.addWidget(widget)
        self.repurchase_fields.hide()
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        form.addWidget(self.product_name, 0, 0, 1, 2)
        form.addWidget(QLabel('Reembolso del PDF'), 0, 2)
        form.addWidget(self.amount, 0, 3)
        form.addWidget(self.status, 0, 4)
        form.addWidget(QLabel('Destino'), 1, 0)
        form.addWidget(self.destination, 1, 1, 1, 2)
        form.addWidget(QLabel('Acreditado el'), 1, 3)
        form.addWidget(self.accredited_at, 1, 4)
        form.addWidget(QLabel('Costo restante a cargo de'), 2, 0)
        form.addWidget(self.allocation, 2, 1, 1, 2)
        form.addWidget(self.repurchase, 2, 3, 1, 2)
        form.addWidget(self.repurchase_fields, 3, 0, 1, 5)
        form.addWidget(self.summary, 4, 0, 1, 5)
        self.repurchase.toggled.connect(self.repurchase_fields.setVisible)
        self.repurchase.toggled.connect(lambda _checked: self.changed.emit())
        self.apply_surplus.toggled.connect(lambda _checked: self.changed.emit())
        for widget in (self.repurchase_amount, self.repurchase_date):
            widget.textChanged.connect(lambda _text: self.changed.emit())
        self.repurchase_instrument.currentIndexChanged.connect(lambda _index: self.changed.emit())
        form.setColumnStretch(1, 1)
        for widget in (self.amount, self.accredited_at):
            widget.textChanged.connect(lambda _text: self.changed.emit())
        self.allocation.changed.connect(self.changed.emit)
        self.destination.currentIndexChanged.connect(lambda _index: self.changed.emit())
        self.status.currentIndexChanged.connect(self._status_changed)

    def _status_changed(self):
        credited = self.status.currentData() == 'ACCREDITED'
        self.accredited_at.setEnabled(credited)
        if not credited:
            self.accredited_at.clear()
        self.changed.emit()

    def net_cost(self):
        amount = money(self.amount.text())
        net = self.original() - amount
        if net < 0:
            raise ValueError('El reembolso supera el valor original del producto.')
        if self.repurchase.isChecked():
            replacement = money(self.repurchase_amount.text())
            if not 0 < replacement <= amount:
                raise ValueError('Revisa la recompra: debe ser positiva y no superar el reembolso disponible.')
            net = self.original() - (amount - replacement if self.apply_surplus.isChecked() else 0)
        return net

    def repurchase_proposal(self):
        if not self.repurchase.isChecked():
            return None
        return dict(amount_cents=money(self.repurchase_amount.text()), ordered_at=self.repurchase_date.text().strip(),
                    instrument_id=self.repurchase_instrument.currentData(), apply_surplus=self.apply_surplus.isChecked())


class RefundRepurchaseDialog(QDialog):
    """The same compact editor for an already saved returned product."""
    def __init__(self, repository, refund, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Lo compré de nuevo')
        self.repository, self.refund = repository, refund
        self.editing_allocations = bool(refund.get('repurchase'))
        self.saved_allocations = {a['user_id']: a.get('effective_final_cents', a['final_cents'])
                                  for a in refund['adjustments']}
        layout = QVBoxLayout(self)
        # Child layout requests (e.g. Dividir) must resize the scroll content,
        # never impose its growing minimum height on the top-level dialog.
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        people = [p for p in repository.list_people() if p['active']]
        if self.editing_allocations:
            allowed = {a['user_id'] for a in repository.get_order(refund['order_id'])['allocations']}
            people = [p for p in people if p['id'] in allowed]
            self.setWindowTitle('Editar reparto de devolución/recompra')
        self.editor = ProductRefundEditor(people,
            repository.list_instruments(), lambda: refund['original_cents'], self)
        self.editor.product_name.setText(f"Producto devuelto #{refund['product_index'] + 1}")
        self.editor.amount.setText(pesos(refund['amount_cents']))
        self.editor.status.setCurrentIndex(self.editor.status.findData(refund['status']))
        self.editor.accredited_at.setText(refund['accredited_at'] or '')
        self.editor.destination.setCurrentIndex(self.editor.destination.findData(refund['destination_id']))
        self.editor.repurchase_instrument.setCurrentIndex(self.editor.repurchase_instrument.findData(refund['destination_id']))
        for widget in (self.editor.amount, self.editor.status, self.editor.accredited_at, self.editor.destination):
            widget.setEnabled(False)
        participant = next((a['user_id'] for a in refund['adjustments'] if a['original_cents']), None)
        self.editor.allocation.person.setCurrentIndex(self.editor.allocation.person.findData(participant))
        self.editor.repurchase.setChecked(True)
        self.editor.repurchase.setEnabled(False)
        # Only this dialog uses a vertical form. Reuse the same field instances
        # so resizing and scrolling never replace entered values.
        form = self.editor.layout()
        form.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        labels = [form.itemAtPosition(row, column).widget()
                  for row, column in ((0, 2), (1, 0), (1, 3), (2, 0))]
        while form.count():
            form.takeAt(0)
        form.addWidget(self.editor.product_name, 0, 0, 1, 2)
        for row, (label, widget) in enumerate(zip(
                (labels[0], QLabel('Estado'), labels[1], labels[2]),
                (self.editor.amount, self.editor.status, self.editor.destination,
                 self.editor.accredited_at)), 1):
            form.addWidget(label, row, 0)
            form.addWidget(widget, row, 1)
        form.addWidget(labels[3], 5, 0, 1, 2)
        form.addWidget(self.editor.allocation, 6, 0, 1, 2)
        self.editor.allocation.split_fields.layout().setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.addWidget(self.editor.repurchase, 7, 0, 1, 2)
        form.addWidget(self.editor.repurchase_fields, 8, 0, 1, 2)
        form.addWidget(self.editor.summary, 9, 0, 1, 2)
        purchase_layout = self.editor.repurchase_fields.layout()
        while purchase_layout.count():
            item = purchase_layout.takeAt(0)
            if isinstance(item.widget(), QLabel):
                item.widget().hide()
        purchase_form = QFormLayout()
        purchase_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        purchase_form.addRow('Recompra $', self.editor.repurchase_amount)
        purchase_form.addRow('Fecha de recompra', self.editor.repurchase_date)
        purchase_form.addRow('Medio de pago', self.editor.repurchase_instrument)
        purchase_form.addRow(self.editor.apply_surplus)
        purchase_layout.addLayout(purchase_form)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.scroll_area.setMinimumHeight(0)
        self.scroll_area.setWidget(self.editor)
        layout.addWidget(self.scroll_area, 1)
        self.footer = QWidget(self)
        self.footer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        actions = QHBoxLayout(self.footer)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addStretch()
        cancel = QPushButton('Cancelar')
        cancel.clicked.connect(self.reject)
        save = QPushButton('Guardar recompra')
        self.cancel_button, self.save_button = cancel, save
        save.clicked.connect(self.save)
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addWidget(self.footer, 0)
        self.editor.changed.connect(self.update_summary)
        if self.editing_allocations:
            linked = refund['repurchase']
            self.editor.repurchase_amount.setText(pesos(linked['charged_cents']))
            self.editor.repurchase_date.setText(linked['ordered_at'])
            # The source remains the instrument used by the registered repurchase.
            order = repository.get_order(linked['order_id'])
            self.editor.repurchase_instrument.setCurrentIndex(
                self.editor.repurchase_instrument.findData(order['instrument_id']))
            self.editor.apply_surplus.setChecked(bool(linked['applied_cents']))
            for widget in (self.editor.repurchase_amount, self.editor.repurchase_date,
                           self.editor.repurchase_instrument, self.editor.apply_surplus):
                widget.setEnabled(False)
            self.editor.allocation.divide.setChecked(True)
            for user, edit in self.editor.allocation.amounts.items():
                edit.setText(pesos(self.saved_allocations.get(user, 0)))
            self.save_button.setText('Guardar reparto')
            self.update_summary()
        self.setMinimumSize(480, 240)
        self.resize(760, 560)

    def showEvent(self, event):
        super().showEvent(event)
        # Reserve space for the native window frame in the available desktop,
        # which already excludes the taskbar. The cap survives field toggles.
        available = self.screen().availableGeometry()
        self.setMaximumHeight(max(240, available.height() - 48))
        self.resize(self.width(), min(self.height(), self.maximumHeight()))

    def update_summary(self):
        try:
            proposal = self.editor.repurchase_proposal()
            surplus = self.refund['amount_cents'] - proposal['amount_cents']
            self.editor.summary.setText(
                f"Original ${pesos(self.refund['original_cents'])} · Reembolso ${pesos(self.refund['amount_cents'])} · "
                f"Recompra ${pesos(proposal['amount_cents'])} · Sobrante ${pesos(surplus)} · "
                f"Aplicado ${pesos(surplus if proposal['apply_surplus'] else 0)} · Pendiente ${pesos(self.editor.net_cost())}\n"
                'Sustituye el reparto anterior sin otro reembolso ni pago bancario. Descuento general separado.')
            if self.editing_allocations:
                linked = self.refund['repurchase']
                difference = self.refund['original_cents'] - self.refund['amount_cents']
                unused = self.refund['amount_cents'] - linked['charged_cents'] - linked['applied_cents']
                explanation = f"Diferencia original ${pesos(difference)} + recompra ${pesos(linked['charged_cents'])}"
                if unused:
                    explanation += f" + sobrante sin aplicar ${pesos(unused)}"
                explanation += f" = pendiente a repartir ${pesos(self.refund['original_cents'] - linked['applied_cents'])}."
                self.editor.summary.setText(explanation + '\n' + self.editor.summary.text()
                    + '\nSolo cambia el reparto familiar; se conservan cargo, reembolso y recompra.')
        except ValueError as error:
            self.editor.summary.setText(str(error))

    def save(self):
        try:
            if self.editing_allocations:
                allocations = self.editor.allocation.shares()
                required = self.refund['original_cents'] - self.refund['repurchase']['applied_cents']
                if sum(allocations.values()) != required:
                    raise ValueError(f'Las participaciones deben sumar exactamente ${pesos(required)}.')
                people = {p['id']: 'Yo' if p['is_owner'] else p['name'] for p in self.repository.list_people()}
                changes = '\n'.join(f"{people[user]}: ${pesos(self.saved_allocations.get(user, 0))} → ${pesos(amount)}"
                                    for user, amount in allocations.items())
                if QMessageBox.question(self, 'Confirmar corrección del reparto',
                    changes + '\n\nSe registrará una corrección auditable, sin repetir el reembolso ni la recompra. ¿Guardar?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                    return
                self.repository.update_refund_repurchase_allocations(self.refund['id'], allocations,
                    expected_allocations=self.saved_allocations)
                self.accept()
                return
            proposal = self.editor.repurchase_proposal()
            proposal['final_allocations'] = self.editor.allocation.shares()
            self.repository.register_refund_repurchase(self.refund['id'], proposal)
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, 'Revisar recompra', str(error))
            return
        self.accept()


class ImportPreview(QDialog):
    def __init__(self, repository, draft, parent=None):
        super().__init__(parent)
        self.repository, self.draft = repository, draft
        self.is_service = draft.get('kind') == 'MOBILE_TOPUP'
        self.refund_source = None
        self.setWindowTitle('Importar PDF — revisar antes de guardar')
        self.resize(1200, 680)
        self.setMinimumSize(640, 280)
        root = QVBoxLayout(self)
        root.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        root.setContentsMargins(12, 12, 12, 12)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.scroll_area.setMinimumHeight(0)
        self.form_content = QWidget()
        layout = QVBoxLayout(self.form_content)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.scroll_area.setWidget(self.form_content)
        root.addWidget(self.scroll_area, 1)
        self.header = QWidget()
        self.header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        header_layout = QVBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        essential = QGridLayout()
        essential.setColumnStretch(1, 2)
        essential.setColumnStretch(3, 1)
        self.details = QWidget()
        self.details.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        details_layout = QVBoxLayout(self.details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        secondary = QGridLayout()
        self.fields = {}
        for key, label in [('date', 'Fecha (AAAA-MM-DD)'), ('number', 'Número de comprobante'),
                           ('payment', 'Medio de pago extraído'), ('discount', 'Descuento'),
                           ('refund', 'Devolución incluida en PDF'), ('charged', 'Cargo bancario original'),
                           ('paid', 'Total pagado neto')] + (
                               [('service', 'Servicio'), ('company', 'Compañía'), ('time', 'Hora (HH:MM:SS)')]
                               if self.is_service else []):
            value = draft[key]
            edit = QLineEdit('' if value is None else f'{value / 100:.2f}' if isinstance(value, int) else value)
            self.fields[key] = edit
            if key not in ('date', 'paid'):
                index = len([k for k in self.fields if k not in ('date', 'paid')]) - 1
                row, column = divmod(index, 3)
                secondary.addWidget(QLabel(label), row * 2, column)
                secondary.addWidget(edit, row * 2 + 1, column)
        self.merchant = QLineEdit('Recarga ' + draft['company'] if self.is_service else 'Mercado Pago')
        self.instrument = QComboBox()
        self.instrument.addItem('Selecciona la tarjeta o medio de pago', None)
        for instrument in repository.list_instruments():
            self.instrument.addItem(str(instrument['alias']), instrument['id'])
        for row, column, label, widget in [(0, 0, 'Comercio', self.merchant),
                                           (0, 2, 'Fecha', self.fields['date']),
                                           (1, 0, 'Tarjeta / instrumento', self.instrument),
                                           (1, 2, 'Total pagado neto', self.fields['paid'])]:
            essential.addWidget(QLabel(label), row, column)
            essential.addWidget(widget, row, column + 1)
        header_layout.addLayout(essential)
        self.details_toggle = QPushButton('Mostrar detalles del comprobante')
        self.details_toggle.setCheckable(True)
        self.details_toggle.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        header_layout.addWidget(self.details_toggle)
        details_layout.addLayout(secondary)
        warning = QLabel('\n'.join(draft['warnings']) + '\nLas participaciones suman el valor original. Descuentos y devoluciones no se reparten automáticamente.')
        warning.setWordWrap(True)
        details_layout.addWidget(warning)
        self.details.hide()
        self.details_toggle.toggled.connect(self.details.setVisible)
        self.details_toggle.toggled.connect(lambda expanded: self.details_toggle.setText(
            'Ocultar detalles del comprobante' if expanded else 'Mostrar detalles del comprobante'))
        header_layout.addWidget(self.details)
        layout.addWidget(self.header, 0)
        self.people = [p for p in repository.list_people() if p['active']]
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Producto', 'Cantidad', 'Precio unitario', 'Persona / Dividir'])
        if self.is_service:
            self.table.setHorizontalHeaderLabels(['Concepto', 'Cantidad', 'Importe', 'Persona / Dividir'])
            self.table.setMinimumHeight(110)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.setMinimumWidth(936)
        if self.is_service:
            self.table.setMinimumWidth(600)
        self.table.setMinimumHeight(300)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.table.verticalHeader().setMinimumSectionSize(52)
        self.table.verticalHeader().hide()
        columns = self.table.horizontalHeader()
        columns.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            columns.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 76)
        self.table.setColumnWidth(2, 125)
        self.table.setColumnWidth(3, 300)
        toolbar = QHBoxLayout()
        self.all_for_me = QPushButton('Todo para Yo')
        self.all_for_me.clicked.connect(lambda: self.assign_all(next((str(p['id']) for p in self.people if p['is_owner']), None)))
        self.all_for_me.setEnabled(any(p['is_owner'] for p in self.people))
        toolbar.addWidget(self.all_for_me)
        self.bulk_person = QComboBox()
        for person in self.people:
            self.bulk_person.addItem('Yo' if person['is_owner'] else str(person['name']), str(person['id']))
        toolbar.addWidget(self.bulk_person)
        self.all_for_person = QPushButton()
        self.bulk_person.currentTextChanged.connect(lambda name: self.all_for_person.setText('Todo para ' + name))
        self.all_for_person.setText('Todo para ' + self.bulk_person.currentText())
        self.all_for_person.setEnabled(bool(self.people))
        self.all_for_person.clicked.connect(lambda: self.assign_all(self.bulk_person.currentData()))
        toolbar.addWidget(self.all_for_person)
        toolbar.addStretch(1)
        layout.addLayout(toolbar, 0)
        layout.addWidget(self.table, 1)
        self.refund_editor = ProductRefundEditor(self.people, repository.list_instruments(),
            lambda: self.product_original(self.refund_source), self)
        self.refund_editor.hide()
        layout.addWidget(self.refund_editor, 0)
        self.footer = QWidget()
        self.footer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        footer_layout = QVBoxLayout(self.footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        self.assignment_totals = QLabel()
        self.assignment_totals.setWordWrap(True)
        layout.addWidget(self.assignment_totals, 0)
        self.table.itemChanged.connect(self.update_totals)
        for index, product in enumerate(draft['products']):
            self.add_row(product, source_index=index)
        self.update_totals()
        add = QPushButton('Agregar producto')
        add.clicked.connect(lambda: self.add_row(dict(description='', quantity=1, unit=0)))
        toolbar.addWidget(add)
        remove = QPushButton('Eliminar producto seleccionado')
        remove.clicked.connect(self.remove_row)
        toolbar.addWidget(remove)
        if self.is_service:
            add.hide()
            remove.hide()
            for key in ('discount', 'refund'):
                self.fields[key].setReadOnly(True)
            self.table.setMinimumHeight(110)
        actions = QHBoxLayout()
        self.refund_toggle = QPushButton('Asignar devolución al producto seleccionado')
        self.refund_toggle.setCheckable(True)
        self.refund_toggle.clicked.connect(self._toggle_refund)
        actions.addWidget(self.refund_toggle)
        self.refund_toggle.setVisible(not self.is_service)
        actions.addStretch(1)
        self.cancel_button = QPushButton('Cancelar')
        self.cancel_button.clicked.connect(self.reject)
        actions.addWidget(self.cancel_button)
        self.save_button = QPushButton('Confirmar y guardar pedido')
        self.save_button.clicked.connect(self.save)
        actions.addWidget(self.save_button)
        footer_layout.addLayout(actions)
        root.addWidget(self.footer, 0)
        self.refund_editor.changed.connect(self.update_totals)
        self.table.horizontalHeader().sectionResized.connect(lambda *_: self.table.resizeRowsToContents())

    def showEvent(self, event):
        super().showEvent(event)
        available = self.screen().availableGeometry()
        self.setMaximumHeight(max(280, available.height() - 48))
        self.resize(self.width(), min(self.height(), self.maximumHeight()))

    def add_row(self, product, source_index=None):
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [product['description'], str(product['quantity']), pesos(product['unit'])]
        for column, value in enumerate(values):
            self.table.setItem(row, column, QTableWidgetItem(value))
        assignment = ProductAssignment(self.people, lambda: self.product_original(assignment), self.table)
        assignment.source_index = source_index
        self.table.setCellWidget(row, 3, assignment)
        assignment.changed.connect(self.update_totals)
        self.update_totals()

    def product_original(self, assignment):
        row = next(row for row in range(self.table.rowCount()) if self.table.cellWidget(row, 3) is assignment)
        quantity = int(self.table.item(row, 1).text())
        if quantity <= 0:
            raise ValueError('La cantidad debe ser positiva.')
        return quantity * money(self.table.item(row, 2).text())

    def remove_row(self):
        if self.table.currentRow() >= 0:
            if self.table.cellWidget(self.table.currentRow(), 3) is self.refund_source:
                self.refund_toggle.setChecked(False)
                self._toggle_refund(False)
            self.table.removeRow(self.table.currentRow())
            self.update_totals()

    def _toggle_refund(self, enabled):
        if self.is_service:
            return
        if enabled:
            row = self.table.currentRow()
            if row < 0 or self.table.cellWidget(row, 3).source_index is None:
                self.refund_toggle.setChecked(False)
                QMessageBox.warning(self, 'Selecciona un producto', 'Selecciona una fila de producto importado para asociar la devolución.')
                return
            self.refund_source = self.table.cellWidget(row, 3)
            editor = self.refund_editor
            editor.product_name.setText('Devuelto: ' + self.table.item(row, 0).text())
            editor.product_name.setToolTip(self.table.item(row, 0).text())
            editor.amount.setText(self.fields['refund'].text())
            editor.allocation.divide.setChecked(False)
            editor.allocation.person.setCurrentIndex(editor.allocation.person.findData(self.refund_source.person.currentData()))
            self.refund_toggle.setText('Quitar asignación de devolución')
        else:
            self.refund_source = None
            self.refund_toggle.setText('Asignar devolución al producto seleccionado')
        self.refund_editor.setVisible(enabled)
        self.update_totals()

    def _refund_proposal(self):
        if self.refund_source is None:
            return None
        editor = self.refund_editor
        amount = money(editor.amount.text())
        if not 0 < amount <= money(self.fields['refund'].text()):
            raise ValueError('El importe asignado debe ser positivo y no exceder la devolución ya incluida en el PDF.')
        final = editor.allocation.shares()
        if sum(final.values()) != editor.net_cost():
            raise ValueError('Las participaciones después de la devolución deben sumar el costo restante del producto.')
        result = dict(product_index=self.refund_source.source_index, amount_cents=amount,
                    destination_id=editor.destination.currentData(), status=editor.status.currentData(),
                    accredited_at=editor.accredited_at.text().strip() or None, final_allocations=final)
        if editor.repurchase.isChecked():
            result['repurchase'] = editor.repurchase_proposal()
        return result

    def assign_all(self, person):
        for row in range(self.table.rowCount()):
            assignment = self.table.cellWidget(row, 3)
            assignment.divide.setChecked(False)
            assignment.person.setCurrentIndex(assignment.person.findData(person))
        self.update_totals()

    def update_totals(self):
        totals = {str(p['id']): 0 for p in self.people}
        original = 0
        incomplete = False
        try:
            for row in range(self.table.rowCount()):
                assignment = self.table.cellWidget(row, 3)
                if assignment is None:
                    continue
                gross = self.product_original(assignment)
                shares = assignment.shares()
                original += gross
                incomplete |= sum(shares.values()) != gross
                for person, amount in shares.items():
                    totals[person] += amount
            self.assignment_totals.setText(' · '.join(
                f"{'Yo' if p['is_owner'] else p['name']}: ${pesos(totals[str(p['id'])])}" for p in self.people
            ) + f'\nTotal asignado: ${pesos(sum(totals.values()))} · Valor original: ${pesos(original)}'
              + ('\nRevisa el reparto: hay productos cuyo importe no cuadra.' if incomplete else ''))
            if self.refund_source is not None:
                proposed = self._refund_proposal()
                gross = self.product_original(self.refund_source)
                before = self.refund_source.shares()
                after = proposed['final_allocations']
                self.refund_editor.summary.setText(
                    f"Original ${pesos(gross)} · Reembolso ${pesos(proposed['amount_cents'])} · "
                    f"Diferencia / costo restante ${pesos(gross - proposed['amount_cents'])} · "
                    'El descuento general queda en el pedido.')
                if proposed.get('repurchase'):
                    repurchase = proposed['repurchase']
                    surplus = proposed['amount_cents'] - repurchase['amount_cents']
                    self.refund_editor.summary.setText(
                        f"Original ${pesos(gross)} · Reembolso ${pesos(proposed['amount_cents'])} · "
                        f"Recompra ${pesos(repurchase['amount_cents'])} · Sobrante ${pesos(surplus)} · "
                        f"Aplicado ${pesos(surplus if repurchase['apply_surplus'] else 0)} · "
                        f"Pendiente ${pesos(self.refund_editor.net_cost())}\n"
                        'Sin abono a tarjeta · Descuento general separado · '
                        f"Neto PDF ${pesos(money(self.fields['paid'].text()))} / cargo ${pesos(money(self.fields['charged'].text()))}: "
                        f"diferencia ${pesos(money(self.fields['charged'].text()) - money(self.fields['paid'].text()))}, revisar.")
                effective = dict(totals)
                if proposed['status'] == 'ACCREDITED':
                    for user in effective:
                        effective[user] += after.get(user, 0) - before.get(user, 0)
                changes = ' · '.join(f"{'Yo' if p['is_owner'] else p['name']}: "
                    f"${pesos(before[str(p['id'])])} → ${pesos(after[str(p['id'])])}" for p in self.people)
                message = '\nProducto devuelto — ' + changes
                if proposed['status'] == 'PENDING':
                    message += '\nPendiente: el reparto propuesto no cambia los saldos hasta acreditar el reembolso.'
                else:
                    message += '\nTotal después del ajuste: $' + pesos(sum(effective.values())) + ' · Reembolso registrado una sola vez.'
                unassigned = money(self.fields['refund'].text()) - proposed['amount_cents']
                if unassigned:
                    message += ' · Devolución aún sin asignar: $' + pesos(unassigned)
                self.assignment_totals.setText(self.assignment_totals.text().replace('\n', ' · ', 1) + message)
        except ValueError:
            self.assignment_totals.setText('Revisa las cantidades, precios y participaciones para calcular los totales.')
        self.table.resizeRowsToContents()

    def save(self):
        try:
            if self.is_service and self.refund_source is not None:
                raise ValueError('Una recarga no admite devoluciones de productos.')
            draft = dict(self.draft)
            for key, edit in self.fields.items():
                draft[key] = money(edit.text()) if key in ('discount', 'refund', 'charged', 'paid') else edit.text().strip()
            draft['products'] = []
            totals = {str(p['id']): 0 for p in self.people}
            for row in range(self.table.rowCount()):
                cells = [self.table.item(row, col).text() for col in range(3)]
                product = dict(description=cells[0], quantity=int(cells[1]), unit=money(cells[2]))
                source_index = self.table.cellWidget(row, 3).source_index
                if source_index is not None:
                    product['source_index'] = source_index
                shares = self.table.cellWidget(row, 3).shares()
                if sum(shares.values()) != product['quantity'] * product['unit']:
                    raise ValueError(f'Las participaciones del producto {row + 1} no suman su valor original.')
                product['allocations'] = shares
                draft['products'].append(product)
                for person, amount in shares.items():
                    totals[person] += amount
            original = validate(draft)
            if self.instrument.currentData() is None:
                raise ValueError('Selecciona una tarjeta o instrumento existente.')
            duplicates = self.repository.find_import_duplicates(draft)
            if duplicates and QMessageBox.question(self, 'Posible duplicado',
                'Ya existe un comprobante con la misma huella, número o fecha e importe. ¿Guardar otro pedido?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            self.repository.create_order(order_id=str(uuid4()), ordered_at=draft['date'],
                merchant=self.merchant.text(), instrument_id=str(self.instrument.currentData()),
                original_cents=original, discount_cents=draft['discount'], charged_cents=draft['charged'],
                allocations=tuple(dict(user_id=person, amount_cents=amount) for person, amount in totals.items()),
                import_evidence=draft, allow_duplicate=bool(duplicates),
                product_refunds=(self._refund_proposal(),) if self.refund_source is not None else ())
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, 'Revisa la importación', str(error))
            return
        self.accept()
