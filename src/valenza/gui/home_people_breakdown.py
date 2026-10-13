"""Compact, read-only presentation of existing dashboard participations."""
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QTransform
from PySide6.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QHBoxLayout,
                              QVBoxLayout, QGridLayout, QSizePolicy)
from valenza.gui.warm_finance import format_money


class OrderAmountsRow(QFrame):
    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry = dict(entry)
        self.setObjectName('personOrderRow')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(3)
        self.title = QLabel(str(entry.get('source_name') or 'Origen por verificar'))
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setWordWrap(True)
        self.title.setObjectName('orderCaption')
        layout.addWidget(self.title)
        date = str(entry['source_date'])[:10] if entry.get('source_date') else 'Fecha sin registrar'
        kind = ' · Compra histórica' if entry.get('purchase_id') and not entry.get('order_id') else ''
        status = ' · Liquidado' if entry['remaining_cents'] == 0 else ''
        meta = QLabel(date + kind + status)
        meta.setObjectName('secondaryText')
        meta.setWordWrap(True)
        layout.addWidget(meta)
        self.amounts = QGridLayout()
        self.amounts.setHorizontalSpacing(12)
        self.amounts.setVerticalSpacing(2)
        layout.addLayout(self.amounts)
        self.values = {}
        self.fields = []
        for caption, key in (('Asignado', 'sale_cents'), ('Abonado', 'paid_cents'), ('Pendiente', 'remaining_cents')):
            label = QLabel(caption)
            label.setObjectName('secondaryText')
            amount = QLabel(format_money(entry[key]))
            amount.setObjectName('debtAmount')
            amount.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            amount.setAccessibleName(f'{caption}: {amount.text()}')
            self.values[key] = amount
            self.fields.append((label, amount))
        self._narrow = None
        self._reflow(True)

    def _reflow(self, narrow):
        if narrow == self._narrow:
            return
        self._narrow = narrow
        for label, amount in self.fields:
            self.amounts.removeWidget(label)
            self.amounts.removeWidget(amount)
        for column in range(3):
            self.amounts.setColumnStretch(column, 0)
        for index, (label, amount) in enumerate(self.fields):
            self.amounts.addWidget(label, index if narrow else 0, 0 if narrow else index)
            self.amounts.addWidget(amount, index if narrow else 1, 1 if narrow else index)
        for column in range(2 if narrow else 3):
            self.amounts.setColumnStretch(column, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow(self.width() < 440)


class PersonOrders(QWidget):
    selected = Signal(str)

    def __init__(self, person, entries, parent=None):
        super().__init__(parent)
        self.person = dict(person)
        self.entries = sorted(entries, key=lambda r: (str(r.get('source_date') or ''), str(r['receivable_id'])), reverse=True)
        self.pending_rows = []
        self.paid_rows = []
        self.paid_toggle = None
        self._built = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.toggle = QPushButton()
        self.toggle.setCheckable(True)
        self.toggle.setObjectName('personAccordionHeader')
        self.toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        header = QHBoxLayout(self.toggle)
        header.setContentsMargins(8, 3, 8, 3)
        self.arrow = QLabel()
        self.arrow.setFixedSize(12, 12)
        self._down_arrow = QIcon(str(Path(__file__).parent / 'assets/controls/down.svg')).pixmap(12, 12)
        self._right_arrow = self._down_arrow.transformed(QTransform().rotate(-90))
        self.arrow.setPixmap(self._right_arrow)
        name = person['name'] + (' (Yo)' if person['is_owner'] else '')
        self.name = QLabel(name)
        self.name.setTextFormat(Qt.TextFormat.PlainText)
        self.name.setWordWrap(True)
        self.balance = QLabel(format_money(person['remaining_cents']))
        self.balance.setObjectName('debtAmount')
        for label in (self.arrow, self.name, self.balance):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header.addWidget(self.arrow)
        header.addWidget(self.name, 1)
        header.addWidget(self.balance)
        self.toggle.setAccessibleName(f'{name}. Pendiente: {self.balance.text()}')
        layout.addWidget(self.toggle)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(4, 0, 4, 4)
        self.body_layout.setSpacing(2)
        self.body.hide()
        layout.addWidget(self.body)
        self.toggle.toggled.connect(self._expand)

    def _build(self):
        if self._built:
            return
        self._built = True
        pending = [r for r in self.entries if r['remaining_cents'] != 0]
        paid = [r for r in self.entries if r['remaining_cents'] == 0]
        if not pending:
            empty = QLabel('Sin pedidos pendientes.' if self.entries else 'Sin pedidos registrados.')
            empty.setObjectName('secondaryText')
            self.body_layout.addWidget(empty)
        for entry in pending:
            row = OrderAmountsRow(entry)
            self.pending_rows.append(row)
            self.body_layout.addWidget(row)
        if paid:
            self.paid_toggle = QPushButton(f'Ver liquidados · {len(paid)}')
            self.paid_toggle.setCheckable(True)
            self.paid_toggle.setAccessibleName(f'Consultar {len(paid)} pedidos liquidados de {self.person["name"]}')
            self.body_layout.addWidget(self.paid_toggle, 0, Qt.AlignmentFlag.AlignLeft)
            paid_body = QWidget()
            paid_layout = QVBoxLayout(paid_body)
            paid_layout.setContentsMargins(0, 0, 0, 0)
            paid_layout.setSpacing(2)
            for entry in paid:
                row = OrderAmountsRow(entry)
                self.paid_rows.append(row)
                paid_layout.addWidget(row)
            paid_body.hide()
            self.body_layout.addWidget(paid_body)
            self.paid_toggle.toggled.connect(paid_body.setVisible)
            self.paid_toggle.toggled.connect(lambda checked: self.paid_toggle.setText(
                f'{"Ocultar" if checked else "Ver"} liquidados · {len(paid)}'))

    def _expand(self, checked):
        self.arrow.setPixmap(self._down_arrow if checked else self._right_arrow)
        self.toggle.setAccessibleDescription('Contraer pedidos' if checked else 'Expandir pedidos')
        self.toggle.setToolTip('Contraer pedidos' if checked else 'Expandir pedidos')
        if checked:
            self._build()
        self.body.setVisible(checked)
        if checked:
            self.selected.emit(str(self.person['id']))


class HomePeopleBreakdown(QWidget):
    person_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('homePeopleBreakdown')
        self.setStyleSheet('''
            QWidget#homePeopleBreakdown QPushButton#personAccordionHeader { padding: 3px; text-align: left; }
            QWidget#homePeopleBreakdown QLabel#debtAmount { font-weight: 600; }
            QWidget#homePeopleBreakdown QLabel#orderCaption { font-weight: 600; }
            QWidget#homePeopleBreakdown QFrame#personOrderRow { background: #fffcf8; border-bottom: 1px solid #e7dfd5; }
        ''')
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.layout_rows = QVBoxLayout(self)
        self.layout_rows.setContentsMargins(0, 4, 0, 0)
        self.layout_rows.setSpacing(6)
        self.sections = {}

    def set_data(self, people, entries):
        states = {key: (section.toggle.isChecked(), bool(section.paid_toggle and section.paid_toggle.isChecked()))
                  for key, section in self.sections.items()}
        while self.layout_rows.count():
            widget = self.layout_rows.takeAt(0).widget()
            widget.hide()
            widget.deleteLater()
        self.sections = {}
        grouped = {}
        for entry in entries:
            grouped.setdefault(str(entry['user_id']), []).append(entry)
        for person in people:
            key = str(person['id'])
            section = PersonOrders(person, grouped.get(key, []))
            self.sections[key] = section
            self.layout_rows.addWidget(section)
            expanded, paid = states.get(key, (False, False))
            section.toggle.setChecked(expanded)
            if paid:
                section._build()
            if section.paid_toggle:
                section.paid_toggle.setChecked(paid)
            section.selected.connect(self.person_selected)
        if not people:
            empty = QLabel('Sin personas registradas.')
            empty.setObjectName('secondaryText')
            self.layout_rows.addWidget(empty)
