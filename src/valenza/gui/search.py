"""Compact command palette for existing records. Never displays amounts."""
from PySide6.QtCore import Qt, QTimer, QEvent, QSize, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from html import escape
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QLabel, QStyledItemDelegate)

from valenza.gui.warm_finance import date_label
from valenza.gui.errors import user_error
from valenza.persistence.database import DATABASE_ERRORS


class SearchDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        result = index.data(Qt.ItemDataRole.UserRole)
        if not result:
            return super().paint(painter, option, index)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(4, 2, -4, -2)
        selected = index.row() == self.parent().currentRow()
        painter.setPen(QPen(QColor('#d9b99e' if selected else '#fffcf7'), 1))
        painter.setBrush(QColor('#f5e5d6' if selected else '#fffcf7'))
        painter.drawRoundedRect(QRectF(rect), 7, 7)
        font = option.font; font.setBold(True); painter.setFont(font)
        painter.setPen(QColor('#293c40'))
        width = max(1, rect.width()-24)
        painter.drawText(rect.adjusted(12, 5, -12, -26), Qt.AlignmentFlag.AlignVCenter,
                         painter.fontMetrics().elidedText(result['title'], Qt.TextElideMode.ElideRight, width))
        font.setBold(False); font.setPointSize(max(8, font.pointSize()-1)); painter.setFont(font)
        painter.setPen(QColor('#73766d'))
        painter.drawText(rect.adjusted(12, 28, -12, -4), Qt.AlignmentFlag.AlignVCenter,
                         painter.fontMetrics().elidedText(index.data(Qt.ItemDataRole.UserRole+1), Qt.TextElideMode.ElideRight, width))
        painter.restore()


class SearchDialog(QDialog):
    recordActivated = Signal(dict)

    def __init__(self, repository, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.setWindowTitle('Buscar en Valenza')
        self.setObjectName('globalSearch')
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(580, 420)
        self.setMinimumSize(360, 280)
        self.setStyleSheet('''QDialog#globalSearch { background: #f8f4ee; }
            QListWidget#searchResults { background: #fffcf7; border: 1px solid #e7dfd5; border-radius: 9px; padding: 4px; }
            QLineEdit#searchInput { background: #fffcf7; border: 1px solid #caa78e; border-radius: 8px; padding: 9px 12px; }''')
        root = QVBoxLayout(self); root.setContentsMargins(14, 14, 14, 12); root.setSpacing(9)
        self.input = QLineEdit(); self.input.setObjectName('searchInput')
        self.input.setPlaceholderText('Buscar pedidos, personas, tarjetas…')
        self.input.setAccessibleName('Buscar en Valenza')
        self.input.setMaxLength(100); self.input.setClearButtonEnabled(True)
        root.addWidget(self.input)
        self.results = QListWidget(); self.results.setObjectName('searchResults')
        self.results.setAccessibleName('Resultados de búsqueda por categoría')
        self.results.setWordWrap(False)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setItemDelegate(SearchDelegate(self.results))
        root.addWidget(self.results, 1)
        footer = QHBoxLayout()
        self.status = QLabel('Escribe al menos dos caracteres'); self.status.setWordWrap(True)
        self.status.setObjectName('secondaryText'); footer.addWidget(self.status, 1)
        hint = QLabel('↑↓ Elegir · ↵ Abrir · Esc'); hint.setObjectName('secondaryText')
        hint.setWordWrap(True); footer.addWidget(hint)
        root.addLayout(footer)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(180)
        self.timer.timeout.connect(self._search)
        self.input.textChanged.connect(self._queue)
        self.results.itemClicked.connect(lambda item: self._activate() if item.data(Qt.ItemDataRole.UserRole) else None)
        self.input.installEventFilter(self); self.results.installEventFilter(self)
        self.finished.connect(self._clear)

    def showEvent(self, event):
        super().showEvent(event)
        if self.parentWidget():
            screen = self.screen().availableGeometry()
            center = self.parentWidget().frameGeometry().center()
            self.move(max(screen.left(), min(center.x()-self.width()//2, screen.right()-self.width())),
                      max(screen.top(), min(center.y()-self.height()//2, screen.bottom()-self.height())))
        self.input.setFocus()

    def _queue(self):
        self.timer.stop(); self.results.clear()
        if len(''.join(self.input.text().split())) < 2:
            self.status.setText('Escribe al menos dos caracteres')
        else:
            self.status.setText('Buscando…')
            self.timer.start()

    def _search(self):
        self.timer.stop(); self.results.clear()
        try:
            response = self.repository.search_records(self.input.text())
        except DATABASE_ERRORS as error:
            user_error(error)
            self.status.setText('No se pudo buscar. Vuelve a intentarlo.')
            return
        groups = {}
        for result in response['results']:
            groups.setdefault(result['category'], []).append(result)
        for category, results in groups.items():
            heading = QListWidgetItem(category)
            heading.setFlags(Qt.ItemFlag.NoItemFlags)
            font = heading.font(); font.setBold(True); heading.setFont(font)
            heading.setForeground(QColor('#9a6649')); heading.setSizeHint(QSize(100, 26))
            self.results.addItem(heading)
            for result in results:
                metadata = ' · '.join(str(part) for part in (result['state'], date_label(result['date']), result['context']) if part)
                item = QListWidgetItem(result['title'] + '\n' + metadata)
                item.setData(Qt.ItemDataRole.UserRole, result)
                item.setData(Qt.ItemDataRole.UserRole+1, metadata)
                item.setToolTip('<p>' + escape(result['title']) + '<br>' + escape(metadata) + '</p>')
                item.setSizeHint(QSize(100, 59))
                self.results.addItem(item)
        if response['timed_out']:
            self.status.setText('Escribe algo más específico para ampliar la búsqueda.')
        elif response['limited']:
            self.status.setText('Primeras coincidencias · Afina tu búsqueda para ver otras')
        elif response['results']:
            self.status.setText(f"{len(response['results'])} coincidencias")
        else:
            self.status.setText('Sin coincidencias. Prueba con otro nombre o referencia.')
        self._move(1)

    def _move(self, direction):
        selectable = [i for i in range(self.results.count()) if self.results.item(i).data(Qt.ItemDataRole.UserRole)]
        if not selectable:
            return
        current = self.results.currentRow()
        index = (selectable.index(current)+direction) % len(selectable) if current in selectable else (0 if direction > 0 else -1)
        self.results.setCurrentRow(selectable[index])

    def _activate(self):
        if self.timer.isActive():
            self._search()
        item = self.results.currentItem()
        result = item.data(Qt.ItemDataRole.UserRole) if item else None
        if result:
            self.accept()
            self.recordActivated.emit(result)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self._move(1 if event.key() == Qt.Key.Key_Down else -1); return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._activate(); return True
            if event.key() == Qt.Key.Key_Escape:
                self.reject(); return True
            if watched is self.results and event.text() and not event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
                self.input.setFocus(); self.input.insert(event.text()); return True
        return super().eventFilter(watched, event)

    def _clear(self):
        self.timer.stop(); self.input.clear(); self.results.clear()
