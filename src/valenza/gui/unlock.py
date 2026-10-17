"""Valenza unlock presentation; encryption remains in LocalDatabase."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QIcon, QRegion
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFrame
from valenza.gui.warm_finance import apply_warm_surface


class UnlockDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        apply_warm_surface(self, 'warmUnlock')
        self.setWindowTitle('Abrir Valenza')
        self.setWindowIcon(QIcon(str(Path(__file__).parent / 'assets/icono_app_claro.png')))
        self.setMinimumWidth(420)
        self.resize(480, 440)
        self.setStyleSheet(self.styleSheet() + '''
QDialog#warmUnlock QLabel, QDialog#warmUnlock QLineEdit, QDialog#warmUnlock QPushButton { font-family: "Segoe UI"; }
QDialog#warmUnlock QFrame#unlockCard { background: #fffcf7; border: 1px solid #e7dfd5; border-radius: 16px; }
QDialog#warmUnlock QLabel#unlockTitle { font-family: Georgia; font-size: 25px; color: #303830; }
QDialog#warmUnlock QLabel#unlockSubtitle { color: #777266; font-size: 13px; }
QDialog#warmUnlock QLabel#unlockFieldLabel { font-size: 12px; font-weight: 600; color: #42473f; }
QDialog#warmUnlock QFrame#unlockField { background: #fffefa; border: 1px solid #d8cbbb; border-radius: 9px; }
QDialog#warmUnlock QFrame#unlockField[invalid="true"] { border: 1px solid #ac6045; }
QDialog#warmUnlock QLineEdit { background: transparent; border: none; padding: 6px 8px; font-size: 14px; selection-background-color: #e7cbb3; }
QDialog#warmUnlock QLineEdit:focus { background: #faf2e8; border-radius: 6px; }
QDialog#warmUnlock QPushButton#unlockVisibility { background: transparent; border: none; color: #92583c; padding: 7px 10px; font-size: 12px; }
QDialog#warmUnlock QPushButton#unlockVisibility:hover { background: #f3e5d6; border-radius: 6px; }
QDialog#warmUnlock QPushButton:focus { border: 1px solid #a55f3e; }
QDialog#warmUnlock QPushButton#unlockCancel { background: transparent; border: 1px solid #e5dace; border-radius: 8px; color: #766553; padding: 10px 14px; }
QDialog#warmUnlock QPushButton#unlockCancel:hover { background: #f5ebdf; }
QDialog#warmUnlock QPushButton#primaryAction { background: #a45c3c; border: 1px solid #a45c3c; border-radius: 8px; color: #fffaf3; font-weight: 600; padding: 10px 20px; }
QDialog#warmUnlock QPushButton#primaryAction:hover { background: #914d31; }
QDialog#warmUnlock QPushButton#primaryAction:pressed { background: #7f422a; }
QDialog#warmUnlock QLabel#unlockError { background: #f7e9de; color: #87472f; border-radius: 7px; padding: 10px; font-size: 12px; }
''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 18, 28, 20)
        layout.setSpacing(14)
        self.logo = QLabel()
        self.logo.setAccessibleName('Valenza · Finanzas compartidas')
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo.setFixedHeight(92)
        self._logo_source = QPixmap(str(Path(__file__).parent / 'assets/logo_horizontal.png'))
        # The source has asymmetric transparent margins. Fit the visible mark,
        # rather than centering a large transparent canvas around it.
        if not self._logo_source.isNull():
            bounds = QRegion(self._logo_source.mask()).boundingRect()
            if not bounds.isEmpty():
                self._logo_source = self._logo_source.copy(bounds)
        self._fit_logo()
        layout.addWidget(self.logo)
        card = QFrame()
        card.setObjectName('unlockCard')
        body = QVBoxLayout(card)
        body.setContentsMargins(24, 22, 24, 22)
        body.setSpacing(12)
        title = QLabel('Bienvenido a Valenza')
        title.setObjectName('unlockTitle')
        body.addWidget(title)
        subtitle = QLabel('Ingresa tu contraseña para continuar.')
        subtitle.setObjectName('unlockSubtitle')
        subtitle.setWordWrap(True)
        body.addWidget(subtitle)
        body.addSpacing(6)
        password_label = QLabel('Contraseña')
        password_label.setObjectName('unlockFieldLabel')
        body.addWidget(password_label)
        self.password_frame = QFrame()
        self.password_frame.setObjectName('unlockField')
        row = QHBoxLayout(self.password_frame)
        row.setContentsMargins(4, 3, 4, 3)
        row.setSpacing(0)
        self.password = QLineEdit()
        password_label.setBuddy(self.password)
        self.password.setPlaceholderText('Tu contraseña')
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setMinimumHeight(34)
        self.password.setAccessibleName('Contraseña de la base cifrada')
        row.addWidget(self.password, 1)
        self.visibility = QPushButton('Mostrar')
        self.visibility.setObjectName('unlockVisibility')
        self.visibility.setAutoDefault(False)
        self.visibility.setCheckable(True)
        self.visibility.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.visibility.setAccessibleName('Mostrar contraseña')
        self.visibility.toggled.connect(self._toggle_visibility)
        row.addWidget(self.visibility)
        body.addWidget(self.password_frame)
        self.error = QLabel()
        self.error.setObjectName('unlockError')
        self.error.setWordWrap(True)
        self.error.hide()
        body.addWidget(self.error)
        protected = QLabel('Tus datos permanecen cifrados en este equipo.')
        protected.setObjectName('secondaryText')
        protected.setAlignment(Qt.AlignmentFlag.AlignCenter)
        protected.setWordWrap(True)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.cancel_button = QPushButton('Cancelar')
        self.cancel_button.setObjectName('unlockCancel')
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        self.unlock_button = QPushButton('Desbloquear')
        self.unlock_button.setObjectName('primaryAction')
        self.unlock_button.setDefault(True)
        self.unlock_button.clicked.connect(self.accept)
        self.password.returnPressed.connect(self.accept)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.unlock_button, 1)
        body.addSpacing(4)
        body.addLayout(actions)
        layout.addWidget(card)
        layout.addWidget(protected)
        self.setTabOrder(self.password, self.visibility)
        self.setTabOrder(self.visibility, self.cancel_button)
        self.setTabOrder(self.cancel_button, self.unlock_button)
        self.rejected.connect(self.password.clear)
        self.rejected.connect(lambda: self.visibility.setChecked(False))
        self.password.textEdited.connect(self._clear_error)

    def _clear_error(self):
        self.error.hide()
        self.password_frame.setProperty('invalid', False)
        self.password_frame.style().unpolish(self.password_frame)
        self.password_frame.style().polish(self.password_frame)

    def _toggle_visibility(self, visible):
        position = self.password.cursorPosition()
        self.password.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        self.password.setCursorPosition(position)
        self.visibility.setText('Ocultar' if visible else 'Mostrar')
        self.visibility.setAccessibleName('Ocultar contraseña' if visible else 'Mostrar contraseña')
        self.password.setFocus()

    def show_error(self):
        self.error.setText('No pudimos abrir tu información. Revisa la contraseña y el acceso al archivo e inténtalo de nuevo.')
        self.error.show()
        self.password_frame.setProperty('invalid', True)
        self.password_frame.style().unpolish(self.password_frame)
        self.password_frame.style().polish(self.password_frame)
        self.password.clear()
        self.visibility.setChecked(False)
        self.password.setFocus()
        self._fit_error()
        self.layout().activate()
        self.resize(self.width(), max(self.height(), self.sizeHint().height()))

    def _fit_error(self):
        if hasattr(self, 'error') and not self.error.isHidden():
            self.error.setMinimumHeight(max(0, self.error.heightForWidth(max(100, self.error.width()))))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_logo()
        self._fit_error()

    def _fit_logo(self):
        if not hasattr(self, '_logo_source') or self._logo_source.isNull():
            return
        ratio = self.devicePixelRatioF()
        width = min(300, max(180, self.width()-112))
        pixmap = self._logo_source.scaled(round(width*ratio), round(78*ratio),
                                         Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation)
        pixmap.setDevicePixelRatio(ratio)
        self.logo.setPixmap(pixmap)

    def take_password(self):
        value = self.password.text()
        self.password.clear()
        self.visibility.setChecked(False)
        return value

    def showEvent(self, event):
        super().showEvent(event)
        available = self.screen().availableGeometry()
        self.move(available.center() - self.rect().center())
        self.password.setFocus()
