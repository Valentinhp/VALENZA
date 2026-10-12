"""Valenza unlock presentation; encryption remains in LocalDatabase."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
from valenza.gui.warm_finance import apply_warm_surface


class UnlockDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        apply_warm_surface(self, 'warmUnlock')
        self.setWindowTitle('Abrir Valenza')
        self.setWindowIcon(QIcon(str(Path(__file__).parent / 'assets/icono_app_claro.png')))
        self.setMinimumWidth(420)
        self.resize(460, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(QPixmap(str(Path(__file__).parent / 'assets/logo_horizontal.png')).scaled(
            260, 65, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)
        title = QLabel('Bienvenido a Valenza')
        title.setObjectName('pageTitle')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        subtitle = QLabel('Desbloquea tu información financiera')
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        layout.addWidget(QLabel('Contraseña de la base cifrada'))
        row = QHBoxLayout()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setMinimumHeight(34)
        self.password.setAccessibleName('Contraseña de la base cifrada')
        row.addWidget(self.password, 1)
        self.visibility = QPushButton('Mostrar')
        self.visibility.setCheckable(True)
        self.visibility.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.visibility.toggled.connect(self._toggle_visibility)
        row.addWidget(self.visibility)
        layout.addLayout(row)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet('color:#a75340; padding:5px;')
        self.error.hide()
        layout.addWidget(self.error)
        protected = QLabel('Información protegida mediante cifrado local')
        protected.setObjectName('secondaryText')
        protected.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(protected)
        actions = QHBoxLayout()
        actions.addStretch()
        self.cancel_button = QPushButton('Cancelar')
        self.cancel_button.clicked.connect(self.reject)
        self.unlock_button = QPushButton('Desbloquear')
        self.unlock_button.setObjectName('primaryAction')
        self.unlock_button.setDefault(True)
        self.unlock_button.clicked.connect(self.accept)
        self.password.returnPressed.connect(self.accept)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.unlock_button)
        layout.addLayout(actions)
        self.rejected.connect(self.password.clear)

    def _toggle_visibility(self, visible):
        position = self.password.cursorPosition()
        self.password.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        self.password.setCursorPosition(position)
        self.visibility.setText('Ocultar' if visible else 'Mostrar')
        self.password.setFocus()

    def show_error(self):
        self.error.setText('No se pudo desbloquear la base. Revisa la contraseña o el acceso al archivo. La base no se reemplazará ni se recreará automáticamente.')
        self.error.show()
        self.password.clear()
        self.visibility.setChecked(False)
        self._fit_error()
        self.layout().activate()
        self.resize(self.width(), max(self.height(), self.sizeHint().height()))

    def _fit_error(self):
        if hasattr(self, 'error') and not self.error.isHidden():
            margins = self.layout().contentsMargins()
            self.error.setMinimumHeight(self.error.heightForWidth(self.width()-margins.left()-margins.right()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_error()

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
