"""Warm Finance surfaces, summaries and charts; no financial queries."""
from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QIcon, QPainterPath
from PySide6.QtWidgets import QWidget, QStyledItemDelegate, QFrame, QVBoxLayout, QLabel
from html import escape
import re
from decimal import Decimal


def format_money(cents):
    return f'${Decimal(cents) / 100:,.2f} MXN'


def period_label(key):
    months = ('Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic')
    return f'{months[int(key[5:7]) - 1]} {key[:4]}' if len(key) == 7 and key[4] == '-' else key


def financial_text_html(text):
    """Format existing strings without changing their values or financial content."""
    paragraphs = []
    for line in text.splitlines():
        safe = escape(line)
        safe = re.sub(r'(\$-?[\d,.]+(?: MXN)?)', r'<b>\1</b>', safe)
        if re.match(r'^\d+\. ', line):
            paragraphs.append(f'<h3 style="color:#9b583b; margin:10px 0 5px">{safe}</h3>')
        elif line:
            paragraphs.append(f'<p style="margin:3px 0">{safe}</p>')
    return ''.join(paragraphs)


class FinancialSummary(QFrame):
    """Present an existing validation message, retaining its exact plain text API."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('summaryCard')
        self._text = ''
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        self.status = QLabel('Resumen y validación')
        self.status.setObjectName('sectionTitle')
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.status)
        layout.addWidget(self.body)

    def text(self):
        return self._text

    def setWordWrap(self, enabled):
        self.body.setWordWrap(enabled)

    def setText(self, text):
        self._text = text
        display = text.replace('Valor original:', 'Total original:').replace('Neto para validar:', 'Total pagado neto:')
        self.body.setText(financial_text_html(display))
        self.setToolTip(text)
        difference = re.search(r'Diferencia: \$(-?[\d,.]+)', text)
        if difference:
            valid = difference.group(1) in ('0.00', '0,00') and 'no cuadra' not in text
            self.status.setText('Importes coinciden · diferencia cero' if valid else 'Revisar diferencia y reparto')
            self.status.setStyleSheet(f"color: {'#587566' if valid else '#a45a3f'}; font-weight: 600;")
        else:
            self.status.setText('Resumen y validación')
            self.status.setStyleSheet('font-weight: 600;')
        self._fit_text()

    def _fit_text(self):
        margins = self.layout().contentsMargins()
        width = max(100, self.width()-margins.left()-margins.right())
        self.body.setMinimumHeight(max(0, self.body.heightForWidth(width)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_text()


def warm_section(title):
    frame = QFrame()
    frame.setObjectName('summaryCard')
    body = QVBoxLayout(frame)
    body.setContentsMargins(12, 8, 12, 8)
    body.setSpacing(6)
    caption = QLabel(title)
    caption.setObjectName('sectionTitle')
    body.addWidget(caption)
    return frame, body


def apply_warm_surface(widget, name):
    widget.setObjectName(name)
    style = HOME_STYLE.replace('#valenzaHome', '#' + name)
    style += f'QWidget#{name}Content {{ background:#f8f4ee; }}'
    widget.setStyleSheet(style)


class MovementDelegate(QStyledItemDelegate):
    """Draw existing history entries; keep full text available for accessibility."""
    def sizeHint(self, option, index):
        return QSize(320, max(48, option.fontMetrics.height() * 2 + 14))

    def paint(self, painter, option, index):
        data = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return super().paint(painter, option, index)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(10, 2, -12, -2)
        kind = str(data['kind'])
        color = '#668474' if kind.startswith('Abono') else '#b96847' if kind == 'Pedido' else '#6489a0'
        icon = line_icon('receipt' if kind == 'Pedido' else 'card', color)
        icon.paint(painter, int(rect.x()), int(rect.center().y()-12), 24, 24)
        font = option.font
        painter.setFont(font)
        metrics = painter.fontMetrics()
        amount = format_money(int(data['amount_cents']))
        amount_width = metrics.horizontalAdvance(amount) + 12
        text_x = rect.x() + 34
        text_width = max(20, rect.width() - amount_width - 44)
        painter.setPen(QColor('#292724'))
        title = f"{kind} · {data['description']}" + (' · Anulado' if data['status'] == 'CANCELLED' else '')
        painter.drawText(QRectF(text_x, rect.y()+3, text_width, metrics.height()+3),
                         metrics.elidedText(title, Qt.TextElideMode.ElideRight, int(text_width)))
        painter.setPen(QColor('#77776f'))
        painter.drawText(QRectF(text_x, rect.y()+metrics.height()+6, text_width, metrics.height()+3), str(data['occurred_at'])[:10])
        painter.setPen(QColor(color))
        painter.drawText(QRectF(rect.right()-amount_width, rect.y(), amount_width, rect.height()),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, amount)
        painter.setPen(QPen(QColor('#efe7dc'), 1))
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
        painter.restore()


def line_icon(kind, color='#b86642'):
    pixmap = QPixmap(56, 56)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.8))
    if kind == 'home':
        path = QPainterPath()
        path.moveTo(4, 13); path.lineTo(14, 4); path.lineTo(24, 13)
        path.moveTo(7, 11); path.lineTo(7, 24); path.lineTo(21, 24); path.lineTo(21, 11)
        path.moveTo(11, 24); path.lineTo(11, 17); path.lineTo(17, 17); path.lineTo(17, 24)
        painter.drawPath(path)
    elif kind == 'people':
        painter.drawEllipse(QRectF(9, 4, 9, 9))
        painter.drawArc(QRectF(4, 15, 20, 17), 0, 180 * 16)
        painter.drawArc(QRectF(19, 7, 6, 7), -90 * 16, 180 * 16)
    elif kind == 'calendar':
        painter.drawRoundedRect(QRectF(4, 6, 20, 18), 3, 3)
        painter.drawLine(4, 12, 24, 12)
        painter.drawLine(9, 3, 9, 9); painter.drawLine(19, 3, 19, 9)
        painter.drawLine(9, 17, 12, 17); painter.drawLine(16, 17, 19, 17)
    elif kind == 'settings':
        painter.drawEllipse(QRectF(5, 5, 18, 18))
        painter.drawEllipse(QRectF(10, 10, 8, 8))
        for x, y, a, b in ((14, 2, 14, 6), (14, 22, 14, 26), (2, 14, 6, 14), (22, 14, 26, 14)):
            painter.drawLine(x, y, a, b)
    elif kind == 'receipt':
        painter.drawRoundedRect(QRectF(6, 3, 16, 22), 2, 2)
        for y in (9, 14, 19): painter.drawLine(10, y, 18, y)
    else:
        painter.drawRoundedRect(QRectF(3, 6, 22, 17), 3, 3)
        painter.drawLine(3, 12, 25, 12)
        painter.drawLine(7, 18, 12, 18)
    painter.end()
    return QIcon(pixmap)


class FinanceChart(QWidget):
    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.values = []
        self.current = ''
        self.setFixedHeight(180)
        self.setMinimumWidth(240)

    def sizeHint(self):
        return QSize(420, 165)

    def set_data(self, values, current=''):
        self.values = values
        self.current = current
        self.setToolTip('\n'.join(f'{label}: {format_money(value)}' for label, value in values))
        self._fit_height()
        self.update()

    def _fit_height(self):
        empty = not any(value > 0 for _, value in self.values)
        horizontal = self.kind == 'bars' and self.width() / max(1, len(self.values)) < 125
        self.setFixedHeight(110 if empty else max(180, 52 + len(self.values) * 32) if horizontal else 180)

    def resizeEvent(self, event):
        self._fit_height()
        super().resizeEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor('#e7dfd5'), 1))
        p.setBrush(QColor('#fffcf7'))
        p.drawRoundedRect(QRectF(1, 1, self.width()-2, self.height()-2), 12, 12)
        p.setPen(QColor('#26343c'))
        font = p.font(); font.setPointSize(11); font.setBold(True); p.setFont(font)
        p.drawText(QRectF(14, 8, self.width()-28, 24), 'Compromisos por mes' if self.kind == 'bars' else 'Distribución del pendiente')
        font.setPointSize(9); font.setBold(False); p.setFont(font)
        total = sum(max(0, value) for _, value in self.values)
        if not total:
            p.setPen(QColor('#7a807e'))
            p.drawText(QRectF(14, 38, self.width()-28, self.height()-45), Qt.AlignmentFlag.AlignCenter,
                       'Sin compromisos previstos' if self.kind == 'bars' else 'Sin obligaciones pendientes')
            p.end()
            return
        if self.kind == 'bars':
            maximum = max(value for _, value in self.values)
            if self.width() / max(1, len(self.values)) < 125:
                for index, (label, value) in enumerate(self.values):
                    y = 46 + index * 32
                    p.setPen(QColor('#6f7472'))
                    p.drawText(QRectF(14, y, 82, 22), period_label(label))
                    amount = format_money(value)
                    amount_width = p.fontMetrics().horizontalAdvance(amount) + 10
                    usable = max(10, self.width()-120-amount_width)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor('#c76b45' if label == self.current else '#a4bccf'))
                    p.drawRoundedRect(QRectF(102, y+3, usable * max(0, value)/maximum, 15), 4, 4)
                    p.setPen(QColor('#292724'))
                    p.drawText(QRectF(self.width()-amount_width-14, y, amount_width, 22), Qt.AlignmentFlag.AlignRight, amount)
                p.end()
                return
            step = (self.width()-32) / max(1, len(self.values))
            bottom = self.height()-34
            for index, (label, value) in enumerate(self.values):
                x = 16 + index * step
                height = max(0, value) / maximum * (self.height()-88)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor('#c66d45' if label == self.current else '#abc7d5'))
                bar_width = min(54, step*.54)
                p.drawRoundedRect(QRectF(x+(step-bar_width)/2, bottom-height, bar_width, height), 5, 5)
                p.setPen(QColor('#6f7472'))
                p.drawText(QRectF(x, bottom+7, step, 20), Qt.AlignmentFlag.AlignCenter, period_label(label) + (' · actual' if label == self.current else ''))
                p.drawText(QRectF(x, bottom-height-22, step, 20), Qt.AlignmentFlag.AlignCenter, format_money(value))
        else:
            diameter = min(106, self.height()-50)
            rect = QRectF(26, 44, diameter, diameter)
            angle = 90 * 16
            colors = ('#cc785c', '#8ca99a')
            for index, (label, value) in enumerate(self.values):
                span = round(max(0, value) / total * 360 * 16)
                p.setPen(QPen(QColor(colors[index % 2]), 17))
                p.drawArc(rect.adjusted(9, 9, -9, -9), angle, -span)
                angle -= span
                x = diameter + 54
                y = 57 + index * 42
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(colors[index % 2]))
                p.drawEllipse(QRectF(x, y, 7, 7))
                p.setPen(QColor('#6f7472'))
                p.drawText(QRectF(x+14, y-5, self.width()-x-20, 20), label)
                p.setPen(QColor('#26343c'))
                p.drawText(QRectF(x+14, y+12, self.width()-x-20, 22), format_money(value))
        p.end()


HOME_STYLE = """
QWidget#valenzaHome { background: #f8f4ee; color: #26343c; }
QWidget#homeContent { background: #f8f4ee; }
QWidget#valenzaHome QScrollArea { border: none; background: transparent; }
QWidget#valenzaHome QLabel { background: transparent; color: #26343c; }
QWidget#valenzaHome QLabel#pageTitle { font-family: Georgia; font-size: 28px; font-weight: 600; }
QWidget#valenzaHome QFrame#summaryCard { background: #fffcf7; border: 1px solid #e7dfd5; border-radius: 12px; padding: 6px; }
QWidget#valenzaHome QLabel#summaryAmount { font-size: 22px; font-weight: 600; }
QWidget#valenzaHome QFrame#monthCommitments { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #d68b5b,stop:1 #a85032); border: none; border-radius: 14px; padding: 10px; }
QWidget#valenzaHome QFrame#monthCommitments QLabel { color: #fffaf4; }
QWidget#valenzaHome QFrame#monthCommitments QLabel#summaryAmount { font-size: 30px; }
QWidget#valenzaHome QLabel#secondaryText { color: #706f66; font-size: 12px; }
QWidget#valenzaHome QLabel#sectionTitle { color: #292724; font-weight: 600; }
QWidget#valenzaHome QFrame#monthCommitments QLabel#secondaryText { color: #fff3e6; }
QWidget#valenzaHome QListWidget#recentMovements::item:selected { background: #f4e3d3; }
"""
