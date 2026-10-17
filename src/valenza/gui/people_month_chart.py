"""Interactive presentation of existing monthly amounts; no financial queries."""
import math

from PySide6.QtCore import Qt, QRectF, QSize, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QFrame, QWidget, QLabel, QPushButton, QToolButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QBoxLayout, QProgressBar, QSizePolicy, QScrollArea,
    QMessageBox)

from valenza.gui.warm_finance import format_money, period_label


class PersonRow(QPushButton):
    hovered = Signal(str)
    moveSelection = Signal(int)

    def __init__(self, label, amount, total, color, owner, parent=None):
        super().__init__(parent)
        self.label = label
        self.setCheckable(True)
        self.setObjectName('personMonthRow')
        self.setProperty('owner', owner)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        percentage = max(0, amount) / total * 100 if total else 0
        self.setAccessibleName(f'{label}: {format_money(amount)}, {percentage:.1f}% del mes')
        self.setToolTip(self.accessibleName())
        layout = QGridLayout(self)
        layout.setContentsMargins(9, 5, 9, 5)
        layout.setHorizontalSpacing(8); layout.setVerticalSpacing(2)
        layout.setColumnStretch(1, 1)
        dot = QLabel('●'); dot.setStyleSheet(f'color: {color}; font-size: 14px;')
        layout.addWidget(dot, 0, 0)
        self.name = QLabel(label.removeprefix('Mi parte · '))
        self.name.setTextFormat(Qt.TextFormat.PlainText)
        self.name.setWordWrap(True)
        self.name.setMinimumWidth(0)
        self.name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.name.setStyleSheet('font-weight: 600;' if owner else 'font-weight: 400;')
        layout.addWidget(self.name, 0, 1)
        self.meter = QProgressBar()
        self.meter.setRange(0, 1000)
        self.meter.setValue(round(percentage * 10))
        self.meter.setTextVisible(False)
        self.meter.setFixedHeight(4)
        self.meter.setStyleSheet(f'QProgressBar {{ border: none; background: #ece6dd; border-radius: 2px; min-height: 4px; max-height: 4px; padding: 0; }} '
                                f'QProgressBar::chunk {{ background: {color}; border-radius: 2px; }}')
        layout.addWidget(self.meter, 1, 1)
        self.amount = QLabel(format_money(amount).removesuffix(' MXN'))
        self.amount.setStyleSheet('font-weight: 600; color: #914a2f;' if owner else 'font-weight: 600; color: #293c40;')
        self.percent = QLabel(('Tu parte · ' if owner else '') + f'{percentage:.1f}%')
        self.percent.setStyleSheet('color: #7b7d75; font-size: 11px;')
        self.amount.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.amount, 0, 2)
        layout.addWidget(self.percent, 1, 2)
        for child in self.findChildren(QWidget):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def enterEvent(self, event):
        self.hovered.emit(self.label)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered.emit('')
        super().leaveEvent(event)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return max(48, self.layout().totalHeightForWidth(width))

    def sizeHint(self):
        return QSize(300, self.heightForWidth(max(240, self.width())))

    def minimumSizeHint(self):
        return QSize(self.layout().minimumSize().width(), 48)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            self.moveSelection.emit(1 if event.key() == Qt.Key.Key_Down else -1)
            event.accept()
        else:
            super().keyPressEvent(event)


class PersonRing(QWidget):
    hovered = Signal(str)
    activated = Signal(str)

    def __init__(self, chart):
        super().__init__(chart)
        self.chart = chart
        self.setFixedSize(160, 160)
        self.setMouseTracking(True)
        self.setAccessibleName('Distribución mensual. Selecciona una persona en la lista.')

    def _label_at(self, position):
        scale = 218 / self.width()
        dx, dy = (position.x()-self.width()/2)*scale, (position.y()-self.height()/2)*scale
        if not 77 <= math.hypot(dx, dy) <= 102:
            return ''
        angle = (math.degrees(math.atan2(dx, -dy)) + 360) % 360
        total = sum(max(0, value) for _, value in self.chart.values)
        boundary = 0
        for label, value in self.chart.values:
            boundary += max(0, value)/total*360 if total else 0
            if angle < boundary:
                return label
        return ''

    def mouseMoveEvent(self, event):
        label = self._label_at(event.position())
        self.setCursor(Qt.CursorShape.PointingHandCursor if label else Qt.CursorShape.ArrowCursor)
        self.hovered.emit(label)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hovered.emit('')
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            label = self._label_at(event.position())
            if label:
                self.activated.emit(label)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        chart = self.chart
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self.width()/218, self.height()/218)
        rect = QRectF(20, 20, 178, 178)
        p.setPen(QPen(QColor('#eee7dd'), 19)); p.drawEllipse(rect)
        total = sum(max(0, value) for _, value in chart.values)
        active = chart.hover_label or chart.selected_label
        angle = 90*16
        for label, value in chart.values:
            span = round(max(0, value)/total*360*16) if total else 0
            color = QColor(chart.colors[label])
            if label != active:
                color.setAlpha(110)
            p.setPen(QPen(color, 23 if label == active else 17))
            gap = 2*16 if span > 5*16 else 0
            if span:
                p.drawArc(rect, angle-gap//2, -max(1, span-gap))
            angle -= span
        value = dict(chart.values).get(active, 0)
        name = 'Tu pendiente' if active == chart.current else active
        font = p.font(); font.setPointSize(12); p.setFont(font)
        p.setPen(QColor('#73786e'))
        p.drawText(QRectF(42, 70, 134, 20), Qt.AlignmentFlag.AlignCenter,
                   p.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, 134))
        amount = format_money(value).removesuffix(' MXN')
        font.setBold(True); font.setPointSize(20); p.setFont(font)
        while font.pointSize() > 8 and p.fontMetrics().horizontalAdvance(amount) > 148:
            font.setPointSize(font.pointSize()-1); p.setFont(font)
        p.setPen(QColor('#914a2f' if active == chart.current else '#293c40'))
        p.drawText(QRectF(35, 93, 148, 33), Qt.AlignmentFlag.AlignCenter, amount)
        font.setBold(False); font.setPointSize(12); p.setFont(font)
        p.setPen(QColor('#73786e'))
        percentage = max(0, value)/total*100 if total else 0
        p.drawText(QRectF(42, 132, 134, 20), Qt.AlignmentFlag.AlignCenter, f'{percentage:.1f}% del mes')
        p.end()


class PeopleMonthChart(QFrame):
    personSelected = Signal(str)
    detailsRequested = Signal(str)
    monthStep = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values, self.current, self.period = [], '', ''
        self.selected_label, self.hover_label = '', ''
        self.rows, self.colors = {}, {}
        self.setObjectName('peopleMonthChart')
        self.setMinimumWidth(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.setStyleSheet('''
            QFrame#peopleMonthChart { background: #fffcf7; border: 1px solid #e7dfd5; border-radius: 14px; }
            QFrame#peopleMonthChart QLabel { background: transparent; border: none; }
            QPushButton#personMonthRow { background: #fffcf7; border: 1px solid #eee8df; border-radius: 7px; text-align: left; min-height: 48px; padding: 0; }
            QPushButton#personMonthRow:hover { background: #f7f3ed; border-color: #d5cbbd; }
            QPushButton#personMonthRow[preview="true"] { border-color: #9baea6; background: #f2f4ef; }
            QPushButton#personMonthRow[owner="true"] { background: #fbf0e6; border-color: #e7cbb6; }
            QPushButton#personMonthRow:checked { border: 1px solid #9baea6; background: #edf2ed; }
            QPushButton#personMonthRow[owner="true"]:checked { background: #f7e6d7; border-color: #bc7755; }
            QPushButton#personMonthRow:focus { border: 2px solid #965839; }
        ''')
        self.root = QVBoxLayout(self); self.root.setContentsMargins(12, 10, 12, 10); self.root.setSpacing(8)
        self.root.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.header_widget = QWidget()
        self.header_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        header = self.header = QBoxLayout(QBoxLayout.Direction.LeftToRight, self.header_widget)
        header.setContentsMargins(0, 0, 0, 0); header.setSpacing(8)
        title_column = QVBoxLayout(); title_column.setSpacing(3)
        self.title = QLabel('Pendiente por persona'); self.title.setObjectName('sectionTitle')
        self.title.setStyleSheet('font-weight: 600; color: #293c40;')
        self.title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        title_column.addWidget(self.title)
        self.subtitle = QLabel(); self.subtitle.setObjectName('secondaryText')
        self.subtitle.setWordWrap(True)
        self.subtitle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.subtitle.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse | Qt.TextInteractionFlag.LinksAccessibleByKeyboard)
        self.subtitle.linkActivated.connect(self._show_explanation)
        header.addLayout(title_column, 1)
        self.navigation = QWidget()
        navigation = QHBoxLayout(self.navigation); navigation.setContentsMargins(0, 0, 0, 0); navigation.setSpacing(8)
        self.previous = QToolButton(); self.previous.setText('‹'); self.previous.setAccessibleName('Mes anterior')
        self.next = QToolButton(); self.next.setText('›'); self.next.setAccessibleName('Mes siguiente')
        self.month = QLabel(); self.month.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for button in (self.previous, self.next):
            button.setFixedSize(30, 30); button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.previous.clicked.connect(lambda: self.monthStep.emit(-1))
        self.next.clicked.connect(lambda: self.monthStep.emit(1))
        navigation.addWidget(self.previous); navigation.addWidget(self.month); navigation.addWidget(self.next)
        header.addWidget(self.navigation, 0, Qt.AlignmentFlag.AlignRight)
        self.root.addWidget(self.header_widget)
        self.root.addWidget(self.subtitle)
        self.empty = QLabel('Sin pendientes en este mes'); self.empty.setObjectName('secondaryText')
        self.root.addWidget(self.empty)
        self.body = QWidget(); self.body_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0); self.body_layout.setSpacing(14)
        ring_column = QWidget(); ring_layout = QVBoxLayout(ring_column); ring_layout.setContentsMargins(0, 0, 0, 0)
        ring_layout.setSpacing(0)
        self.ring = PersonRing(self); ring_layout.addWidget(self.ring, 0, Qt.AlignmentFlag.AlignCenter)
        self.total = QLabel(); self.total.setAlignment(Qt.AlignmentFlag.AlignCenter); self.total.setObjectName('secondaryText')
        self.total.setWordWrap(True)
        self.body_layout.addWidget(ring_column, 0, Qt.AlignmentFlag.AlignCenter)
        self.list = QWidget(); self.list_layout = QVBoxLayout(self.list)
        self.list_layout.setContentsMargins(0, 0, 0, 0); self.list_layout.setSpacing(5)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_scroll.setWidget(self.list)
        self.body_layout.addWidget(self.list_scroll, 1, Qt.AlignmentFlag.AlignVCenter)
        self.root.addWidget(self.body)
        self.footer = QWidget()
        footer_layout = QHBoxLayout(self.footer); footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.addWidget(self.total, 1)
        self.total.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.detail_button = QPushButton('Ver cuenta')
        self.detail_button.setObjectName('chartPersonDetails')
        self.detail_button.clicked.connect(lambda: self.detailsRequested.emit(self.selected_label))
        footer_layout.addWidget(self.detail_button)
        self.root.addWidget(self.footer)
        self.ring.hovered.connect(self._hover)
        self.ring.activated.connect(self.select_person)
        self.set_data([])

    def set_data(self, values, current='', *, period=''):
        previous = self.selected_label
        same_period = period == self.period
        self.values, self.current, self.period = list(values), current, period
        self.month.setText(period_label(period))
        self.subtitle.setText(
            'Compras sin MSI pendientes del mes y anteriores + MSI del mes. '
            'Abonos familiares ya descontados. No es el pago a Nu. '
            '<a href="explanation" style="color: #965839;">¿Qué&nbsp;estoy&nbsp;viendo?</a>')
        self.previous.setEnabled(bool(period)); self.next.setEnabled(bool(period))
        self.setToolTip('\n'.join(f'{label}: {format_money(value)}' for label, value in values))
        while self.list_layout.count():
            widget = self.list_layout.takeAt(0).widget()
            widget.hide(); widget.deleteLater()
        self.rows, self.colors = {}, {}
        palette = ('#7d9f91', '#8ba6b5', '#b39db2', '#bca574', '#91a7a0', '#9dabbc')
        family = 0
        total = sum(max(0, amount) for _, amount in values)
        for label, amount in values:
            owner = label == current
            color = '#bb6846' if owner else palette[family % len(palette)]
            family += not owner
            self.colors[label] = color
            row = PersonRow(label, amount, total, color, owner, self.list)
            row.clicked.connect(lambda checked=False, label=label: self.select_person(label))
            row.hovered.connect(self._hover)
            row.moveSelection.connect(lambda direction, label=label: self._move(label, direction))
            self.rows[label] = row; self.list_layout.addWidget(row)
        self.selected_label = previous if same_period and previous in self.rows else current if current in self.rows else next(iter(self.rows), '')
        self.hover_label = ''
        self.total.setText('Total · ' + format_money(total))
        self.empty.setVisible(not total); self.body.setVisible(bool(total)); self.footer.setVisible(bool(total))
        self.setMaximumHeight(16777215)
        self.setMinimumHeight(0)
        self.select_person(self.selected_label, emit=False)
        self._reflow()

    def explanation_text(self):
        return (
            f'Mes seleccionado: {period_label(self.period)}.\n\n'
            'Incluye compras sin MSI pendientes de ese mes y de meses anteriores, '
            'más las mensualidades MSI de ese mes. Los abonos familiares ya están descontados.\n\n'
            'No incluye mensualidades MSI anteriores ni futuras: no es todo lo que deben tus familiares. '
            'También aparece tu parte.\n\n'
            'Compromisos del mes muestra lo que falta pagar al banco; esta gráfica muestra '
            'lo pendiente por persona. Por eso pueden ser distintos.\n\n'
            'Usa los abonos registrados hasta hoy, incluso al consultar un mes anterior.')

    def _show_explanation(self, _link=''):
        QMessageBox.information(self, '¿Qué estoy viendo?', self.explanation_text())

    def select_person(self, label, *, emit=True):
        if label not in self.rows:
            return
        self._hover('')
        self.selected_label = label
        for name, row in self.rows.items():
            row.setChecked(name == label)
        self.list_scroll.ensureWidgetVisible(self.rows[label])
        self.ring.update()
        self.detail_button.setAccessibleName('Ver cuenta de ' + label)
        if emit:
            self.personSelected.emit(label)

    def _hover(self, label):
        if label == self.hover_label:
            return
        self.hover_label = label if label in self.rows else ''
        for name, row in self.rows.items():
            row.setProperty('preview', name == self.hover_label)
            row.style().unpolish(row); row.style().polish(row)
        self.ring.setToolTip(self.rows[label].accessibleName() if label in self.rows else '')
        self.ring.update()

    def _move(self, label, direction):
        labels = list(self.rows)
        selected = labels[(labels.index(label)+direction) % len(labels)]
        self.select_person(selected)
        self.rows[selected].setFocus()

    def _reflow(self):
        narrow = self.width() < 480
        # Reserve only the lines needed at the actual card width, rather than
        # QLabel's conservative rich-text size hint at an unrelated width.
        self.subtitle.setFixedHeight(self.subtitle.heightForWidth(max(1, self.width() - 24)))
        self.header.setDirection(QBoxLayout.Direction.TopToBottom if self.width() < 440 else QBoxLayout.Direction.LeftToRight)
        self.header.setAlignment(self.navigation, Qt.AlignmentFlag.AlignLeft if self.width() < 440 else Qt.AlignmentFlag.AlignRight)
        self.body_layout.setDirection(QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight)
        list_width = max(100, self.width() - 24 - (0 if narrow else self.ring.width()+14))
        list_height = sum(max(row.minimumHeight(), row.heightForWidth(list_width)) for row in self.rows.values()) + 4
        list_height += max(0, len(self.rows)-1)*self.list_layout.spacing()
        self.list_scroll.setFixedHeight(min(240, max(48, list_height)))
        self.root.activate()
        self.setMinimumHeight(self.root.minimumSize().height())
        self.updateGeometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()

    def sizeHint(self):
        return QSize(680, self.root.sizeHint().height())
