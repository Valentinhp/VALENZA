"""Application-wide Warm Finance controls, including independent popup windows."""
from pathlib import Path
from PySide6.QtCore import Qt, QObject, QEvent, QSize, QTranslator, QLibraryInfo, QRectF, QPoint, QRect
from PySide6.QtGui import QFont, QPalette, QColor, QTextCharFormat, QPainter, QPixmap, QIcon
from PySide6.QtWidgets import QComboBox, QCalendarWidget, QLineEdit, QProxyStyle, QStyle, QFileDialog, QTableView, QScrollArea, QLayout

COLORS = dict(canvas='#f8f4ee', surface='#fffcf8', text='#292724', muted='#706f66',
              border='#ddcfc0', accent='#9b583b', selection='#f0d8c6',
              success='#48705a', warning='#805b27', error='#a75340', disabled='#eeeae4')
SPACING = (4, 6, 8, 12, 16, 24)
RADII = dict(control=6, panel=12)

CONTROL_STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 14px; color: @text; }
QMainWindow, QDialog, QMessageBox, QInputDialog { background: @canvas; }
QLabel { background: transparent; }
QLabel#pageTitle { font-family: Georgia; font-size: 28px; font-weight: 600; }
QLabel#sectionTitle { font-weight: 600; color: @accent; }
QLabel#secondaryText { color: @muted; font-size: 12px; }
QLabel#summaryAmount { font-size: 22px; font-weight: 600; }
QFrame#summaryCard { background: @surface; border: 1px solid @border; border-radius: 12px; padding: 6px; }
QLabel#demoBanner, QLabel#securityNotice { padding: 10px; background: #fff3dc; color: @warning; border: 1px solid #e4c586; border-radius: 6px; }
QPushButton, QToolButton { background: #f3e6d8; border: 1px solid #ead8c8; border-radius: 7px; padding: 5px 12px; min-height: 24px; color: #804728; }
QPushButton:hover, QToolButton:hover { background: #eed8c5; }
QPushButton:pressed, QToolButton:pressed, QToolButton:checked { background: #e8c4aa; }
QPushButton:focus, QToolButton:focus { border: 2px solid @accent; padding: 4px 11px; }
QPushButton#primaryAction { background: #a65e3e; color: #fffaf4; border-color: #9b583b; }
QPushButton#primaryAction:hover { background: #914e33; }
QPushButton#dangerAction { color: @error; background: #f5e8e1; border-color: #e1c3b7; }
QPushButton:disabled, QToolButton:disabled, QPushButton#primaryAction:disabled, QPushButton#dangerAction:disabled { background: @disabled; color: #78736b; border-color: @border; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox { background: @surface; border: 1px solid @border; border-radius: 6px; padding: 5px 7px; selection-background-color: @selection; selection-color: @text; }
QLineEdit, QComboBox, QAbstractSpinBox { min-height: 24px; }
QLineEdit:hover, QComboBox:hover, QAbstractSpinBox:hover { border-color: #b99b80; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QAbstractSpinBox:focus { border-color: @accent; }
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled { background: @disabled; color: #78736b; }
QLineEdit[validationState="error"], QAbstractSpinBox[validationState="error"] { border: 2px solid @error; background: #fff5f0; }
QLineEdit[readOnly="true"] { background: #f5efe7; }
QComboBox { padding-right: 28px; }
QComboBox::drop-down { width: 24px; border: none; border-left: 1px solid @border; }
QComboBox::down-arrow { image: url(@down); width: 10px; height: 10px; }
QComboBox QAbstractItemView { background: @surface; color: @text; border: 1px solid @border; outline: 0; padding: 4px; selection-background-color: @selection; selection-color: @text; }
QComboBox QAbstractItemView::item { min-height: 28px; padding: 3px 8px; }
QAbstractSpinBox { padding-right: 24px; }
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { width: 20px; border-left: 1px solid @border; background: #f3e6d8; }
QAbstractSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; border-top-right-radius: 5px; }
QAbstractSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; border-bottom-right-radius: 5px; }
QAbstractSpinBox::up-arrow { image: url(@up); width: 9px; height: 9px; }
QAbstractSpinBox::down-arrow { image: url(@down); width: 9px; height: 9px; }
QDateEdit::drop-down { width: 24px; border-left: 1px solid @border; }
QDateEdit::down-arrow { image: url(@down); width: 10px; height: 10px; }
QMenu, QMenuBar { background: @surface; color: @text; padding: 4px; }
QMenu { border: 1px solid @border; }
QMenu::item { padding: 7px 28px 7px 12px; border-radius: 4px; }
QMenu::item:selected, QMenuBar::item:selected { background: @selection; }
QMenu::item:disabled { color: #78736b; }
QMenu::separator { height: 1px; background: @border; margin: 4px 8px; }
QMenu::indicator:checked { image: url(@check); width: 14px; height: 14px; }
QMenuBar::item { padding: 6px 10px; background: transparent; }
QCalendarWidget { background: @surface; }
QCalendarWidget QWidget#qt_calendar_navigationbar { background: #efe7dc; }
QCalendarWidget QToolButton { background: transparent; color: @text; padding: 3px 6px; }
QCalendarWidget QAbstractItemView { background: @surface; alternate-background-color: #f5efe7; selection-background-color: @selection; selection-color: @text; }
QCheckBox, QRadioButton { spacing: 7px; min-height: 24px; }
QCheckBox:disabled, QRadioButton:disabled { color: #78736b; }
QCheckBox::indicator, QRadioButton::indicator { width: 16px; height: 16px; border: 1px solid #b99b80; background: @surface; }
QCheckBox::indicator { border-radius: 4px; }
QRadioButton::indicator { border-radius: 8px; }
QCheckBox::indicator:checked { image: url(@check); background: @selection; border-color: @accent; }
QCheckBox::indicator:indeterminate { image: url(@minus); background: @selection; }
QRadioButton::indicator:checked { image: url(@dot); background: @selection; border-color: @accent; }
QCheckBox::indicator:focus, QRadioButton::indicator:focus { border: 2px solid @accent; }
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled { background: @disabled; border-color: @border; }
QTabWidget::pane { border: 1px solid @border; background: @surface; border-radius: 6px; }
QTabBar::tab { background: #efe7dc; padding: 8px 14px; border: 1px solid @border; margin-right: 3px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:selected { background: @surface; color: @accent; border-bottom-color: @accent; }
QTabBar::tab:hover { background: @selection; }
QTabBar::tab:disabled { color: #78736b; }
QTableView, QTreeView, QListView { background: @surface; alternate-background-color: #f5efe7; border: 1px solid @border; border-radius: 8px; gridline-color: #eee7df; selection-background-color: @selection; selection-color: @text; }
QTableView:focus, QTreeView:focus, QListView:focus { border-color: @accent; }
QHeaderView::section { background: #efe7dc; color: #5e605b; padding: 6px; border: none; border-right: 1px solid @border; font-weight: 600; }
QTableCornerButton::section { background: #efe7dc; border: none; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: #f4eee6; width: 10px; margin: 0; }
QScrollBar:horizontal { background: #f4eee6; height: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #c4ae98; border-radius: 4px; min-height: 28px; }
QScrollBar::handle:horizontal { background: #c4ae98; border-radius: 4px; min-width: 28px; }
QScrollBar::handle:hover { background: #a8876c; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QToolTip { background: #fffaf4; color: @text; border: 1px solid #b99b80; padding: 6px 8px; }
QProgressBar { border: 1px solid @border; border-radius: 5px; background: #efe7dc; text-align: center; min-height: 18px; }
QProgressBar::chunk { background: #d8ac8d; border-radius: 4px; }
QGroupBox { border: 1px solid @border; border-radius: 8px; margin-top: 12px; padding-top: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: @accent; }
QStatusBar { background: #efe7dc; }
"""

def control_style():
    style = CONTROL_STYLE
    for key, value in COLORS.items():
        style = style.replace('@' + key, value)
    for key in ('down', 'up', 'check', 'minus', 'dot'):
        path = (Path(__file__).parent / 'assets' / 'controls' / f'{key}.svg').as_posix()
        style = style.replace('@' + key, '"' + path + '"')
    return style

class WarmStyle(QProxyStyle):
    """Keep standard accessible message semantics with warm status illustrations."""
    def __init__(self):
        super().__init__('Fusion')

    def standardIcon(self, icon, option=None, widget=None):
        messages = {
            QStyle.StandardPixmap.SP_MessageBoxInformation: ('i', '#6489a0'),
            QStyle.StandardPixmap.SP_MessageBoxQuestion: ('?', COLORS['accent']),
            QStyle.StandardPixmap.SP_MessageBoxWarning: ('!', COLORS['warning']),
            QStyle.StandardPixmap.SP_MessageBoxCritical: ('!', COLORS['error']),
        }
        if icon not in messages:
            return super().standardIcon(icon, option, widget)
        symbol, color = messages[icon]
        pixmap = QPixmap(80, 80); pixmap.setDevicePixelRatio(2)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor(color))
        painter.drawEllipse(QRectF(3, 3, 34, 34))
        painter.setPen(QColor('#fffaf4')); painter.setFont(QFont('Segoe UI', 19, QFont.Weight.DemiBold))
        painter.drawText(QRectF(3, 1, 34, 36), Qt.AlignmentFlag.AlignCenter, symbol)
        painter.end()
        return QIcon(pixmap)


class FlowLayout(QLayout):
    """Keep controls in reading order, wrapping complete controls onto new rows."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(8)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < self.count() else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < self.count() else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), False)

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def sizeHint(self):
        return self.minimumSize()

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, True)

    def _arrange(self, rect, apply):
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y, row_height = area.x(), area.y(), 0
        for item in self._items:
            if item.isEmpty():
                continue
            hint = item.sizeHint()
            width = min(hint.width(), area.width())
            if x > area.x() and x + width > area.right() + 1:
                x = area.x()
                y += row_height + self.spacing()
                row_height = 0
            if apply:
                item.setGeometry(QRect(x, y, width, hint.height()))
            x += width + self.spacing()
            row_height = max(row_height, hint.height())
        return y - rect.y() + row_height + margins.bottom()


class WarmScrollArea(QScrollArea):
    """Keep the complete focused control visible, including padding and borders."""
    def ensureWidgetVisible(self, widget, xmargin=50, ymargin=50):
        if not self.widget() or not self.widget().isAncestorOf(widget):
            return
        super().ensureWidgetVisible(widget, xmargin, ymargin)
        viewport = self.viewport()
        rect = widget.rect().translated(widget.mapTo(viewport, QPoint()))
        if rect.height() <= viewport.height():
            bar = self.verticalScrollBar()
            if rect.top() < 0:
                bar.setValue(bar.value() + rect.top())
            elif rect.bottom() >= viewport.height():
                bar.setValue(bar.value() + rect.bottom() - viewport.height() + 1)
        if rect.width() <= viewport.width():
            bar = self.horizontalScrollBar()
            if rect.left() < 0:
                bar.setValue(bar.value() + rect.left())
            elif rect.right() >= viewport.width():
                bar.setValue(bar.value() + rect.right() - viewport.width() + 1)

    def focusNextPrevChild(self, forward):
        moved = super().focusNextPrevChild(forward)
        focused = self.focusWidget()
        if moved and focused:
            self.ensureWidgetVisible(focused)
        return moved

class PopupPolish(QObject):
    """Set the actual view too: combo popups may live outside the page hierarchy."""
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.FocusOut and isinstance(obj, QLineEdit) and obj.validator():
            state = 'error' if obj.text() and not obj.hasAcceptableInput() else ''
            if obj.property('validationState') != state:
                obj.setProperty('validationState', state)
                obj.style().unpolish(obj)
                obj.style().polish(obj)
        if event.type() == QEvent.Type.Polish:
            if isinstance(obj, QFileDialog):
                # Some bundled Qt translations omit these file dialog labels.
                for role, text in ((QFileDialog.DialogLabel.LookIn, 'Carpeta'),
                                   (QFileDialog.DialogLabel.FileName, 'Nombre del archivo'),
                                   (QFileDialog.DialogLabel.FileType, 'Tipo de archivo'),
                                   (QFileDialog.DialogLabel.Reject, 'Cancelar')):
                    obj.setLabelText(role, text)
                obj.setLabelText(QFileDialog.DialogLabel.Accept,
                    'Guardar' if obj.acceptMode() == QFileDialog.AcceptMode.AcceptSave else 'Abrir')
            if isinstance(obj, QComboBox):
                obj.setIconSize(QSize(24, 24))
                obj.view().setStyleSheet('QAbstractItemView { background:#fffcf8; color:#292724; border:1px solid #ddcfc0; selection-background-color:#f0d8c6; selection-color:#292724; padding:4px; } QAbstractItemView::item { min-height:28px; padding:3px 8px; }')
                obj.view().setTextElideMode(Qt.TextElideMode.ElideRight)
            elif isinstance(obj, QCalendarWidget):
                obj.setGridVisible(False)
                weekend = QTextCharFormat()
                weekend.setForeground(QColor(COLORS['accent']))
                obj.setWeekdayTextFormat(Qt.DayOfWeek.Saturday, weekend)
                obj.setWeekdayTextFormat(Qt.DayOfWeek.Sunday, weekend)
            elif isinstance(obj, QTableView):
                obj.setIconSize(QSize(24, 24))
        return False

def install_design_system(application):
    if getattr(application, '_warm_design_installed', False):
        return
    application.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)
    application.setStyle(WarmStyle())
    if not hasattr(application, '_warm_translation'):
        translator = QTranslator(application)
        if translator.load('qtbase_es', QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
            application.installTranslator(translator)
        application._warm_translation = translator
    application.setFont(QFont('Segoe UI', 10))
    palette = application.palette()
    for role, key in ((QPalette.ColorRole.Window, 'canvas'), (QPalette.ColorRole.Base, 'surface'),
                      (QPalette.ColorRole.WindowText, 'text'), (QPalette.ColorRole.Text, 'text'),
                      (QPalette.ColorRole.ButtonText, 'text'), (QPalette.ColorRole.Highlight, 'selection'),
                      (QPalette.ColorRole.HighlightedText, 'text'), (QPalette.ColorRole.ToolTipBase, 'surface'),
                      (QPalette.ColorRole.ToolTipText, 'text')):
        palette.setColor(role, QColor(COLORS[key]))
    application.setPalette(palette)
    application.setStyleSheet(control_style())
    if not hasattr(application, '_warm_popup_polish'):
        application._warm_popup_polish = PopupPolish(application)
        application.installEventFilter(application._warm_popup_polish)
    application._warm_design_installed = True
