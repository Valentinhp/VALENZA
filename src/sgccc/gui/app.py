from __future__ import annotations

from dataclasses import dataclass
from calendar import monthrange
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import sys
import sqlite3
from datetime import date, datetime
from html import escape
from io import BytesIO
from uuid import uuid4
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLayout,
    QHeaderView,
    QLabel,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStyledItemDelegate,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, Signal, QSignalBlocker, QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator

from sgccc.persistence.database import DATABASE_ERRORS, DatabaseSecurityError, LocalDatabase, SCHEMA_VERSION
from sgccc.persistence.repository import FinanceRepository


@dataclass(frozen=True)
class DemoData:
    """Datos inmutables de demostración; no representan operaciones reales."""

    receivables_cents: int = 125000
    institutional_balance_cents: int = 238000
    recent_movements: tuple[tuple[str, str, int], ...] = (
        ("DEMO-001", "Movimiento institucional sintético", -45000),
        ("DEMO-002", "Cobro sintético pendiente de revisión", 30000),
    )


def format_money(cents: int) -> str:
    amount = (Decimal(cents) / Decimal("100")).quantize(Decimal("0.01"))
    return f"${amount:,.2f} MXN"


class MxnLineEdit(QLineEdit):
    """Entrada MXN visible; setValue conserva compatibilidad con pruebas antiguas."""

    def setValue(self, cents: int) -> None:
        self.setText(format_money(cents).replace("$", "").replace(" MXN", ""))


class CompactMoneyDelegate(QStyledItemDelegate):
    """Present the common MXN unit once, retaining full values in the model."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if option.text.endswith(' MXN'):
            option.text = option.text[:-4]
            option.displayAlignment = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        text = str(index.data() or '')
        if text.endswith(' MXN'):
            size.setWidth(option.fontMetrics.horizontalAdvance(text[:-4]) + 12)
        return size


def write_family_pdf(statement, path):
    """Local, paginated PDF; financial values come from existing receivables."""
    import pymupdf
    parts = [f"<h1>Estado de cuenta · {escape(statement['person'])}</h1>",
             f"<p>Asignado: {format_money(statement['assigned_cents'])}<br>Abonado: {format_money(statement['paid_cents'])}<br><b>Pendiente: {format_money(statement['remaining_cents'])}</b></p>"]
    for row in statement['rows']:
        parts.append(f"<h2>{escape(str(row['source_name']))} · {escape(str(row['source_date'] or 'Fecha por revisar'))}</h2>")
        parts.append('<table><tr><th>Concepto</th><th>Importe asignado original</th></tr>')
        for concept in row['concepts']:
            parts.append(f"<tr><td>{escape(concept['description'])}</td><td>{format_money(concept['amount_cents'])}</td></tr>")
        if not row['concepts']:
            parts.append(f"<tr><td>Participación registrada; sin conceptos detallados disponibles</td><td>{format_money(row['sale_cents'])}</td></tr>")
        if row['concept_adjustment_cents']:
            parts.append(f"<tr><td>Ajustes auditados de devolución / recompra</td><td>{format_money(row['concept_adjustment_cents'])}</td></tr>")
        parts.append('</table>')
        for receipt in row['receipts']:
            parts.append(f"<p>Abono aplicado {escape(receipt['received_at'])}: {format_money(receipt['amount_cents'])}</p>")
        parts.append(f"<p>Participación vigente: {format_money(row['sale_cents'])} · Abonado: {format_money(row['paid_cents'])}<br><b>Pendiente: {format_money(row['remaining_cents'])}</b></p>")
    parts.append('<p>Los importes originales y los ajustes explican la participación vigente; no son cargos adicionales. Los abonos personales/familiares no constituyen pagos bancarios.</p>')
    buffer = BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    try:
        story = pymupdf.Story(''.join(parts), user_css='body{font-family:sans-serif;font-size:11pt;color:#182536}h1{font-size:20pt;color:#233f60}h2{font-size:13pt}table{width:100%;border-spacing:0}td,th{padding:6pt;border-bottom:1px solid #d8dee9;text-align:left}tr{page-break-inside:avoid}')
        def page_rect(number, filled):
            box = pymupdf.Rect(0, 0, 595, 842)
            return box, pymupdf.Rect(36, 36, 559, 796), None
        story.write(writer, page_rect)
    finally:
        writer.close()
    with pymupdf.open(stream=buffer.getvalue(), filetype='pdf') as document:
        for number, page in enumerate(document, 1):
            page.insert_text((36, 819), f'Valenza | {number} / {len(document)}', fontsize=9)
        Path(path).write_bytes(document.tobytes())


class MainWindow(QMainWindow):
    """Ventana principal local para operaciones financieras explícitas."""

    PAGES = (
        "Inicio",
        "Usuarios",
        "Pedidos",
        "Cobros",
        "Tarjetas",
        "Suscripciones",
        "Configuración",
    )
    data_changed = Signal(str)

    def __init__(
        self,
        demo_data: DemoData | None = None,
        database: LocalDatabase | None = None,
        test_mode: bool = False,
    ) -> None:
        super().__init__()
        self.demo_data = demo_data or DemoData()
        self.database = database
        self.test_mode = test_mode
        self.repository = FinanceRepository(database) if database is not None else None
        self.data_changed.connect(self._refresh_visible_data)
        self.setWindowTitle(
            "SGCCC - BASE DE PRUEBAS" if test_mode
            else "SGCCC - demostración local" if database is None
            else "SGCCC - PRUEBAS EN MEMORIA" if database.synthetic
            else "SGCCC"
        )
        self.setMinimumSize(680, 480)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(1080, 680)
        self.statusBar()
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QGridLayout(root)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(0, 1)
        if self.test_mode:
            warning = QLabel(
                "BASE DE PRUEBAS · Esta ventana usa una base cifrada independiente; "
                "no contiene ni modifica la base real."
            )
            warning.setObjectName("demoBanner")
            warning.setWordWrap(True)
            layout.addWidget(warning, 0, 0, 1, 2)

        navigation = QListWidget()
        navigation.setObjectName("navigation")
        navigation.setFixedWidth(150)
        navigation.addItems(self.PAGES)
        navigation.currentRowChanged.connect(self._show_page)
        content_row = 1 if self.test_mode else 0
        layout.addWidget(navigation, content_row, 0)

        self.pages = QStackedWidget()
        self.pages.setObjectName("pages")
        # The legacy form remains available only for compatibility and is not
        # exposed in the main navigation.
        self._legacy_purchases_page = (
            self._make_legacy_purchases_page()
            if self.repository is not None
            else QWidget()
        )
        for page_name in self.PAGES:
            self.pages.addWidget(self._make_page(page_name))
        self.pages.addWidget(self._legacy_purchases_page)
        layout.addWidget(self.pages, content_row, 1)
        navigation.setCurrentRow(0)
        self.setCentralWidget(root)
        for combo in self.findChildren(QComboBox):
            combo.setMinimumContentsLength(10)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        if self.repository is not None:
            for table in (self.cards_table, self.card_payment_history, self.collection_items,
                          self.collection_history, self.orders_table, self.people_table,
                          self.owner_people_table):
                table.itemSelectionChanged.connect(self._update_action_states)
                table.setAlternatingRowColors(True)
                table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
                table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
                table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
            for table, column in ((self.cards_table, 0), (self.collection_items, 2), (self.orders_table, 0)):
                table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
                table.horizontalHeader().setMinimumSectionSize(75)
            self.cards_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
            self.cards_table.setColumnWidth(1, 120)
            self.cards_table.horizontalHeaderItem(4).setText('Pendiente')
            for table, columns in ((self.collection_items, (3, 4, 5)), (self.cards_table, (2, 3, 4))):
                delegate = CompactMoneyDelegate(table)
                for column in columns:
                    table.setItemDelegateForColumn(column, delegate)
            self.collection_items.horizontalHeaderItem(3).setText('Asignado')
            self.collection_items.horizontalHeader().setStretchLastSection(False)
            for column in (6, 8, 9, 10):
                self.collection_items.setColumnHidden(column, True)
            self.collection_items.setToolTip('Selecciona una cuenta: origen, fecha y tipo se muestran en su detalle.')
            self.cards_columns_toggle = QPushButton('Ver todas las columnas de tarjetas')
            self.cards_columns_toggle.setCheckable(True)
            self.cards_columns_toggle.toggled.connect(lambda visible: [self.cards_table.setColumnHidden(c, not visible) for c in list(range(5, 12)) + [13, 14, 15]])
            self.cards_table.parentWidget().layout().insertWidget(3, self.cards_columns_toggle)
            self.cards_columns_toggle.toggled.emit(False)
            self.card_apply_payment.currentIndexChanged.connect(self._update_action_states)
            self.card_apply_installment.currentIndexChanged.connect(self._update_action_states)
            self.card_apply_amount.textChanged.connect(self._update_action_states)
            self.collection_amount.textChanged.connect(self._update_action_states)
            for field in (self.person_name, self.card_payment_amount, self.card_payment_date,
                          self.extra_amount, self.extra_description, self.fee_amount, self.fee_description):
                field.textChanged.connect(self._update_action_states)
            self.extra_person.currentIndexChanged.connect(self._update_action_states)
            self.card_instrument.currentIndexChanged.connect(self._update_action_states)
            self._update_action_states()
            self._fit_money_columns()

    def _fit_money_columns(self):
        for name, columns in (('collection_items', (3, 4, 5)), ('cards_table', (2, 3, 4))):
            table = getattr(self, name, None)
            if table is None:
                continue
            for column in columns:
                width = max(75, table.horizontalHeader().fontMetrics().horizontalAdvance(table.horizontalHeaderItem(column).text()) + 14)
                for row in range(table.rowCount()):
                    item = table.item(row, column)
                    if item:
                        width = max(width, table.fontMetrics().horizontalAdvance(item.text().removesuffix(' MXN')) + 12)
                        item.setToolTip(item.text())
                table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
                table.setColumnWidth(column, width)

    def _make_page(self, page_name: str) -> QWidget:
        if page_name == "Inicio":
            return self._make_dashboard()
        if page_name == "Usuarios" and self.repository is not None:
            return self._make_users_page()
        if page_name == "Pedidos" and self.repository is not None:
            return self._make_orders_page()
        if page_name == "Cobros" and self.repository is not None:
            return self._make_collections_page()
        if page_name == "Tarjetas" and self.repository is not None:
            return self._make_cards_page()
        if page_name == "Configuración" and self.repository is not None:
            return self._make_settings_page()
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel(page_name)
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        message = QLabel(
            f"{page_name}: todavía no está habilitado.\n"
            "Esta sección no realiza operaciones financieras."
        )
        message.setWordWrap(True)
        layout.addWidget(message)
        if page_name == "Configuración":
            security = QLabel("Persistencia real: protegida por SQLCipher; "
                              "modo demostración: solo datos sintéticos.")
            security.setObjectName("securityNotice")
            layout.addWidget(security)
        layout.addStretch()
        return page

    def _make_cards_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        title = QLabel("Tarjetas")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        notice = QLabel(
            "Los cargos de Pedidos usan el cargo real a tarjeta. Los abonos "
            "familiares no se consideran pagos a la institución. Las cuotas "
            "sin calendario confirmado aparecen como pendientes de confirmar."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)

        self.cards_table = QTableWidget(0, 16)
        notice.setText('Importes en MXN. ' + notice.text())
        self.cards_table.setObjectName("cardsTable")
        self.cards_table.setHorizontalHeaderLabels(
            ["Tarjeta", "Institución", "Cargado", "Pagado", "Por liquidar",
             "MSI del periodo", "MSI futuros", "Corte", "Límite", "Próximo corte",
             "Vencimiento", "Estado", "ID", "Banco (deuda total)", "Consultado", "Banco − Valenza"]
        )
        self.cards_table.setColumnHidden(12, True)
        self.cards_table.setMinimumHeight(180)
        self.cards_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cards_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cards_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.cards_table.itemSelectionChanged.connect(self._select_card)
        layout.addWidget(self.cards_table)
        self.bank_query_comparison = QLabel('Saldo bancario: Sin consultar')
        self.bank_query_comparison.setWordWrap(True)
        layout.addWidget(self.bank_query_comparison)
        bank_form = QGridLayout()
        bank_note = QLabel('Consulta de deuda total de la tarjeta seleccionada. No es pago mínimo ni pago para no generar intereses; no crea movimientos.')
        bank_note.setWordWrap(True)
        bank_form.addWidget(bank_note, 0, 0, 1, 2)
        self.bank_query_amount = MxnLineEdit()
        self.bank_query_amount.setPlaceholderText('Deuda total informada por el banco')
        self.bank_query_date = QLineEdit(date.today().isoformat())
        self.bank_query_save = QPushButton('Guardar consulta')
        self.bank_query_save.setEnabled(False)
        self.bank_query_save.clicked.connect(self._record_bank_query)
        bank_form.addWidget(QLabel('Saldo adeudado (MXN)'), 1, 0)
        bank_form.addWidget(self.bank_query_amount, 1, 1)
        bank_form.addWidget(QLabel('Consultado el (AAAA-MM-DD)'), 2, 0)
        bank_form.addWidget(self.bank_query_date, 2, 1)
        bank_form.addWidget(self.bank_query_save, 3, 1)
        layout.addLayout(bank_form)

        form = QGridLayout()
        self.card_institution = QComboBox()
        self.card_institution.currentIndexChanged.connect(self._refresh_card_instruments)
        self.card_instrument = QComboBox()
        form.addWidget(self.card_institution, 0, 1)
        form.addWidget(QLabel('Institución'), 0, 0)
        form.addWidget(QLabel('Tarjeta / cuenta'), 1, 0)
        form.addWidget(self.card_instrument, 1, 1)
        self.card_payment_amount = QLineEdit()
        self.card_payment_amount.setPlaceholderText("0.00")
        self.card_payment_date = QLineEdit(date.today().isoformat())
        self.card_payment_reference = QLineEdit()
        self.card_payment_reference.setPlaceholderText("Referencia opcional")
        form.addWidget(QLabel("Pago real (MXN)"), 2, 0)
        form.addWidget(self.card_payment_amount, 2, 1)
        form.addWidget(QLabel("Fecha"), 3, 0)
        form.addWidget(self.card_payment_date, 3, 1)
        form.addWidget(QLabel("Referencia"), 4, 0)
        form.addWidget(self.card_payment_reference, 4, 1)
        self.record_card_button = QPushButton("Registrar pago a tarjeta")
        self.record_card_button.clicked.connect(self._record_card_payment)
        form.addWidget(self.record_card_button, 5, 1)
        layout.addLayout(form)

        application_form = QGridLayout()
        self.card_apply_payment = QComboBox()
        self.card_apply_installment = QComboBox()
        self.card_apply_amount = QLineEdit()
        self.card_apply_amount.setPlaceholderText("0.00")
        application_form.addWidget(QLabel("Pago sin asignar"), 0, 0)
        application_form.addWidget(self.card_apply_payment, 0, 1, 1, 3)
        application_form.addWidget(QLabel("Cuota MSI"), 1, 0)
        application_form.addWidget(self.card_apply_installment, 1, 1, 1, 3)
        application_form.addWidget(QLabel("Aplicar (MXN)"), 2, 0)
        application_form.addWidget(self.card_apply_amount, 2, 1)
        self.apply_card_button = QPushButton("Aplicar pago a cuota")
        self.apply_card_button.clicked.connect(self._apply_card_payment)
        application_form.addWidget(self.apply_card_button, 2, 2, 1, 2)
        layout.addLayout(application_form)
        self.card_payment_history = QTableWidget(0, 6)
        self.card_payment_history.setHorizontalHeaderLabels(
            ["Fecha", "Importe", "Referencia", "Estado", "ID", "Disponible"]
        )
        self.card_payment_history.setColumnHidden(4, True)
        self.card_payment_history.setMinimumHeight(120)
        self.card_payment_history.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.card_payment_history.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.card_payment_history.itemSelectionChanged.connect(
            self._select_card_payment
        )
        layout.addWidget(self.card_payment_history)
        payment_actions = QGridLayout()
        self.edit_payment_button = QPushButton("Guardar cambios de pago")
        self.edit_payment_button.clicked.connect(self._edit_selected_card_payment)
        self.cancel_payment_button = QPushButton("Anular pago")
        self.cancel_payment_button.clicked.connect(self._cancel_selected_card_payment)
        payment_actions.addWidget(self.edit_payment_button, 0, 0)
        payment_actions.addWidget(self.cancel_payment_button, 0, 1)
        layout.addLayout(payment_actions)

        calendar = QGridLayout()
        self.card_calendar_effective = QLineEdit(date.today().isoformat())
        self.card_closing_day = QLineEdit()
        self.card_closing_day.setPlaceholderText("Día 1-31")
        self.card_due_day = QLineEdit()
        self.card_due_day.setPlaceholderText("Día 1-31")
        calendar.addWidget(QLabel("Vigente desde"), 0, 0)
        calendar.addWidget(self.card_calendar_effective, 0, 1)
        calendar.addWidget(QLabel("Día de corte"), 1, 0)
        calendar.addWidget(self.card_closing_day, 1, 1)
        calendar.addWidget(QLabel("Día límite"), 1, 2)
        calendar.addWidget(self.card_due_day, 1, 3)
        calendar_button = QPushButton("Guardar fechas")
        calendar_button.clicked.connect(self._save_card_calendar)
        calendar.addWidget(calendar_button, 2, 2, 1, 2)
        calendar_note = QLabel('Fechas de la tarjeta seleccionada en la tabla superior.')
        calendar_note.setWordWrap(True)
        calendar.addWidget(calendar_note, 3, 0, 1, 4)
        self._add_advanced_section(layout, "Fechas de corte y pago", calendar)

        administration = QGridLayout()
        self.admin_institution = QComboBox()
        self.admin_institution_name = QLineEdit()
        self.admin_institution.currentIndexChanged.connect(self._load_admin_institution_name)
        self.admin_institution_name.setPlaceholderText("Nueva institución")
        add_institution_button = QPushButton("Agregar institución")
        add_institution_button.clicked.connect(self._add_institution)
        edit_institution_button = QPushButton("Guardar institución")
        edit_institution_button.clicked.connect(self._edit_institution)
        toggle_institution_button = QPushButton("Activar/desactivar institución")
        toggle_institution_button.clicked.connect(self._toggle_institution)
        administration.addWidget(QLabel("Institución"), 0, 0)
        administration.addWidget(self.admin_institution, 0, 1, 1, 2)
        administration.addWidget(QLabel('Nombre'), 1, 0)
        administration.addWidget(self.admin_institution_name, 1, 1, 1, 2)
        administration.addWidget(add_institution_button, 2, 0)
        administration.addWidget(edit_institution_button, 2, 1)
        administration.addWidget(toggle_institution_button, 2, 2)

        self.admin_card_name = QLineEdit()
        self.admin_card_name.setPlaceholderText("Nombre de tarjeta")
        self.admin_card_type = QComboBox()
        self.admin_card_type.addItem("Tarjeta de crédito", "CREDIT_CARD")
        self.admin_card_type.addItem("Línea de crédito", "CREDIT_LINE")
        self.admin_card_type.addItem("Saldo wallet", "WALLET_BALANCE")
        self.admin_card_type.addItem("Otro", "OTHER")
        self.admin_card_institution = QComboBox()
        self.admin_card_last_four = QLineEdit()
        self.admin_card_last_four.setValidator(QRegularExpressionValidator(QRegularExpression('[0-9]{0,4}'), self.admin_card_last_four))
        self.admin_card_last_four.setPlaceholderText('Opcional: cuatro dígitos')
        self.admin_card_description = QLineEdit()
        self.admin_card_description.setPlaceholderText('Descripción opcional')
        add_card_button = QPushButton("Agregar tarjeta")
        add_card_button.clicked.connect(self._add_instrument)
        edit_card_button = QPushButton("Guardar cambios")
        edit_card_button.clicked.connect(self._edit_instrument)
        toggle_card_button = QPushButton("Activar/desactivar")
        toggle_card_button.clicked.connect(self._toggle_instrument)
        hint = QLabel('Para editar, selecciona la tarjeta o billetera en la tabla superior. Se conserva su identificador e historial.')
        hint.setWordWrap(True)
        administration.addWidget(hint, 3, 0, 1, 3)
        for row, label, widget in ((4, 'Institución de la cuenta', self.admin_card_institution),
                                   (5, 'Nombre / alias', self.admin_card_name),
                                   (6, 'Naturaleza', self.admin_card_type),
                                   (7, 'Terminación', self.admin_card_last_four),
                                   (8, 'Descripción', self.admin_card_description)):
            administration.addWidget(QLabel(label), row, 0)
            administration.addWidget(widget, row, 1, 1, 2)
        administration.addWidget(add_card_button, 9, 0)
        administration.addWidget(edit_card_button, 9, 1)
        administration.addWidget(toggle_card_button, 9, 2)
        new_card_button = QPushButton('Preparar nueva cuenta')
        new_card_button.clicked.connect(self._prepare_new_account)
        administration.addWidget(new_card_button, 10, 0, 1, 3)
        for button, text in ((add_institution_button, 'Agregar institución'), (edit_institution_button, 'Guardar nombre'),
                             (toggle_institution_button, 'Activar/desactivar'), (add_card_button, 'Agregar cuenta')):
            button.setText(text)
        self._add_advanced_section(layout, "Administrar instituciones y tarjetas", administration)
        self._load_admin_catalogs()

        self.card_detail = QLabel("Selecciona una tarjeta para ver sus compras.")
        self.card_detail.setWordWrap(True)
        self.card_detail.setObjectName("cardDetail")
        layout.addWidget(self.card_detail)
        self._load_card_catalogs()
        self._refresh_cards()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        return page

    @staticmethod
    def _add_advanced_section(layout: QVBoxLayout, label: str, content_layout) -> None:
        toggle = QPushButton(label)
        toggle.setCheckable(True)
        content = QWidget()
        content.setLayout(content_layout)
        content.setVisible(False)
        toggle.toggled.connect(content.setVisible)
        layout.addWidget(toggle)
        layout.addWidget(content)

    def _load_card_catalogs(self) -> None:
        self.card_institution.clear()
        for item in self.repository.list_institutions():
            self.card_institution.addItem(str(item["name"]), item["id"])
        self._refresh_card_instruments()

    def _refresh_card_instruments(self) -> None:
        if not hasattr(self, "card_instrument"):
            return
        self.card_instrument.clear()
        institution_id = self.card_institution.currentData()
        for item in self.repository.list_instruments(institution_id) if institution_id else []:
            self.card_instrument.addItem(str(item["alias"]), item["id"])

    def _record_bank_query(self):
        instrument_id = self._selected_card_id()
        try:
            if not instrument_id or not self.bank_query_amount.text().strip():
                raise ValueError('Selecciona la tarjeta e introduce su deuda total informada por el banco.')
            self.repository.record_bank_balance(instrument_id,
                self._parse_mxn_to_cents(self.bank_query_amount.text()), self.bank_query_date.text().strip())
        except ValueError as error:
            self._show_error(self._safe_error(error))
            return
        self.data_changed.emit('cards')

    def _refresh_cards(self) -> None:
        if not hasattr(self, "cards_table"):
            return
        selected_id = self._selected_card_id()
        blocker = QSignalBlocker(self.cards_table)
        self.cards_table.setRowCount(0)
        comparisons = {item['instrument_id']: item for item in self.repository.list_bank_comparisons()}
        for card in self.repository.list_card_summaries(include_inactive=True):
            comparison = comparisons.get(card['instrument_id'])
            row = self.cards_table.rowCount()
            self.cards_table.insertRow(row)
            values = (
                card["alias"], card["institution_name"],
                format_money(int(card["charged_cents"])),
                format_money(int(card["paid_cents"])),
                format_money(int(card["remaining_cents"])),
                format_money(int(card["period_cents"])),
                format_money(int(card["future_installments_cents"])),
                card["closing_day"] or "Pendiente",
                card["due_day"] or "Pendiente",
                card["next_cut"] or "Pendiente de confirmar",
                card["next_due"] or "Pendiente de confirmar",
                "Activa" if card["active"] else "Inactiva",
                card["instrument_id"],
                format_money(comparison['reported_cents']) if comparison and comparison['reported_cents'] is not None else 'Sin consultar' if comparison else 'No aplica',
                comparison['consulted_at'] or 'Sin consultar' if comparison else 'No aplica',
                format_money(comparison['difference_cents']) if comparison and comparison['difference_cents'] is not None else 'Sin consultar' if comparison else 'No aplica',
            )
            for column, value in enumerate(values):
                self.cards_table.setItem(row, column, QTableWidgetItem(str(value)))
            if card["instrument_id"] == selected_id:
                self.cards_table.selectRow(row)
        blocker.unblock()
        self._select_card()

    def _selected_card_id(self) -> str | None:
        rows = self.cards_table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.cards_table.item(rows[0].row(), 12).text()

    def _select_card(self) -> None:
        instrument_id = self._selected_card_id()
        self.admin_card_type.setEnabled(instrument_id is None)
        selection_changed = getattr(self, '_bank_query_selection', None) != instrument_id
        if selection_changed:
            self.bank_query_amount.clear()
            self.bank_query_date.setText(date.today().isoformat())
        self._bank_query_selection = instrument_id
        comparison = next((item for item in self.repository.list_bank_comparisons() if item['instrument_id'] == instrument_id), None)
        self.bank_query_save.setEnabled(comparison is not None)
        self.bank_query_comparison.setText(
            f"Consulta de {comparison['alias']} · {comparison['institution_name']}\nValenza: {format_money(comparison['calculated_cents'])} · Banco: {format_money(comparison['reported_cents'])} "
            f"({comparison['consulted_at']}) · Diferencia banco − Valenza: {format_money(comparison['difference_cents'])}"
            if comparison and comparison['reported_cents'] is not None else 'Saldo bancario: Sin consultar' if comparison else
            'Selecciona una tarjeta o línea de crédito para consultar su deuda total.')
        if instrument_id is None:
            self.card_detail.setText("Selecciona una tarjeta para ver sus compras.")
            self._refresh_card_application_options()
            return
        instrument = self._selected_admin_instrument()
        if instrument is not None:
            fields = (self.admin_card_name.text(), self.admin_card_type.currentData(), self.admin_card_institution.currentData(), self.admin_card_last_four.text(), self.admin_card_description.text())
            dirty = fields != getattr(self, '_admin_loaded_fields', fields)
            if getattr(self, '_admin_edit_selection', None) != instrument_id or not dirty:
                self.admin_card_name.setText(str(instrument['alias']))
                self.admin_card_type.setCurrentIndex(self.admin_card_type.findData(instrument['instrument_type']))
                self.admin_card_institution.setCurrentIndex(self.admin_card_institution.findData(instrument['institution_id']))
                profile = self.repository.instrument_profile(instrument_id)
                self.admin_card_last_four.setText(profile['last_four'])
                self.admin_card_description.setText(profile['description'])
                self._admin_edit_selection = instrument_id
                self._admin_loaded_fields = (self.admin_card_name.text(), self.admin_card_type.currentData(), self.admin_card_institution.currentData(), self.admin_card_last_four.text(), self.admin_card_description.text())
            if selection_changed or self.card_instrument.currentData() == instrument_id:
                institution_index = self.card_institution.findData(instrument['institution_id'])
                self.card_institution.setCurrentIndex(institution_index)
                if institution_index >= 0:
                    self.card_instrument.setCurrentIndex(self.card_instrument.findData(instrument_id))
        summary = next(i for i in self.repository.list_card_summaries(include_inactive=True)
                       if i["instrument_id"] == instrument_id)
        details = [
            (f"Saldo de billetera registrado: {format_money(int(summary['wallet_balance_cents']))}"
             if summary['instrument_type'] == 'WALLET_BALANCE' else
             f"Saldo registrado en otro medio: {format_money(int(summary['cash_balance_cents']))}"
             if summary['instrument_type'] == 'OTHER' else
             f"Deuda registrada: {format_money(int(summary['remaining_cents']))}"),
            f"MSI por pagar hasta hoy: {format_money(int(summary['exigible_cents']))}",
            f"MSI pendiente de confirmar: {format_money(int(summary['pending_confirmation_cents']))}",
        ]
        if summary["credit_cents"]:
            details.append(f"Saldo a favor registrado: {format_money(int(summary['credit_cents']))}")
        purchases = self.repository.list_card_purchases(instrument_id)
        if not purchases:
            self.card_detail.setText("\n".join(details + ["Esta tarjeta aún no tiene compras asociadas."]))
            self._refresh_card_application_options(instrument_id)
            return
        details.append("Compras asociadas:")
        details.extend(
            f"- {item['ordered_at']} · {item['merchant']} · "
            f"{format_money(int(item['charged_cents']))}"
            for item in purchases
        )
        installments = self.repository.list_installments(instrument_id)
        if installments:
            details.append("")
            details.append("Mensualidades:")
            details.extend(
                f"- Cuota {item['number']}: "
                f"total {format_money(int(item['principal_cents']) + int(item['interest_cents']))} · "
                f"pendiente {format_money(int(item['remaining_cents']))} · "
                f"{item['due_date'] or 'Vencimiento pendiente'} · "
                f"{item['period_key'] or 'Periodo pendiente de confirmar'} · "
                f"{'Pagada' if item['payment_status'] == 'PAID' else 'Pago parcial' if item['payment_status'] == 'PARTIAL' else 'Pendiente'}"
                for item in installments
            )
        self.card_detail.setText("\n".join(details))
        self._refresh_card_application_options(instrument_id)

    def _refresh_card_application_options(self, instrument_id: str | None = None) -> None:
        if not hasattr(self, "card_payment_history"):
            return
        instrument_id = instrument_id or self._selected_card_id()
        self.card_apply_payment.clear()
        self.card_apply_installment.clear()
        self.card_payment_history.setRowCount(0)
        if not instrument_id:
            return
        payments = self.repository.list_institution_payments(instrument_id)
        for payment in payments:
            applied = sum(
                int(item["amount_cents"])
                for item in self.repository.database.connection.execute(
                    """
                    SELECT amount_cents FROM installment_payment_application
                    WHERE payment_id = ? AND application_status = 'ACTIVE'
                    """,
                    (payment["id"],),
                ).fetchall()
            )
            available = (
                int(payment["amount_cents"]) - applied
                if payment["payment_status"] == "ACTIVE" else 0
            )
            row = self.card_payment_history.rowCount()
            self.card_payment_history.insertRow(row)
            values = (
                payment["paid_at"],
                format_money(int(payment["amount_cents"])),
                payment["reference"] or "",
                "ANULADO" if payment["payment_status"] == "CANCELLED" else "Activo",
                payment["id"],
                format_money(max(available, 0)),
            )
            for column, value in enumerate(values):
                self.card_payment_history.setItem(row, column, QTableWidgetItem(str(value)))
            if available > 0 and payment["payment_status"] == "ACTIVE":
                self.card_apply_payment.addItem(
                    f"{payment['paid_at']} · disponible {format_money(available)}",
                    payment["id"],
                )
                self.card_apply_payment.setItemData(self.card_apply_payment.count() - 1, available,
                                                    Qt.ItemDataRole.UserRole + 1)
        for installment in self.repository.list_installments(instrument_id):
            remaining = int(installment["remaining_cents"])
            if remaining > 0:
                self.card_apply_installment.addItem(
                    f"{installment['merchant']} · cuota {installment['number']} · "
                    f"{format_money(remaining)}",
                    installment["id"],
                )
                self.card_apply_installment.setItemData(self.card_apply_installment.count() - 1, remaining,
                                                        Qt.ItemDataRole.UserRole + 1)

    def _selected_card_payment(self) -> dict[str, object] | None:
        rows = self.card_payment_history.selectionModel().selectedRows()
        if not rows:
            return None
        payment_id = self.card_payment_history.item(rows[0].row(), 4).text()
        instrument_id = self._selected_card_id()
        return next(
            (
                item for item in self.repository.list_institution_payments(instrument_id)
                if str(item["id"]) == payment_id
            ),
            None,
        ) if instrument_id else None

    def _select_card_payment(self) -> None:
        payment = self._selected_card_payment()
        if payment is None:
            return
        self.card_payment_amount.setText(
            f"{Decimal(int(payment['amount_cents'])) / Decimal('100'):.2f}"
        )
        self.card_payment_date.setText(str(payment["paid_at"])[:10])
        self.card_payment_reference.setText(str(payment["reference"] or ""))

    def _edit_selected_card_payment(self) -> None:
        payment = self._selected_card_payment()
        if payment is None:
            self._show_error("Selecciona un pago en el historial.")
            return
        try:
            self.repository.update_institution_payment(
                str(payment["id"]),
                paid_at=self.card_payment_date.text().strip(),
                amount_cents=self._parse_mxn_to_cents(self.card_payment_amount.text()),
                reference=self.card_payment_reference.text().strip() or None,
            )
        except (ValueError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        self.data_changed.emit("cards")
        self._show_information("El pago quedó actualizado.")

    def _cancel_selected_card_payment(self) -> None:
        payment = self._selected_card_payment()
        if payment is None:
            self._show_error("Selecciona un pago en el historial.")
            return
        if payment["payment_status"] == "CANCELLED":
            self._show_error("Ese pago ya está anulado.")
            return
        answer = QMessageBox.question(
            self,
            "Confirmar anulación",
            f"¿Anular el pago de {format_money(int(payment['amount_cents']))} "
            f"del {payment['paid_at']}?\n"
            "Las aplicaciones MSI se revertirán y quedarán auditadas.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.repository.cancel_institution_payment(
                str(payment["id"]), reason="Anulación confirmada desde Tarjetas"
            )
        except (ValueError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        self.data_changed.emit("cards")
        self._show_information("El pago fue anulado y las cuotas se recalcularon.")

    def _apply_card_payment(self) -> None:
        payment_id = self.card_apply_payment.currentData()
        installment_id = self.card_apply_installment.currentData()
        if not payment_id or not installment_id:
            self._show_error("Selecciona un pago y una cuota MSI.")
            return
        try:
            amount = self._parse_mxn_to_cents(self.card_apply_amount.text())
            self.repository.apply_institution_payment_to_installment(
                payment_id=str(payment_id),
                installment_id=str(installment_id),
                amount_cents=amount,
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            self._show_error(self._safe_error(error))
            return
        self.card_apply_amount.clear()
        self.data_changed.emit("cards")
        self._show_information("Pago aplicado a la cuota.")

    def _record_card_payment(self) -> None:
        try:
            instrument_id = self.card_instrument.currentData()
            if instrument_id is None:
                raise ValueError("Selecciona una tarjeta.")
            amount = self._parse_mxn_to_cents(self.card_payment_amount.text())
            self.repository.record_institution_payment(
                payment_id=str(uuid4()),
                instrument_id=str(instrument_id),
                paid_at=self.card_payment_date.text().strip(),
                amount_cents=amount,
                reference=self.card_payment_reference.text().strip() or None,
            )
        except (ValueError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        self.card_payment_amount.clear()
        self.card_payment_reference.clear()
        self.data_changed.emit("cards")
        self._show_information("El pago a la tarjeta quedó registrado.")

    def _save_card_calendar(self) -> None:
        try:
            instrument_id = self._selected_card_id()
            if instrument_id is None:
                raise ValueError("Selecciona una tarjeta en la tabla superior.")
            self.repository.save_instrument_calendar(
                calendar_id=str(uuid4()),
                instrument_id=str(instrument_id),
                effective_from=self.card_calendar_effective.text().strip(),
                closing_day=self._parse_day(self.card_closing_day.text()),
                due_day=self._parse_day(self.card_due_day.text()),
            )
        except (ValueError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        self.data_changed.emit("cards")
        self._show_information("Las fechas de corte y límite quedaron guardadas.")

    @staticmethod
    def _parse_day(value: str) -> int:
        try:
            day = int(value.strip())
        except (TypeError, ValueError) as error:
            raise ValueError("Los días de corte y pago deben ser números entre 1 y 31.") from error
        if not 1 <= day <= 31:
            raise ValueError("Los días de corte y pago deben estar entre 1 y 31.")
        return day

    def _load_admin_catalogs(self) -> None:
        self.admin_institution.clear()
        for institution in self.repository.list_all_institutions():
            self.admin_institution.addItem(
                f"{institution['name']} "
                f"({'activa' if institution['active'] else 'inactiva'})",
                institution["id"],
            )
        self._fill_combo(self.admin_card_institution, [(str(i['name']), i['id']) for i in self.repository.list_all_institutions()])

    def _load_admin_institution_name(self):
        if not hasattr(self, 'admin_institution_name'):
            return
        item = next((i for i in self.repository.list_all_institutions() if i['id']==self.admin_institution.currentData()), None)
        if item:
            self.admin_institution_name.setText(item['name'])

    def _prepare_new_account(self):
        self.cards_table.clearSelection()
        self._admin_edit_selection = None
        self.admin_card_type.setEnabled(True)
        self.admin_card_name.clear()
        self.admin_card_last_four.clear()
        self.admin_card_description.clear()
        self.admin_card_name.setFocus()

    def _selected_admin_instrument(self) -> dict[str, object] | None:
        instrument_id = self._selected_card_id()
        if instrument_id is None:
            return None
        return next(
            (
                item for item in self.repository.list_all_instruments()
                if str(item["id"]) == instrument_id
            ),
            None,
        )

    def _add_institution(self) -> None:
        try:
            name = self.admin_institution_name.text().strip()
            if not name:
                raise ValueError("Escribe el nombre de la institución.")
            self.repository.add_institution(str(uuid4()), name)
        except (ValueError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        self.admin_institution_name.clear()
        self.data_changed.emit("cards")
        self._show_information("La institución quedó registrada.")

    def _edit_institution(self) -> None:
        institution_id = self.admin_institution.currentData()
        if institution_id is None:
            self._show_error("Selecciona una institución.")
            return
        try:
            self.repository.update_institution(
                str(institution_id), self.admin_institution_name.text()
            )
        except (ValueError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        self.data_changed.emit("cards")
        self._show_information("La institución quedó actualizada.")

    def _toggle_institution(self) -> None:
        institution_id = self.admin_institution.currentData()
        if institution_id is None:
            self._show_error("Selecciona una institución.")
            return
        institution = next(
            (
                item for item in self.repository.list_all_institutions()
                if str(item["id"]) == str(institution_id)
            ),
            None,
        )
        if institution is None:
            self._show_error("La institución seleccionada ya no existe.")
            return
        try:
            self.repository.set_institution_active(
                str(institution_id), not bool(institution["active"])
            )
        except (ValueError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        self.data_changed.emit("cards")
        self._show_information(
            "La institución quedó "
            + ("activada." if not institution["active"] else "desactivada.")
        )

    def _add_instrument(self) -> None:
        try:
            institution_id = self.admin_card_institution.currentData()
            if institution_id is None:
                raise ValueError("Primero registra o selecciona una institución.")
            self.repository.add_instrument(
                str(uuid4()),
                str(institution_id),
                self.admin_card_name.text(),
                str(self.admin_card_type.currentData()),
                last_four=self.admin_card_last_four.text().strip(),
                description=self.admin_card_description.text(),
            )
        except (ValueError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        self.admin_card_name.clear()
        self.data_changed.emit("cards")
        self._show_information("La tarjeta quedó registrada.")
        self.admin_card_last_four.clear()
        self.admin_card_description.clear()

    def _edit_instrument(self) -> None:
        instrument = self._selected_admin_instrument()
        if instrument is None:
            self._show_error("Selecciona una tarjeta en la tabla.")
            return
        try:
            self.repository.update_instrument(
                str(instrument["id"]),
                self.admin_card_name.text(),
                str(self.admin_card_type.currentData()),
                institution_id=self.admin_card_institution.currentData(),
                last_four=self.admin_card_last_four.text().strip(),
                description=self.admin_card_description.text(),
            )
        except (ValueError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        self._admin_edit_selection = None
        self.data_changed.emit("cards")
        self._show_information("Los datos de la cuenta quedaron actualizados; se conservó su historial.")

    def _toggle_instrument(self) -> None:
        instrument = self._selected_admin_instrument()
        if instrument is None:
            self._show_error("Selecciona una tarjeta en la tabla.")
            return
        try:
            self.repository.set_instrument_active(
                str(instrument["id"]), not bool(instrument["active"])
            )
        except (ValueError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        self.data_changed.emit("cards")
        self._show_information(
            "La tarjeta quedó "
            + ("activada." if not instrument["active"] else "desactivada.")
        )

    def _make_collections_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        title = QLabel("Cobros")
        title.setObjectName("pageTitle")
        outer.addWidget(title)
        notice = QLabel(
            "Mi parte registra mis abonos personales; Cobros familiares registra "
            "lo recibido de otras personas. Ningún abono crea un pago bancario. "
            "Los pagos a la institución se registran únicamente en Tarjetas."
        )
        notice.setWordWrap(True)
        outer.addWidget(notice)
        self.collection_totals = QLabel()
        notice.setToolTip(notice.text())
        notice.setText('Importes en MXN. Un abono familiar no paga al banco.')
        self.collection_totals.setWordWrap(True)
        outer.addWidget(self.collection_totals)
        self.collection_filter = QComboBox()
        self.collection_filter.addItem("Todos", "ALL")
        self.collection_filter.addItem("Mi parte", "PERSONAL")
        self.collection_filter.addItem("Cobros familiares", "FAMILY")
        self.collection_filter.addItem("Históricos por revisar", "UNKNOWN")
        self.collection_filter.currentIndexChanged.connect(self._filter_collections)
        self.family_pdf_button = QPushButton('PDF de la persona seleccionada')
        self.family_pdf_button.clicked.connect(self._export_family_pdf)
        filters = QHBoxLayout()
        filters.addWidget(self.collection_filter, 1)
        filters.addWidget(self.family_pdf_button)
        outer.addLayout(filters)
        footer_layout = outer
        self.collections_scroll = QScrollArea()
        self.collections_scroll.setWidgetResizable(True)
        collections_content = QWidget()
        outer = QVBoxLayout(collections_content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.collections_scroll.setWidget(collections_content)
        footer_layout.addWidget(self.collections_scroll, 1)

        self.collection_items = QTableWidget(0, 11)
        self.collection_items.setObjectName("collectionItemsTable")
        self.collection_items.setHorizontalHeaderLabels(
            ["Persona", "ID persona", "Comercio", "Parte asignada", "Abonado",
             "Pendiente", "Estado", "ID cuenta", "Origen", "Fecha de origen", "Tipo"]
        )
        self.collection_items.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.collection_items.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.collection_items.setSortingEnabled(True)
        self.collection_items.setAlternatingRowColors(True)
        self.collection_items.setMinimumHeight(200)
        self.collection_items.verticalHeader().setDefaultSectionSize(32)
        self.collection_items.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.collection_items.horizontalHeader().setStretchLastSection(True)
        self.collection_items.setColumnHidden(7, True)
        self.collection_items.setColumnHidden(1, True)
        self.collection_items.itemSelectionChanged.connect(
            self._select_collection_item
        )
        outer.addWidget(self.collection_items, 1)

        payment_row = QGridLayout()
        self.collection_current_balance = QLabel("Selecciona una cuenta para ver el saldo.")
        self.collection_current_balance.setObjectName("collectionBalance")
        self.collection_current_balance.setWordWrap(True)
        payment_row.addWidget(self.collection_current_balance, 0, 0, 1, 3)
        self.collection_amount = QLineEdit()
        self.collection_amount.setPlaceholderText("Importe del abono")
        payment_row.addWidget(QLabel("Abono (MXN)"), 1, 0)
        payment_row.addWidget(self.collection_amount, 1, 1)
        self.record_collection_button = QPushButton("Registrar abono")
        self.record_collection_button.clicked.connect(self._record_collection)
        self.record_collection_button.setDefault(True)
        payment_row.addWidget(self.record_collection_button, 1, 2)
        payment_row.setColumnStretch(1, 1)
        footer_layout.addLayout(payment_row)

        self.collection_details_toggle = QPushButton("Más detalles")
        self.collection_details_toggle.setCheckable(True)
        self.collection_details_toggle.toggled.connect(
            lambda visible: self.collection_details.setVisible(visible)
        )
        options_actions = QHBoxLayout()
        options_actions.addWidget(self.collection_details_toggle)
        self.collection_details_toggle.setText('Fecha / referencia')
        outer.addLayout(options_actions)
        self.collection_details = QWidget()
        details_layout = QGridLayout(self.collection_details)
        self.collection_reference = QLineEdit()
        self.collection_reference.setPlaceholderText("Referencia opcional")
        self.collection_received_date = QLineEdit(date.today().isoformat())
        self.collection_received_date.setPlaceholderText("AAAA-MM-DD")
        details_layout.addWidget(QLabel("Fecha del abono"), 0, 2)
        details_layout.addWidget(self.collection_received_date, 0, 3)
        details_layout.addWidget(QLabel("Referencia"), 0, 0)
        details_layout.addWidget(self.collection_reference, 0, 1)
        self.collection_details.setVisible(False)
        outer.addWidget(self.collection_details)

        self.other_operations_toggle = QPushButton("Otras operaciones")
        self.other_operations_toggle.setCheckable(True)
        self.other_operations_toggle.toggled.connect(
            lambda visible: self.other_operations.setVisible(visible)
        )
        self.other_operations_toggle.setText('Extras / comisiones')
        options_actions.addWidget(self.other_operations_toggle)
        self.other_operations = QWidget()
        extras = QGridLayout(self.other_operations)
        self.extra_person = QComboBox()
        self.extra_amount = QLineEdit()
        self.extra_amount.setPlaceholderText("0.00")
        self.extra_description = QLineEdit()
        self.extra_description.setPlaceholderText("Motivo del extra")
        self.record_extra_button = QPushButton("Registrar extra")
        self.record_extra_button.clicked.connect(self._record_extra)
        self.fee_amount = QLineEdit()
        self.fee_amount.setPlaceholderText("0.00")
        self.fee_description = QLineEdit()
        self.fee_description.setPlaceholderText("Comisión del depósito")
        self.record_fee_button = QPushButton("Registrar comisión")
        self.record_fee_button.clicked.connect(self._record_fee)
        extras.addWidget(QLabel("Persona del extra"), 0, 0)
        extras.addWidget(self.extra_person, 0, 1)
        extras.addWidget(QLabel("Extra (ganancia separada)"), 1, 0)
        extras.addWidget(self.extra_amount, 1, 1)
        extras.addWidget(self.extra_description, 1, 2)
        extras.addWidget(self.record_extra_button, 1, 3)
        extras.addWidget(QLabel("Comisión (un depósito)"), 2, 0)
        extras.addWidget(self.fee_amount, 2, 1)
        extras.addWidget(self.fee_description, 2, 2)
        extras.addWidget(self.record_fee_button, 2, 3)
        self.other_operations.setVisible(False)
        outer.addWidget(self.other_operations)

        self.collection_history_toggle = QPushButton("Ver historial")
        self.collection_history_toggle.setCheckable(True)
        self.collection_history_toggle.toggled.connect(
            self._toggle_collection_history
        )
        options_actions.addWidget(self.collection_history_toggle)
        self.collection_history = QTableWidget(0, 8)
        self.collection_history.setHorizontalHeaderLabels(
            ["Fecha", "Persona", "Comercio", "Importe", "Referencia", "Estado", "ID", "Tipo"]
        )
        self.collection_history.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.collection_history.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.collection_history.verticalHeader().setDefaultSectionSize(28)
        self.collection_history.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.collection_history.setColumnHidden(6, True)
        self.collection_history.itemSelectionChanged.connect(
            self._select_receipt_history
        )
        outer.addWidget(self.collection_history)
        self.collection_history.setMinimumHeight(160)
        self.collection_history.hide()
        receipt_actions = QGridLayout()
        self.edit_receipt_button = QPushButton("Guardar cambios del abono")
        self.edit_receipt_button.clicked.connect(self._edit_selected_receipt)
        self.cancel_receipt_button = QPushButton("Anular abono")
        self.cancel_receipt_button.clicked.connect(self._cancel_selected_receipt)
        receipt_actions.addWidget(self.edit_receipt_button, 0, 0)
        receipt_actions.addWidget(self.cancel_receipt_button, 0, 1)
        outer.addLayout(receipt_actions)
        self.edit_receipt_button.hide()
        self.cancel_receipt_button.hide()
        self._collection_history_rows: list[dict[str, object]] = []
        self._collection_receipt_in_progress = False
        self._refresh_collections()
        return page

    def _refresh_collections(self) -> None:
        if self.repository is None:
            return
        people = [
            person for person in self.repository.list_people()
            if int(person["active"]) == 1
        ]
        self._fill_combo(self.extra_person, [(str(p["name"]), str(p["id"])) for p in people])
        self._refresh_collection_items()
        self._collection_history_rows = self.repository.list_receipt_history()
        self._render_collection_history()

    def _render_collection_history(self) -> None:
        selected_id = self._table_id(self.collection_history, 6)
        blocker = QSignalBlocker(self.collection_history)
        role = self.collection_filter.currentData()
        rows = [r for r in self._collection_history_rows if role == "ALL" or r["payment_kind"] == role]
        if not self.collection_history_toggle.isChecked():
            rows = rows[:5]
        self.collection_history.setRowCount(0)
        for item in rows:
            row = self.collection_history.rowCount()
            self.collection_history.insertRow(row)
            values = (
                str(item["received_at"])[:10],
                item["user_name"],
                item["source_name"],
                format_money(int(item["amount_cents"])),
                item["reference"] or "",
                "ANULADO" if item["payment_status"] == "CANCELLED" else "Activo",
            )
            for column, value in enumerate(values):
                self.collection_history.setItem(
                    row, column, QTableWidgetItem(str(value))
                )
            self.collection_history.setItem(row, 6, QTableWidgetItem(str(item["id"])))
            self.collection_history.setItem(row, 7, QTableWidgetItem(self._participation_label(item["payment_kind"])))
            if str(item["id"]) == selected_id:
                self.collection_history.selectRow(row)
        blocker.unblock()

    def _selected_receipt_history(self) -> dict[str, object] | None:
        rows = self.collection_history.selectionModel().selectedRows()
        if not rows:
            return None
        payment_id = self.collection_history.item(rows[0].row(), 6).text()
        return next(
            (item for item in self._collection_history_rows if str(item["id"]) == payment_id),
            None,
        )

    def _select_receipt_history(self) -> None:
        item = self._selected_receipt_history()
        if item is None:
            return
        with QSignalBlocker(self.collection_items):
            self.collection_items.clearSelection()
        self.collection_amount.setText(
            f"{Decimal(int(item['amount_cents'])) / Decimal('100'):.2f}"
        )
        self.collection_received_date.setText(str(item["received_at"])[:10])
        self.collection_reference.setText(str(item["reference"] or ""))
        self.collection_current_balance.setText(
            f"Abono seleccionado: {item['user_name']} · "
            f"{format_money(int(item['amount_cents']))} · "
            f"{'ANULADO' if item['payment_status'] == 'CANCELLED' else 'Activo'}"
        )

    def _edit_selected_receipt(self) -> None:
        item = self._selected_receipt_history()
        if item is None:
            self._show_error("Selecciona un abono en el historial.")
            return
        try:
            amount = self._parse_mxn_to_cents(self.collection_amount.text())
            self.repository.update_user_payment(
                str(item["id"]),
                received_at=self.collection_received_date.text().strip(),
                amount_cents=amount,
                reference=self.collection_reference.text().strip() or None,
            )
        except (ValueError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        self.data_changed.emit("collections")
        self._show_information("El abono quedó actualizado.")

    def _cancel_selected_receipt(self) -> None:
        item = self._selected_receipt_history()
        if item is None:
            self._show_error("Selecciona un abono en el historial.")
            return
        if item["payment_status"] == "CANCELLED":
            self._show_error("Ese abono ya está anulado.")
            return
        answer = QMessageBox.question(
            self,
            "Confirmar anulación",
            f"¿Anular el abono de {item['user_name']} por "
            f"{format_money(int(item['amount_cents']))}?\n"
            "Se revertirá su aplicación a la cuenta por cobrar y quedará auditado.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.repository.cancel_user_payment(
                str(item["id"]), reason="Anulación confirmada desde Cobros"
            )
        except (ValueError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        self.data_changed.emit("collections")
        self._show_information("El abono fue anulado y el saldo se recalculó.")

    def _toggle_collection_history(self, expanded: bool) -> None:
        self.collection_history_toggle.setText(
            "Ocultar historial" if expanded else "Ver historial"
        )
        self.collection_history.setVisible(expanded)
        self.edit_receipt_button.setVisible(expanded)
        self.cancel_receipt_button.setVisible(expanded)
        self._render_collection_history()

    def _refresh_collection_items(self) -> None:
        if self.repository is None or not hasattr(self, "collection_items"):
            return
        selected_id = self._table_id(self.collection_items, 7)
        blocker = QSignalBlocker(self.collection_items)
        self.collection_items.setSortingEnabled(False)
        self.collection_items.setRowCount(0)
        items = self.repository.list_collection_items()
        personal = sum(int(i["remaining_cents"]) for i in items if i["participant_role"] == "PERSONAL")
        family = sum(int(i["remaining_cents"]) for i in items if i["participant_role"] == "FAMILY")
        unknown = sum(int(i["remaining_cents"]) for i in items if i["participant_role"] == "UNKNOWN")
        self.collection_totals.setText(
            f"Mi parte pendiente: {format_money(personal)} · "
            f"Cobros familiares pendientes: {format_money(family)}"
            + (f" · Históricos por revisar: {format_money(unknown)}" if unknown else "")
        )
        role = self.collection_filter.currentData()
        for item in items:
            if role != "ALL" and item["participant_role"] != role:
                continue
            row = self.collection_items.rowCount()
            self.collection_items.insertRow(row)
            values = (
                item["user_name"],
                item["user_id"],
                item["source_name"] or "Sin comercio identificado",
                format_money(int(item["sale_cents"])),
                format_money(int(item["paid_cents"])),
                format_money(int(item["remaining_cents"])),
                item["status"],
                item["receivable_id"],
                item["source_kind"],
                str(item["source_date"] or "Sin fecha")[:10],
                self._participation_label(item["participant_role"]),
            )
            for column, value in enumerate(values):
                self.collection_items.setItem(
                    row, column, QTableWidgetItem(str(value))
                )
            self.collection_items.item(row, 0).setToolTip(
                "Participación histórica reconstruida del reparto guardado. "
                "Su cuenta de seguimiento se crea al registrar el primer abono."
                if item["virtual"] else
                "Participación registrada; los abonos no generan pagos bancarios."
            )
        self.collection_items.setSortingEnabled(True)
        for row in range(self.collection_items.rowCount()):
            if self.collection_items.item(row, 7).text() == selected_id:
                self.collection_items.selectRow(row)
        blocker.unblock()
        row = self._selected_row(self.collection_items)
        if row is None:
            self.collection_current_balance.setText("Selecciona una cuenta para ver el saldo.")
            self.record_collection_button.setText("Registrar abono")
        else:
            self.collection_current_balance.setText(
                f"{self.collection_items.item(row, 10).text()} · "
                f"Saldo actual: {self.collection_items.item(row, 5).text()} · "
                f"{self.collection_items.item(row, 6).text()}"
            )
        self.collection_items.resizeRowsToContents()

    @staticmethod
    def _participation_label(role: object) -> str:
        return "Mi parte" if role == "PERSONAL" else "Cobros familiares" if role == "FAMILY" else "Histórico por revisar"

    def _filter_collections(self) -> None:
        if not hasattr(self, "collection_history"):
            return
        self._refresh_collection_items()
        self._render_collection_history()
        self._update_action_states()

    def _select_collection_item(self) -> None:
        row = self._selected_row(self.collection_items)
        if row is None:
            self.collection_current_balance.setText(
                "Selecciona una cuenta para ver el saldo."
            )
            return
        with QSignalBlocker(self.collection_history):
            self.collection_history.clearSelection()
        receivable_id = self.collection_items.item(row, 7).text()
        item = next(
            (
                value for value in self.repository.list_collection_items()
                if value["receivable_id"] == receivable_id
            ),
            None,
        )
        if item is None:
            return
        remaining_cents = int(item["remaining_cents"])
        self.collection_current_balance.setText(
            f"{self._participation_label(item['participant_role'])}: "
            f"pendiente {format_money(remaining_cents)} · {item['status']}\n"
            f"{item['source_kind']} · {item['source_date'] or 'Fecha por revisar'}"
        )
        self.collection_current_balance.setWordWrap(True)
        self.record_collection_button.setText(
            "Registrar abono personal" if item["participant_role"] == "PERSONAL" else "Registrar abono"
        )
        self.collection_amount.setText(
            f"{Decimal(remaining_cents) / Decimal('100'):.2f}"
        )

    def _record_collection(self) -> None:
        if self._collection_receipt_in_progress:
            return
        row = self._selected_row(self.collection_items)
        if row is None:
            self._show_error("Selecciona el pedido al que corresponde el abono.")
            return
        try:
            self._collection_receipt_in_progress = True
            self.record_collection_button.setEnabled(False)
            amount = self._parse_mxn_to_cents(self.collection_amount.text())
            receivable_id = self.collection_items.item(row, 7).text()
            self.repository.record_receipt(
                payment_id=str(uuid4()),
                receivable_id=receivable_id,
                amount_cents=amount,
                received_at=self.collection_received_date.text().strip(),
                reference=self.collection_reference.text().strip() or None,
            )
        except (ValueError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        finally:
            self._collection_receipt_in_progress = False
            self.record_collection_button.setEnabled(True)
        self.collection_amount.clear()
        self.collection_reference.clear()
        self.collection_received_date.setText(date.today().isoformat())
        self.data_changed.emit("collections")
        self._show_information("Se actualizó la participación. No se registró ningún pago bancario.")

    def _record_extra(self) -> None:
        user_id = self.extra_person.currentData()
        try:
            if user_id is None:
                raise ValueError("Selecciona la persona que entregó el extra.")
            description = self.extra_description.text().strip()
            if not description:
                raise ValueError("Indica el motivo del extra.")
            self.repository.record_extra(
                extra_id=str(uuid4()), user_id=str(user_id),
                received_at=date.today().isoformat(),
                amount_cents=self._parse_mxn_to_cents(self.extra_amount.text()),
                description=description,
            )
        except (ValueError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        self.extra_amount.clear()
        self.extra_description.clear()
        self.data_changed.emit("collections")
        QMessageBox.information(self, "Extra registrado", "Se guardó como ganancia separada.")

    def _record_fee(self) -> None:
        try:
            description = self.fee_description.text().strip()
            if not description:
                raise ValueError("Indica a qué depósito corresponde la comisión.")
            self.repository.record_deposit_fee(
                fee_id=str(uuid4()), incurred_at=date.today().isoformat(),
                amount_cents=self._parse_mxn_to_cents(self.fee_amount.text()),
                description=description,
            )
        except (ValueError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        self.fee_amount.clear()
        self.fee_description.clear()
        self.data_changed.emit("collections")
        QMessageBox.information(self, "Comisión registrada", "Se guardó como gasto propio.")

    def _make_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("Configuración")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        notice = QLabel(
            "Configura explícitamente el propietario persistente. "
            "No se elige automáticamente por nombre y no se modifican "
            "pedidos ni deudas históricas."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)

        layout.addWidget(QLabel("Personas y propietario"))
        self.owner_people_table = QTableWidget(0, 4)
        self.owner_people_table.setObjectName("ownerPeopleTable")
        self.owner_people_table.setHorizontalHeaderLabels(
            ["ID", "Persona", "Activa", "Propietario"]
        )
        self.owner_people_table.setColumnHidden(0, True)
        self.owner_people_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.owner_people_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.owner_people_table.itemSelectionChanged.connect(
            self._load_selected_owner
        )
        layout.addWidget(self.owner_people_table)

        self.owner_selection = QLabel(
            "Selecciona una persona activa para configurar el propietario."
        )
        self.owner_selection.setWordWrap(True)
        layout.addWidget(self.owner_selection)
        self.configure_owner_button = QPushButton("Configurar propietario")
        self.configure_owner_button.setObjectName("configureOwnerButton")
        self.configure_owner_button.clicked.connect(self._configure_owner)
        layout.addWidget(self.configure_owner_button, alignment=Qt.AlignmentFlag.AlignRight)
        maintenance = QGridLayout()
        for column, title, slot in ((0, 'Crear respaldo cifrado', self._create_backup),
                                    (1, 'Restaurar respaldo', self._restore_backup),
                                    (2, 'Diagnóstico de integridad', self._run_integrity)):
            button = QPushButton(title)
            button.clicked.connect(slot)
            if column < 2:
                button.setEnabled(self.database.encrypted)
            maintenance.addWidget(button, column // 2, column % 2, 1, 2 if column == 2 else 1)
        layout.addLayout(maintenance)
        self.maintenance_result = QTextEdit()
        self.maintenance_result.setReadOnly(True)
        self.maintenance_result.setMaximumHeight(160)
        self.maintenance_result.setPlaceholderText('Restaurar requiere confirmación y crea un respaldo cifrado de la base actual.')
        layout.addWidget(self.maintenance_result)
        layout.addStretch()
        self._refresh_owner_people()
        return page

    def _run_integrity(self):
        try:
            report = self.database.integrity_report()
            self.maintenance_result.setPlainText(('Integridad y relaciones correctas. Revisión de solo lectura.' if report['ok'] else '\n'.join(report['issues'])) + '\n' + '\n'.join(report['warnings']))
        except Exception:
            self._show_error('No se pudo completar el diagnóstico. No se modificaron registros.')

    def _create_backup(self):
        name = f"valenza-{datetime.now():%Y%m%d-%H%M%S}.db"
        path, _ = QFileDialog.getSaveFileName(self, 'Crear respaldo cifrado', name, 'Base cifrada (*.db)')
        if not path:
            return
        try:
            self.database.create_backup(path)
        except Exception:
            self._show_error('No se pudo crear y verificar el respaldo. Elige una ruta nueva con permisos de escritura; no reemplaces un archivo existente.')
            return
        self.maintenance_result.setPlainText(f'Respaldo cifrado creado y verificado:\n{path}\nConserva la clave actual en un lugar seguro; no se incluye en el archivo.')
        self._show_information('Respaldo cifrado verificado.')

    def _restore_backup(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Seleccionar respaldo cifrado', '', 'Base cifrada (*.db)')
        if not path:
            return
        try:
            self.database.verify_backup(path)
        except Exception:
            self._show_error('El respaldo no es válido para esta sesión: comprueba su clave y versión. La base actual no se modificó.')
            return
        if QMessageBox.question(self, 'Restaurar respaldo',
            'Se reemplazarán los datos activos por el respaldo seleccionado y se descartarán capturas sin guardar.\n'
            'Antes se guardará una copia cifrada y verificada de los datos actuales.\n¿Restaurar?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        current = Path(self.database.connection.execute('PRAGMA database_list').fetchone()[2])
        safety = current.parent / 'backups' / f'pre-restauracion-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex}.db'
        try:
            safety.parent.mkdir(parents=True, exist_ok=True)
            self.database.restore_backup(path, safety)
        except Exception:
            self.maintenance_result.setPlainText(f'La restauración no terminó. Respaldo de seguridad, si pudo completarse:\n{safety}')
            self._show_error('No se completó la restauración. Revisa el diagnóstico y conserva el respaldo de seguridad antes de continuar.')
            return
        self.manual_dialog.reject()
        self._clear_order_form()
        self._admin_edit_selection = None
        self._bank_query_selection = None
        self.data_changed.emit('all')
        self.maintenance_result.setPlainText(f'Respaldo restaurado. Se conservó la copia anterior:\n{safety}')
        self._show_information('Restauración completada; se conservó la copia anterior.')

    def _export_family_pdf(self):
        row = self._selected_row(self.collection_items)
        if row is None:
            self._show_error('Selecciona una participación de la persona que quieres consultar.')
            return
        user_id = self.collection_items.item(row, 1).text()
        path, _ = QFileDialog.getSaveFileName(self, 'Guardar estado de cuenta de esta persona', 'estado-de-cuenta.pdf', 'PDF (*.pdf)')
        if not path:
            return
        try:
            write_family_pdf(self.repository.family_statement(user_id), path)
        except ImportError:
            self._show_error('Instala la dependencia local PyMuPDF para generar PDF.')
            return
        except Exception:
            self._show_error('No se pudo generar el PDF. Comprueba el destino y sus permisos. No se modificaron movimientos.')
            return
        self._show_information('Estado de cuenta PDF generado; no se modificaron saldos.')

    def _show_result_breakdown(self, visible):
        self.dashboard_result_details.setVisible(visible)
        if not visible or self.repository is None:
            return
        rows = self.repository.expected_result_breakdown()
        parts = ['<b>Familia asignada − costo efectivo de cada operación</b><br>Recompras vinculadas incluidas una vez. Antes de abonos personales; sin intereses ni comisiones.<br>']
        for row in rows:
            parts.append(f"<p>{escape(row['merchant'])} · {escape(row['date'])}<br>{format_money(row['family_cents'])} − {format_money(row['cost_cents'])} = <b>{format_money(row['result_cents'])}</b></p>")
        total = sum(r['result_cents'] for r in rows)
        parts.append(f"<b>Resultado previsto total {'a favor' if total >= 0 else 'a mi cargo'}: {format_money(abs(total))}</b><br>Los descuentos ya están reflejados en el costo efectivo; no se restan otra vez. No es dinero cobrado ni saldo bancario.")
        self.dashboard_result_details.setHtml(''.join(parts))

    def _refresh_owner_people(self, selected_id: str | None = None) -> None:
        if not hasattr(self, "owner_people_table") or self.repository is None:
            return
        selected_id = selected_id or self._selected_owner_id()
        blocker = QSignalBlocker(self.owner_people_table)
        self.owner_people_table.setRowCount(0)
        for person in self.repository.list_people():
            row = self.owner_people_table.rowCount()
            self.owner_people_table.insertRow(row)
            values = (
                str(person["id"]),
                str(person["name"]),
                "Sí" if person["active"] else "No",
                "Sí" if person["is_owner"] else "No",
            )
            for column, value in enumerate(values):
                self.owner_people_table.setItem(row, column, QTableWidgetItem(value))
            if selected_id is not None and str(person["id"]) == selected_id:
                self.owner_people_table.selectRow(row)
        blocker.unblock()
        self._load_selected_owner()
        self.owner_people_table.resizeColumnsToContents()

    def _selected_owner_id(self) -> str | None:
        rows = self.owner_people_table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.owner_people_table.item(rows[0].row(), 0).text()

    def _load_selected_owner(self) -> None:
        person_id = self._selected_owner_id()
        if person_id is None:
            self.owner_selection.setText("Selecciona una persona activa para configurar el propietario.")
            return
        person = self.repository.get_person(person_id)
        if person is not None:
            self.owner_selection.setText(
                f"Seleccionado: {person['name']} · "
                f"{'Activa' if person['active'] else 'Inactiva'} · "
                f"Propietario: {'Sí' if person['is_owner'] else 'No'}"
            )

    def _configure_owner(self) -> None:
        person_id = self._selected_owner_id()
        if person_id is None:
            self._show_error("Selecciona la persona que será el propietario.")
            return
        person = self.repository.get_person(person_id)
        if person is None or not person["active"]:
            self._show_error("Solo puedes seleccionar una persona activa.")
            return
        answer = QMessageBox.question(
            self,
            "Confirmar propietario",
            f"¿Configurar a {person['name']} como único propietario activo?\n\n"
            "Las personas, IDs, movimientos, deudas y auditoría se conservarán. "
            "Las deudas históricas no se reclasificarán.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self.repository.configure_owner(
                person_id, actor="desktop"
            )
        except ValueError as error:
            self._show_error(self._safe_error(error))
            return
        self._refresh_owner_people(person_id)
        self._refresh_people()
        self._reset_order_allocations()
        references = result["historical_references"]
        self.data_changed.emit("users")
        self._show_information(
            f"Propietario configurado: {person['name']}.\n"
            f"Referencias históricas conservadas: "
            f"{references['purchase_allocations']} compras, "
            f"{references['order_allocations']} pedidos y "
            f"{references['receivables']} cuentas por cobrar."
        )

    def _make_users_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("Usuarios")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        notice = QLabel(
            "Administra las personas de la base activa. Desactivar una persona "
            "conserva sus movimientos y deudas históricas."
        )
        notice.setObjectName("demoBanner")
        layout.addWidget(notice)

        form = QGridLayout()
        form.addWidget(QLabel("Nombre"), 0, 0)
        self.person_name = QLineEdit()
        self.person_name.setPlaceholderText("Nombre de la persona")
        form.addWidget(self.person_name, 0, 1)
        self.person_owner = QCheckBox("Es propietario")
        form.addWidget(self.person_owner, 0, 2)
        layout.addLayout(form)

        actions = QGridLayout()
        self.create_person_button = QPushButton("Crear persona")
        self.create_person_button.clicked.connect(self._create_person)
        actions.addWidget(self.create_person_button, 0, 0)
        self.update_person_button = QPushButton("Guardar edición")
        self.update_person_button.clicked.connect(self._update_person)
        actions.addWidget(self.update_person_button, 0, 1)
        self.deactivate_person_button = QPushButton("Desactivar seleccionada")
        self.deactivate_person_button.clicked.connect(self._deactivate_person)
        actions.addWidget(self.deactivate_person_button, 0, 2)
        self.reactivate_person_button = QPushButton("Reactivar seleccionada")
        self.reactivate_person_button.clicked.connect(self._reactivate_person)
        actions.addWidget(self.reactivate_person_button, 0, 3)
        clear_button = QPushButton("Limpiar selección")
        clear_button.clicked.connect(self._clear_person_form)
        actions.addWidget(clear_button, 0, 4)
        layout.addLayout(actions)

        self.people_table = QTableWidget(0, 4)
        self.people_table.setObjectName("peopleTable")
        self.people_table.setHorizontalHeaderLabels(["ID", "Nombre", "Propietario", "Estado"])
        self.people_table.setColumnHidden(0, True)
        self.people_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.people_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.people_table.itemSelectionChanged.connect(self._load_selected_person)
        layout.addWidget(self.people_table)
        self._refresh_people()
        return page

    def _make_purchases_page(self) -> QWidget:
        return self._make_legacy_purchases_page()

    def _make_legacy_purchases_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("Compras históricas")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        notice = QLabel(
            "Consulta y captura de compras antiguas con productos. "
            "Este flujo no forma parte del registro de Pedidos."
        )
        notice.setObjectName("demoBanner")
        layout.addWidget(notice)
        header = QGridLayout()
        header.addWidget(QLabel("Comercio"), 0, 0)
        self.purchase_merchant = QLineEdit()
        header.addWidget(self.purchase_merchant, 0, 1)
        header.addWidget(QLabel("Fecha"), 0, 2)
        self.purchase_date = QLineEdit(date.today().isoformat())
        header.addWidget(self.purchase_date, 0, 3)
        header.addWidget(QLabel("Institución"), 1, 0)
        self.purchase_institution = QComboBox()
        self.purchase_institution.currentIndexChanged.connect(self._refresh_instruments)
        header.addWidget(self.purchase_institution, 1, 1)
        header.addWidget(QLabel("Instrumento"), 1, 2)
        self.purchase_instrument = QComboBox()
        header.addWidget(self.purchase_instrument, 1, 3)
        layout.addLayout(header)
        product_form = QGridLayout()
        self.product_description = QLineEdit()
        self.product_quantity = QSpinBox()
        self.product_quantity.setRange(1, 100000)
        self.product_unit_price = MxnLineEdit()
        product_form.addWidget(QLabel("Producto"), 0, 0)
        product_form.addWidget(self.product_description, 0, 1)
        product_form.addWidget(QLabel("Unidades"), 0, 2)
        product_form.addWidget(self.product_quantity, 0, 3)
        product_form.addWidget(QLabel("Precio unitario (MXN)"), 0, 4)
        product_form.addWidget(self.product_unit_price, 0, 5)
        add_product = QPushButton("Agregar producto")
        add_product.clicked.connect(self._add_product_row)
        product_form.addWidget(add_product, 0, 6)
        layout.addLayout(product_form)
        self.products_table = QTableWidget(0, 4)
        self.products_table.setObjectName("purchaseProducts")
        self.products_table.setHorizontalHeaderLabels(
            ["ID", "Descripción", "Unidades", "Precio unitario (MXN)"]
        )
        self.products_table.setColumnHidden(0, True)
        layout.addWidget(self.products_table)
        allocation_form = QGridLayout()
        self.allocation_product = QComboBox()
        self.allocation_user = QComboBox()
        self.allocation_method = QComboBox()
        self.allocation_method.addItem("Unidades", "UNITS")
        self.allocation_method.addItem("Proporción (%)", "PERCENT")
        self.allocation_basis = QSpinBox()
        self.allocation_basis.setRange(1, 10000)
        for column, widget in enumerate(
            (
                QLabel("Producto"), self.allocation_product,
                QLabel("Persona"), self.allocation_user,
                QLabel("Método"), self.allocation_method,
                QLabel("Valor"), self.allocation_basis,
            )
        ):
            allocation_form.addWidget(widget, 0, column)
        add_allocation = QPushButton("Agregar asignación")
        add_allocation.clicked.connect(self._add_allocation_row)
        allocation_form.addWidget(add_allocation, 0, 8)
        layout.addLayout(allocation_form)
        self.allocations_table = QTableWidget(0, 6)
        self.allocations_table.setHorizontalHeaderLabels(
            ["Producto", "Persona", "Método", "Valor", "Producto ID", "Persona ID"]
        )
        self.allocations_table.setColumnHidden(4, True)
        self.allocations_table.setColumnHidden(5, True)
        layout.addWidget(self.allocations_table)
        save_purchase = QPushButton("Guardar compra histórica")
        save_purchase.clicked.connect(self._save_purchase)
        layout.addWidget(save_purchase)
        self.purchase_total = QLabel(
            "Total: $0.00 MXN · Propietario: $0.00 MXN · "
            "Cuentas por cobrar: $0.00 MXN"
        )
        layout.addWidget(self.purchase_total)
        layout.addWidget(QLabel("Compras históricas registradas"))
        self.purchases_table = QTableWidget(0, 4)
        self.purchases_table.setObjectName("purchasesTable")
        self.purchases_table.setHorizontalHeaderLabels(
            ["ID", "Comercio", "Total", "Parte del propietario"]
        )
        self.purchases_table.setColumnHidden(0, True)
        self.purchases_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.purchases_table.itemSelectionChanged.connect(self._show_purchase_detail)
        layout.addWidget(self.purchases_table)
        self.purchase_detail = QTextEdit()
        self.purchase_detail.setReadOnly(True)
        layout.addWidget(self.purchase_detail)
        self._load_legacy_purchase_catalogs()
        self._refresh_purchases()
        return page

    def _make_orders_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        title = QLabel('Pedidos')
        title.setObjectName('pageTitle')
        outer.addWidget(title)
        toolbar = QHBoxLayout()
        self.new_expense_button = QPushButton('Nuevo gasto')
        self.new_expense_button.clicked.connect(self._open_manual_expense)
        toolbar.addWidget(self.new_expense_button)
        import_pdf = QPushButton('Importar PDF')
        import_pdf.clicked.connect(self._import_order_pdf)
        toolbar.addWidget(import_pdf)
        toolbar.addStretch()
        outer.addLayout(toolbar)
        self.manual_dialog = QDialog(self)
        self.manual_dialog.setWindowTitle('Nuevo gasto')
        self.manual_dialog.resize(760, 580)
        self.manual_dialog.setMinimumSize(480, 280)
        dialog_root = QVBoxLayout(self.manual_dialog)
        dialog_root.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        scroll = QScrollArea(self.manual_dialog)
        self.manual_scroll = scroll
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        notice = QLabel(
            "Un concepto por producto o servicio. Un solo cargo por gasto."
        )
        notice.setObjectName("demoBanner")
        notice.setWordWrap(True)
        layout.addWidget(notice)

        general = QFormLayout()
        self.order_merchant = QLineEdit()
        self.order_merchant.setPlaceholderText("Nombre del comercio")
        self.order_date = QLineEdit(date.today().isoformat())
        self.order_institution = QComboBox()
        self.order_institution.currentIndexChanged.connect(self._refresh_order_instruments)
        self.order_instrument = QComboBox()
        basic = QGridLayout()
        basic.setColumnStretch(0, 2)
        basic.setColumnStretch(1, 1)
        for row, labels, widgets in [(0, ('Comercio', 'Fecha (AAAA-MM-DD)'), (self.order_merchant, self.order_date)),
                                    (2, ('Institución', 'Tarjeta / instrumento'), (self.order_institution, self.order_instrument))]:
            for column, (label, widget) in enumerate(zip(labels, widgets)):
                basic.addWidget(QLabel(label), row, column)
                basic.addWidget(widget, row + 1, column)
        layout.addLayout(basic)
        general.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.order_purchase_mode = QComboBox()
        self.order_purchase_mode.addItem("Contado", "CASH")
        self.order_purchase_mode.addItem("MSI", "MSI")
        self.order_purchase_mode.currentIndexChanged.connect(self._toggle_msi_fields)
        general.addRow("Modalidad", self.order_purchase_mode)
        self.order_installments = QSpinBox()
        self.order_installments.setRange(1, 60)
        self.order_installments.setValue(3)
        self.order_first_due_date = QLineEdit()
        self.order_first_due_date.setPlaceholderText("AAAA-MM-DD; confirmar con institución")
        self.order_interest = MxnLineEdit()
        self.order_interest.setPlaceholderText("0.00")
        general.addRow("Número de cuotas", self.order_installments)
        general.addRow("Vencimiento primera cuota", self.order_first_due_date)
        general.addRow("Intereses del plan (MXN)", self.order_interest)
        self.order_msi_labels = tuple(general.labelForField(w) for w in (
            self.order_installments, self.order_first_due_date, self.order_interest
        ))
        self._toggle_msi_fields()
        layout.addLayout(general)

        amounts = QGridLayout()
        self.order_original = MxnLineEdit()
        self.order_original.setPlaceholderText("5000.00")
        self.order_charged = MxnLineEdit()
        self.order_charged.setPlaceholderText("5000.00")
        self.order_discount = QLabel("$0.00 MXN")
        self.order_exception = QLabel()
        self.order_exception.setWordWrap(True)
        amounts.addWidget(QLabel("Total de conceptos (MXN)"), 0, 0)
        amounts.addWidget(self.order_original, 1, 0)
        amounts.addWidget(QLabel("Cargo real (MXN)"), 0, 1)
        amounts.addWidget(self.order_charged, 1, 1)
        amounts.addWidget(QLabel("Descuento calculado"), 2, 0)
        amounts.addWidget(self.order_discount, 2, 1)
        amounts.addWidget(self.order_exception, 3, 0, 1, 2)
        self.manual_edit_id = None
        self.manual_expected_concepts = None
        self.manual_dialog.rejected.connect(self._cancel_manual_edit)
        self.manual_concepts = QTableWidget(0, 3)
        self.manual_concepts.setHorizontalHeaderLabels(['Concepto', 'Importe (MXN)', 'Persona / Dividir'])
        self.manual_concepts.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.manual_concepts.setColumnWidth(0, 220)
        self.manual_concepts.setColumnWidth(1, 100)
        self.manual_concepts.setColumnWidth(2, 270)
        self.manual_concepts.setWordWrap(True)
        self.manual_concepts.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.manual_concepts.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.manual_concepts.setMinimumHeight(180)
        self.manual_concepts.verticalHeader().hide()
        layout.addWidget(self.manual_concepts)
        concepts_actions = QHBoxLayout()
        add_concept = QPushButton('Agregar concepto')
        add_concept.clicked.connect(lambda: self._add_manual_concept())
        remove_concept = QPushButton('Eliminar concepto seleccionado')
        remove_concept.clicked.connect(self._remove_manual_concept)
        concepts_actions.addWidget(add_concept)
        concepts_actions.addWidget(remove_concept)
        layout.addLayout(concepts_actions)
        layout.addLayout(amounts)
        self.manual_concepts.itemChanged.connect(self._update_manual_concepts)

        self.order_allocation_label = QLabel('Reparto por persona')
        layout.addWidget(self.order_allocation_label)
        self.order_allocations_table = QTableWidget(0, 2)
        self.order_allocations_table.setHorizontalHeaderLabels(["Persona", "Importe (MXN)"])
        self.order_allocations_table.setObjectName("orderAllocationsTable")
        self.order_allocations_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.order_allocations_table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.EditKeyPressed
            | QTableWidget.EditTrigger.SelectedClicked
        )
        self.order_allocations_table.horizontalHeader().setStretchLastSection(True)
        self.order_allocations_table.verticalHeader().setDefaultSectionSize(32)
        self.order_allocations_table.setMinimumHeight(96)
        self.order_allocations_table.setMaximumHeight(260)
        self.order_allocations_table.itemChanged.connect(self._update_order_preview)
        self.order_allocations_table.horizontalHeader().sectionClicked.connect(
            self._enable_order_allocation_sorting
        )
        layout.addWidget(self.order_allocations_table)
        # Compatibility-only editor for callers of the previous API. It is
        # intentionally not added to the redesigned layout.
        self.order_amount = MxnLineEdit()
        self.order_user = QComboBox()
        self.order_summary = QLabel()
        self.order_summary.setObjectName("orderSummary")
        self.order_summary.setWordWrap(True)
        self.order_summary.setStyleSheet("font-weight: 600; padding: 6px;")
        layout.addWidget(self.order_summary)
        self.save_order_button = QPushButton("Guardar pedido")
        self.save_order_button.setObjectName("primaryAction")
        self.save_order_button.clicked.connect(self._save_order)
        scroll.setWidget(content)
        dialog_root.addWidget(scroll, 1)
        footer = QHBoxLayout()
        self.cancel_manual_button = QPushButton('Cancelar')
        self.cancel_manual_button.clicked.connect(self.manual_dialog.reject)
        footer.addStretch()
        footer.addWidget(self.cancel_manual_button)
        footer.addWidget(self.save_order_button)
        dialog_root.addLayout(footer)
        layout = outer

        orders_header = QGridLayout()
        orders_header.addWidget(QLabel("Pedidos registrados"), 0, 0)
        self.order_filter = QComboBox()
        self.order_filter.addItem("Activos", "ACTIVE")
        self.order_filter.addItem("Anulados", "CANCELLED")
        self.order_filter.addItem("Todos", "ALL")
        self.order_filter.currentIndexChanged.connect(self._refresh_orders)
        orders_header.addWidget(QLabel("Mostrar:"), 0, 1)
        orders_header.addWidget(self.order_filter, 0, 2)
        layout.addLayout(orders_header)
        self.orders_table = QTableWidget(0, 9)
        self.orders_table.setObjectName("ordersTable")
        self.orders_table.setHorizontalHeaderLabels(
            ["Comercio", "Fecha", "Original", "Cargo real", "Descuento",
             "Yo (vigente)", "Familia (vigente)", "Estado", "ID"]
        )
        for column in (5, 6):
            self.orders_table.horizontalHeaderItem(column).setToolTip(
                'Participación vigente después de ajustes, antes de abonos. '
                'Los importes originales y las participaciones sin clasificar están en el detalle.')
        self.orders_table.setColumnHidden(8, True)
        self.orders_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.orders_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.orders_table.verticalHeader().setDefaultSectionSize(36)
        self.orders_table.setMinimumHeight(140)
        self.orders_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        for column in range(1, 8):
            self.orders_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.orders_table.itemSelectionChanged.connect(self._show_order_detail)
        layout.addWidget(self.orders_table, 3)
        self.cancel_order_button = QPushButton("Anular pedido seleccionado")
        self.cancel_order_button.clicked.connect(self._cancel_selected_order)
        self.edit_order_button = QPushButton("Editar comercio")
        self.edit_order_button.clicked.connect(self._edit_order_merchant)
        self.accredit_refund_button = QPushButton('Acreditar devolución pendiente')
        self.accredit_refund_button.clicked.connect(self._confirm_pending_product_refund)
        self.accredit_refund_button.setEnabled(False)
        self.repurchase_button = QPushButton('Lo compré de nuevo')
        self.repurchase_button.clicked.connect(self._register_product_repurchase)
        self.repurchase_button.setEnabled(False)
        order_actions = QGridLayout()
        order_actions.addWidget(self.edit_order_button, 0, 0)
        order_actions.addWidget(self.cancel_order_button, 0, 1)
        order_actions.addWidget(self.accredit_refund_button, 1, 0)
        order_actions.addWidget(self.repurchase_button, 1, 1)
        self.edit_concepts_button = QPushButton('Editar conceptos y reparto')
        self.edit_concepts_button.clicked.connect(self._edit_manual_expense)
        order_actions.addWidget(self.edit_concepts_button, 2, 0, 1, 2)
        layout.addLayout(order_actions)
        self.order_detail = QTextEdit()
        self.order_detail.setObjectName("orderDetail")
        self.order_detail.setReadOnly(True)
        self.order_detail.setMinimumHeight(60)
        layout.addWidget(self.order_detail, 2)
        self._load_order_catalogs()
        self._reset_order_allocations()
        self._refresh_orders()
        self.order_original.textChanged.connect(self._update_order_preview)
        self.order_charged.textChanged.connect(self._update_order_preview)
        self.order_merchant.textChanged.connect(self._update_order_preview)
        self.order_date.textChanged.connect(self._update_order_preview)
        self.order_instrument.currentIndexChanged.connect(self._update_order_preview)
        self.order_first_due_date.textChanged.connect(self._update_order_preview)
        self.order_interest.textChanged.connect(self._update_order_preview)
        return page

    def _open_manual_expense(self):
        self._manual_started = True
        available = self.screen().availableGeometry()
        self.manual_dialog.resize(min(760, available.width() - 32), min(580, available.height() - 64))
        if self.manual_edit_id:
            self.manual_dialog.show()
            return
        if not self.manual_concepts.rowCount():
            self._add_manual_concept()
        self.manual_dialog.setWindowTitle('Nuevo gasto')
        self.manual_dialog.show()

    def _cancel_manual_edit(self):
        if self.database is not None and self.manual_edit_id:
            self._clear_order_form()

    def _add_manual_concept(self, concept=None):
        from sgccc.gui.pdf_import import ProductAssignment, pesos
        concept = concept or dict(description='', amount_cents=0, allocations={})
        row = self.manual_concepts.rowCount()
        with QSignalBlocker(self.manual_concepts):
            self.manual_concepts.insertRow(row)
            description = QTableWidgetItem(concept['description'])
            amount = QTableWidgetItem(pesos(concept['amount_cents']))
            self.manual_concepts.setItem(row, 0, description)
            self.manual_concepts.setItem(row, 1, amount)
            assignment = ProductAssignment(list(self._order_people_catalog().values()),
                lambda: self._parse_mxn_to_cents(amount.text()), self.manual_concepts)
            shares = concept['allocations']
            nonzero = [person for person, value in shares.items() if value]
            if nonzero:
                assignment.person.setCurrentIndex(assignment.person.findData(nonzero[0]))
            if len(nonzero) > 1:
                assignment.divide.setChecked(True)
                for person, edit in assignment.amounts.items():
                    edit.setText(pesos(shares.get(person, 0)))
            assignment.changed.connect(self._update_manual_concepts)
            self.manual_concepts.setCellWidget(row, 2, assignment)
        self._update_manual_concepts()

    def _remove_manual_concept(self):
        row = self.manual_concepts.currentRow()
        if row >= 0:
            self.manual_concepts.removeRow(row)
            self._update_manual_concepts()

    def _read_manual_concepts(self):
        return [dict(description=self.manual_concepts.item(row, 0).text().strip(),
                     amount_cents=self._parse_mxn_to_cents(self.manual_concepts.item(row, 1).text()),
                     allocations=self.manual_concepts.cellWidget(row, 2).shares())
                for row in range(self.manual_concepts.rowCount())]

    def _update_manual_concepts(self, *_args):
        if not hasattr(self, 'order_allocations_table'):
            return
        try:
            concepts = self._read_manual_concepts()
            totals = {}
            for concept in concepts:
                for person, value in concept['allocations'].items():
                    totals[person] = totals.get(person, 0) + value
            if concepts:
                with QSignalBlocker(self.order_original):
                    self.order_original.setText(f"{sum(c['amount_cents'] for c in concepts) / 100:.2f}")
                with QSignalBlocker(self.order_allocations_table):
                    self._reset_order_allocations()
                    for row in range(self.order_allocations_table.rowCount()):
                        person = self.order_allocations_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                        self.order_allocations_table.item(row, 1).setText(f'{totals.get(person, 0) / 100:.2f}')
                self.order_allocations_table.hide()
                self.order_allocation_label.hide()
                self.order_original.setReadOnly(True)
            self._update_order_preview()
        except ValueError:
            self.order_summary.setText('Revisa los conceptos y sus repartos.')
            self.save_order_button.setEnabled(False)
        self.manual_concepts.resizeRowsToContents()
        control_width = 270
        for row in range(self.manual_concepts.rowCount()):
            widget = self.manual_concepts.cellWidget(row, 2)
            control_width = max(control_width, widget.minimumSizeHint().width())
            self.manual_concepts.setRowHeight(row, max(self.manual_concepts.rowHeight(row), 52, widget.sizeHint().height()))
        self.manual_concepts.setColumnWidth(2, control_width)
        height = min(300, max(100, sum(self.manual_concepts.rowHeight(row) for row in range(self.manual_concepts.rowCount()))
                             + self.manual_concepts.horizontalHeader().height() + 24))
        self.manual_concepts.setMinimumHeight(height)
        self.manual_concepts.setMaximumHeight(height)

    def _edit_manual_expense(self):
        order_id = self._table_id(self.orders_table, 8)
        order = self.repository.get_order(order_id) if order_id else None
        if not order or order['manual_concepts'] is None:
            return
        if self.manual_concepts.rowCount() and self.manual_edit_id != order_id:
            if QMessageBox.question(self, 'Captura en proceso', '¿Descartar el borrador para editar este gasto?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
        self._clear_order_form()
        self.manual_edit_id = order_id
        self.manual_expected_concepts = order['manual_concepts']
        self.order_merchant.setText(order['merchant'])
        self.order_date.setText(order['ordered_at'])
        instrument = next(i for i in self.repository.list_all_instruments() if i['id'] == order['instrument_id'])
        self.order_institution.setCurrentIndex(self.order_institution.findData(instrument['institution_id']))
        self.order_instrument.setCurrentIndex(self.order_instrument.findData(order['instrument_id']))
        self.order_charged.setText(f"{order['charged_cents'] / 100:.2f}")
        self.order_purchase_mode.setCurrentIndex(self.order_purchase_mode.findData(order['purchase_mode']))
        for widget in (self.order_merchant, self.order_date, self.order_institution, self.order_instrument,
                       self.order_charged, self.order_purchase_mode, self.order_installments,
                       self.order_first_due_date, self.order_interest):
            widget.setEnabled(False)
        for concept in order['manual_concepts']:
            self._add_manual_concept(concept)
        self.manual_dialog.setWindowTitle('Editar conceptos y reparto')
        self._open_manual_expense()

    def _import_order_pdf(self) -> None:
        from sgccc.ocr.order_import import read_receipt
        from sgccc.gui.pdf_import import ImportPreview
        path, _ = QFileDialog.getOpenFileName(self, 'Importar comprobante', '', 'PDF (*.pdf)')
        if not path:
            return
        try:
            draft = read_receipt(Path(path))
            if ImportPreview(self.repository, draft, self).exec():
                self._refresh_visible_data()
        except (ValueError, RuntimeError, OSError) as error:
            self._show_error(self._safe_error(error))

    def _load_order_catalogs(self) -> None:
        self.order_institution.clear()
        for item in self.repository.list_institutions():
            self.order_institution.addItem(str(item["name"]), item["id"])
        self._refresh_order_instruments()
        # Compatibility-only object for old programmatic callers; it is not
        # part of the Pedidos layout.
        self.order_user = QComboBox()
        for person in self.repository.list_people():
            if person["active"]:
                self.order_user.addItem(str(person["name"]), person["id"])

    def _refresh_order_instruments(self) -> None:
        if not hasattr(self, "order_instrument"):
            return
        self.order_instrument.clear()
        institution_id = self.order_institution.currentData()
        for item in self.repository.list_instruments(institution_id) if institution_id else []:
            self.order_instrument.addItem(str(item["alias"]), item["id"])

    def _show_order_detail(self) -> None:
        self.accredit_refund_button.setEnabled(False)
        self.repurchase_button.setEnabled(False)
        self.repurchase_button.setText('Lo compré de nuevo')
        rows = self.orders_table.selectionModel().selectedRows()
        if not rows:
            self.order_detail.clear()
            return
        order_id = self.orders_table.item(rows[0].row(), 8).text()
        order = self.repository.get_order(order_id)
        if order is None:
            return
        lines = [
            f"{order['merchant']} · {order['ordered_at']}",
            "\n1. Compra original y descuento",
            f"Original: {format_money(order['original_cents'])}",
            f"Descuento personal (incluido en el cargo): {format_money(order['discount_cents'])}",
            f"Cargo real: {format_money(order['charged_cents'])}",
            f"Estado: {'Anulado' if order['order_status'] == 'CANCELLED' else 'Activo'}",
        ]
        people = {str(person["id"]): str(person["name"])
                  for person in self.repository.list_people()}
        original_participations = [
            f"- {people.get(str(item['user_id']), item['user_id'])}: "
            f"{format_money(item['amount_cents'])}"
            for item in order["allocations"]
        ]
        evidence = order.get('import_evidence')
        for concept in order.get('manual_concepts') or []:
            lines.append(f"Concepto: {concept['description']} · {format_money(concept['amount_cents'])}")
            for person, amount in concept['allocations'].items():
                if amount:
                    lines.append(f"  {people.get(person, person)}: {format_money(amount)}")
        if evidence:
            assigned_refund = sum(int(r['amount_cents']) for r in order['product_refunds'])
            lines.extend([f"Comprobante: {evidence['number']} · {evidence['payment']}",
                          f"Total pagado neto: {format_money(evidence['paid'])}"])
            if evidence.get('kind') == 'MOBILE_TOPUP':
                lines.append(f"Servicio: {evidence['service']} · Compañía: {evidence['company']} · Hora: {evidence.get('time') or 'No indicada'}")
            for product in evidence['products']:
                lines.append(f"{product['description']} × {product['quantity']} · {format_money(product['unit'])} por unidad")
                for person, amount in product.get('allocations', {}).items():
                    if amount:
                        lines.append(f"  {people.get(person, person)}: {format_money(amount)}")
            lines.append("\n2. Devolución, recompra y compensación")
            if evidence.get('kind') != 'MOBILE_TOPUP':
                lines.append(f"Devolución del PDF: {format_money(evidence['refund'])} · "
                             f"Sin asignar: {format_money(evidence['refund'] - assigned_refund)}")
            if not order['product_refunds']:
                lines.append('Sin devolución asociada a un concepto.')
            for refund in order['product_refunds']:
                product = next(p for index, p in enumerate(evidence['products'])
                               if p.get('source_index', index) == refund['product_index'])
                lines.append(f"Devuelto: {product['description']} · {format_money(refund['amount_cents'])} · "
                             f"Destino: {refund['destination_name']} · "
                             f"{'Acreditado el ' + refund['accredited_at'] if refund['status'] == 'ACCREDITED' else 'Pendiente, sin efecto en saldos'}")
                for adjustment in refund['adjustments']:
                    if adjustment['original_cents'] or adjustment.get('effective_final_cents', adjustment['final_cents']):
                        lines.append(f"  {people.get(adjustment['user_id'], adjustment['user_id'])}: "
                            f"{format_money(adjustment['original_cents'])} → {format_money(adjustment.get('effective_final_cents', adjustment['final_cents']))}")
                if refund.get('repurchase'):
                    linked = refund['repurchase']
                    lines.append(f"  Recompra: {format_money(linked['charged_cents'])} · {linked['ordered_at']} · {linked['payment_name']} · "
                        f"Sobrante aplicado: {format_money(linked['applied_cents'])} · "
                        f"Pendiente original: {format_money(refund['original_cents'] - linked['applied_cents'])}")
                    lines.append('  Financiada con el reembolso; compensación familiar sin abono bancario.')
            self.accredit_refund_button.setEnabled(order['order_status'] == 'ACTIVE' and
                any(r['status'] == 'PENDING' for r in order['product_refunds']))
            self.repurchase_button.setEnabled(order['order_status'] == 'ACTIVE' and
                any(r['status'] == 'ACCREDITED' for r in order['product_refunds']))
            if any(r.get('repurchase') for r in order['product_refunds']):
                self.repurchase_button.setText('Editar reparto devolución/recompra')
        comparison = self.repository.order_benefit_summary(order_id)
        if not evidence:
            lines.extend(['\n2. Devolución, recompra y compensación', 'Sin devolución de producto registrada.'])
        if comparison['original_order_id'] != order_id:
            lines.append(f"Recompra vinculada al pedido {comparison['original_order_id']}; "
                         "financiada con el reembolso, sin otro cobro familiar.")
        lines.extend(["\n3. Participaciones y abonos", 'Participaciones originales:', *original_participations,
                      "Comparación de la operación completa (incluye recompra vinculada):"])
        lines.append(f"Participaciones ajustadas: {format_money(comparison['assigned_cents'])} · "
                     f"Costo de compras menos reembolsos acreditados: {format_money(comparison['effective_purchase_cost_cents'])}")
        for item in comparison['participations']:
            if (item['adjustment_cents'] or item['paid_cents']) and (item['sale_cents'] or item['paid_cents']):
                lines.append(f"  {people.get(str(item['user_id']), item['user_id'])}: "
                             f"asignado {format_money(item['sale_cents'])} · "
                             f"aportado {format_money(item['paid_cents'])} · "
                             f"pendiente {format_money(item['remaining_cents'])}")
        lines.append(f"Abonos familiares recibidos: {format_money(comparison['family_received_cents'])}. "
                     "Los abonos personales no cambian el resultado previsto.")
        lines.append("\n4. Beneficio personal y resultado previsto")
        lines.append(f"Beneficio personal por descuentos: {format_money(comparison['discount_benefit_cents'])} "
                     "(ahorro; contado una sola vez en Inicio).")
        result = int(comparison['expected_result_cents'])
        lines.append(f"Resultado previsto {'a favor' if result >= 0 else 'a mi cargo'}: "
                     f"{format_money(abs(result))} si se cobra todo a familiares; no es dinero recibido.")
        lines.append("Comparación de compras, sin intereses ni comisiones. "
                     "El descuento no es un abono bancario ni reduce participaciones familiares.")
        if comparison['unclassified_cents']:
            lines.append("Hay participaciones sin clasificar: revisar el resultado previsto.")
        self.order_detail.setPlainText("\n".join(lines))

    def _register_product_repurchase(self):
        order_id = self._table_id(self.orders_table, 8)
        if not order_id:
            return
        refunds = [r for r in self.repository.list_product_refunds(order_id)
                   if r['status'] == 'ACCREDITED']
        if not refunds:
            return
        choices = [f"Producto {r['product_index'] + 1} · {format_money(r['amount_cents'])} · "
                   f"{'Editar reparto' if r.get('repurchase') else 'Registrar recompra'}" for r in refunds]
        selection, accepted = QInputDialog.getItem(self, 'Devolución/recompra', 'Producto devuelto:', choices, 0, False)
        if not accepted:
            return
        from sgccc.gui.pdf_import import RefundRepurchaseDialog
        RefundRepurchaseDialog(self.repository, refunds[choices.index(selection)], self).exec()
        self._refresh_visible_data()

    def _confirm_pending_product_refund(self) -> None:
        order_id = self._table_id(self.orders_table, 8)
        if not order_id:
            return
        pending = [r for r in self.repository.list_product_refunds(order_id) if r['status'] == 'PENDING']
        if not pending:
            return
        choices = [f"Producto {r['product_index'] + 1} · {format_money(r['amount_cents'])} → {r['destination_name']}" for r in pending]
        selection, accepted = QInputDialog.getItem(self, 'Acreditar devolución', 'Reembolso recibido:', choices, 0, False)
        if not accepted:
            return
        refund = pending[choices.index(selection)]
        credited_at, accepted = QInputDialog.getText(self, 'Fecha real de acreditación',
            'Fecha en que se recibió el reembolso (AAAA-MM-DD):')
        if not accepted:
            return
        if QMessageBox.question(self, 'Confirmar acreditación',
            f"{selection}\nFecha: {credited_at}\nSe aplicarán el reembolso y los ajustes de participación registrados. ¿Confirmar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.repository.confirm_product_refund(refund['id'], credited_at)
        except ValueError as error:
            self._show_error(self._safe_error(error))
            return
        self._refresh_visible_data()

    def _edit_order_merchant(self) -> None:
        order_id = self._table_id(self.orders_table, 8)
        order = self.repository.get_order(order_id) if order_id else None
        if order is None or order["order_status"] != "ACTIVE":
            return
        merchant, accepted = QInputDialog.getText(
            self, "Editar comercio", "Nombre del comercio:", text=str(order["merchant"])
        )
        if not accepted:
            return
        try:
            self.repository.update_order_merchant(order_id, merchant)
        except (ValueError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        self.data_changed.emit("orders")
        self._show_information("Comercio actualizado. Los importes y el reparto se conservaron.")

    def _cancel_selected_order(self) -> None:
        rows = self.orders_table.selectionModel().selectedRows()
        if not rows:
            self._show_error("Selecciona un pedido para anularlo.")
            return
        order_id = self.orders_table.item(rows[0].row(), 8).text()
        order = self.repository.get_order(order_id)
        if order is None:
            self._show_error("El pedido no existe.")
            return
        people = {str(p["id"]): str(p["name"]) for p in self.repository.list_people()}
        names = ", ".join(
            people.get(str(item["user_id"]), str(item["user_id"]))
            for item in order["allocations"]
        )
        confirmation = QMessageBox.question(
            self,
            "Confirmar anulación",
            f"Comercio: {order['merchant']}\n"
            f"Fecha: {order['ordered_at']}\n"
            f"Cargo real: {format_money(int(order['charged_cents']))}\n"
            f"Personas: {names}\n\n¿Anular este pedido?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        try:
            self.repository.cancel_order(
                order_id, reason="Anulación confirmada desde Pedidos"
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            self._show_error(self._safe_error(error))
            return
        self.data_changed.emit("orders")
        self._show_information("Pedido anulado. Se conservaron su historial y auditoría.")

    def _build_obsolete_order_compatibility_page(self) -> QWidget:
        self.repository.ensure_demo_catalog()
        page = QWidget()
        layout = QVBoxLayout(page)
        self.orders_layout = layout
        title = QLabel("Pedidos")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        notice = QLabel(
            "MODO DEMOSTRACIÓN · Registra el importe total y distribúyelo por "
            "persona. El desglose de productos es opcional y secundario."
        )
        notice.setObjectName("demoBanner")
        layout.addWidget(notice)

        header = QGridLayout()
        header.addWidget(QLabel("Comercio"), 0, 0)
        self.purchase_merchant = QLineEdit()
        self.purchase_merchant.setPlaceholderText("Comercio ficticio")
        header.addWidget(self.purchase_merchant, 0, 1)
        header.addWidget(QLabel("Fecha"), 0, 2)
        self.purchase_date = QLineEdit(date.today().isoformat())
        header.addWidget(self.purchase_date, 0, 3)
        header.addWidget(QLabel("Institución"), 1, 0)
        self.purchase_institution = QComboBox()
        self.purchase_institution.currentIndexChanged.connect(self._refresh_instruments)
        header.addWidget(self.purchase_institution, 1, 1)
        header.addWidget(QLabel("Instrumento"), 1, 2)
        self.purchase_instrument = QComboBox()
        header.addWidget(self.purchase_instrument, 1, 3)
        layout.addLayout(header)

        order_form = QGridLayout()
        self.order_original = MxnLineEdit()
        self.order_discount = MxnLineEdit()
        self.order_charged = MxnLineEdit()
        self.order_original.setPlaceholderText("5000.00")
        self.order_discount.setPlaceholderText("0.00")
        self.order_charged.setPlaceholderText("5000.00")
        order_form.addWidget(QLabel("Importe original (MXN)"), 0, 0)
        order_form.addWidget(self.order_original, 0, 1)
        order_form.addWidget(QLabel("Descuento (MXN)"), 0, 2)
        order_form.addWidget(self.order_discount, 0, 3)
        order_form.addWidget(QLabel("Cargado a tarjeta (MXN)"), 0, 4)
        order_form.addWidget(self.order_charged, 0, 5)
        layout.addLayout(order_form)

        order_allocation_form = QGridLayout()
        self.order_user = QComboBox()
        self.order_amount = MxnLineEdit()
        self.order_amount.setPlaceholderText("0.00")
        order_allocation_form.addWidget(QLabel("Persona"), 0, 0)
        order_allocation_form.addWidget(self.order_user, 0, 1)
        order_allocation_form.addWidget(QLabel("Importe asignado (MXN)"), 0, 2)
        order_allocation_form.addWidget(self.order_amount, 0, 3)
        add_order_allocation = QPushButton("Agregar asignación")
        add_order_allocation.clicked.connect(self._add_order_allocation)
        order_allocation_form.addWidget(add_order_allocation, 0, 4)
        edit_order_allocation = QPushButton("Actualizar asignación")
        edit_order_allocation.clicked.connect(self._edit_order_allocation)
        order_allocation_form.addWidget(edit_order_allocation, 0, 5)
        delete_order_allocation = QPushButton("Eliminar asignación")
        delete_order_allocation.clicked.connect(self._delete_order_allocation)
        order_allocation_form.addWidget(delete_order_allocation, 0, 6)
        layout.addLayout(order_allocation_form)

        self.order_allocations_table = QTableWidget(0, 2)
        self.order_allocations_table.setHorizontalHeaderLabels(["Persona", "Importe"])
        self.order_allocations_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.order_allocations_table.itemSelectionChanged.connect(
            self._load_order_allocation
        )
        layout.addWidget(self.order_allocations_table)
        self.order_summary = QLabel(
            "Distribuido: $0.00 MXN · Pendiente: $0.00 MXN · "
            "Propietario: $0.00 MXN · Cuentas por cobrar: $0.00 MXN"
        )
        layout.addWidget(self.order_summary)
        save_order = QPushButton("Guardar pedido")
        save_order.clicked.connect(self._save_order)
        layout.addWidget(save_order)

        product_form = QGridLayout()
        self.product_description = QLineEdit()
        self.product_description.setPlaceholderText("Producto ficticio")
        self.product_quantity = QSpinBox()
        self.product_quantity.setRange(1, 100000)
        self.product_unit_price = MxnLineEdit()
        self.product_unit_price.setPlaceholderText("10.00")
        product_form.addWidget(QLabel("Producto"), 0, 0)
        product_form.addWidget(self.product_description, 0, 1)
        product_form.addWidget(QLabel("Unidades"), 0, 2)
        product_form.addWidget(self.product_quantity, 0, 3)
        product_form.addWidget(QLabel("Precio unitario (MXN)"), 0, 4)
        product_form.addWidget(self.product_unit_price, 0, 5)
        add_product = QPushButton("Agregar producto")
        add_product.clicked.connect(self._add_product_row)
        product_form.addWidget(add_product, 0, 6)
        edit_product = QPushButton("Actualizar producto")
        edit_product.clicked.connect(self._edit_product_row)
        product_form.addWidget(edit_product, 0, 7)
        delete_product = QPushButton("Eliminar producto")
        delete_product.clicked.connect(self._delete_product_row)
        product_form.addWidget(delete_product, 0, 8)
        layout.addLayout(product_form)

        self.products_table = QTableWidget(0, 4)
        self.products_table.setObjectName("purchaseProducts")
        self.products_table.setHorizontalHeaderLabels(
            ["ID", "Descripción", "Unidades", "Precio unitario (MXN)"]
        )
        self.products_table.setColumnHidden(0, True)
        layout.addWidget(self.products_table)

        allocation_form = QGridLayout()
        self.allocation_product = QComboBox()
        self.allocation_user = QComboBox()
        self.allocation_method = QComboBox()
        self.allocation_method.addItem("Unidades", "UNITS")
        self.allocation_method.addItem("Proporción (%)", "PERCENT")
        self.allocation_basis = QSpinBox()
        self.allocation_basis.setRange(1, 10000)
        allocation_form.addWidget(QLabel("Producto"), 0, 0)
        allocation_form.addWidget(self.allocation_product, 0, 1)
        allocation_form.addWidget(QLabel("Persona"), 0, 2)
        allocation_form.addWidget(self.allocation_user, 0, 3)
        allocation_form.addWidget(QLabel("Método"), 0, 4)
        allocation_form.addWidget(self.allocation_method, 0, 5)
        allocation_form.addWidget(QLabel("Valor"), 0, 6)
        allocation_form.addWidget(self.allocation_basis, 0, 7)
        add_allocation = QPushButton("Agregar asignación")
        add_allocation.clicked.connect(self._add_allocation_row)
        allocation_form.addWidget(add_allocation, 0, 8)
        edit_allocation = QPushButton("Actualizar asignación")
        edit_allocation.clicked.connect(self._edit_allocation_row)
        allocation_form.addWidget(edit_allocation, 0, 9)
        delete_allocation = QPushButton("Eliminar asignación")
        delete_allocation.clicked.connect(self._delete_allocation_row)
        allocation_form.addWidget(delete_allocation, 0, 10)
        layout.addLayout(allocation_form)

        self.allocations_table = QTableWidget(0, 6)
        self.allocations_table.setObjectName("purchaseAllocations")
        self.allocations_table.setHorizontalHeaderLabels(
            ["Producto", "Persona", "Método", "Valor", "Producto ID", "Persona ID"]
        )
        self.allocations_table.setColumnHidden(4, True)
        self.allocations_table.setColumnHidden(5, True)
        layout.addWidget(self.allocations_table)

        actions = QGridLayout()
        save_purchase = QPushButton("Guardar compra")
        save_purchase.clicked.connect(self._save_purchase)
        actions.addWidget(save_purchase, 0, 0)
        self.purchase_total = QLabel(
            "Total: $0.00 MXN · Propietario: $0.00 MXN · Cuentas por cobrar: $0.00 MXN"
        )
        actions.addWidget(self.purchase_total, 0, 1)
        layout.addLayout(actions)

        layout.addWidget(QLabel("Compras registradas"))
        self.purchases_table = QTableWidget(0, 4)
        self.purchases_table.setObjectName("purchasesTable")
        self.purchases_table.setHorizontalHeaderLabels(
            ["ID", "Comercio", "Total", "Parte del propietario"]
        )
        self.purchases_table.setColumnHidden(0, True)
        self.purchases_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.purchases_table.itemSelectionChanged.connect(self._show_purchase_detail)
        layout.addWidget(self.purchases_table)
        self.purchase_detail = QTextEdit()
        self.purchase_detail.setReadOnly(True)
        self.purchase_detail.setObjectName("purchaseDetail")
        layout.addWidget(self.purchase_detail)
        self._load_legacy_purchase_catalogs()
        self._refresh_purchases()
        return page

    def _load_legacy_purchase_catalogs(self) -> None:
        self.purchase_institution.clear()
        for item in self.repository.list_institutions():
            self.purchase_institution.addItem(str(item["name"]), item["id"])
        self._refresh_instruments()
        self.allocation_user.clear()
        if hasattr(self, "order_user") and self.order_user is not None:
            self.order_user.clear()
        for person in self.repository.list_people():
            if person["active"]:
                self.allocation_user.addItem(str(person["name"]), person["id"])
                if hasattr(self, "order_user") and self.order_user is not None:
                    self.order_user.addItem(str(person["name"]), person["id"])

    def _refresh_instruments(self) -> None:
        if not hasattr(self, "purchase_instrument"):
            return
        self.purchase_instrument.clear()
        institution_id = self.purchase_institution.currentData()
        for item in self.repository.list_instruments(institution_id):
            self.purchase_instrument.addItem(str(item["alias"]), item["id"])

    def _reset_order_allocations(self) -> None:
        self.order_allocations_table.setSortingEnabled(False)
        self.order_allocations_table.setRowCount(0)
        people = [
            person for person in self._order_people_catalog().values()
            if person["active"]
        ]
        people.sort(key=lambda person: (not bool(person["is_owner"]), str(person["name"]).lower()))
        for person in people:
            self._insert_order_allocation(str(person["id"]), 0)
        self._update_order_preview()

    def _enable_order_allocation_sorting(self, section: int) -> None:
        self.order_allocations_table.setSortingEnabled(True)
        self.order_allocations_table.sortItems(section)

    def _order_people_catalog(self) -> dict[str, dict[str, object]]:
        return {
            str(person["id"]): {
                **person,
                "id": str(person["id"]),
                "is_owner": bool(person["is_owner"]),
                "active": bool(person["active"]),
            }
            for person in self.repository.list_people()
        }

    def _order_catalog_issue(
        self, catalog: dict[str, dict[str, object]]
    ) -> str | None:
        active_people = [
            person for person in catalog.values() if person["active"]
        ]
        owner_ids = {
            str(person["id"]) for person in active_people if person["is_owner"]
        }
        if not owner_ids:
            return (
                "Inconsistencia de catálogo: falta configurar un propietario activo. "
                "Revisa Configuración antes de guardar."
            )
        visible_ids = {
            str(self.order_allocations_table.item(row, 0).data(Qt.ItemDataRole.UserRole))
            for row in range(self.order_allocations_table.rowCount())
            if self.order_allocations_table.item(row, 0) is not None
        }
        missing_owner_ids = owner_ids - visible_ids
        if missing_owner_ids:
            details = ", ".join(
                str(catalog[user_id]['name'])
                for user_id in sorted(missing_owner_ids)
            )
            return (
                "Inconsistencia de catálogo: el propietario persistente no está "
                f"visible en el reparto: {details}."
            )
        yo_people = [
            person for person in active_people
            if str(person["name"]).strip().casefold() == "yo"
        ]
        if yo_people and not any(person["is_owner"] for person in yo_people):
            details = ", ".join(
                str(person['name'])
                for person in yo_people
            )
            owners = ", ".join(
                str(person['name'])
                for person in active_people if person["is_owner"]
            )
            return (
                "Inconsistencia de catálogo: la persona visible como Yo no es "
                f"el propietario persistente: {details}. Propietario reconocido "
                f"por la base: {owners}."
            )
        return None

    def _insert_order_allocation(self, user_id: str, amount_cents: int) -> None:
        row = self.order_allocations_table.rowCount()
        self.order_allocations_table.insertRow(row)
        person = self.repository.get_person(user_id)
        name = str(person["name"]) if person is not None else user_id
        name_item = QTableWidgetItem(name)
        name_item.setData(Qt.ItemDataRole.UserRole, user_id)
        self.order_allocations_table.setItem(row, 0, name_item)
        self.order_allocations_table.setItem(
            row, 1, QTableWidgetItem(
                f"{Decimal(amount_cents) / Decimal('100'):.2f}"
            )
        )

    def _order_input_cents(self, widget: QLineEdit, label: str) -> int:
        text = widget.text().strip()
        if not text:
            return 0
        try:
            return self._parse_mxn_to_cents(text)
        except ValueError as error:
            raise ValueError(f"{label}: {error}") from error

    def _add_order_allocation(self) -> None:
        user_id = self.order_user.currentData()
        if user_id is None:
            self._show_error("Selecciona una persona.")
            return
        try:
            amount = self._order_input_cents(self.order_amount, "El importe asignado")
        except ValueError as error:
            self._show_error(self._safe_error(error))
            return
        for row in range(self.order_allocations_table.rowCount()):
            if self.order_allocations_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == user_id:
                self.order_allocations_table.item(row, 1).setText(
                    f"{Decimal(amount) / Decimal('100'):.2f}"
                )
                self._update_order_preview()
                return
        self._insert_order_allocation(str(user_id), amount)
        self._update_order_preview()

    def _selected_order_row(self) -> int | None:
        rows = self.order_allocations_table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def _load_order_allocation(self) -> None:
        row = self._selected_order_row()
        if row is None:
            return
        item = self.order_allocations_table.item(row, 0)
        user_id = item.data(Qt.ItemDataRole.UserRole)
        index = self.order_user.findData(user_id)
        if index >= 0:
            self.order_user.setCurrentIndex(index)
        self.order_amount.setText(
            self.order_allocations_table.item(row, 1).text().replace("$", "").replace(" MXN", "").replace(",", "")
        )

    def _edit_order_allocation(self) -> None:
        row = self._selected_order_row()
        if row is None:
            self._show_error("Selecciona una asignación para actualizarla.")
            return
        try:
            amount = self._order_input_cents(self.order_amount, "El importe asignado")
        except ValueError as error:
            self._show_error(self._safe_error(error))
            return
        self.order_allocations_table.item(row, 1).setText(format_money(amount))
        self._update_order_preview()

    def _delete_order_allocation(self) -> None:
        row = self._selected_order_row()
        if row is None:
            self._show_error("Selecciona una asignación para eliminarla.")
            return
        self.order_allocations_table.removeRow(row)
        self._update_order_preview()

    def _update_order_preview(self) -> None:
        if not hasattr(self, "order_summary"):
            return
        try:
            original = self._order_input_cents(self.order_original, "El importe original")
            charged = self._order_input_cents(self.order_charged, "El cargo real")
            allocations = self._read_order_allocations()
        except ValueError:
            self.order_summary.setText("Revisa los importes del pedido.")
            self.save_order_button.setEnabled(False)
            return
        discount = max(original - charged, 0)
        self.order_discount.setText(format_money(discount))
        self.order_exception.setText(
            "Cargo superior al original: se conserva como excepción de conciliación."
            if charged > original
            else ""
        )
        recover = original
        distributed = sum(item["amount_cents"] for item in allocations)
        catalog = self._order_people_catalog()
        catalog_issue = self._order_catalog_issue(catalog)
        owner_ids = {
            person_id for person_id, person in catalog.items()
            if person["active"] and person["is_owner"]
        }
        owner = sum(
            item["amount_cents"]
            for item in allocations
            if str(item["user_id"]) in owner_ids
        )
        receivables = distributed - owner
        summary = (
            f"Distribuido: {format_money(distributed)} · "
            f"Pendiente: {format_money(recover - distributed)} · "
            f"Propietario: {format_money(owner)} · "
            f"Cuentas por cobrar: {format_money(receivables)}"
        )
        if catalog_issue:
            summary += f"\n{catalog_issue}"
        self.order_summary.setText(summary)
        try:
            date.fromisoformat(self.order_date.text().strip())
            if self.order_purchase_mode.currentData() == "MSI" and not getattr(self, 'manual_edit_id', None):
                date.fromisoformat(self.order_first_due_date.text().strip())
                self._order_input_cents(self.order_interest, "Intereses")
            dates_valid = True
        except ValueError:
            dates_valid = False
        self.save_order_button.setEnabled(
            original > 0 and distributed == recover and catalog_issue is None
            and bool(self.order_merchant.text().strip()) and dates_valid
            and self.order_instrument.currentData() is not None
            and all(catalog.get(str(a["user_id"]), {}).get("active", False) for a in allocations)
        )

    def _read_order_allocations(self) -> tuple[dict[str, object], ...]:
        allocations: list[dict[str, object]] = []
        for row in range(self.order_allocations_table.rowCount()):
            identity_item = self.order_allocations_table.item(row, 0)
            amount_item = self.order_allocations_table.item(row, 1)
            if identity_item is None:
                continue
            user_id = identity_item.data(Qt.ItemDataRole.UserRole)
            if user_id is None:
                raise ValueError("La fila de una persona no tiene un identificador válido.")
            amount_text = amount_item.text() if amount_item is not None else "0.00"
            allocations.append(
                {
                    "user_id": str(user_id),
                    "amount_cents": self._parse_mxn_to_cents(
                        amount_text.replace("$", "").replace(" MXN", "").replace(",", "")
                    ),
                }
            )
        return tuple(allocations)

    def _save_order(self) -> None:
        if getattr(self, '_order_save_in_progress', False):
            return
        self._order_save_in_progress = True
        self.save_order_button.setEnabled(False)
        try:
            if self.manual_dialog.isVisible() and not self.manual_concepts.rowCount():
                raise ValueError('Agrega al menos un concepto antes de guardar el gasto.')
            if getattr(self, 'manual_edit_id', None):
                self.repository.update_manual_concepts(self.manual_edit_id, self._read_manual_concepts(),
                    expected_concepts=self.manual_expected_concepts)
                self.data_changed.emit('orders')
                self.manual_dialog.accept()
                self._clear_order_form()
                return
            original = self._order_input_cents(self.order_original, "El importe original")
            charged = self._order_input_cents(self.order_charged, "El cargado a tarjeta")
            discount = max(original - charged, 0)
            allocations = self._read_order_allocations()
            catalog_issue = self._order_catalog_issue(self._order_people_catalog())
            if catalog_issue:
                raise ValueError(catalog_issue)
            purchase_mode = str(self.order_purchase_mode.currentData())
            financing_specs: tuple[str | None, ...] | None = None
            interest_cents = 0
            if purchase_mode == "MSI":
                first_due = self.order_first_due_date.text().strip()
                try:
                    first_date = date.fromisoformat(first_due)
                except ValueError as error:
                    raise ValueError(
                        "La primera cuota requiere una fecha válida AAAA-MM-DD."
                    ) from error
                interest_cents = self._order_input_cents(
                    self.order_interest, "Los intereses del plan"
                )
                dates = []
                for offset in range(self.order_installments.value()):
                    month_index = first_date.month - 1 + offset
                    year = first_date.year + month_index // 12
                    month = month_index % 12 + 1
                    day = min(first_date.day, monthrange(year, month)[1])
                    dates.append(date(year, month, day).isoformat())
                financing_specs = tuple(dates)
            merchant_widget = getattr(self, "order_merchant", self.purchase_merchant)
            date_widget = getattr(self, "order_date", self.purchase_date)
            instrument_widget = getattr(
                self, "order_instrument", self.purchase_instrument
            )
            self.repository.create_order(
                order_id=str(uuid4()),
                ordered_at=date_widget.text().strip(),
                merchant=merchant_widget.text().strip()
                or getattr(self, "purchase_merchant", QLineEdit()).text().strip(),
                instrument_id=str(instrument_widget.currentData()),
                original_cents=original,
                discount_cents=discount,
                charged_cents=charged,
                allocations=allocations,
                purchase_mode=purchase_mode,
                financing_specs=financing_specs,
                interest_cents=interest_cents,
                concepts=self._read_manual_concepts() if self.manual_concepts.rowCount() else None,
            )
        except (ValueError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        finally:
            self._order_save_in_progress = False
            self._update_order_preview()
        self.data_changed.emit("orders")
        self._show_information("Pedido guardado correctamente.")
        self.manual_dialog.accept()
        self._clear_order_form()

    def _clear_order_form(self) -> None:
        self.manual_edit_id = None
        self.manual_expected_concepts = None
        with QSignalBlocker(self.manual_concepts):
            self.manual_concepts.setRowCount(0)
        self.order_original.setReadOnly(False)
        self.order_allocations_table.show()
        self.order_allocation_label.show()
        for widget in (self.order_merchant, self.order_date, self.order_institution, self.order_instrument,
                       self.order_charged, self.order_purchase_mode, self.order_installments,
                       self.order_first_due_date, self.order_interest):
            widget.setEnabled(True)
        self.order_original.clear()
        self.order_charged.clear()
        self.order_discount.setText("$0.00 MXN")
        self.order_exception.clear()
        self._reset_order_allocations()
        self.order_purchase_mode.setCurrentIndex(0)
        self.order_first_due_date.clear()
        self.order_interest.clear()

    def _toggle_msi_fields(self) -> None:
        if not hasattr(self, "order_purchase_mode"):
            return
        visible = self.order_purchase_mode.currentData() == "MSI"
        for widget in (
            self.order_installments,
            self.order_first_due_date,
            self.order_interest,
        ):
            widget.setEnabled(visible)
            widget.setVisible(visible)
        for label in getattr(self, "order_msi_labels", ()):
            label.setVisible(visible)
        self._update_order_preview()

    def _refresh_orders(self) -> None:
        if not hasattr(self, "orders_table"):
            return
        selected_id = self._table_id(self.orders_table, 8)
        blocker = QSignalBlocker(self.orders_table)
        self.orders_table.setRowCount(0)
        participations = {}
        for item in self.repository.list_collection_items():
            amounts = participations.setdefault(item['order_id'], [0, 0])
            if item['participant_role'] == 'PERSONAL':
                amounts[0] += int(item['sale_cents'])
            elif item['participant_role'] == 'FAMILY':
                amounts[1] += int(item['sale_cents'])
        status = (
            str(self.order_filter.currentData())
            if hasattr(self, "order_filter") else "ACTIVE"
        )
        for order in self.repository.list_orders(status):
            row = self.orders_table.rowCount()
            self.orders_table.insertRow(row)
            current = participations.get(order['id'], [order['owner_cents'],
                order['total_to_recover_cents'] - order['owner_cents']]) if order['order_status'] == 'ACTIVE' else [0, 0]
            values = (
                order["merchant"],
                order["ordered_at"],
                format_money(order["original_cents"]),
                format_money(order["charged_cents"]),
                format_money(order["discount_cents"]),
                format_money(current[0]),
                format_money(current[1]),
                "Anulado" if order["order_status"] == "CANCELLED" else "Activo",
                order["id"],
            )
            for column, value in enumerate(values):
                self.orders_table.setItem(row, column, QTableWidgetItem(str(value)))
            if str(order["id"]) == selected_id:
                self.orders_table.selectRow(row)
        blocker.unblock()
        self._show_order_detail()

    def _add_product_row(self) -> None:
        description = self.product_description.text().strip()
        if not description:
            self._show_error("El producto requiere descripción.")
            return
        try:
            unit_price_cents = self._parse_mxn_to_cents(self.product_unit_price.text())
        except ValueError as error:
            self._show_error(self._safe_error(error))
            return
        row = self.products_table.rowCount()
        product_id = str(uuid4())
        self.products_table.insertRow(row)
        values = (product_id, description, self.product_quantity.value(),
                  format_money(unit_price_cents))
        for column, value in enumerate(values):
            self.products_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.allocation_product.addItem(description, product_id)
        self.product_description.clear()
        self._update_purchase_preview()

    @staticmethod
    def _parse_mxn_to_cents(value: str) -> int:
        text = value.strip()
        if not text:
            raise ValueError("El precio unitario es obligatorio.")
        try:
            amount = Decimal(text.replace(",", ""))
        except InvalidOperation as error:
            raise ValueError("Usa un precio MXN válido, por ejemplo 10.00.") from error
        if not amount.is_finite() or amount < 0:
            raise ValueError("El precio unitario no puede ser negativo.")
        if amount.as_tuple().exponent < -2:
            raise ValueError("El precio unitario solo admite hasta dos decimales.")
        return int((amount * Decimal("100")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        ))

    @staticmethod
    def _selected_row(table: QTableWidget) -> int | None:
        rows = table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def _edit_product_row(self) -> None:
        row = self._selected_row(self.products_table)
        if row is None:
            self._show_error("Selecciona un producto para actualizarlo.")
            return
        description = self.product_description.text().strip()
        if not description:
            self._show_error("El producto requiere descripción.")
            return
        try:
            unit_price_cents = self._parse_mxn_to_cents(self.product_unit_price.text())
        except ValueError as error:
            self._show_error(self._safe_error(error))
            return
        product_id = self.products_table.item(row, 0).text()
        self.products_table.item(row, 1).setText(description)
        self.products_table.item(row, 2).setText(str(self.product_quantity.value()))
        self.products_table.item(row, 3).setText(format_money(unit_price_cents))
        for index in range(self.allocation_product.count()):
            if self.allocation_product.itemData(index) == product_id:
                self.allocation_product.setItemText(index, description)
        self._update_purchase_preview()

    def _delete_product_row(self) -> None:
        row = self._selected_row(self.products_table)
        if row is None:
            self._show_error("Selecciona un producto para eliminarlo.")
            return
        product_id = self.products_table.item(row, 0).text()
        if any(
            self.allocations_table.item(index, 4).text() == product_id
            for index in range(self.allocations_table.rowCount())
        ):
            self._show_error(
                "No puedes eliminar un producto con asignaciones. "
                "Elimina primero sus asignaciones."
            )
            return
        self.products_table.removeRow(row)
        for index in range(self.allocation_product.count() - 1, -1, -1):
            if self.allocation_product.itemData(index) == product_id:
                self.allocation_product.removeItem(index)
        for index in range(self.allocations_table.rowCount() - 1, -1, -1):
            if self.allocations_table.item(index, 4).text() == product_id:
                self.allocations_table.removeRow(index)
        self._update_purchase_preview()

    def _product_price_cents(self, row: int) -> int:
        return self._parse_mxn_to_cents(
            self.products_table.item(row, 3).text()
            .replace("$", "").replace(" MXN", "").replace(",", "")
        )

    def _add_allocation_row(self) -> None:
        if self.allocation_product.count() == 0 or self.allocation_user.count() == 0:
            self._show_error("Agrega un producto y una persona activa antes de asignar.")
            return
        row = self.allocations_table.rowCount()
        product_id = str(self.allocation_product.currentData())
        product_name = self.allocation_product.currentText()
        user_id = str(self.allocation_user.currentData())
        user_name = self.allocation_user.currentText()
        method = str(self.allocation_method.currentData())
        value = self.allocation_basis.value()
        method_label = self.allocation_method.currentText()
        duplicates = any(
            self.allocations_table.item(index, 4).text() == product_id
            and self.allocations_table.item(index, 5).text() == user_id
            for index in range(self.allocations_table.rowCount())
        )
        if duplicates:
            self._show_error(
                "Esa persona ya está asignada a este producto. "
                "Selecciona la fila y pulsa Actualizar asignación."
            )
            return
        product_row = next(
            index for index in range(self.products_table.rowCount())
            if self.products_table.item(index, 0).text() == product_id
        )
        limit = int(self.products_table.item(product_row, 2).text()) if method == "UNITS" else 10000
        assigned = sum(
            int(self.allocations_table.item(index, 3).text())
            for index in range(self.allocations_table.rowCount())
            if self.allocations_table.item(index, 4).text() == product_id
        )
        if assigned + value > limit:
            self._show_error(f"Exceso de asignación. Solo faltan {limit - assigned}.")
            return
        values = (product_name, user_name, method_label, value, product_id, user_id)
        self.allocations_table.insertRow(row)
        for column, item in enumerate(values):
            self.allocations_table.setItem(row, column, QTableWidgetItem(str(item)))
        self._update_purchase_preview()

    def _edit_allocation_row(self) -> None:
        row = self._selected_row(self.allocations_table)
        if row is None:
            self._show_error("Selecciona una asignación para actualizarla.")
            return
        product_id = self.allocations_table.item(row, 4).text()
        method = str(self.allocation_method.currentData())
        value = self.allocation_basis.value()
        product_row = next(
            index for index in range(self.products_table.rowCount())
            if self.products_table.item(index, 0).text() == product_id
        )
        limit = int(self.products_table.item(product_row, 2).text()) if method == "UNITS" else 10000
        assigned_other = sum(
            int(self.allocations_table.item(index, 3).text())
            for index in range(self.allocations_table.rowCount())
            if index != row and self.allocations_table.item(index, 4).text() == product_id
        )
        if assigned_other + value > limit:
            self._show_error(f"Exceso de asignación. Solo faltan {limit - assigned_other}.")
            return
        self.allocations_table.item(row, 2).setText(self.allocation_method.currentText())
        self.allocations_table.item(row, 3).setText(str(value))
        self._update_purchase_preview()

    def _delete_allocation_row(self) -> None:
        row = self._selected_row(self.allocations_table)
        if row is None:
            self._show_error("Selecciona una asignación para eliminarla.")
            return
        self.allocations_table.removeRow(row)
        self._update_purchase_preview()

    def _update_purchase_preview(self) -> None:
        total = sum(
            int(self.products_table.item(row, 2).text())
            * self._product_price_cents(row)
            for row in range(self.products_table.rowCount())
        )
        owner_ids = {
            str(person["id"]) for person in self.repository.list_people() if person["is_owner"]
        }
        owner = 0
        receivables = 0
        missing_labels: list[str] = []
        for row in range(self.allocations_table.rowCount()):
            product_id = self.allocations_table.item(row, 4).text()
            product_row = next(
                index for index in range(self.products_table.rowCount())
                if self.products_table.item(index, 0).text() == product_id
            )
            quantity = int(self.products_table.item(product_row, 2).text())
            unit_price = self._product_price_cents(product_row)
            basis = int(self.allocations_table.item(row, 3).text())
            method = self.allocations_table.item(row, 2).text()
            share = (
                unit_price * basis
                if method == "Unidades"
                else int(
                    (Decimal(unit_price * quantity) * Decimal(basis) / Decimal(10000))
                    .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                )
            )
            if self.allocations_table.item(row, 5).text() in owner_ids:
                owner += share
            else:
                receivables += share
        for product_row in range(self.products_table.rowCount()):
            product_id = self.products_table.item(product_row, 0).text()
            product_quantity = int(self.products_table.item(product_row, 2).text())
            product_rows = [
                index for index in range(self.allocations_table.rowCount())
                if self.allocations_table.item(index, 4).text() == product_id
            ]
            if not product_rows:
                missing_labels.append(f"{product_quantity} unidades")
                continue
            method = self.allocations_table.item(product_rows[0], 2).text()
            assigned = sum(
                int(self.allocations_table.item(index, 3).text())
                for index in product_rows
            )
            limit = product_quantity if method == "Unidades" else 10000
            if assigned < limit:
                missing_labels.append(
                    f"{limit - assigned} {'unidades' if method == 'Unidades' else 'puntos porcentuales'}"
                )
        missing = ", ".join(missing_labels) if missing_labels else "0"
        self.purchase_total.setText(
            f"Total: {format_money(total)} · Propietario: {format_money(owner)} · "
            f"Cuentas por cobrar: {format_money(receivables)} · Por asignar: {missing}"
        )

    def _save_purchase(self) -> None:
        try:
            products = tuple(
                {
                    "id": self.products_table.item(row, 0).text(),
                    "description": self.products_table.item(row, 1).text(),
                    "quantity": int(self.products_table.item(row, 2).text()),
                    "unit_price_cents": self._product_price_cents(row),
                }
                for row in range(self.products_table.rowCount())
            )
            allocations = tuple(
                {
                    "product_id": self.allocations_table.item(row, 4).text(),
                    "user_id": self.allocations_table.item(row, 5).text(),
                    "method": (
                        "UNITS"
                        if self.allocations_table.item(row, 2).text() == "Unidades"
                        else "PERCENT"
                    ),
                    "basis": int(self.allocations_table.item(row, 3).text()),
                }
                for row in range(self.allocations_table.rowCount())
            )
            self.repository.create_purchase(
                purchase_id=str(uuid4()),
                purchased_at=self.purchase_date.text().strip(),
                merchant=self.purchase_merchant.text(),
                instrument_id=str(self.purchase_instrument.currentData()),
                products=products,
                allocations=allocations,
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            self._show_error(self._safe_error(error))
            return
        self.data_changed.emit("orders")
        self._show_information("Compra guardada correctamente.")
        self._refresh_purchases()
        self._clear_purchase_form()

    def _refresh_purchases(self) -> None:
        if not hasattr(self, "purchases_table"):
            return
        self.purchases_table.setRowCount(0)
        for purchase in self.repository.list_purchases():
            row = self.purchases_table.rowCount()
            self.purchases_table.insertRow(row)
            for column, value in enumerate(
                (purchase["id"], purchase["merchant"], format_money(purchase["total_cents"]),
                 format_money(purchase["owner_cents"]))
            ):
                self.purchases_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.purchases_table.resizeColumnsToContents()
        if self.purchases_table.rowCount():
            self.purchases_table.selectRow(0)

    def _show_purchase_detail(self) -> None:
        rows = self.purchases_table.selectionModel().selectedRows()
        if not rows:
            return
        purchase_id = self.purchases_table.item(rows[0].row(), 0).text()
        purchase = self.repository.get_purchase(purchase_id)
        if purchase is None:
            return
        lines = [
            f"{purchase['merchant']} · Total {format_money(purchase['total_cents'])}",
            f"Propietario: {format_money(purchase['owner_cents'])}",
        ]
        for product in purchase["products"]:
            lines.append(
                f"- {product['description']}: {product['quantity']} x "
                f"{format_money(product['unit_price_cents'])}"
            )
            for allocation in product["allocations"]:
                lines.append(
                    f"  · {allocation['user_id']}: {format_money(allocation['share_cents'])}"
                )
        lines.append("Cuentas por cobrar:")
        lines.extend(
            f"- {row['user_id']}: {format_money(row['sale_cents'])}"
            for row in purchase["receivables"]
        )
        self.purchase_detail.setPlainText("\n".join(lines))

    def _clear_purchase_form(self) -> None:
        self.purchase_merchant.clear()
        self.product_description.clear()
        self.product_unit_price.clear()
        self.products_table.setRowCount(0)
        self.allocations_table.setRowCount(0)
        self.allocation_product.clear()
        self._update_purchase_preview()

    def _refresh_people(self, selected_id: str | None = None) -> None:
        if self.repository is None:
            return
        selected_id = selected_id or self._selected_person_id()
        blocker = QSignalBlocker(self.people_table)
        people = self.repository.list_people()
        self.people_table.setRowCount(0)
        for person in people:
            row = self.people_table.rowCount()
            self.people_table.insertRow(row)
            self.people_table.setItem(row, 0, QTableWidgetItem(str(person["id"])))
            self.people_table.setItem(row, 1, QTableWidgetItem(str(person["name"])))
            owner = "Sí" if person["is_owner"] else "No"
            self.people_table.setItem(row, 2, QTableWidgetItem(owner))
            self.people_table.setItem(row, 3, QTableWidgetItem(
                "Activo" if person["active"] else "Desactivado"
            ))
            if selected_id == person["id"]:
                self.people_table.selectRow(row)
        blocker.unblock()
        self.people_table.resizeColumnsToContents()

    def _selected_person_id(self) -> str | None:
        rows = self.people_table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.people_table.item(rows[0].row(), 0).text()

    def _load_selected_person(self) -> None:
        person_id = self._selected_person_id()
        if person_id is None or self.repository is None:
            return
        person = self.repository.get_person(person_id)
        if person is not None:
            self.person_name.setText(str(person["name"]))
            self.person_owner.setChecked(bool(person["is_owner"]))

    def _create_person(self) -> None:
        if self.repository is None:
            return
        try:
            self.repository.create_person(
                self.person_name.text(),
                is_owner=self.person_owner.isChecked(),
                actor="desktop",
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            self._show_error(self._person_error(error))
            return
        self._refresh_people()
        self._clear_person_form()
        self.data_changed.emit("users")
        self._show_information("Persona creada correctamente.")

    def _update_person(self) -> None:
        person_id = self._selected_person_id()
        if person_id is None or self.repository is None:
            self._show_error("Selecciona una persona para editar.")
            return
        try:
            self.repository.update_person(
                person_id,
                self.person_name.text(),
                is_owner=self.person_owner.isChecked(),
                actor="desktop",
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            self._show_error(self._person_error(error))
            return
        self._refresh_people(person_id)
        self.data_changed.emit("users")
        self._show_information("Persona actualizada correctamente.")

    def _deactivate_person(self) -> None:
        person_id = self._selected_person_id()
        if person_id is None or self.repository is None:
            self._show_error("Selecciona una persona para desactivar.")
            return
        answer = QMessageBox.question(
            self,
            "Confirmar desactivación",
            "¿Desactivar la persona seleccionada? El historial se conservará.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.repository.deactivate_person(person_id, actor="desktop")
        except ValueError as error:
            self._show_error(self._safe_error(error))
            return
        self._refresh_people(person_id)
        self.data_changed.emit("users")
        self._show_information("Persona desactivada. El registro histórico se conserva.")

    def _reactivate_person(self) -> None:
        person_id = self._selected_person_id()
        if person_id is None or self.repository is None:
            self._show_error("Selecciona una persona para reactivar.")
            return
        try:
            self.repository.reactivate_person(person_id, actor="desktop")
        except ValueError as error:
            self._show_error(self._safe_error(error))
            return
        self._refresh_people(person_id)
        self.data_changed.emit("users")
        self._show_information("Persona reactivada. El historial se conservó.")

    def _clear_person_form(self) -> None:
        self.people_table.clearSelection()
        self.person_name.clear()
        self.person_owner.setChecked(False)

    @staticmethod
    def _person_error(error: Exception) -> str:
        if "uq_person_normalized_name" in str(error) or "UNIQUE constraint" in str(error):
            return "Ya existe una persona con ese nombre."
        return str(error)

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "No se pudo completar la operación", message)

    @staticmethod
    def _safe_error(error):
        if isinstance(error, DATABASE_ERRORS):
            return 'No se pudo completar la operación de almacenamiento. Conserva la captura, revisa el diagnóstico y vuelve a intentarlo.'
        return str(error)

    def _show_information(self, message: str) -> None:
        self.statusBar().showMessage(message, 10000)

    def _make_dashboard(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        title = QLabel("Panel inicial")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        banner = QLabel(
            "MODO DEMOSTRACIÓN · Los importes son sintéticos y no se guardan."
            if self.repository is None else
            "Operaciones de la base activa. La deuda registrada no sustituye "
            "el saldo confirmado por el banco. Mi parte, Cobros familiares y "
            "pagos a tarjetas se mantienen separados."
        )
        banner.setWordWrap(True)
        banner.setObjectName("demoBanner")
        layout.addWidget(banner)

        cards = QGridLayout()
        self.dashboard_personal = self._make_card("Mi parte pendiente", "")
        self.dashboard_receivables = self._make_card("Cobros familiares pendientes", "")
        self.dashboard_debt = self._make_card("Deuda registrada en tarjetas", "")
        self.dashboard_discount = self._make_card("Beneficio acumulado por descuentos", "")
        cards.addWidget(self.dashboard_personal, 0, 0)
        cards.addWidget(self.dashboard_receivables, 0, 1)
        cards.addWidget(self.dashboard_debt, 1, 0)
        cards.addWidget(self.dashboard_discount, 1, 1)
        layout.addLayout(cards)
        self.dashboard_discount.setToolTip("Ahorro personal de pedidos activos; ya incluido en sus cargos. No es dinero cobrado.")
        self.dashboard_credit = QLabel()
        layout.addWidget(self.dashboard_credit)
        self.dashboard_unclassified = QLabel()
        layout.addWidget(self.dashboard_unclassified)
        self.dashboard_net_pending = QLabel()
        self.dashboard_expected = QLabel()
        self.dashboard_received = QLabel()
        expected_row = QHBoxLayout()
        for label in (self.dashboard_net_pending, self.dashboard_expected, self.dashboard_received):
            label.setWordWrap(True)
            if label is self.dashboard_expected:
                expected_row.addWidget(label, 1)
                layout.addLayout(expected_row)
            else:
                layout.addWidget(label)
        self.dashboard_expected.setToolTip('Resultado de pedidos activos antes de abonos personales. Incluye cada recompra vinculada una vez; excluye intereses y comisiones. No es dinero cobrado.')
        self.dashboard_result_toggle = QPushButton('Ver cálculo')
        self.dashboard_result_toggle.setToolTip('Desglose del resultado previsto: si se cobra todo a familiares, antes de abonos personales.')
        self.dashboard_result_toggle.setCheckable(True)
        self.dashboard_result_toggle.setEnabled(self.repository is not None)
        self.dashboard_result_toggle.toggled.connect(self._show_result_breakdown)
        expected_row.addWidget(self.dashboard_result_toggle)
        self.dashboard_result_details = QTextEdit()
        self.dashboard_result_details.setReadOnly(True)
        self.dashboard_result_details.setMinimumHeight(120)
        self.dashboard_result_details.setMaximumHeight(200)
        self.dashboard_result_details.hide()
        layout.addWidget(self.dashboard_result_details)
        self.dashboard_received.setToolTip('Dinero registrado como abonos familiares activos, contado una vez por abono. Aportaciones personales y reembolsos son conceptos distintos.')
        layout.addWidget(QLabel('Deudas por tarjeta · diferencia = banco − Valenza'))
        self.dashboard_cards = QTableWidget(0, 5)
        self.dashboard_cards.setHorizontalHeaderLabels(['Tarjeta / institución', 'Valenza', 'Banco', 'Consultado', 'Diferencia'])
        self.dashboard_cards.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.dashboard_cards.verticalHeader().hide()
        self.dashboard_cards.verticalHeader().setDefaultSectionSize(26)
        self.dashboard_cards.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.dashboard_cards.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.dashboard_cards.setMinimumHeight(85)
        self.dashboard_cards.setMaximumHeight(140)
        layout.addWidget(self.dashboard_cards)
        self.dashboard_cards_total = QLabel()
        self.dashboard_cards_total.setWordWrap(True)
        layout.addWidget(self.dashboard_cards_total)

        layout.addWidget(QLabel("Movimientos recientes"))
        self.dashboard_movements = QListWidget()
        self.dashboard_movements.setObjectName("recentMovements")
        self.dashboard_movements.setMinimumHeight(80)
        self.dashboard_movements.setMaximumHeight(140)
        layout.addWidget(self.dashboard_movements, 1)
        self._refresh_dashboard()
        return page

    def _refresh_dashboard(self) -> None:
        if not hasattr(self, "dashboard_movements"):
            return
        self.dashboard_movements.clear()
        self.dashboard_cards.setRowCount(0)
        if self.repository is None:
            personal = 0
            discount = 0
            net_pending = 0
            expected = 0
            received = 0
            receivables = self.demo_data.receivables_cents
            debt = self.demo_data.institutional_balance_cents
            self.dashboard_credit.clear()
            self.dashboard_unclassified.clear()
            for reference, description, cents in self.demo_data.recent_movements:
                self.dashboard_movements.addItem(
                    f"{reference} · {description} · {format_money(cents)}"
                )
        else:
            summary = self.repository.dashboard_summary()
            net_pending = int(summary['personal_pending_less_discounts_cents'])
            expected = int(summary['personal_expected_result_cents'])
            received = int(summary['family_received_cents'])
            for comparison in summary['bank_comparisons']:
                row = self.dashboard_cards.rowCount()
                self.dashboard_cards.insertRow(row)
                values = [f"{comparison['alias']} · {comparison['institution_name']}",
                          format_money(comparison['calculated_cents']),
                          format_money(comparison['reported_cents']) if comparison['reported_cents'] is not None else 'Sin consultar',
                          comparison['consulted_at'] or 'Sin consultar',
                          format_money(comparison['difference_cents']) if comparison['difference_cents'] is not None else 'Sin consultar']
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    self.dashboard_cards.setItem(row, column, item)
            discount = int(summary['discount_benefit_cents'])
            personal = int(summary["personal_pending_cents"])
            receivables = int(summary["receivables_cents"])
            debt = int(summary["institutional_balance_cents"])
            credit = int(summary["credit_cents"])
            self.dashboard_credit.setText(
                f"Saldo a favor registrado: {format_money(credit)}" if credit else ""
            )
            unknown = int(summary["unclassified_pending_cents"])
            self.dashboard_unclassified.setText(
                f"Participaciones históricas por revisar: {format_money(unknown)}" if unknown else ""
            )
            for item in summary["recent_movements"]:
                state = " · Anulado" if item["status"] == "CANCELLED" else ""
                self.dashboard_movements.addItem(
                    f"{str(item['occurred_at'])[:10]} · {item['kind']} · "
                    f"{item['description']} · {format_money(int(item['amount_cents']))}{state}"
                )
            if not summary["recent_movements"]:
                self.dashboard_movements.addItem("Todavía no hay movimientos registrados.")
        self.dashboard_receivables.findChild(QLabel, "summaryAmount").setText(format_money(receivables))
        self.dashboard_personal.findChild(QLabel, "summaryAmount").setText(format_money(personal))
        self.dashboard_debt.findChild(QLabel, "summaryAmount").setText(format_money(debt))
        self.dashboard_discount.findChild(QLabel, 'summaryAmount').setText(format_money(discount))
        self.dashboard_net_pending.setText(f'Mi parte pendiente menos descuentos: {format_money(net_pending)} · comparación, sin modificar deudas.')
        self.dashboard_expected.setText(f"Resultado personal previsto {'a favor' if expected >= 0 else 'a mi cargo'}: {format_money(abs(expected))} · antes de abonos personales.")
        self.dashboard_cards.setFixedHeight(min(140, max(85, self.dashboard_cards.horizontalHeader().height() + self.dashboard_cards.rowCount() * 26 + 4)))
        self.dashboard_received.setText(f'Abonos familiares realmente recibidos: {format_money(received)} · descuentos = ahorro; resultado previsto ≠ dinero cobrado.')
        self.dashboard_cards_total.setText(f'Total de deuda calculada: {format_money(debt)} · las consultas bancarias no ajustan los saldos.')
        self.dashboard_credit.setVisible(bool(self.dashboard_credit.text()))
        self.dashboard_unclassified.setVisible(bool(self.dashboard_unclassified.text()))
        if self.dashboard_result_toggle.isChecked():
            self._show_result_breakdown(True)

    @staticmethod
    def _make_card(label: str, value: str) -> QFrame:
        card = QFrame()
        card.setObjectName("summaryCard")
        layout = QVBoxLayout(card)
        caption = QLabel(label)
        caption.setWordWrap(True)
        amount = QLabel(value)
        amount.setObjectName("summaryAmount")
        layout.addWidget(caption)
        layout.addWidget(amount)
        return card

    def _show_page(self, index: int) -> None:
        if 0 <= index < self.pages.count():
            self.pages.setCurrentIndex(index)
            self._refresh_visible_data("navigation")

    def _refresh_visible_data(self, _domain: str = "all") -> None:
        if self.repository is None or not hasattr(self, "pages"):
            return
        page_name = self.PAGES[self.pages.currentIndex()]
        scroll_positions = [(bar, bar.value()) for table in self.findChildren(QTableWidget) for bar in (table.verticalScrollBar(), table.horizontalScrollBar())]
        if _domain != "navigation" or page_name in {"Pedidos", "Tarjetas"}:
            self._sync_catalogs()
        refreshers = {
            "Inicio": self._refresh_dashboard,
            "Usuarios": self._refresh_people,
            "Pedidos": self._refresh_orders,
            "Cobros": self._refresh_collections,
            "Tarjetas": self._refresh_cards,
            "Configuración": self._refresh_owner_people,
        }
        for name, refresher in refreshers.items():
            if _domain != "navigation" or name == page_name:
                refresher()
        self._update_action_states()

        self._fit_money_columns()
        for bar, value in scroll_positions:
            bar.setValue(value)
        for table, column in ((self.cards_table, 0), (self.collection_items, 2)):
            for row in range(table.rowCount()):
                item = table.item(row, column)
                if item:
                    item.setToolTip('<p>' + escape(item.text()) + '</p>')

    @staticmethod
    def _table_id(table: QTableWidget, column: int) -> str | None:
        rows = table.selectionModel().selectedRows()
        item = table.item(rows[0].row(), column) if rows else None
        return item.text() if item is not None else None

    @staticmethod
    def _fill_combo(combo: QComboBox, choices: list[tuple[str, object]]) -> None:
        selected = combo.currentData()
        with QSignalBlocker(combo):
            combo.clear()
            for label, value in choices:
                combo.addItem(label, value)
            index = combo.findData(selected)
            if index >= 0:
                combo.setCurrentIndex(index)

    def _sync_catalogs(self) -> None:
        institutions = [(str(i["name"]), i["id"]) for i in self.repository.list_institutions()]
        by_instrument = {i['id']: i for i in self.repository.list_all_instruments()}
        for prefix in ("order", "card"):
            selected_instrument = getattr(self, f'{prefix}_instrument').currentData()
            selected_institution = getattr(self, f'{prefix}_institution').currentData()
            if selected_instrument in by_instrument:
                selected_institution = by_instrument[selected_instrument]['institution_id']
            self._fill_combo(getattr(self, f"{prefix}_institution"), institutions)
            with QSignalBlocker(getattr(self, f'{prefix}_institution')):
                index = getattr(self, f'{prefix}_institution').findData(selected_institution)
                if index >= 0:
                    getattr(self, f'{prefix}_institution').setCurrentIndex(index)
            if prefix == 'order' and selected_institution is not None:
                combo = self.order_institution
                if combo.findData(selected_institution) < 0:
                    combo.addItem('Institución anterior (revisar disponibilidad)', selected_institution)
                combo.setCurrentIndex(combo.findData(selected_institution))
            institution_id = getattr(self, f"{prefix}_institution").currentData()
            instruments = self.repository.list_instruments(institution_id) if institution_id else []
            self._fill_combo(getattr(self, f"{prefix}_instrument"),
                             [(str(i["alias"]), i["id"]) for i in instruments])
            combo = getattr(self, f'{prefix}_instrument')
            if prefix == 'order' and selected_instrument is not None:
                if combo.findData(selected_instrument) < 0:
                    combo.addItem('Instrumento anterior (revisar disponibilidad)', selected_instrument)
                combo.setCurrentIndex(combo.findData(selected_instrument))
        self._fill_combo(self.admin_institution, [
            (f"{i['name']} ({'activa' if i['active'] else 'inactiva'})", i["id"])
            for i in self.repository.list_all_institutions()
        ])
        self._fill_combo(self.admin_card_institution, [(str(i['name']), i['id']) for i in self.repository.list_all_institutions()])
        people = self._order_people_catalog()
        for row in range(self.manual_concepts.rowCount()):
            self.manual_concepts.cellWidget(row, 2).refresh_people(list(people.values()))
        self._fill_combo(self.order_user, [(str(p["name"]), p["id"])
                                          for p in people.values() if p["active"]])
        amounts = {
            str(self.order_allocations_table.item(row, 0).data(Qt.ItemDataRole.UserRole)):
                self.order_allocations_table.item(row, 1).text()
            for row in range(self.order_allocations_table.rowCount())
        }
        visible = [p for p in people.values() if p["active"] or amounts.get(p["id"], "0.00") != "0.00"]
        visible.sort(key=lambda p: (not p["is_owner"], str(p["name"]).lower()))
        with QSignalBlocker(self.order_allocations_table):
            self.order_allocations_table.setSortingEnabled(False)
            self.order_allocations_table.setRowCount(0)
            for person in visible:
                self._insert_order_allocation(person["id"], 0)
                row = self.order_allocations_table.rowCount() - 1
                self.order_allocations_table.item(row, 1).setText(amounts.get(person["id"], "0.00"))
        self._update_order_preview()
        if self.manual_concepts.rowCount():
            self._update_manual_concepts()

    def _update_action_states(self, *_args) -> None:
        if self.repository is None or not hasattr(self, "configure_owner_button"):
            return
        receipt = self._selected_receipt_history()
        receipt_active = receipt is not None and receipt["payment_status"] == "ACTIVE"
        self.edit_receipt_button.setEnabled(receipt_active)
        self.cancel_receipt_button.setEnabled(receipt_active)
        payment = self._selected_card_payment()
        payment_active = payment is not None and payment["payment_status"] == "ACTIVE"
        self.edit_payment_button.setEnabled(payment_active)
        self.cancel_payment_button.setEnabled(payment_active)
        receivable_id = self._table_id(self.collection_items, 7)
        self.family_pdf_button.setEnabled(receivable_id is not None)
        account = next((i for i in self.repository.list_collection_items()
                        if i["receivable_id"] == receivable_id), None)
        try:
            amount = self._parse_mxn_to_cents(self.collection_amount.text())
        except ValueError:
            amount = 0
        self.record_collection_button.setEnabled(
            account is not None and 0 < amount <= int(account["remaining_cents"])
            and not self._collection_receipt_in_progress
        )
        try:
            apply_amount = self._parse_mxn_to_cents(self.card_apply_amount.text())
        except ValueError:
            apply_amount = 0
        self.apply_card_button.setEnabled(
            self.card_apply_payment.currentData() is not None
            and self.card_apply_installment.currentData() is not None
            and 0 < apply_amount <= min(
                int(self.card_apply_payment.currentData(Qt.ItemDataRole.UserRole + 1) or 0),
                int(self.card_apply_installment.currentData(Qt.ItemDataRole.UserRole + 1) or 0),
            )
        )
        order_id = self._table_id(self.orders_table, 8)
        order = self.repository.get_order(order_id) if order_id else None
        cancellable = order is not None and order["order_status"] == "ACTIVE"
        if cancellable:
            has_receipts = any(i["source_id"] == order_id and int(i["paid_cents"]) > 0
                               for i in self.repository.list_collection_items())
            has_applications = any(i["order_id"] == order_id and int(i["applied_cents"]) > 0
                                   for i in self.repository.list_installments(str(order["instrument_id"])))
            cancellable = not has_receipts and not has_applications
        self.cancel_order_button.setEnabled(cancellable)
        self.edit_concepts_button.setEnabled(order is not None and order['order_status'] == 'ACTIVE'
                                            and order['manual_concepts'] is not None)
        self.edit_order_button.setEnabled(order is not None and order["order_status"] == "ACTIVE")
        self.cancel_order_button.setToolTip(
            "Selecciona un pedido activo sin abonos ni pagos aplicados. "
            "Anula primero esos movimientos si necesitas cancelar el pedido."
        )
        person_id = self._selected_person_id()
        person = self.repository.get_person(person_id) if person_id else None
        self.create_person_button.setEnabled(bool(self.person_name.text().strip()))
        self.update_person_button.setEnabled(person is not None and bool(self.person_name.text().strip()))
        self.deactivate_person_button.setEnabled(person is not None and bool(person["active"]))
        self.reactivate_person_button.setEnabled(person is not None and not bool(person["active"]))
        owner_id = self._selected_owner_id()
        owner = self.repository.get_person(owner_id) if owner_id else None
        self.configure_owner_button.setEnabled(owner is not None and bool(owner["active"]))
        try:
            card_amount = self._parse_mxn_to_cents(self.card_payment_amount.text())
            date.fromisoformat(self.card_payment_date.text().strip())
        except ValueError:
            card_amount = 0
        payment_instrument = next((item for item in self.repository.list_all_instruments()
                                   if item['id'] == self.card_instrument.currentData()), None)
        self.record_card_button.setEnabled(payment_instrument is not None
            and payment_instrument['instrument_type'] in ('CREDIT_CARD', 'CREDIT_LINE') and card_amount > 0)
        for button, field, description, identity in (
            (self.record_extra_button, self.extra_amount, self.extra_description, self.extra_person.currentData()),
            (self.record_fee_button, self.fee_amount, self.fee_description, True),
        ):
            try:
                value = self._parse_mxn_to_cents(field.text())
            except ValueError:
                value = 0
            button.setEnabled(value > 0 and bool(description.text().strip()) and bool(identity))

    def closeEvent(self, event) -> None:
        if self.database is not None and self.database.encrypted and not self.test_mode and getattr(self, '_manual_started', False):
            dirty = bool(self.order_merchant.text().strip()) or any(self.manual_concepts.item(r, 0).text().strip() for r in range(self.manual_concepts.rowCount()))
            if dirty and QMessageBox.question(self, 'Captura sin guardar', 'Hay un gasto sin guardar. ¿Cerrar y descartarlo?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        if self.database is not None:
            self.database.close()
            self.database = None
        self.data_changed.disconnect()
        super().closeEvent(event)


def create_application(argv: list[str] | None = None) -> QApplication:
    application = QApplication.instance()
    if application is None:
        application = QApplication(argv if argv is not None else sys.argv)
    application.setStyleSheet(
        """
        QWidget { font-size: 14px; }
        QPushButton { min-height: 26px; padding: 4px 10px; border: 1px solid #aebdce; border-radius: 4px; background: #f8fafc; color: #182536; }
        QPushButton:hover { background: #edf4fc; }
        QPushButton:focus { border-color: #2563eb; }
        QPushButton:disabled { background: #edf1f5; color: #64748b; border-color: #cbd5e1; }
        QPushButton#primaryAction { background: #1d4ed8; color: white; border-color: #1d4ed8; }
        QPushButton#primaryAction:disabled { background: #edf1f5; color: #64748b; border-color: #cbd5e1; }
        QLineEdit, QComboBox, QSpinBox { min-height: 22px; padding: 3px; }
        QComboBox { min-height: 26px; padding: 4px; border: 1px solid #aebdce; border-radius: 4px; }
        QTableWidget { gridline-color: #dbe2ea; selection-background-color: #dceafb; selection-color: #102a43; }
        QHeaderView::section { padding: 5px; font-weight: 600; }
        #pageTitle { font-size: 24px; font-weight: 600; }
        #demoBanner, #securityNotice {
            padding: 10px; background: #fff3cd; color: #664d03;
            border: 1px solid #ffda6a; border-radius: 4px;
        }
        #summaryCard {
            padding: 8px; border: 1px solid #d8dee9;
            border-radius: 6px; background: #f7f9fc;
        }
        #summaryAmount { font-size: 20px; font-weight: 600; }
        QListWidget#navigation { padding: 6px; }
        """
    )
    return application


def main() -> int:
    application = create_application()
    test_mode = "--test-database" in sys.argv[1:]
    if "--demo" in sys.argv[1:]:
        if test_mode:
            QMessageBox.critical(None, "Modo de apertura", "Elige demostración o base de pruebas.")
            return 2
        window = MainWindow()
        window.show()
        return application.exec()
    database_path = Path.home() / "AppData" / "Local" / "SGCCC" / (
        "sgccc-test.db" if test_mode else "sgccc.db"
    )
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database = open_database_with_prompt(application, database_path)
    if database is None:
        return 0
    window = MainWindow(database=database, test_mode=test_mode)
    window.show()
    return application.exec()


def open_database_with_prompt(
    application: QApplication,
    database_path: Path,
) -> LocalDatabase | None:
    """Open the encrypted database, allowing retry without replacing it."""
    del application
    while True:
        database = None
        password, accepted = QInputDialog.getText(
            None,
            "Abrir SGCCC",
            "Contraseña de la base cifrada:",
            QLineEdit.EchoMode.Password,
        )
        if not accepted or not password:
            return None
        try:
            database = LocalDatabase.open(database_path, password)
            version = int(database.connection.execute("PRAGMA user_version").fetchone()[0])
            if 0 < version < SCHEMA_VERSION:
                backup_directory = database_path.parent / "backups"
                backup_directory.mkdir(parents=True, exist_ok=True)
                backup_path = backup_directory / f"{database_path.stem}-v{version}-{uuid4().hex}.db"
                database.prepare_migration_backup(backup_path, password)
                QMessageBox.information(
                    None, "Respaldo verificado",
                    f"Se creó y verificó un respaldo cifrado antes de actualizar la base:\n{backup_path}",
                )
            database.migrate()
            return database
        except (DatabaseSecurityError, OSError) as error:
            if database is not None:
                database.close()
                database = None
            retry = QMessageBox.critical(
                None,
                "No se pudo abrir SGCCC",
                f"{error}\nLa base no se reemplazará ni se recreará automáticamente.",
                QMessageBox.StandardButton.Retry
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Retry,
            )
            if retry != QMessageBox.StandardButton.Retry:
                return None


if __name__ == "__main__":
    raise SystemExit(main())
