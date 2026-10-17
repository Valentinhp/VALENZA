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
    QDateEdit,
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
    QSizePolicy,
    QStyledItemDelegate,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from valenza.gui.cards_layout import CardExplanation
from PySide6.QtCore import Qt, Signal, QSignalBlocker, QRegularExpression, QEvent, QSize, QDate
from PySide6.QtGui import QRegularExpressionValidator, QPixmap, QIcon, QColor, QFont, QFontMetrics, QShortcut, QKeySequence
from valenza.gui.warm_finance import (FinanceChart, HOME_STYLE, line_icon, MovementDelegate,
                                    apply_warm_surface, warm_section, FinancialSummary, financial_text_html,
                                    date_label, period_label, RecordedDateDelegate)
from valenza.gui.unlock import UnlockDialog
from valenza.gui.errors import user_error
from valenza.gui.design_system import install_design_system, FlowLayout, WarmScrollArea
from valenza.gui.branding import brand_icon, PaymentIdentity
from valenza.gui.home_people_breakdown import HomePeopleBreakdown
from valenza.gui.people_month_chart import PeopleMonthChart
from valenza.gui.search import SearchDialog
from valenza.gui.personal_result import personal_result, result_label, EXPLANATION
from valenza.gui.home_month_summary import home_month_summary, home_month_text
from valenza.gui.bank_reconciliation import (difference_text, query_text, reported_text, breakdown_html,
    forecast_text, forecast_notice, scheduled_text, official_period_query, official_text, monthly_comparison_text, BALANCE_TYPES)

from valenza.persistence.database import DATABASE_ERRORS, DatabaseSecurityError, LocalDatabase, SCHEMA_VERSION
from valenza.persistence.repository import FinanceRepository


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


def person_statement_html(statement):
    """The same presentation and balances for the screen and individual PDF."""
    parts = [f"<h1>Estado de cuenta · {escape(statement['person'])}</h1>",
             f"<p>Asignado: {format_money(statement['assigned_cents'])}<br>Abonado: {format_money(statement['paid_cents'])}<br><b>Pendiente: {format_money(statement['remaining_cents'])}</b></p>"]
    for row in statement['rows']:
        parts.append(f"<h2>{escape(str(row['source_name']))} · {escape(str(row['source_date'] or 'Fecha por revisar'))}</h2>")
        detail = row.get('financial_detail')
        if detail:
            parts.append(f"<p>Compra original: {format_money(detail['original_cents'])} · Descuento personal: {format_money(detail['discount_cents'])} · Cargo real: {format_money(detail['charged_cents'])}. Referencia de la operación; no se suma a la participación.</p>")
            if detail['subscription']:
                parts.append(f"<p>Suscripción: {escape(detail['subscription']['name'])}</p>")
            if detail['purchase_mode']=='MSI':
                parts.append('<p>MSI: mensualidades previstas incluidas en el pendiente actual, sin nuevos cargos.</p>')
            for refund in detail['refunds']:
                parts.append(f"<p>Devolución: {format_money(refund['amount_cents'])} · {escape(refund['destination_name'])} · {'Acreditada' if refund['status']=='ACCREDITED' else 'Pendiente'}</p>")
                if refund.get('repurchase'):
                    linked = refund['repurchase']
                    parts.append(f"<p>Recompra vinculada: {format_money(linked['charged_cents'])} · Compensación aplicada: {format_money(linked['applied_cents'])}. Sin un segundo cobro familiar.</p>")
        parts.append('<table><tr><th>Concepto</th><th>Asignación registrada</th></tr>')
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
    if statement.get('forecasts'):
        parts.append('<h2>Próximos importes previstos</h2><p>Suscripciones: todavía sin cargo real. MSI: desglose del pendiente actual; no sumar nuevamente. Para mostrar el calendario familiar, los abonos se descuentan primero de las cuotas más antiguas; no son pagos al banco.</p>')
        for forecast in statement['forecasts']:
            parts.append(f"<p>{escape(forecast['due_date'] or 'Fecha por confirmar')} · {escape(forecast['description'])} · {escape(forecast['alias'])}: {format_money(forecast['amount_cents'])}</p>")
    return ''.join(parts)


def write_family_pdf(statement, path, *, issued_at=None, repository=None):
    from valenza.gui.family_pdf import write_report
    return write_report(statement, path, issued_at=issued_at, repository=repository)


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
            "Valenza - BASE DE PRUEBAS" if test_mode
            else "Valenza - demostración local" if database is None
            else "Valenza - PRUEBAS EN MEMORIA" if database.synthetic
            else "Valenza"
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
            warning.setStyleSheet('padding: 5px 10px; background: #fff3cd; color: #664d03; border: 1px solid #e4c586; border-radius: 6px;')
            layout.addWidget(warning, 0, 0, 1, 2)

        navigation = QListWidget()
        self.navigation = navigation
        navigation.setObjectName("navigation")
        navigation.setFixedWidth(164)
        navigation.setAccessibleName('Secciones de Valenza')
        navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        navigation.setTextElideMode(Qt.TextElideMode.ElideNone)
        navigation.addItems(self.PAGES)
        for index, icon in enumerate(('home', 'people', 'receipt', 'card', 'card', 'calendar', 'settings')):
            navigation.item(index).setIcon(line_icon(icon))
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        brand = QLabel('Valenza')
        brand.setObjectName('valenzaSidebarLogo')
        brand_pixmap = QPixmap(str(Path(__file__).parent / 'assets' / 'logo_vertical.png'))
        if not brand_pixmap.isNull():
            brand.setPixmap(brand_pixmap.scaled(150, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setToolTip('Valenza · Finanzas compartidas')
        sidebar_layout.addWidget(brand)
        subtitle = QLabel('Finanzas compartidas')
        subtitle.setStyleSheet('color: #7e817b; font-size: 11px; padding: 0 4px 12px;')
        if brand_pixmap.isNull():
            sidebar_layout.addWidget(subtitle)
        else:
            subtitle.deleteLater()
        self.setWindowIcon(QIcon(str(Path(__file__).parent / 'assets' / 'icono_app_claro.png')))
        self.search_button = QPushButton('Buscar · Ctrl+K')
        self.search_button.setObjectName('globalSearchButton')
        self.search_button.setAccessibleName('Buscar en Valenza, Control K')
        self.search_button.setEnabled(self.repository is not None)
        self.search_button.clicked.connect(self._open_search)
        sidebar_layout.addWidget(self.search_button)
        sidebar_layout.addWidget(navigation, 1)
        navigation.setStyleSheet('QListWidget { background: #f6f0e7; border: none; border-radius: 10px; padding: 6px; } QListWidget::item { padding: 10px 3px; border-radius: 7px; color: #535b5d; } QListWidget::item:selected { background: #f0d5bc; color: #844625; }')
        navigation.setStyleSheet(navigation.styleSheet() + ' QListWidget:focus { border: 2px solid #9b583b; padding: 4px; } QListWidget::item:focus { border: 1px solid #9b583b; }')
        navigation.currentRowChanged.connect(self._show_page)
        QWidget.setTabOrder(self.search_button, navigation)
        content_row = 1 if self.test_mode else 0
        layout.addWidget(sidebar, content_row, 0)

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
        self.action_feedback = QLabel()
        self.action_feedback.setObjectName('savedActionFeedback')
        self.action_feedback.setWordWrap(True)
        self.action_feedback.setTextFormat(Qt.TextFormat.PlainText)
        self.action_feedback.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.action_feedback.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.action_feedback.hide()
        layout.addWidget(self.action_feedback, content_row + 1, 1)
        navigation.setCurrentRow(0)
        self.setCentralWidget(root)
        self._search_dialog = None
        self.search_shortcut = QShortcut(QKeySequence('Ctrl+K'), self)
        self.search_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.search_shortcut.activated.connect(self._open_search)
        for combo in self.findChildren(QComboBox):
            if combo not in (self.bank_query_type, self.bank_scope):
                combo.setMinimumContentsLength(10)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        if self.repository is not None:
            for name, columns in (
                ('cards_table', (9, 10, 14)), ('card_payment_history', (0,)),
                ('collection_history', (0,)), ('collection_items', (9,)),
                ('orders_table', (1,)), ('subscription_table', (1,)),
                ('bank_history', (0,)), ('dashboard_cards', (3,)),
            ):
                table = getattr(self, name)
                delegate = RecordedDateDelegate(table)
                for column in columns:
                    table.setItemDelegateForColumn(column, delegate)
            for table in (self.cards_table, self.card_payment_history, self.collection_items,
                          self.collection_history, self.orders_table, self.people_table,
                          self.owner_people_table):
                table.itemSelectionChanged.connect(self._update_action_states)
                table.setAlternatingRowColors(True)
                table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
                table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
                table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
            for table, column in ((self.cards_table, 0), (self.collection_items, 2)):
                table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
                table.horizontalHeader().setMinimumSectionSize(75)
            for table, name in ((self.orders_table, 'Pedidos: usa las flechas para consultar y Tab para ir a las acciones'),
                                (self.collection_items, 'Deudas por persona'), (self.collection_history, 'Historial de abonos'),
                                (self.cards_table, 'Tarjetas y cuentas'), (self.card_payment_history, 'Pagos bancarios registrados'),
                                (self.people_table, 'Personas registradas'), (self.subscription_table, 'Suscripciones registradas')):
                table.setAccessibleName(name)
                table.setTabKeyNavigation(False)
            self.cards_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
            self.cards_table.setColumnWidth(1, 150)
            self.cards_table.horizontalHeaderItem(3).setText('Pagado al banco')
            self.cards_table.horizontalHeaderItem(4).setText('Deuda total pendiente')
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
            self.cards_summary_layout.insertWidget(1, self.cards_columns_toggle, alignment=Qt.AlignmentFlag.AlignLeft)
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
            header_font = QFont(table.horizontalHeader().font())
            header_font.setBold(True)
            header_metrics = QFontMetrics(header_font)
            for column in columns:
                width = max(75, header_metrics.horizontalAdvance(table.horizontalHeaderItem(column).text()) + 22)
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
        if page_name == "Suscripciones" and self.repository is not None:
            return self._make_subscriptions_page()
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
            security = QLabel("Datos protegidos con cifrado local. La demostración usa datos ficticios.")
            security.setObjectName("securityNotice")
            layout.addWidget(security)
        layout.addStretch()
        return page

    @staticmethod
    def _money_input(cents=0):
        field = MxnLineEdit()
        field.setValue(cents)
        return field

    def _read_mxn(self, field):
        return self._parse_mxn_to_cents(field.text())

    def _financial_dialog(self, title, *, save_text='Guardar cambios', cancel_text='Cancelar'):
        self.statusBar().clearMessage()
        if hasattr(self,'action_feedback'):
            self.action_feedback.clear()
            self.action_feedback.hide()
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(600, 440)
        outer = QVBoxLayout(dialog)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        footer = QHBoxLayout()
        footer.addStretch()
        cancel = QPushButton(cancel_text)
        save = QPushButton(save_text)
        dialog.cancel_button, dialog.save_button = cancel, save
        cancel.clicked.connect(dialog.reject)
        footer.addWidget(cancel)
        footer.addWidget(save)
        outer.addLayout(footer)
        return dialog, body, save

    def _make_subscriptions_page(self):
        page = QWidget()
        apply_warm_surface(page, 'warmSubscriptions')
        layout = QVBoxLayout(page)
        title = QLabel('Suscripciones'); title.setObjectName('pageTitle')
        header = QHBoxLayout(); header.addWidget(title); header.addStretch()
        create = QPushButton('Nueva suscripción'); create.setObjectName('primaryAction')
        create.clicked.connect(lambda: self._edit_subscription())
        header.addWidget(create); layout.addLayout(header)
        notice = QLabel('Próximos cobros estimados. Registra solo cargos reales; vincula los pedidos que ya existen.')
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.subscription_summary = QLabel(); self.subscription_summary.setWordWrap(True)
        summary, summary_body = warm_section('Previsión mensual · sin deuda bancaria')
        summary_body.addWidget(self.subscription_summary); layout.addWidget(summary)
        self.subscription_empty_card, empty_body = warm_section('Tu primer servicio, en orden')
        self.subscription_empty = QLabel('Organiza el calendario y reparto de tus servicios. Una previsión no registra cargos reales.')
        self.subscription_empty.setWordWrap(True); empty_body.addWidget(self.subscription_empty)
        first = QPushButton('Crear primera suscripción'); first.setObjectName('primaryAction')
        first.clicked.connect(lambda: self._edit_subscription())
        empty_body.addWidget(first, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.subscription_empty_card)
        detail, detail_body = warm_section('Suscripción seleccionada')
        actions = QGridLayout()
        self.subscription_actions = []
        for index, (text, callback) in enumerate((('Editar',lambda:self._edit_subscription(self._table_id(self.subscription_table,5))),
                ('Pausar / reactivar',lambda:self._subscription_status(False)),
                ('Cancelar suscripción',lambda:self._subscription_status(True)),
                ('Registrar o vincular cargo real',self._subscription_charge_dialog),
                ('Eliminar definitivamente',self._delete_subscription))):
            button = QPushButton(text)
            if index in (2,4): button.setObjectName('dangerAction')
            button.clicked.connect(callback)
            actions.addWidget(button,index//2,index%2, alignment=Qt.AlignmentFlag.AlignLeft)
            self.subscription_actions.append(button)
        self.subscription_table = QTableWidget(0,6)
        self.subscription_table.setHorizontalHeaderLabels(['Servicio / cuenta','Próximo previsto','Mensual MXN','Estado','Reparto familiar MXN','ID'])
        self.subscription_table.setColumnHidden(5,True)
        self.subscription_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.subscription_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.subscription_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.subscription_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.subscription_table.setMaximumHeight(260)
        self.subscription_table.setAlternatingRowColors(True)
        self.subscription_table.setIconSize(QSize(24, 24))
        self.subscription_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.subscription_table.verticalHeader().setVisible(False)
        layout.addWidget(self.subscription_table)
        self.subscription_detail = QLabel()
        self.subscription_detail.setWordWrap(True)
        self.subscription_detail.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.subscription_brand = QLabel()
        self.subscription_brand.setFixedSize(32, 32)
        self.subscription_brand.setAccessibleName('Identidad del servicio')
        detail_row = QHBoxLayout()
        detail_row.setAlignment(Qt.AlignmentFlag.AlignTop)
        detail_row.addWidget(self.subscription_brand, 0, Qt.AlignmentFlag.AlignTop)
        detail_row.addWidget(self.subscription_detail, 1)
        detail_body.addLayout(detail_row)
        self.subscription_payment_identity = PaymentIdentity()
        detail_body.addWidget(self.subscription_payment_identity)
        actions.setColumnStretch(2, 1)
        detail_body.addLayout(actions); layout.addWidget(detail); layout.addStretch()
        self.subscription_table.itemSelectionChanged.connect(self._subscription_selection)
        self._refresh_subscriptions()
        return self._admin_scroll(page)

    @staticmethod
    def _admin_scroll(content):
        scroll = WarmScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    def _refresh_subscriptions(self):
        selected = self._table_id(self.subscription_table,5)
        subscriptions = self.repository.list_subscriptions()
        active = [s for s in subscriptions if s['status'] == 'ACTIVE']
        family = sum(a['amount_cents'] + a['surcharge_cents'] for s in active for a in s['allocations'] if not a['is_owner'])
        next_due = min((s['next_due'] for s in active), default='Sin cargos previstos')
        self.subscription_summary.setText(f"Gasto previsto: {format_money(sum(s['amount_cents'] for s in active))} · Activas: {len(active)}\nPróximo cargo previsto: {date_label(next_due)} · Familia prevista (incluye recargos): {format_money(family)}")
        self.subscription_empty.setVisible(not subscriptions)
        self.subscription_empty_card.setVisible(not subscriptions)
        self.subscription_table.setVisible(bool(subscriptions))
        self.subscription_table.setFixedHeight(min(260, 48 + len(subscriptions) * 32))
        with QSignalBlocker(self.subscription_table):
            self.subscription_table.setRowCount(0)
            for subscription in subscriptions:
                row = self.subscription_table.rowCount()
                self.subscription_table.insertRow(row)
                values = [subscription['name']+' · '+subscription['alias'],subscription['next_due'],
                          format_money(subscription['amount_cents']),{'ACTIVE':'Activa','PAUSED':'Pausada','CANCELLED':'Cancelada'}[subscription['status']],
                          format_money(sum(a['amount_cents']+a['surcharge_cents'] for a in subscription['allocations'] if not a['is_owner'])),subscription['id']]
                for column,value in enumerate(values):
                    item = QTableWidgetItem(str(value)); item.setToolTip(str(value))
                    if column == 3:
                        item.setForeground(QColor({'ACTIVE':'#48705a','PAUSED':'#9b6839','CANCELLED':'#9d5043'}[subscription['status']]))
                    if column == 0:
                        item.setIcon(brand_icon(subscription['name']))
                    if column in (2, 4):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.subscription_table.setItem(row,column,item)
                if subscription['id'] == selected:
                    self.subscription_table.selectRow(row)
        self._subscription_selection()

    def _subscription_selection(self):
        identity = self._table_id(self.subscription_table,5)
        subscription = next((s for s in self.repository.list_subscriptions() if s['id']==identity),None)
        for index, button in enumerate(self.subscription_actions):
            button.setEnabled(bool(subscription and (index==4 or subscription['status'] != 'CANCELLED' and (index != 3 or subscription['status'] == 'ACTIVE'))))
        self.subscription_actions[1].setText('Reactivar' if subscription and subscription['status']=='PAUSED' else 'Pausar')
        self.subscription_payment_identity.set_instrument(self._brand_instrument(subscription["instrument_id"]) if subscription else None)
        self.subscription_brand.setVisible(bool(subscription))
        if subscription:
            self.subscription_brand.setPixmap(brand_icon(subscription["name"]).pixmap(32, 32))
            self.subscription_brand.setToolTip(subscription["name"])
        if not subscription:
            self.subscription_detail.setText('Selecciona un servicio para consultar su calendario, reparto y cargos registrados. Al editar puedes elegir si también reduces recargos anteriores; revisa la vista previa antes de guardar.')
            return
        state = {'ACTIVE':'Activa','PAUSED':'Pausada','CANCELLED':'Cancelada'}[subscription['status']]
        shares = '\n'.join(f"{a['name']}: {format_money(a['amount_cents'])}" + (f" + recargo {format_money(a['surcharge_cents'])}" if a['surcharge_cents'] else '') for a in subscription['allocations'])
        self.subscription_detail.setText(f"{subscription['name']} · {state} · {subscription['alias']}\nMensual: {format_money(subscription['amount_cents'])} · Próximo previsto: {date_label(subscription['next_due'])} · Día del ciclo: {subscription['billing_day']}\n{shares}\nFamilia pendiente de cargos ya registrados: {format_money(subscription['family_pending_cents'])}")
        self.subscription_detail.setMinimumHeight(self.subscription_detail.fontMetrics().lineSpacing() * (len(self.subscription_detail.text().splitlines()) + 1))

    def _edit_subscription(self, identity=None):
        existing = next((s for s in self.repository.list_subscriptions() if s['id']==identity),None)
        if identity and not existing:
            return
        if existing and existing['status']=='CANCELLED':
            self._show_error('Una suscripción cancelada conserva su historial y no se edita.'); return
        dialog,body,save = self._financial_dialog('Editar suscripción' if existing else 'Nueva suscripción mensual',
            save_text='Guardar suscripción' if existing else 'Crear suscripción',
            cancel_text='Descartar cambios' if existing else 'Cancelar')
        apply_warm_surface(dialog, 'warmSubscriptionDialog')
        dialog.resize(660, 590)
        body.parentWidget().setObjectName('warmSubscriptionDialogContent')
        body.parentWidget().setStyleSheet('#warmSubscriptionDialogContent { background: #f8f4ee; }')
        heading = QLabel(dialog.windowTitle()); heading.setObjectName('sectionTitle'); heading.setWordWrap(True); body.addWidget(heading)
        service, service_body = warm_section('Servicio y calendario'); body.addWidget(service)
        save.setObjectName('primaryAction')
        form = QFormLayout()
        name = QLineEdit(existing['name'] if existing else '')
        name.setAccessibleName('Nombre del servicio, obligatorio')
        service_identity = QLabel()
        service_identity.setFixedSize(32, 32)
        service_identity.setAccessibleName('Identidad del servicio')
        def update_service_identity(text):
            service_identity.setPixmap(brand_icon(text).pixmap(32, 32))
            service_identity.setToolTip(text or 'Suscripción')
        name.textChanged.connect(update_service_identity)
        update_service_identity(name.text())
        service_name_row = QWidget()
        service_name_layout = QHBoxLayout(service_name_row)
        service_name_layout.setContentsMargins(0, 0, 0, 0)
        service_name_layout.addWidget(service_identity)
        service_name_layout.addWidget(name, 1)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        amount = self._money_input(existing['amount_cents'] if existing else 0)
        due = QLineEdit(existing['next_due'] if existing else date.today().isoformat())
        instrument = QComboBox()
        for card in self.repository.list_all_instruments():
            if card['active'] or existing and card['id']==existing['instrument_id']:
                instrument.addItem(brand_icon(card['institution_name'], 'institution'), f"{card['alias']} · {card['institution_name']}", card['id'])
        if existing: instrument.setCurrentIndex(instrument.findData(existing['instrument_id']))
        for label,field in (('Servicio *',service_name_row),('Importe mensual MXN *',amount),('Próximo cobro previsto *',due),('Cuenta / tarjeta *',instrument)):
            form.addRow(label,field)
        due.setPlaceholderText('AAAA-MM-DD')
        due.setAccessibleName('Fecha del próximo cobro previsto, AAAA-MM-DD')
        amount.setAccessibleName('Importe mensual de la suscripción en MXN')
        instrument.setAccessibleName('Cuenta de la suscripción')
        service_body.addLayout(form)
        required = QLabel('* Campos obligatorios · Fechas en formato AAAA-MM-DD.')
        required.setObjectName('secondaryText'); required.setWordWrap(True); service_body.addWidget(required)
        reparto, reparto_body = warm_section('Reparto mensual · importes en MXN'); body.addWidget(reparto)
        explanation = QLabel('Las participaciones deben sumar el importe mensual. Los recargos familiares no aumentan el cargo bancario.')
        explanation.setWordWrap(True); reparto_body.addWidget(explanation)
        fees = QCheckBox('Recargo familiar por persona (opcional)')
        fees.setChecked(bool(existing and any(a['surcharge_cents'] for a in existing['allocations'])))
        reparto_body.addWidget(fees)
        shares = QFormLayout()
        shares.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        fields = []
        previous = {a['user_id']:a for a in existing['allocations']} if existing else {}
        for person in self.repository.list_people():
            if not person['active'] and person['id'] not in previous: continue
            allocation = previous.get(person['id'],{})
            value = self._money_input(allocation.get('amount_cents',0))
            fee = self._money_input(allocation.get('surcharge_cents',0))
            value.setAccessibleName('Parte mensual de ' + person['name'] + ', en MXN')
            fee.setAccessibleName('Recargo familiar de ' + person['name'] + ', en MXN')
            fee.setEnabled(fees.isChecked() and not person['is_owner'])
            fee.setToolTip('Recargo familiar; no aumenta el cargo bancario.')
            if not person['active']:
                value.setReadOnly(True); fee.setReadOnly(True)
                value.setToolTip('Responsable inactivo conservado. Reactiva la persona en Usuarios antes de guardar cambios, según las reglas existentes.')
            row = QHBoxLayout(); row.addWidget(value); row.addWidget(QLabel('Recargo')); row.addWidget(fee)
            shares.addRow(person['name'] + (' · inactiva' if not person['active'] else ''),row)
            fields.append((person,value,fee))
        fees.toggled.connect(lambda checked:[fee.setEnabled(checked and not p['is_owner']) for p,value,fee in fields])
        reparto_body.addLayout(shares)
        posted_fees=QCheckBox('Quitar o reducir también los recargos de cargos ya registrados')
        posted_fees.setChecked(bool(existing));posted_fees.setVisible(bool(existing))
        posted_fees.setObjectName('updatePostedSubscriptionFees')
        body.addWidget(posted_fees)
        fee_preview=CardExplanation();fee_preview.setObjectName('postedSubscriptionFeePreview')
        fee_preview.setVisible(bool(existing));body.addWidget(fee_preview)
        error = QLabel(); error.setWordWrap(True); body.addWidget(error)
        surcharge_state={'token':None}
        def update_fee_preview(*_):
            if not existing:return
            if not posted_fees.isChecked():
                fee_preview.setText('Solo cambia la configuración futura. Los cargos y el recuento anteriores se conservan.')
                surcharge_state['token']=None;save.setEnabled(True);return
            try:
                from valenza.persistence.subscription_fees import preview
                amounts={p['id']:self._read_mxn(f) if fees.isChecked() and not p['is_owner'] else 0 for p,v,f in fields}
                plan=preview(self.repository,identity,amounts);surcharge_state['token']=plan['token']
                changes=plan['changes'];blocked=[c for c in changes if c['blocked']]
                total=sum(-c['delta_cents'] for c in changes)
                details=[c['name']+' · '+c['cycle_date']+': '+format_money(c['old_fee'])+' → '+format_money(c['new_fee']) for c in changes]
                text=(f"{len(changes)} recargos anteriores por reducir: {format_money(total)}. "
                    'Se ajusta la deuda familiar, sin cambiar el cargo bancario ni los abonos.\n'
                    'En el recuento se ajustan las marcas completas; los parciales se conservan.') if changes else 'No hay recargos anteriores que reducir.'
                if details:text+='\n'+'\n'.join(details[:3])+(' · Más detalles al pasar el cursor.' if len(details)>3 else '')
                if blocked:text+='\nNo se aplicará: '+blocked[0]['name']+' · '+blocked[0]['blocked']
                fee_preview.setText(text);fee_preview.setToolTip('\n'.join(details));save.setEnabled(not blocked)
            except ValueError:
                fee_preview.setText('Completa los recargos para revisar los cargos anteriores.');save.setEnabled(False)
        posted_fees.toggled.connect(update_fee_preview);fees.toggled.connect(update_fee_preview)
        for p,v,f in fields:f.textChanged.connect(update_fee_preview)
        update_fee_preview()
        def persist():
            save.setEnabled(False)
            try:
                self.repository.save_subscription(subscription_id=identity or str(uuid4()),name=name.text(),
                    amount_cents=self._read_mxn(amount),instrument_id=instrument.currentData(),next_due=due.text(),
                    allocations=[dict(user_id=p['id'],amount_cents=self._read_mxn(v),surcharge_cents=self._read_mxn(f) if fees.isChecked() and not p['is_owner'] else 0) for p,v,f in fields],
                    expected_revision=existing['revision'] if existing else None,
                    reduce_posted_surcharges=bool(existing and posted_fees.isChecked()),
                    expected_surcharge_state=surcharge_state['token'] if existing and posted_fees.isChecked() else None)
            except (ValueError,*DATABASE_ERRORS) as exc:
                error.setText(self._safe_error(exc)); save.setEnabled(True); return
            dialog.accept(); self.data_changed.emit('subscriptions')
            self._show_saved_information('Suscripción actualizada.' if existing else 'Suscripción creada.', 'Suscripciones: '+name.text().strip()+' · selecciona el servicio para consultar sus datos.')
        save.clicked.connect(persist)
        dialog.exec()

    def _delete_subscription(self):
        from valenza.persistence.subscription_delete import preview,delete
        identity=self._table_id(self.subscription_table,5)
        if not identity:return
        try:
            plan=preview(self.repository,identity)
            if plan['blocked']:
                self._show_error('\n'.join(plan['blocked']));return
            text=(f"Eliminar definitivamente «{plan['subscription']['name']}»: "
                f"{len(plan['orders'])} pedidos/cargos, {len(plan['accounts'])} cuentas por cobrar "
                f"y {len(plan['payments'])} abonos exclusivos.\n\n"
                'Se quitarán sus recargos, historial y referencias en los recuentos guardados. '
                'Esto reduce la deuda registrada; no cancela cargos en el banco. '
                'Los pagos bancarios globales se conservan.\n\n'
                'Se requiere un respaldo cifrado. El respaldo y los archivos de cortes exportados '
                'conservarán la información anterior. ¿Continuar?')
            if QMessageBox.warning(self,'Eliminar definitivamente',text,
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
            path,_=QFileDialog.getSaveFileName(self,'Guardar respaldo cifrado antes de eliminar',
                'Valenza-antes-de-eliminar-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.db','Base cifrada (*.db)')
            if not path:return
            delete(self.repository,identity,expected_token=plan['token'],backup_path=path)
        except (ValueError,OSError,DatabaseSecurityError,*DATABASE_ERRORS) as exc:
            self._show_error(self._safe_error(exc));return
        self.data_changed.emit('subscriptions')
        self._show_information('Suscripción, cargos y deudas vinculados eliminados. Respaldo cifrado: '+path)

    def _subscription_status(self, cancel):
        identity = self._table_id(self.subscription_table,5)
        existing = next((s for s in self.repository.list_subscriptions() if s['id']==identity),None)
        if not existing: return
        if cancel and QMessageBox.question(self,'Cancelar previsión en Valenza','¿Cancelar la previsión de esta suscripción en Valenza?\nEsto NO cancela el servicio ni los cobros del proveedor. Debes gestionarlo con el proveedor.\nLos pedidos y pendientes existentes se conservan.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:
            return
        try:
            self.repository.set_subscription_status(identity,'CANCELLED' if cancel else 'PAUSED' if existing['status']=='ACTIVE' else 'ACTIVE')
        except (ValueError,*DATABASE_ERRORS) as exc:
            self._show_error(self._safe_error(exc)); return
        self.data_changed.emit('subscriptions')

        self._show_information('Previsión cancelada en Valenza; se conserva su historial. El servicio con el proveedor no se canceló.' if cancel else
            'Suscripción pausada.' if existing['status']=='ACTIVE' else 'Suscripción reactivada.')

    def _subscription_charge_dialog(self):
        identity = self._table_id(self.subscription_table,5)
        existing = next((s for s in self.repository.list_subscriptions() if s['id']==identity),None)
        if not existing: return
        dialog,body,save = self._financial_dialog('Cargo real de suscripción')
        apply_warm_surface(dialog, 'warmSubscriptionCharge')
        body.parentWidget().setObjectName('warmSubscriptionChargeContent')
        body.parentWidget().setStyleSheet('#warmSubscriptionChargeContent { background: #f8f4ee; }')
        save.setObjectName('primaryAction'); save.setText('Registrar cargo real')
        body.addWidget(QLabel(f"{existing['name']} · ciclo {existing['next_due']} · {format_money(existing['amount_cents'])}"))
        choices = QComboBox(); choices.addItem('Registrar un nuevo cargo REAL',None)
        for order in self.repository.list_orders():
            if order['instrument_id']==existing['instrument_id']:
                choices.addItem(f"Vincular: {order['merchant']} · {order['ordered_at']} · {format_money(order['charged_cents'])}",order['id'])
        body.addWidget(choices)
        actual = QLineEdit(date.today().isoformat())
        body.addWidget(QLabel('Fecha del cargo real AAAA-MM-DD (solo para nuevo cargo)')); body.addWidget(actual)
        choices.currentIndexChanged.connect(lambda:actual.setEnabled(choices.currentData() is None))
        choices.currentIndexChanged.connect(lambda: save.setText('Registrar cargo real' if choices.currentData() is None else 'Vincular pedido existente'))
        notice = QLabel('Guarda únicamente cuando el cargo exista. Los pedidos importados se vinculan seleccionándolos; no los registres de nuevo. El importe, cuenta y reparto deben coincidir.')
        notice.setWordWrap(True); body.addWidget(notice)
        error = QLabel(); error.setWordWrap(True); body.addWidget(error)
        body.addStretch()
        def persist():
            save.setEnabled(False)
            try:
                self.repository.record_subscription_charge(identity,cycle_date=existing['next_due'],order_id=choices.currentData(),charged_at=actual.text())
            except (ValueError,*DATABASE_ERRORS) as exc:
                error.setText(self._safe_error(exc)); save.setEnabled(True); return
            dialog.accept(); self.data_changed.emit('subscriptions')
            self._show_information('Cargo real registrado.' if choices.currentData() is None else 'Pedido vinculado a la suscripción.')
        save.clicked.connect(persist); dialog.exec()

    def _make_cards_page(self) -> QWidget:
        page = QWidget()
        apply_warm_surface(page, 'warmCards')
        outer = QVBoxLayout(page)
        outer.setContentsMargins(12, 10, 12, 10)
        scroll = WarmScrollArea()
        self.cards_scroll = scroll
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName('warmCardsContent')
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(8)
        title = QLabel("Tarjetas")
        title.setObjectName("pageTitle")
        outer.addWidget(title)
        notice = QLabel(
            "Los cargos de Pedidos usan el cargo real a tarjeta. Los abonos "
            "familiares no se consideran pagos a la institución. Las cuotas "
            "sin calendario confirmado aparecen como pendientes de confirmar."
        )
        notice.setWordWrap(True)
        notice.setToolTip(notice.text())
        notice.setText('Cargos, pagos reales y mensualidades. Los abonos familiares no pagan al banco.')
        outer.addWidget(notice)

        self.card_panels = {}
        self.card_summary_cards = [self._make_card(label, '—') for label in
            ('Deuda total seleccionada', 'Correspondiente al mes · previsto', 'Meses futuros · previstos')]
        self.card_indicators = QGridLayout()
        for index, card in enumerate(self.card_summary_cards):
            self.card_indicators.addWidget(card, 0, index)
        layout.addLayout(self.card_indicators)
        summary_frame, self.cards_summary_layout = warm_section('Tarjetas y cuentas')
        layout.addWidget(summary_frame)
        self.cards_table = QTableWidget(0, 16)
        notice.setText('Importes en MXN. ' + notice.text())
        self.cards_table.setObjectName("cardsTable")
        self.cards_table.setHorizontalHeaderLabels(
            ["Tarjeta", "Institución", "Cargado", "Pagado", "Por liquidar",
             "Programado en el periodo", "Meses futuros previstos", "Corte", "Límite", "Próximo corte",
             "Vencimiento", "Estado", "ID", "Último saldo banco", "Consultado", "Diferencia histórica"]
        )
        self.cards_table.setColumnHidden(12, True)
        self.cards_table.setMinimumHeight(0)
        self.cards_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cards_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cards_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.cards_table.itemSelectionChanged.connect(self._select_card)
        self.cards_summary_layout.addWidget(self.cards_table)
        self.cards_empty_notice = QLabel('No hay tarjetas registradas. Abre Administración bancaria para agregar una cuenta.')
        self.cards_empty_notice.setWordWrap(True)
        self.cards_summary_layout.addWidget(self.cards_empty_notice)
        bank_body = self._cards_panel(layout, 'bank', 'Comparar con mi banco', 'Guardar conserva una referencia; no registra pagos ni cambia tu deuda.')
        bank_body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.card_panels['bank'][1].setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Minimum)
        bank_panel=self.card_panels['bank'][1].parentWidget()
        bank_panel.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Minimum)
        bank_panel.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        self.bank_query_comparison = CardExplanation('Saldo bancario: Sin consultar')
        self.bank_query_comparison.setWordWrap(True)
        bank_body.addWidget(self.bank_query_comparison)
        self.bank_nu_help = CardExplanation('Nu: «saldo actual» y «saldo a pagar» no equivalen a deuda total con MSI futuros. '
            'Confirma con Nu el total de la misma cuenta, con cargos y pagos ya reflejados. '
            'Para saber cuánto pagar, copia «Pago para no generar intereses» con sus fechas.')
        self.bank_nu_help.setToolTip('Si el alcance no está confirmado, guarda sin comparación. '
            'No uses pago mínimo, crédito disponible ni saldo futuro como deuda total o pago para no generar intereses.')
        self.bank_nu_help.setWordWrap(True)
        bank_body.addWidget(self.bank_nu_help)
        bank_form = self._cards_compact_form()
        self.bank_period_picker = self._make_period_picker()
        bank_form.addRow(QLabel('Periodo de vencimiento'), self.bank_period_picker)
        bank_note = CardExplanation('Elige el mismo periodo que muestra tu banco. El calendario de Valenza es una previsión, no un estado de cuenta confirmado.')
        bank_note.setWordWrap(True)
        bank_form.addRow(bank_note)
        self.bank_query_amount = MxnLineEdit()
        self.bank_query_amount.setAccessibleName('Importe del banco, en MXN')
        self.bank_query_amount.setPlaceholderText('Importe que muestra tu banco (MXN)')
        self.bank_query_date = QLineEdit(datetime.now().astimezone().isoformat(timespec='seconds'))
        self.bank_query_date.setAccessibleName('Fecha y hora de consulta')
        self.bank_query_type = QComboBox()
        for key in ('NO_INTEREST', 'MINIMUM', 'OTHER', 'TOTAL', 'STATEMENT', 'MONTHLY', 'PENDING', 'UNKNOWN'):
            label = 'Deuda total · incluye MSI futuros' if key == 'TOTAL' else BALANCE_TYPES[key]
            self.bank_query_type.addItem(label,key)
        self.bank_query_type.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.bank_query_type.setMinimumContentsLength(32)
        self.bank_query_type.setAccessibleName('Concepto del saldo informado por el banco')
        self.bank_query_type.setToolTip('Deuda total es la comparación secundaria: incluye todas las cuotas futuras.')
        self.bank_query_label = QLineEdit()
        self.bank_query_label.setPlaceholderText('Nombre del otro saldo, tal como aparece en el banco')
        self.bank_query_label.setAccessibleName('Nombre del otro saldo bancario')
        self.bank_query_label.setMaxLength(120)
        self.bank_query_label.hide()
        self.bank_scope = QComboBox()
        self.bank_scope.setAccessibleName('Cuenta o línea compartida')
        self.bank_scope.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.bank_scope.setMinimumContentsLength(32)
        self.bank_scope_save = QPushButton('Guardar vínculo informativo')
        self.bank_scope_save.clicked.connect(self._record_bank_scope)
        self.bank_query_save = QPushButton('Guardar comparación')
        self.bank_query_save.setEnabled(False)
        self.bank_query_save.clicked.connect(self._record_bank_query)
        self.bank_query_save.setToolTip('Selecciona una tarjeta o línea de crédito. Esta consulta no registra movimientos.')
        question = QLabel('Importe del banco')
        question.setToolTip('¿Cuánto muestra tu banco para ese mismo periodo?')
        question.setBuddy(self.bank_query_amount)
        bank_form.addRow(QLabel('Tipo de saldo'), self.bank_query_type)
        bank_form.addRow(self.bank_query_label)
        bank_form.addRow(question, self.bank_query_amount)
        self.bank_total_confirmed = QCheckBox('Confirmo deuda total con MSI futuros')
        self.bank_total_confirmed.setToolTip('Misma cuenta y momento. No marques si copiaste saldo actual, al corte, a pagar, disponible o con movimientos pendientes.')
        self.bank_total_confirmed.toggled.connect(self._preview_bank_query)
        bank_form.addRow(self.bank_total_confirmed)
        self.bank_closing_date = QLineEdit()
        self.bank_due_date = QLineEdit()
        for field, label in ((self.bank_closing_date, 'Fecha de corte'), (self.bank_due_date, 'Fecha límite de pago')):
            field.setPlaceholderText('AAAA-MM-DD · copiar del banco')
            field.setAccessibleName(label)
        self.bank_closing_label = QLabel('Fecha de corte')
        self.bank_due_label = QLabel('Fecha límite de pago')
        self.bank_closing_label.setBuddy(self.bank_closing_date)
        self.bank_due_label.setBuddy(self.bank_due_date)
        bank_form.addRow(self.bank_closing_label, self.bank_closing_date)
        bank_form.addRow(self.bank_due_label, self.bank_due_date)
        advanced_form = self._cards_compact_form()
        self.bank_date_manual = QCheckBox('Usar otra fecha y hora')
        advanced_form.addRow(self.bank_date_manual)
        self.bank_query_date.setEnabled(False)
        self.bank_date_manual.toggled.connect(self.bank_query_date.setEnabled)
        advanced_form.addRow(QLabel('Fecha y hora de consulta'), self.bank_query_date)
        bank_form.addRow(self.bank_query_save)
        scope_form=self._cards_compact_form()
        scope_form.addRow(QLabel('Cuenta / línea compartida'), self.bank_scope)
        scope_form.addRow(self.bank_scope_save)
        scope_note=CardExplanation('Vincula solo tarjetas de la misma línea con movimientos distintos. El vínculo no mueve cargos ni pagos.')
        scope_note.setWordWrap(True)
        scope_form.addRow(scope_note)
        for button in (self.bank_query_save, self.bank_scope_save):
            button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.bank_form_widget = QWidget()
        self.bank_form_widget.setLayout(bank_form)
        self.bank_form_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        bank_body.addWidget(self.bank_form_widget)
        self.bank_query_feedback = CardExplanation()
        self.bank_query_feedback.setWordWrap(True)
        bank_body.addWidget(self.bank_query_feedback)
        self.bank_query_amount.textChanged.connect(self._preview_bank_query)
        self.bank_query_type.currentIndexChanged.connect(self._preview_bank_query)
        self.bank_query_date.textChanged.connect(self._preview_bank_query)
        self.bank_date_manual.toggled.connect(self._preview_bank_query)
        QWidget.setTabOrder(self.bank_period_picker, self.bank_query_type)
        QWidget.setTabOrder(self.bank_query_type, self.bank_query_label)
        QWidget.setTabOrder(self.bank_query_label, self.bank_query_amount)
        QWidget.setTabOrder(self.bank_query_amount, self.bank_total_confirmed)
        QWidget.setTabOrder(self.bank_total_confirmed, self.bank_closing_date)
        QWidget.setTabOrder(self.bank_closing_date, self.bank_due_date)
        QWidget.setTabOrder(self.bank_due_date, self.bank_query_save)
        self._add_advanced_section(bank_body, 'Opciones avanzadas', advanced_form)
        self._add_advanced_section(bank_body,'Tarjetas de una misma línea',scope_form)
        self.bank_query_save.setObjectName('primaryAction')
        self.bank_breakdown_toggle=QPushButton('Ver desglose bancario')
        self.bank_breakdown_toggle.setCheckable(True)
        self.bank_breakdown=CardExplanation()
        self.bank_breakdown.setWordWrap(True)
        self.bank_breakdown.setTextFormat(Qt.TextFormat.RichText)
        self.bank_breakdown.hide()
        self.bank_breakdown_toggle.toggled.connect(self.bank_breakdown.setVisible)
        bank_body.addWidget(self.bank_breakdown_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        bank_body.addWidget(self.bank_breakdown)
        self.bank_history_toggle=QPushButton('Ver historial de consultas')
        self.bank_history_toggle.setCheckable(True)
        self.bank_history=QTableWidget(0,6)
        self.bank_history.setHorizontalHeaderLabels(['Consulta','Concepto','Banco','Valenza al guardar','Diferencia','Tarjeta / cuenta'])
        self.bank_history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.bank_history.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.bank_history.setMaximumHeight(190)
        self.bank_history.horizontalHeader().setMinimumSectionSize(100)
        self.bank_history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.bank_history.itemSelectionChanged.connect(self._select_bank_history)
        self.bank_history_detail=CardExplanation()
        self.bank_history_detail.setWordWrap(True)
        self.bank_history.hide(); self.bank_history_detail.hide()
        self.bank_history_toggle.toggled.connect(self.bank_history.setVisible)
        self.bank_history_toggle.toggled.connect(self.bank_history_detail.setVisible)
        bank_body.addWidget(self.bank_history_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        bank_body.addWidget(self.bank_history)
        bank_body.addWidget(self.bank_history_detail)
        for label in bank_panel.findChildren(QLabel):
            label.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Minimum)

        payments_body = self._cards_panel(layout, 'payments', 'Pagos reales e historial', 'Dinero pagado a la tarjeta. Independiente de los abonos familiares.')
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
        payments_body.addLayout(form)
        self.record_card_button.setObjectName('primaryAction')

        msi_body = self._cards_panel(layout, 'msi', 'Mensualidades MSI', 'Asigna pagos ya registrados a cuotas; no crea otro pago bancario.')
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
        self.apply_card_button.setToolTip('Requiere un pago disponible, una cuota pendiente y un importe válido para ambos.')
        application_form.addWidget(self.apply_card_button, 2, 2, 1, 2)
        self.card_application_form = application_form
        msi_body.addLayout(application_form)
        self.apply_card_button.setObjectName('primaryAction')
        self.card_payment_history = QTableWidget(0, 6)
        self.card_payment_history.setHorizontalHeaderLabels(
            ["Fecha", "Importe", "Referencia", "Estado", "ID", "Sin asignar a cuotas"]
        )
        self.card_payment_history.setColumnHidden(4, True)
        self.card_payment_history.setMinimumHeight(0)
        self.card_payment_history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.card_payment_history.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.card_payment_history.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.card_payment_history.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.card_payment_history.itemSelectionChanged.connect(
            self._select_card_payment
        )
        payments_body.addWidget(QLabel('Historial de pagos de la tarjeta seleccionada'))
        payments_body.addWidget(self.card_payment_history)
        payment_actions = QGridLayout()
        self.edit_payment_button = QPushButton("Guardar cambios de pago")
        self.edit_payment_button.clicked.connect(self._edit_selected_card_payment)
        self.cancel_payment_button = QPushButton("Anular pago")
        self.cancel_payment_button.clicked.connect(self._cancel_selected_card_payment)
        payment_actions.addWidget(self.edit_payment_button, 0, 0)
        payment_actions.addWidget(self.cancel_payment_button, 0, 1)
        payments_body.addLayout(payment_actions)
        self.cancel_payment_button.setObjectName('dangerAction')

        admin_body = self._cards_panel(layout, 'admin', 'Administraci\u00f3n bancaria', 'Fechas, instituciones y cuentas; conserva sus relaciones e historial.')
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
        self.card_calendar_layout = calendar
        self.card_calendar_tail = (calendar.itemAtPosition(1, 2).widget(), self.card_due_day,
                                   calendar_button, calendar_note)
        self._add_advanced_section(admin_body, "Fechas de corte y pago", calendar)

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
        edit_card_button = QPushButton("Guardar cuenta")
        edit_card_button.clicked.connect(self._edit_instrument)
        toggle_card_button = QPushButton("Activar/desactivar")
        toggle_card_button.clicked.connect(self._toggle_instrument)
        hint = QLabel('Selecciona una tarjeta o billetera para editarla. Su historial se conserva.')
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
        # Establish QWidget ownership before moving controls into nested layouts.
        # With an unattached grid, Qt can retain stale native layout items.
        self._add_advanced_section(admin_body, "Administrar instituciones y tarjetas", administration)
        for row, buttons in ((2, (add_institution_button, edit_institution_button, toggle_institution_button)),
                             (9, (add_card_button, edit_card_button, toggle_card_button))):
            actions = QWidget()
            flow = FlowLayout(actions)
            for button in buttons:
                administration.removeWidget(button)
                flow.addWidget(button)
            administration.addWidget(actions, row, 0, 1, 3)
        self._load_admin_catalogs()

        self.card_detail = QLabel("Selecciona una tarjeta para ver sus compras.")
        self.card_detail.setWordWrap(True)
        self.card_detail.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.card_detail.setObjectName("cardDetail")
        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        detail_scroll.setWidget(self.card_detail)
        detail_scroll.setFixedHeight(154)
        self.cards_summary_layout.addWidget(detail_scroll)
        self.card_detail_scroll = detail_scroll
        self.card_detail_toggle = QPushButton('Ver desglose de la tarjeta')
        self.card_detail_toggle.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.card_detail_toggle.setCheckable(True)
        self.card_detail_toggle.toggled.connect(detail_scroll.setVisible)
        self.cards_summary_layout.insertWidget(self.cards_summary_layout.indexOf(detail_scroll), self.card_detail_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        detail_scroll.hide()
        self.card_period_notice = QLabel()
        self.card_period_notice.setWordWrap(True)
        self.card_period_notice.setObjectName('secondaryText')
        self.cards_summary_layout.insertWidget(self.cards_summary_layout.indexOf(self.card_detail_toggle), self.card_period_notice)
        for grid in (form, application_form, payment_actions, calendar, administration):
            for index in range(grid.count()):
                widget = grid.itemAt(index).widget()
                if isinstance(widget, QLabel):
                    row, column, _, _ = grid.getItemPosition(index)
                    adjacent = grid.itemAtPosition(row, column + 1)
                    field = adjacent.widget() if adjacent else None
                    if isinstance(field, (QLineEdit, QComboBox, QDateEdit, QSpinBox)):
                        widget.setBuddy(field)
                        if not field.accessibleName():
                            field.setAccessibleName(widget.text())
                if isinstance(widget, QPushButton):
                    grid.setAlignment(widget, Qt.AlignmentFlag.AlignLeft)
                elif isinstance(widget, QComboBox):
                    widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                    widget.setMinimumContentsLength(16)
        self.card_panels['bank'][0].toggled.connect(lambda _: self._fit_card_tables())
        self._load_card_catalogs()
        self._refresh_cards()
        layout.addStretch()
        scroll.setWidget(content)
        scroll.viewport().installEventFilter(self)
        outer.addWidget(scroll)
        return page

    def _cards_panel(self, layout, key, title, note):
        frame, body = warm_section(title)
        caption = body.itemAt(0).widget()
        body.removeWidget(caption)
        heading = QHBoxLayout()
        heading.addWidget(caption)
        heading.addStretch()
        toggle = QPushButton('Abrir')
        toggle.setCheckable(True)
        toggle.setAccessibleName(title)
        toggle.setIcon(line_icon('calendar' if key == 'msi' else 'card'))
        heading.addWidget(toggle)
        body.addLayout(heading)
        content = QWidget()
        inner = QVBoxLayout(content)
        inner.setContentsMargins(0, 0, 0, 0)
        hint = QLabel(note)
        hint.setWordWrap(True)
        inner.addWidget(hint)
        body.addWidget(content)
        content.hide()
        toggle.toggled.connect(content.setVisible)
        toggle.toggled.connect(lambda expanded: toggle.setText('Cerrar' if expanded else 'Abrir'))
        self.card_panels[key] = (toggle, content)
        layout.addWidget(frame)
        return inner

    def _fit_card_tables(self):
        width = self.cards_scroll.viewport().width()
        columns = 3 if width >= 780 else 2 if width >= 560 else 1
        for index, card in enumerate(self.card_summary_cards):
            self.card_indicators.removeWidget(card)
            self.card_indicators.addWidget(card, index // columns, index % columns)
        for column in range(3):
            self.card_indicators.setColumnStretch(column, 1 if column < columns else 0)
        narrow = width < 650
        self.card_application_form.removeWidget(self.apply_card_button)
        self.card_application_form.addWidget(self.apply_card_button, 3 if narrow else 2,
                                              1 if narrow else 2, 1, 3 if narrow else 2, Qt.AlignmentFlag.AlignLeft)
        calendar = self.card_calendar_layout
        label, due, save, note = self.card_calendar_tail
        for widget in self.card_calendar_tail:
            calendar.removeWidget(widget)
        calendar.addWidget(label, 2 if narrow else 1, 0 if narrow else 2)
        calendar.addWidget(due, 2 if narrow else 1, 1 if narrow else 3)
        calendar.addWidget(save, 3 if narrow else 2, 0 if narrow else 2, 1, 2, Qt.AlignmentFlag.AlignLeft)
        calendar.addWidget(note, 4 if narrow else 3, 0, 1, 2 if narrow else 4)
        if hasattr(self, 'card_detail_scroll'):
            width = max(100, self.card_detail_scroll.viewport().width() - 20)
            self.card_detail.setMinimumHeight(max(40, self.card_detail.heightForWidth(width)))
        for table, columns in ((self.cards_table, (2, 3, 4, 5, 6, 13, 15)),
                               (self.card_payment_history, (1, 5))):
            for row in range(table.rowCount()):
                for column in columns:
                    item = table.item(row, column)
                    if item:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                first = table.item(row, 0)
                if first:
                    font = first.font()
                    font.setBold(True)
                    first.setFont(font)
            table.setFixedHeight(table.horizontalHeader().height() + 4
                + sum(max(32, table.rowHeight(r)) for r in range(min(6, max(1, table.rowCount()))))
                + table.horizontalScrollBar().sizeHint().height())

    @staticmethod
    def _cards_compact_form():
        """Let Qt size rows and wrap labels when horizontal space is limited."""
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        return form

    @staticmethod
    def _add_advanced_section(layout: QVBoxLayout, label: str, content_layout) -> None:
        toggle = QPushButton(label)
        toggle.setCheckable(True)
        content = QWidget()
        content.setLayout(content_layout)
        content.setVisible(False)
        toggle.toggled.connect(content.setVisible)
        toggle.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout.addWidget(toggle, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(content)

    def _load_card_catalogs(self) -> None:
        self.card_institution.clear()
        for item in self.repository.list_institutions():
            self.card_institution.addItem(brand_icon(str(item["name"]), "institution"), str(item["name"]), item["id"])
        self._refresh_card_instruments()

    def _refresh_card_instruments(self) -> None:
        if not hasattr(self, "card_instrument"):
            return
        self.card_instrument.clear()
        institution_id = self.card_institution.currentData()
        for item in self.repository.list_instruments(institution_id) if institution_id else []:
            self.card_instrument.addItem(brand_icon(self.card_institution.currentText(), "institution"), str(item["alias"]), item["id"])

    def _forecast_date(self):
        return date.fromisoformat(self._forecast_period+'-01') if getattr(self, '_forecast_period', None) else date.today()

    def _make_period_picker(self):
        picker = QDateEdit()
        picker.setDisplayFormat('MM/yyyy')
        picker.setCalendarPopup(True)
        picker.setAccessibleName('Periodo de vencimiento del calendario')
        today = self._forecast_date()
        picker.setDate(QDate(today.year, today.month, 1))
        picker.dateChanged.connect(self._change_forecast_period)
        return picker

    def _change_forecast_period(self, value):
        self._forecast_period = value.toString('yyyy-MM')
        for name in ('bank_period_picker', 'dashboard_period_picker'):
            picker = getattr(self, name, None)
            if picker:
                with QSignalBlocker(picker):
                    picker.setDate(QDate(value.year(), value.month(), 1))
        if hasattr(self, 'pages'):
            self._refresh_cards()
            self._refresh_dashboard()

    def _bank_consulted_at(self):
        return (self.bank_query_date.text().strip() if self.bank_date_manual.isChecked()
                else datetime.now().astimezone().isoformat(timespec='seconds'))

    def _preview_bank_query(self, *_):
        if not hasattr(self, 'bank_query_feedback'):
            return
        account = next((a for a in self.repository.list_bank_comparisons(as_of=self._forecast_date())
                        if self._selected_card_id() in a['members']), None)
        self.bank_query_label.setVisible(self.bank_query_type.currentData() == 'OTHER')
        self.bank_total_confirmed.setVisible(self.bank_query_type.currentData() == 'TOTAL')
        for field in (self.bank_closing_date, self.bank_due_date, self.bank_closing_label, self.bank_due_label):
            field.setVisible(self.bank_query_type.currentData() == 'NO_INTEREST')
        message = 'Introduce el importe del banco. Puedes guardarlo como referencia del periodo, sin crear movimientos.'
        if account:
            forecast = account['monthly_forecast']
            self.bank_query_comparison.setText(
                f"Deuda total Valenza: {format_money(account['calculated_cents'])} · incluye MSI futuros.\n"
                f"{account['alias']} · {period_label(forecast['period'])} · Programado antes de pagos: {scheduled_text(forecast, format_money)}\n"
                + forecast_notice(forecast) + '\n' + ' '.join(account['warnings']))
            self.bank_breakdown.setText(breakdown_html(account['components'], format_money)
                + financial_text_html(forecast_text(forecast, format_money)))
            official = official_period_query(self.repository.list_bank_reconciliation_history(),account,self._forecast_date().strftime('%Y-%m'))
            if official:
                self.bank_query_comparison.setText(self.bank_query_comparison.text()+'\n'+official_text(official,format_money))
        if account and self.bank_query_amount.text().strip():
            try:
                amount = self._parse_mxn_to_cents(self.bank_query_amount.text())
                from valenza.persistence.bank_reconciliation import same_moment
                if self.bank_query_type.currentData() != 'TOTAL':
                    message = monthly_comparison_text(account['monthly_forecast'],amount,self.bank_query_type.currentData(),
                        format_money,reliable=account['comparable'])
                elif not self.bank_total_confirmed.isChecked():
                    message = 'No comparable: confirma que el importe incluye la misma deuda total, con MSI futuros y movimientos ya aplicados. Se puede guardar como referencia.'
                elif not account['comparable']:
                    message = 'No comparable: el alcance de la línea no permite confirmar una deuda neta fiable.'
                elif self._forecast_date().strftime('%Y-%m') != date.today().strftime('%Y-%m'):
                    message = 'No comparable: el periodo seleccionado no es el actual. No se compara ese periodo con la deuda total actual.'
                elif not same_moment(self._bank_consulted_at()):
                    message = 'No comparable: esa fecha y hora no corresponden a la deuda actual. Se puede guardar como referencia, sin confirmar coincidencia.'
                else:
                    delta = amount - account['calculated_cents']
                    message = ('Los saldos coinciden para la deuda total actual.' if delta == 0 else
                               difference_text(delta, format_money) + '. Puede haber cargos o pagos aún sin registrar. Revisa los detalles antes de concluir que hay un error.')
            except ValueError:
                message = 'Introduce un importe válido en pesos para comprobarlo.'
        self.bank_query_feedback.setText(message)
        if hasattr(self, 'card_application_form'):
            self._fit_card_tables()

    def _record_bank_query(self):
        instrument_id = self._selected_card_id()
        try:
            if not instrument_id or not self.bank_query_amount.text().strip():
                raise ValueError('Selecciona la tarjeta e introduce el importe informado por el banco.')
            official = self.bank_query_type.currentData() == 'NO_INTEREST'
            if official and (not self.bank_closing_date.text().strip() or not self.bank_due_date.text().strip()):
                raise ValueError('Copia la fecha de corte y la fecha límite que muestra el banco.')
            self.repository.record_bank_balance(instrument_id,
                self._parse_mxn_to_cents(self.bank_query_amount.text()), self._bank_consulted_at(),
                balance_type=self.bank_query_type.currentData(), period=self._forecast_date().strftime('%Y-%m'),
                balance_label=self.bank_query_label.text(),
                closing_date=self.bank_closing_date.text().strip() if official else None,
                due_date=self.bank_due_date.text().strip() if official else None,
                total_confirmed=self.bank_total_confirmed.isChecked())
        except ValueError as error:
            self._show_error(self._safe_error(error))
            return
        self.data_changed.emit('cards')
        self.bank_query_amount.clear()

        self._show_information('Comparación guardada en el historial.')

    def _record_bank_scope(self):
        try:
            self.repository.set_bank_reconciliation_scope(self._selected_card_id(),self.bank_scope.currentData())
        except ValueError as error:
            self._show_error(self._safe_error(error)); return
        self.data_changed.emit('cards')
        self._show_information('Vínculo informativo guardado.')

    def _select_bank_history(self):
        rows=self.bank_history.selectionModel().selectedRows()
        query=self.bank_history.item(rows[0].row(),0).data(Qt.ItemDataRole.UserRole) if rows else None
        self.bank_history_detail.setText(query_text(query,format_money))

    def _refresh_cards(self) -> None:
        if not hasattr(self, "cards_table"):
            return
        selected_id = self._selected_card_id()
        blocker = QSignalBlocker(self.cards_table)
        self.cards_table.setRowCount(0)
        comparisons = {item['instrument_id']: item for item in self.repository.list_bank_comparisons(as_of=self._forecast_date())}
        for account in list(comparisons.values()):
            for member in account['members']:
                comparisons[member]=account
        for card in self.repository.list_card_summaries(include_inactive=True):
            from valenza.persistence.bank_periods import period_forecast
            period = period_forecast(self.repository, [card['instrument_id']], self._forecast_date())
            comparison = comparisons.get(card['instrument_id'])
            row = self.cards_table.rowCount()
            self.cards_table.insertRow(row)
            values = (
                card["alias"], card["institution_name"],
                format_money(int(card["charged_cents"])),
                format_money(int(card["paid_cents"])),
                format_money(int(card["remaining_cents"])),
                scheduled_text(period,format_money),
                format_money(period['future_cents']),
                card["closing_day"] or "Pendiente",
                card["due_day"] or "Pendiente",
                card["next_cut"] or "Pendiente de confirmar",
                card["next_due"] or "Pendiente de confirmar",
                "Activa" if card["active"] else "Inactiva",
                card["instrument_id"],
                reported_text(comparison['last_query'],format_money) if comparison else 'No aplica',
                comparison['consulted_at'] or 'Sin consulta' if comparison else 'No aplica',
                difference_text(comparison['difference_cents'],format_money) if comparison and comparison['last_query'] else 'Sin consulta' if comparison else 'No aplica',
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column in (5, 6):
                    cell.setToolTip(forecast_text(period, format_money))
                if column in (13,14,15) and comparison:
                    cell.setToolTip('Cuenta / línea: '+comparison['alias']+'\n'+query_text(comparison['last_query'],format_money)+'\n'+' '.join(comparison['warnings']))
                if column == 1:
                    cell.setIcon(brand_icon(card['institution_name'], 'institution'))
                    cell.setToolTip(str(value))
                self.cards_table.setItem(row, column, cell)
            if card["instrument_id"] == selected_id:
                self.cards_table.selectRow(row)
        blocker.unblock()
        self.cards_empty_notice.setVisible(self.cards_table.rowCount() == 0)
        self._select_card()
        self._fit_card_tables()

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
            self.bank_date_manual.setChecked(False)
            self.bank_total_confirmed.setChecked(False)
            self.bank_closing_date.clear()
            self.bank_due_date.clear()
            self.bank_query_amount.clear()
            self.bank_query_date.setText(datetime.now().astimezone().isoformat(timespec='seconds'))
        self._bank_query_selection = instrument_id
        accounts = self.repository.list_bank_comparisons(as_of=self._forecast_date())
        comparison = next((item for item in accounts if instrument_id in item['members']), None)
        self.bank_query_save.setEnabled(comparison is not None)
        self.bank_scope_save.setEnabled(comparison is not None)
        self.bank_scope.clear()
        if comparison:
            self.bank_scope.addItem('Esta cuenta independiente',instrument_id)
            institution=self.repository.database.connection.execute('SELECT institution_id FROM payment_instrument WHERE id=?',(instrument_id,)).fetchone()[0]
            for account in accounts:
                same=self.repository.database.connection.execute('SELECT institution_id FROM payment_instrument WHERE id=?',(account['account_id'],)).fetchone()[0]==institution
                if same and account['account_id']!=instrument_id:
                    self.bank_scope.addItem(account['alias']+' · línea compartida',account['account_id'])
            self.bank_scope.setCurrentIndex(self.bank_scope.findData(comparison['account_id']))
            if selection_changed:
                self.bank_query_type.setCurrentIndex(0)
            self.bank_query_comparison.setText(
                f"Deuda total calculada por Valenza: {format_money(comparison['calculated_cents'])}\n"
                f"{comparison['alias']} · {comparison['institution_name']}\n" + ' '.join(comparison['warnings']))
            self.bank_breakdown.setText(breakdown_html(comparison['components'],format_money))
        else:
            self.bank_query_comparison.setText('Selecciona una tarjeta o línea de crédito para consultar su deuda total.')
            self.bank_breakdown.clear()
        self._preview_bank_query()
        blocker=QSignalBlocker(self.bank_history)
        self.bank_history.setRowCount(0)
        history=self.repository.list_bank_reconciliation_history() if comparison else []
        account_names = {str(i['id']): str(i['alias']) for i in self.repository.list_all_instruments()}
        for query in history:
            if query['account_id'] not in comparison['members']:
                continue
            row=self.bank_history.rowCount(); self.bank_history.insertRow(row)
            concept = {'TOTAL': 'Deuda total', 'NO_INTEREST': 'Sin intereses',
                       'MINIMUM': 'Pago mínimo', 'OTHER': 'Otro saldo'}.get(
                           query['balance_type'], BALANCE_TYPES[query['balance_type']])
            difference = ('Sin comparación' if query['difference_cents'] is None else
                          format_money(query['difference_cents']))
            values=(query['consulted_at'],concept,format_money(query['amount_cents']),
                format_money(query['calculated_cents']) if query['calculated_cents'] is not None else 'Sin fotografía',
                difference,account_names.get(str(query['account_id']), 'Cuenta no disponible'))
            for col,value in enumerate(values):
                item=QTableWidgetItem(value); item.setToolTip(query_text(query,format_money))
                if col==0: item.setData(Qt.ItemDataRole.UserRole,query)
                if col==5:
                    item.setData(Qt.ItemDataRole.UserRole, query['account_id'])
                    item.setToolTip(value)
                self.bank_history.setItem(row,col,item)
        blocker.unblock()
        self.bank_history_detail.setText('Selecciona una consulta para ver su fotografía y advertencias.' if history else 'Sin consulta')
        if instrument_id is None:
            self.card_period_notice.clear()
            for card in self.card_summary_cards:
                card.findChild(QLabel, 'summaryAmount').setText('\u2014')
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
        from valenza.persistence.bank_periods import period_forecast
        period = period_forecast(self.repository, [instrument_id], self._forecast_date())
        for widget, field in zip(self.card_summary_cards, ('remaining_cents', 'scheduled_month_cents', 'scheduled_future_cents')):
            if widget is self.card_summary_cards[0]:
                field = ('wallet_balance_cents' if summary['instrument_type'] == 'WALLET_BALANCE' else
                         'cash_balance_cents' if summary['instrument_type'] == 'OTHER' else field)
            widget.findChild(QLabel, 'summaryAmount').setText(format_money(int(summary[field])))
        for widget, field in zip(self.card_summary_cards[1:], ('current_cents', 'future_cents')):
            widget.findChild(QLabel, 'summaryAmount').setText(format_money(period[field]))
            widget.setToolTip(forecast_text(period, format_money))
        self.card_summary_cards[1].findChild(QLabel,'summaryAmount').setText(scheduled_text(period,format_money))
        self.card_summary_cards[1].layout().itemAt(0).widget().setText(f"{period_label(period['period'])} · antes de pagos")
        self.card_period_notice.setText(forecast_notice(period))
        self.card_period_notice.setToolTip('\n'.join(period['warnings']))
        self.card_summary_cards[0].layout().itemAt(0).widget().setText(
            'Saldo registrado seleccionado' if summary['instrument_type'] in ('WALLET_BALANCE', 'OTHER') else 'Deuda total (incluye futuras)')
        details = [
            (f"Saldo de billetera registrado: {format_money(int(summary['wallet_balance_cents']))}"
             if summary['instrument_type'] == 'WALLET_BALANCE' else
             f"Saldo registrado en otro medio: {format_money(int(summary['cash_balance_cents']))}"
             if summary['instrument_type'] == 'OTHER' else
             f"Deuda total registrada (incluye cuotas futuras): {format_money(int(summary['remaining_cents']))}"),
            forecast_text(period, format_money),
            (f"MSI por pagar hasta hoy: {format_money(int(summary['exigible_cents']))} · "
             'importe adicional por confirmar con el calendario bancario'
             if summary['pending_confirmation_cents'] and summary['exigible_cents'] else
             'MSI por pagar hasta hoy: Por confirmar con el calendario bancario'
             if summary['pending_confirmation_cents'] else
             f"MSI por pagar hasta hoy: {format_money(int(summary['exigible_cents']))}"),
            f"Total del plan pendiente de confirmación bancaria (no es la cuota de este mes): {format_money(int(summary['pending_confirmation_cents']))}",
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
            f"- {date_label(item['ordered_at'])} · {item['merchant']} · "
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
                f"{date_label(item['due_date']) or 'Vencimiento pendiente'} · "
                f"{period_label(item['period_key']) if item['period_key'] else 'Periodo por confirmar'} · "
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
        self._fit_card_tables()
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
                "Anulado" if payment["payment_status"] == "CANCELLED" else "Activo",
                payment["id"],
                format_money(max(available, 0)),
            )
            for column, value in enumerate(values):
                self.card_payment_history.setItem(row, column, QTableWidgetItem(str(value)))
            if available > 0 and payment["payment_status"] == "ACTIVE":
                self.card_apply_payment.addItem(
                    f"{payment['paid_at']} · sin asignar a cuotas {format_money(available)}",
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
        self._fit_card_tables()

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
                brand_icon(institution["name"], "institution"),
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
        apply_warm_surface(page, 'warmCollections')
        outer = QVBoxLayout(page)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)
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
        self.collection_totals.setObjectName('secondaryText')
        self.collection_personal_card = self._make_card('Mi parte pendiente', '$0.00 MXN')
        self.collection_family_card = self._make_card('Cobros familiares pendientes', '$0.00 MXN')
        summary = QHBoxLayout()
        summary.addWidget(self.collection_personal_card)
        summary.addWidget(self.collection_family_card)
        outer.addLayout(summary)
        outer.addWidget(self.collection_totals)
        self.collection_filter = QComboBox()
        self.collection_filter.setAccessibleName('Filtrar deudas por participación')
        self.collection_filter.addItem("Todos", "ALL")
        self.collection_filter.addItem("Mi parte", "PERSONAL")
        self.collection_filter.addItem("Cobros familiares", "FAMILY")
        self.collection_filter.addItem("Históricos por revisar", "UNKNOWN")
        self.collection_filter.currentIndexChanged.connect(self._filter_collections)
        self.family_pdf_button = QPushButton('PDF de la persona')
        self.family_pdf_button.setToolTip('Exportar el estado de cuenta de la persona seleccionada')
        self.family_pdf_button.clicked.connect(self._export_family_pdf)
        filters = QHBoxLayout()
        filters.addWidget(QLabel('Participación'))
        filters.addWidget(self.collection_filter, 1)
        filters.addWidget(self.family_pdf_button)
        outer.addLayout(filters)
        footer_layout = outer
        self.collections_scroll = WarmScrollArea()
        self.collections_scroll.setWidgetResizable(True)
        collections_content = QWidget()
        collections_content.setObjectName('warmCollectionsContent')
        outer = QVBoxLayout(collections_content)
        outer.setContentsMargins(0, 0, 4, 0)
        outer.setSpacing(8)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        # Keep every action reachable vertically when the window is short.
        footer_layout.removeItem(summary)
        footer_layout.removeWidget(self.collection_totals)
        footer_layout.removeItem(filters)
        outer.addLayout(summary)
        outer.addWidget(self.collection_totals)
        outer.addLayout(filters)
        self.collections_scroll.setWidget(collections_content)
        footer_layout.addWidget(self.collections_scroll, 1)
        self.collections_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.collections_scroll.viewport().installEventFilter(self)
        from valenza.gui.person_receipts import PersonReceiptPanel
        self.person_receipt_panel = PersonReceiptPanel(self.repository, lambda: self.data_changed.emit('collections'))
        outer.addWidget(self.person_receipt_panel)
        debts, debts_body = warm_section('Deudas · selecciona un movimiento')
        outer.addWidget(debts)

        self.collection_items = QTableWidget(0, 14)
        self.collection_items.setObjectName("collectionItemsTable")
        self.collection_items.setHorizontalHeaderLabels(
            ["Persona", "ID persona", "Comercio", "Parte asignada", "Abonado",
             "Deuda total pendiente", "Estado", "ID cuenta", "Origen", "Fecha de origen", "Tipo",
             "Este mes", "Meses futuros", "Meses anteriores pendientes"]
        )
        self.collection_items.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.collection_items.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.collection_items.setSortingEnabled(True)
        self.collection_items.setAlternatingRowColors(True)
        self.collection_items.setMinimumHeight(0)
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
        debts_body.addWidget(self.collection_items)
        self.collections_empty_notice = QLabel('No hay deudas en este filtro. Prueba otra participación.')
        self.collections_empty_notice.setObjectName('secondaryText')
        self.collections_empty_notice.setWordWrap(True)
        debts_body.addWidget(self.collections_empty_notice)

        payment, payment_body = warm_section('Abono individual · movimiento seleccionado')
        outer.addWidget(payment)
        self._collection_return_context = None
        self._consulting_receipt = False
        self.collection_mode_notice = QLabel('Nuevo abono: selecciona una participación. Para editar un abono existente, abre su historial.')
        self.collection_mode_notice.setWordWrap(True)
        payment_body.addWidget(self.collection_mode_notice)
        self.collection_return_button = QPushButton('Volver a mi selección y borrador')
        self.collection_return_button.clicked.connect(self._return_to_collection_draft)
        self.collection_return_button.hide()
        payment_body.addWidget(self.collection_return_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.collection_selected_details = QLabel('Selecciona una deuda para consultar sus importes.')
        self.collection_selected_details.setWordWrap(True)
        self.collection_selected_details.setTextFormat(Qt.TextFormat.RichText)
        payment_body.addWidget(self.collection_selected_details)
        self.collection_payment_identity = PaymentIdentity()
        payment_body.addWidget(self.collection_payment_identity)
        payment_row = QGridLayout()
        self.collection_current_balance = QLabel("Selecciona una cuenta para ver el saldo.")
        self.collection_current_balance.setObjectName("collectionBalance")
        self.collection_current_balance.setWordWrap(True)
        payment_row.addWidget(self.collection_current_balance, 0, 0, 1, 3)
        self.collection_amount = QLineEdit()
        self.collection_amount.setAccessibleName('Importe del abono seleccionado en MXN')
        self.collection_amount.setPlaceholderText("Importe del abono")
        payment_row.addWidget(QLabel("Abono (MXN)"), 1, 0)
        payment_row.addWidget(self.collection_amount, 1, 1)
        self.record_collection_button = QPushButton("Registrar abono")
        self.record_collection_button.clicked.connect(self._record_collection)
        self.record_collection_button.setDefault(True)
        payment_row.addWidget(self.record_collection_button, 1, 2)
        payment_row.setColumnStretch(1, 1)
        self.collection_payment_layout = payment_row
        self.record_collection_button.setObjectName('primaryAction')
        self.collection_capture_form = QWidget()
        self.collection_capture_form.setLayout(payment_row)
        payment_body.addWidget(self.collection_capture_form)

        self.collection_details_toggle = QPushButton("Más detalles")
        self.collection_details_toggle.setCheckable(True)
        self.collection_details_toggle.toggled.connect(
            lambda visible: self.collection_details.setVisible(visible)
        )
        options_actions = QHBoxLayout()
        options_actions.addWidget(self.collection_details_toggle)
        self.collection_details_toggle.setText('Fecha / referencia')
        payment_body.addLayout(options_actions)
        self.collection_details = QWidget()
        details_layout = QGridLayout(self.collection_details)
        self.collection_reference = QLineEdit()
        self.collection_reference.setAccessibleName('Referencia opcional del abono individual')
        self.collection_reference.setPlaceholderText("Referencia opcional")
        self.collection_received_date = QLineEdit(date.today().isoformat())
        self.collection_received_date.setAccessibleName('Fecha del abono individual, AAAA-MM-DD')
        self.collection_received_date.setPlaceholderText("AAAA-MM-DD")
        details_layout.addWidget(QLabel("Fecha del abono"), 0, 2)
        details_layout.addWidget(self.collection_received_date, 0, 3)
        details_layout.addWidget(QLabel("Referencia"), 0, 0)
        details_layout.addWidget(self.collection_reference, 0, 1)
        self.collection_date_layout = details_layout
        self.collection_date_labels = (details_layout.itemAtPosition(0, 0).widget(),
                                       details_layout.itemAtPosition(0, 2).widget())
        self.collection_details.setVisible(False)
        payment_body.addWidget(self.collection_details)

        self.other_operations_toggle = QPushButton("Otras operaciones")
        self.other_operations_toggle.setCheckable(True)
        self.other_operations_toggle.toggled.connect(
            lambda visible: self.other_operations.setVisible(visible)
        )
        self.other_operations_toggle.setText('Extras / comisiones')
        operations, operations_body = warm_section('Extras y comisiones')
        outer.addWidget(operations)
        operations_body.addWidget(self.other_operations_toggle)
        self.other_operations = QWidget()
        extras = QGridLayout(self.other_operations)
        extras.setContentsMargins(0, 0, 0, 0)
        explanation = QLabel('Extra: ganancia separada de la deuda. Comisión: costo del depósito registrado.')
        explanation.setWordWrap(True)
        extras.addWidget(explanation, 3, 0, 1, 4)
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
        self.collection_extras_layout = extras
        self.collection_extras_labels = [extras.itemAtPosition(r, 0).widget() for r in range(3)]
        self.collection_extras_explanation = explanation
        self.other_operations.setVisible(False)
        operations_body.addWidget(self.other_operations)

        self.collection_history_toggle = QPushButton("Ver historial")
        self.collection_history_toggle.setCheckable(True)
        self.collection_history_toggle.toggled.connect(
            self._toggle_collection_history
        )
        history, history_body = warm_section('Historial de abonos')
        outer.addWidget(history)
        history_body.addWidget(self.collection_history_toggle)
        self.collection_integrity_warning = QLabel()
        self.collection_integrity_warning.setWordWrap(True)
        self.collection_integrity_warning.setAccessibleName('Aviso de consistencia de abonos')
        history_body.addWidget(self.collection_integrity_warning)
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
        self.collection_history.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.collection_history.setColumnHidden(6, True)
        self.collection_history.itemSelectionChanged.connect(
            self._select_receipt_history
        )
        history_body.addWidget(self.collection_history)
        self.collection_history.setMinimumHeight(0)
        self.collection_history.hide()
        receipt_actions = QGridLayout()
        self.edit_receipt_button = QPushButton("Editar abono seleccionado")
        self.edit_receipt_button.clicked.connect(self._edit_selected_receipt)
        self.cancel_receipt_button = QPushButton("Anular abono")
        self.cancel_receipt_button.clicked.connect(self._cancel_selected_receipt)
        receipt_actions.addWidget(self.edit_receipt_button, 0, 0)
        receipt_actions.addWidget(self.cancel_receipt_button, 0, 1)
        self.cancel_receipt_button.setObjectName('dangerAction')
        history_body.addLayout(receipt_actions)
        self.edit_receipt_button.hide()
        self.cancel_receipt_button.hide()
        self._collection_history_rows: list[dict[str, object]] = []
        self._collection_receipt_in_progress = False
        outer.addStretch()
        self._refresh_collections()
        return page

    def _refresh_collections(self) -> None:
        if self.repository is None:
            return
        if hasattr(self, 'person_receipt_panel'):
            self.person_receipt_panel.refresh()
        people = [
            person for person in self.repository.list_people()
            if int(person["active"]) == 1
        ]
        self._fill_combo(self.extra_person, [(str(p["name"]), str(p["id"])) for p in people])
        self._refresh_collection_items()
        self._collection_history_rows = self.repository.list_receipt_history()
        issues = self.repository.receipt_inconsistencies()
        self.collection_integrity_warning.setText(
            f'{len(issues)} aplicación(es) de abonos anulados detectada(s). '
            'No se cuentan como dinero recibido activo. No se modificaron los registros.' if issues else '')
        self.collection_integrity_warning.setToolTip('\n'.join(
            f"Abono {i['payment_id']} · cuenta {i['receivable_id']} · {format_money(i['amount_cents'])}"
            for i in issues))
        self.collection_integrity_warning.setVisible(bool(issues))
        self._render_collection_history()

    def _render_collection_history(self) -> None:
        selected_id = self._table_id(self.collection_history, 6)
        blocker = QSignalBlocker(self.collection_history)
        role = self.collection_filter.currentData()
        rows = [r for r in self._collection_history_rows if role == "ALL" or r["payment_kind"] == role]
        grouped = {}
        for entry in rows:
            if self.repository.is_global_receipt(entry['id']):
                if entry['id'] not in grouped:
                    grouped[entry['id']] = dict(entry, source_name='Abono global', application_count=0)
                grouped[entry['id']]['application_count'] += 1
        seen = set()
        consolidated = []
        for entry in rows:
            if entry['id'] in grouped:
                if entry['id'] in seen:
                    continue
                seen.add(entry['id'])
                entry = grouped[entry['id']]
                entry['source_name'] = f"Abono global · {entry['application_count']} pedido(s)"
            consolidated.append(entry)
        rows = consolidated
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
                "Anulado" if item["payment_status"] == "CANCELLED" else "Activo",
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
        self._style_collection_table(self.collection_history, (3,))
        if self._consulting_receipt and self._selected_receipt_history():
            self._select_receipt_history()

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
        self._remember_collection_draft()
        self._consulting_receipt = True
        self._show_collection_capture(False)
        self.collection_mode_notice.setText('Consultando abono del '+date_label(str(item['received_at'])[:10])+
            ' · '+str(item['user_name'])+'. Solo lectura. Usa Editar abono seleccionado para modificar este mismo registro.')
        self.collection_return_button.show()
        for field in (self.collection_amount,self.collection_received_date,self.collection_reference):
            field.setReadOnly(True)
        self.record_collection_button.setEnabled(False)
        with QSignalBlocker(self.collection_items):
            self.collection_items.clearSelection()
        self.collection_payment_identity.set_instrument(None)
        self.collection_selected_details.setText(
            f"<b>{escape(str(item['user_name']))}</b> · {escape(str(item['source_name'] or 'Sin comercio identificado'))}<br>"
            f"{escape(self._participation_label(item['payment_kind']))} · Abono: <b>{escape(format_money(int(item['amount_cents'])))}</b>"
        )
        self.collection_current_balance.setText(
            f"Abono seleccionado: {item['user_name']} · "
            f"{format_money(int(item['amount_cents']))} · "
            f"{'ANULADO' if item['payment_status'] == 'CANCELLED' else 'Activo'}"
        )
        applications = [r for r in self._collection_history_rows if r['id'] == item['id']]
        self.collection_selected_details.setText(self.collection_selected_details.text()
            + '<br>Estado: '+('Anulado' if item['payment_status']=='CANCELLED' else 'Activo')
            + ' · Fecha: '+escape(date_label(str(item['received_at'])[:10]))
            + ' · Referencia: '+escape(str(item['reference'] or 'Sin referencia'))
            + '<br>'+'<br>'.join(escape(str(r['source_name']))+' · '
                +escape(format_money(int(r['application_cents'] or 0)))+' · '
                +('Aplicación activa' if r['application_status']=='ACTIVE' else 'Aplicación anulada' if r['application_status']=='CANCELLED' else 'Sin aplicación') for r in applications))
        if self.repository.is_global_receipt(item['id']):
            self.collection_current_balance.setText(self.collection_current_balance.text() +
                '\nAbono global: edición de fecha/referencia; para cambiar importe o reparto, anula completo y registra el correcto.')

    def _remember_collection_draft(self):
        if self._collection_return_context is not None:return
        self._collection_return_context = dict(
            role=self.collection_filter.currentData(),
            receivable=self._table_id(self.collection_items,7),
            values=[f.text() for f in (self.collection_amount,self.collection_received_date,self.collection_reference)],
            history=self.collection_history_toggle.isChecked(),
            scroll=self.collections_scroll.verticalScrollBar().value())

    def _show_collection_capture(self, visible):
        self.collection_capture_form.setVisible(visible)
        self.collection_details_toggle.setVisible(visible)
        self.collection_details.setVisible(visible and self.collection_details_toggle.isChecked())

    def _return_to_collection_draft(self):
        context=self._collection_return_context
        if context is None:return
        self._consulting_receipt=False
        self._show_collection_capture(True)
        with QSignalBlocker(self.collection_filter):
            self.collection_filter.setCurrentIndex(self.collection_filter.findData(context['role']))
        with QSignalBlocker(self.collection_history):self.collection_history.clearSelection()
        self._refresh_collection_items()
        self._render_collection_history()
        with QSignalBlocker(self.collection_items):
            self.collection_items.clearSelection()
            if context['receivable']:self._search_select(self.collection_items,7,context['receivable'])
        self._show_collection_details()
        for field,value in zip((self.collection_amount,self.collection_received_date,self.collection_reference),context['values']):
            field.setReadOnly(False)
            field.setText(value)
        self.collection_history_toggle.setChecked(context['history'])
        self.collections_scroll.verticalScrollBar().setValue(context['scroll'])
        self.collection_mode_notice.setText('Nuevo abono · selección y borrador recuperados. Registrar crea un abono nuevo; no edita el historial.')
        self.collection_return_button.hide()
        self._collection_return_context=None
        self._update_action_states()

    def _edit_selected_receipt(self) -> None:
        item = self._selected_receipt_history()
        if item is None:
            self._show_error("Selecciona un abono en el historial.")
            return
        from valenza.gui.receipt_editor import ReceiptEditDialog
        dialog = ReceiptEditDialog(item, self.repository.is_global_receipt(item['id']), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            dialog.deleteLater()
            return
        try:
            amount = self._parse_mxn_to_cents(dialog.amount.text())
            edited_date = dialog.received_at.text().strip()
            self.repository.update_user_payment(
                str(item["id"]),
                received_at=edited_date,
                amount_cents=amount,
                reference=dialog.reference.text().strip() or None,
            )
        except (ValueError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        finally:
            dialog.deleteLater()
        self.data_changed.emit("collections")
        self._show_saved_information("El abono quedó actualizado.", 'Cobros → Ver historial: '+str(item['user_name'])+' · '+date_label(edited_date)+' · '+str(item['source_name']))

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
        monthly = self.repository.collection_monthly_summaries()
        personal = sum(int(i["remaining_cents"]) for i in items if i["participant_role"] == "PERSONAL")
        family = sum(int(i["remaining_cents"]) for i in items if i["participant_role"] == "FAMILY")
        unknown = sum(int(i["remaining_cents"]) for i in items if i["participant_role"] == "UNKNOWN")
        self.collection_totals.setText(
            f"Mi parte pendiente: {format_money(personal)} · "
            f"Cobros familiares pendientes: {format_money(family)}"
            + (f" · Históricos por revisar: {format_money(unknown)}" if unknown else "")
        )
        self.collection_personal_card.findChild(QLabel, 'summaryAmount').setText(format_money(personal))
        self.collection_family_card.findChild(QLabel, 'summaryAmount').setText(format_money(family))
        self.collection_totals.setVisible(bool(unknown))
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
                format_money(monthly[item['receivable_id']]['current_cents']),
                format_money(monthly[item['receivable_id']]['future_cents']),
                format_money(monthly[item['receivable_id']]['overdue_cents']),
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
                f"Pendiente: {self.collection_items.item(row, 5).text()} · "
                f"{self.collection_items.item(row, 6).text()}"
            )
        self.collection_items.resizeRowsToContents()
        self._style_collection_table(self.collection_items, (3, 4, 5, 11, 12, 13))
        self.collections_empty_notice.setVisible(self.collection_items.rowCount() == 0)
        self._show_collection_details()

    def _style_collection_table(self, table, money_columns):
        for row in range(table.rowCount()):
            for column in money_columns:
                item = table.item(row, column)
                if item:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            for column in (1, 2) if table is self.collection_history else (0, 2, 5):
                item = table.item(row, column)
                if item:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
        visible_rows = min(7, max(1, table.rowCount()))
        height = table.horizontalHeader().height() + 4
        height += sum(max(32, table.rowHeight(r)) for r in range(visible_rows))
        height += table.horizontalScrollBar().sizeHint().height()
        table.setFixedHeight(height)

    def _reflow_collections(self):
        narrow = self.collections_scroll.viewport().width() < 950
        payment = self.collection_payment_layout
        payment.removeWidget(self.record_collection_button)
        payment.addWidget(self.record_collection_button, 2 if narrow else 1, 1 if narrow else 2)
        details = self.collection_date_layout
        fields = (self.collection_reference, self.collection_received_date)
        for widget in (*self.collection_date_labels, *fields):
            details.removeWidget(widget)
        for index, (label, field) in enumerate(zip(self.collection_date_labels, fields)):
            details.addWidget(label, index if narrow else 0, 0 if narrow else index * 2)
            details.addWidget(field, index if narrow else 0, 1 if narrow else index * 2 + 1)
        extras = self.collection_extras_layout
        rows = ((self.collection_extras_labels[0], self.extra_person),
                (self.collection_extras_labels[1], self.extra_amount, self.extra_description, self.record_extra_button),
                (self.collection_extras_labels[2], self.fee_amount, self.fee_description, self.record_fee_button))
        for widgets in rows:
            for widget in widgets:
                extras.removeWidget(widget)
        extras.removeWidget(self.collection_extras_explanation)
        for index, widgets in enumerate(rows):
            row = index * 2 if narrow else index
            for column, widget in enumerate(widgets):
                extras.addWidget(widget, row + (column // 2 if narrow else 0), column % 2 if narrow else column)
        extras.addWidget(self.collection_extras_explanation, 6 if narrow else 3, 0, 1, 2 if narrow else 4)

    def _show_collection_details(self):
        self.collection_payment_identity.set_instrument(None)
        row = self._selected_row(self.collection_items)
        if row is None:
            self.collection_selected_details.setText('Selecciona una deuda para consultar sus importes.')
            return
        identity = self.collection_items.item(row, 7).text()
        entry = next((i for i in self.repository.list_collection_items() if i['receivable_id'] == identity), None)
        if entry and entry.get('order_id'):
            order = self.repository.get_order(entry['order_id'])
            if order:
                self.collection_payment_identity.set_instrument(self._brand_instrument(order['instrument_id']))
        values = [self.collection_items.item(row, c).text() for c in (0, 2, 3, 4, 5, 10)]
        self.collection_selected_details.setText(
            f'<b>{escape(values[0])}</b> · {escape(values[1])} · {escape(values[5])}<br>'
            f'Asignado: <b>{escape(values[2])}</b> &nbsp; Abonado: <b>{escape(values[3])}</b>'
            f' &nbsp; Pendiente: <b>{escape(values[4])}</b>')

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
        self._show_collection_details()
        row = self._selected_row(self.collection_items)
        if row is None:
            self.collection_current_balance.setText(
                "Selecciona una cuenta para ver el saldo."
            )
            return
        self._consulting_receipt=False
        self._show_collection_capture(True)
        for field in (self.collection_amount,self.collection_received_date,self.collection_reference):field.setReadOnly(False)
        self.collection_mode_notice.setText('Nuevo abono para la participación seleccionada. Registrar crea un abono nuevo; no modifica un abono del historial.')
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
        monthly = self.repository.collection_monthly_summaries()[receivable_id]
        self.collection_current_balance.setText(
            f"{self._participation_label(item['participant_role'])}: "
            f"pendiente {format_money(remaining_cents)} · {item['status']}\n"
            f"{item['source_kind']} · {item['source_date'] or 'Fecha por revisar'}"
        )
        self.collection_current_balance.setWordWrap(True)
        if monthly['is_msi']:
            self.collection_current_balance.setText(
                f"Deuda total del plan pendiente: {format_money(remaining_cents)}\n"
                f"Este mes: {format_money(monthly['current_cents'])} · "
                f"Meses futuros: {format_money(monthly['future_cents'])} · "
                f"Meses anteriores pendientes: {format_money(monthly['overdue_cents'])} · "
                f"Sin fecha: {format_money(monthly['undated_cents'])}")
        self.record_collection_button.setText(
            "Registrar abono personal" if item["participant_role"] == "PERSONAL" else "Registrar abono"
        )
        self.collection_amount.setText(
            f"{Decimal(monthly['current_cents']) / Decimal('100'):.2f}"
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
            receipt_description = self.collection_items.item(row,0).text()+' · '+self.collection_items.item(row,2).text()+' · '+date_label(self.collection_received_date.text().strip())
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
        self._show_saved_information("Se actualizó la participación. No se registró ningún pago bancario.", 'Cobros → Ver historial: '+receipt_description)

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
        apply_warm_surface(page, 'warmSettings')
        layout = QVBoxLayout(page)
        title = QLabel("Configuración")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        notice = QLabel(
            "Elige al propietario de Valenza y administra tus respaldos. "
            "Cambiar el propietario no modifica pedidos ni deudas anteriores."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)

        owner_card, owner_body = warm_section('Personas y propietario')
        layout.addWidget(owner_card)
        self.owner_current = QLabel(); self.owner_current.setWordWrap(True)
        owner_body.addWidget(self.owner_current)
        self.owner_picker = QComboBox()
        self.owner_picker.setAccessibleName('Persona activa para configurar propietario')
        owner_body.addWidget(self.owner_picker)
        self.owner_picker.currentIndexChanged.connect(self._pick_owner_person)
        self.owner_people_table = QTableWidget(0, 4)
        self.owner_people_table.setParent(owner_card)
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
        self.owner_people_table.hide()

        self.owner_selection = QLabel(
            "Selecciona una persona activa para configurar el propietario."
        )
        self.owner_selection.setWordWrap(True)
        owner_body.addWidget(self.owner_selection)
        self.configure_owner_button = QPushButton("Configurar propietario")
        self.configure_owner_button.setObjectName("configureOwnerButton")
        self.configure_owner_button.clicked.connect(self._configure_owner)
        owner_body.addWidget(self.configure_owner_button, alignment=Qt.AlignmentFlag.AlignLeft)
        security, security_body = warm_section('Seguridad y respaldos')
        layout.addWidget(security)
        explanation = QLabel('Crear respaldo conserva una copia cifrada y verificada. Restaurar reemplaza los datos activos y guarda antes una copia de seguridad.')
        explanation.setWordWrap(True); security_body.addWidget(explanation)
        maintenance = QGridLayout()
        for column, title, slot in ((0, 'Crear respaldo cifrado', self._create_backup),
                                    (1, 'Restaurar respaldo', self._restore_backup),
                                    (2, 'Diagnóstico de integridad', self._run_integrity)):
            button = QPushButton(title)
            if column == 1: button.setObjectName('dangerAction')
            button.clicked.connect(slot)
            if column < 2:
                button.setEnabled(self.database.encrypted)
            if column < 2:
                maintenance.addWidget(button, 0, column, alignment=Qt.AlignmentFlag.AlignLeft)
            else:
                diagnostic, diagnostic_body = warm_section('Diagnóstico e integridad')
                layout.addWidget(diagnostic)
                button.setText('Ejecutar diagnóstico')
                diagnostic_body.addWidget(button, alignment=Qt.AlignmentFlag.AlignLeft)
        maintenance.setColumnStretch(2, 1)
        security_body.addLayout(maintenance)
        self.maintenance_result = QTextEdit()
        self.maintenance_result.setReadOnly(True)
        self.maintenance_result.setMinimumHeight(90)
        self.maintenance_result.setPlaceholderText('Restaurar requiere confirmación y crea un respaldo cifrado de la base actual.')
        results_toggle = QPushButton('Mostrar resultados')
        results_toggle.setCheckable(True)
        diagnostic_body.addWidget(results_toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        self.maintenance_result.hide()
        results_toggle.toggled.connect(self.maintenance_result.setVisible)
        self.maintenance_result.textChanged.connect(lambda: results_toggle.setChecked(True))
        diagnostic_body.addWidget(self.maintenance_result)
        layout.addStretch()
        self._refresh_owner_people()
        return self._admin_scroll(page)

    def _pick_owner_person(self):
        identity = self.owner_picker.currentData()
        self.owner_people_table.clearSelection()
        for row in range(self.owner_people_table.rowCount()):
            if self.owner_people_table.item(row, 0).text() == identity:
                self.owner_people_table.selectRow(row)
                break

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

    def _export_family_pdf(self, user_id=None):
        if not user_id or isinstance(user_id,bool):
            row = self._selected_row(self.collection_items)
            if row is None:
                self._show_error('Selecciona una participación de la persona que quieres consultar.')
                return
            user_id = self.collection_items.item(row, 1).text()
        path, _ = QFileDialog.getSaveFileName(self, 'Guardar estado de cuenta de esta persona', 'estado-de-cuenta.pdf', 'PDF (*.pdf)')
        if not path:
            return
        try:
            write_family_pdf(self.repository.family_statement(user_id), path, repository=self.repository)
        except ImportError:
            self._show_error('Instala la dependencia local PyMuPDF para generar PDF.')
            return
        except Exception:
            self._show_error('No se pudo generar el PDF. Comprueba el destino y sus permisos. No se modificaron movimientos.')
            return
        self._show_information('Estado de cuenta PDF generado: '+str(Path(path).resolve())+' · No se modificaron saldos.')

    def _toggle_personal_privacy(self, visible):
        self.dashboard_privacy.setText('👁 Ocultar importes' if visible else '👁 Mostrar importes')
        self.dashboard_privacy.setAccessibleName('Ocultar importes personales' if visible else 'Mostrar importes personales')
        self._refresh_dashboard()

    def _show_result_breakdown(self, visible):
        self.dashboard_result_details.setVisible(visible)
        if not visible or self.repository is None:
            return
        if not self.dashboard_privacy.isChecked():
            self.dashboard_result_details.setPlainText('Importes personales ocultos. ' + EXPLANATION)
            return
        projection = personal_result(self.repository)
        rows = projection['rows']
        parts = ['<b>Resultado personal previsto · por operación</b><br>']
        for number,row in enumerate(rows,1):
            parts.append(f"<p><b>{escape(row['merchant'])}</b> · {escape(date_label(row['date']))} · Operación {number}<br>Costo efectivo: {format_money(row['cost_cents'])} · Asignado a familiares: {format_money(row['family_cents'])}<br>Resultado personal previsto {result_label(row['result_cents'])}: <b>{format_money(abs(row['result_cents']))}</b></p>")
        total = projection['result_cents']
        parts.append(f"<p>Total costo efectivo: {format_money(sum(r['cost_cents'] for r in rows))}<br>Total asignado a familiares: {format_money(sum(r['family_cents'] for r in rows))}<br><b>Resultado personal previsto total {result_label(total)}: {format_money(abs(total))}</b></p>{EXPLANATION}")
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
        people = self.repository.list_people()
        owners = [p['name'] for p in people if p['is_owner']]
        self.owner_current.setText('Propietario actual: ' + (', '.join(owners) or 'Sin configurar'))
        with QSignalBlocker(self.owner_picker):
            self.owner_picker.clear()
            self.owner_picker.addItem('Selecciona una persona activa', None)
            for person in people:
                if person['active']: self.owner_picker.addItem(person['name'], str(person['id']))
            self.owner_picker.setCurrentIndex(max(0, self.owner_picker.findData(selected_id)))

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
        apply_warm_surface(page, 'warmUsers')
        layout = QVBoxLayout(page)
        title = QLabel("Usuarios")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        notice = QLabel(
            "Administra las personas de la base activa. Desactivar una persona "
            "conserva sus movimientos y deudas históricas."
        )
        notice.setObjectName("secondaryText")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.people_summary = QLabel(); self.people_summary.setWordWrap(True)
        layout.addWidget(self.people_summary)
        self.people_empty = QLabel('Aún no hay personas. Escribe un nombre para crear la primera.')
        self.people_empty.setWordWrap(True); layout.addWidget(self.people_empty)
        editor, editor_body = warm_section('Persona · crear o editar selección')
        layout.addWidget(editor)

        form = QGridLayout()
        form.addWidget(QLabel("Nombre *"), 0, 0)
        self.person_name = QLineEdit()
        self.person_name.setAccessibleName('Nombre de la persona')
        self.person_name.setPlaceholderText("Nombre de la persona")
        form.addWidget(self.person_name, 0, 1)
        self.person_owner = QCheckBox("Es propietario")
        self.person_owner.setToolTip('Identidad explícita. Cambiar el propietario requiere confirmación; no reclasifica deudas históricas.')
        form.addWidget(self.person_owner, 0, 2)
        editor_body.addLayout(form)

        actions = QGridLayout()
        self.create_person_button = QPushButton("Crear persona")
        self.create_person_button.setObjectName('primaryAction')
        self.create_person_button.clicked.connect(self._create_person)
        actions.addWidget(self.create_person_button, 0, 0)
        self.update_person_button = QPushButton("Guardar persona")
        self.update_person_button.clicked.connect(self._update_person)
        actions.addWidget(self.update_person_button, 0, 1)
        self.deactivate_person_button = QPushButton("Desactivar")
        self.deactivate_person_button.setObjectName('dangerAction')
        self.deactivate_person_button.clicked.connect(self._deactivate_person)
        actions.addWidget(self.deactivate_person_button, 1, 0)
        self.reactivate_person_button = QPushButton("Reactivar")
        self.reactivate_person_button.clicked.connect(self._reactivate_person)
        actions.addWidget(self.reactivate_person_button, 1, 1)
        clear_button = QPushButton("Limpiar selección")
        clear_button.clicked.connect(self._clear_person_form)
        actions.addWidget(clear_button, 1, 2)
        for index in range(actions.count()):
            actions.itemAt(index).setAlignment(Qt.AlignmentFlag.AlignLeft)
        actions.setColumnStretch(3, 1)
        editor_body.addLayout(actions)

        self.people_table = QTableWidget(0, 4)
        self.people_table.setObjectName("peopleTable")
        self.people_table.setHorizontalHeaderLabels(["ID", "Nombre", "Tipo", "Estado"])
        self.people_table.setColumnHidden(0, True)
        self.people_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.people_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.people_table.itemSelectionChanged.connect(self._load_selected_person)
        layout.addWidget(self.people_table)
        self.people_table.setMaximumHeight(260)
        self.people_table.verticalHeader().setVisible(False)
        self.people_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addStretch()
        self._refresh_people()
        return self._admin_scroll(page)

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
        apply_warm_surface(page, 'warmOrders')
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        self.orders_scroll = WarmScrollArea()
        self.orders_scroll.setWidgetResizable(True)
        self.orders_scroll.viewport().installEventFilter(self)
        content = QWidget()
        content.setObjectName('warmOrdersContent')
        outer = QVBoxLayout(content)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(8)
        self.orders_scroll.setWidget(content)
        root.addWidget(self.orders_scroll)
        heading = QHBoxLayout()
        title = QLabel('Pedidos')
        title.setObjectName('pageTitle')
        heading.addWidget(title)
        heading.addStretch()
        outer.addLayout(heading)
        toolbar = FlowLayout()
        self.new_expense_button = QPushButton('Nuevo gasto')
        self.new_expense_button.setObjectName('primaryAction')
        self.new_expense_button.setIcon(line_icon('card', '#fffaf4'))
        self.new_expense_button.clicked.connect(self._open_manual_expense)
        toolbar.addWidget(self.new_expense_button)
        import_pdf = QPushButton('Importar PDF')
        import_pdf.setIcon(line_icon('receipt'))
        import_pdf.clicked.connect(self._import_order_pdf)
        toolbar.addWidget(import_pdf)
        outer.addLayout(toolbar)
        self.manual_dialog = QDialog(self)
        apply_warm_surface(self.manual_dialog, 'warmExpense')
        self.manual_dialog.setWindowTitle('Nuevo gasto')
        self.manual_dialog.resize(760, 580)
        self.manual_dialog.setMinimumSize(480, 280)
        dialog_root = QVBoxLayout(self.manual_dialog)
        dialog_root.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.manual_heading = QLabel('Nuevo gasto')
        self.manual_heading.setObjectName('pageTitle')
        dialog_root.addWidget(self.manual_heading)
        self.manual_action_notice = QLabel()
        self.manual_action_notice.setObjectName('secondaryText')
        self.manual_action_notice.setWordWrap(True)
        dialog_root.addWidget(self.manual_action_notice)
        scroll = WarmScrollArea(self.manual_dialog)
        self.manual_scroll = scroll
        scroll.viewport().installEventFilter(self)
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(12, 10, 12, 10)
        content.setObjectName('warmExpenseContent')
        layout.setSpacing(6)
        notice = QLabel(
            "* Campos obligatorios · Importes en MXN."
        )
        notice.setObjectName("secondaryText")
        notice.setWordWrap(True)
        layout.addWidget(notice)

        general = QFormLayout()
        self.order_merchant = QLineEdit()
        self.order_merchant.setAccessibleName('Comercio de la compra, obligatorio')
        self.order_merchant.setPlaceholderText("Nombre del comercio")
        self.order_date = QLineEdit(date.today().isoformat())
        self.order_date.setAccessibleName('Fecha de compra, AAAA-MM-DD')
        self.order_date.setToolTip('Fecha de compra registrada; no es la fecha de corte ni el vencimiento.')
        self.order_institution = QComboBox()
        self.order_institution.currentIndexChanged.connect(self._refresh_order_instruments)
        self.order_instrument = QComboBox()
        self.order_institution.setAccessibleName('Institución de la compra')
        self.order_instrument.setAccessibleName('Cuenta o tarjeta de la compra')
        self.manual_information_grid = QGridLayout()
        self.manual_information_sections = []
        layout.addLayout(self.manual_information_grid)
        section, section_body = warm_section('Datos del gasto')
        basic = QGridLayout()
        basic.setColumnStretch(1, 1)
        basic.setColumnStretch(3, 1)
        for row, pairs in enumerate(((('Comercio *', self.order_merchant), ('Fecha de compra *', self.order_date)),
                                      (('Institución *', self.order_institution), ('Cuenta / tarjeta *', self.order_instrument)))):
            for column, (text, field) in enumerate(pairs):
                label = QLabel(text); label.setBuddy(field)
                basic.addWidget(label, row * 2, column * 2, 1, 2)
                basic.addWidget(field, row * 2 + 1, column * 2, 1, 2)
        section_body.addLayout(basic)
        self.manual_information_sections.append(section)
        self.manual_information_grid.addWidget(section, 0, 0)
        general.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.order_purchase_mode = QComboBox()
        self.order_purchase_mode.addItem("Contado", "CASH")
        self.order_purchase_mode.addItem("MSI", "MSI")
        self.order_purchase_mode.currentIndexChanged.connect(self._toggle_msi_fields)
        general.addRow("Modalidad", self.order_purchase_mode)
        self.order_installments = QSpinBox()
        self.order_installments.setRange(1, 60)
        self.order_installments.setValue(3)
        self.order_amount_basis = QComboBox()
        self.order_amount_basis.setAccessibleName('Los importes capturados corresponden al total o a cada mensualidad')
        self.order_amount_basis.addItem('TOTAL de la compra', 'TOTAL')
        self.order_amount_basis.addItem('CADA MENSUALIDAD', 'INSTALLMENT')
        self.order_amount_basis.currentIndexChanged.connect(self._update_order_preview)
        self.order_installments.valueChanged.connect(self._update_order_preview)
        general.addRow('Base de captura', self.order_amount_basis)
        self.order_basis_note = QLabel('En mensualidades, todos los importes capturados corresponden a una cuota; se multiplican una sola vez por el número de cuotas.')
        self.order_basis_note.setWordWrap(True)
        self.order_basis_note.setToolTip(self.order_basis_note.text())
        self.order_basis_note.setText('Por cuota: conceptos, reparto y cargo se multiplican una sola vez por el plazo.')
        self.order_basis_note.setObjectName('secondaryText')
        general.addRow(self.order_basis_note)
        self.order_basis_label = general.labelForField(self.order_amount_basis)
        self.order_first_due_date = QLineEdit()
        self.order_first_due_date.setAccessibleName('Primer vencimiento MSI, AAAA-MM-DD, obligatorio para un plan nuevo')
        self.order_first_due_date.setPlaceholderText("AAAA-MM-DD; confirmar con institución")
        self.order_interest = MxnLineEdit()
        self.order_interest.setPlaceholderText("0.00")
        self.order_interest.textChanged.connect(self._update_order_preview)
        general.addRow("Número de cuotas", self.order_installments)
        general.addRow("Vencimiento primera cuota *", self.order_first_due_date)
        general.addRow("Intereses del plan (MXN, opcional)", self.order_interest)
        self.order_msi_labels = tuple(general.labelForField(w) for w in (
            self.order_installments, self.order_first_due_date, self.order_interest
        ))
        self._toggle_msi_fields()
        section_body.addLayout(general)

        amounts = QGridLayout()
        self.order_original = MxnLineEdit()
        self.order_original.setPlaceholderText("5000.00")
        self.order_charged = MxnLineEdit()
        self.order_original.setAccessibleName('Suma de los conceptos capturados en MXN')
        self.order_charged.setAccessibleName('Cargo real capturado en MXN, obligatorio')
        self.order_charged.setPlaceholderText("5000.00")
        self.order_discount = QLabel("$0.00 MXN")
        self.order_exception = QLabel()
        self.order_exception.setWordWrap(True)
        amounts.addWidget(QLabel("Total de conceptos (MXN)"), 0, 0)
        amounts.addWidget(self.order_original, 1, 0)
        amounts.addWidget(QLabel("Cargo real (MXN) *"), 0, 1)
        amounts.addWidget(self.order_charged, 1, 1)
        self.order_discount_caption = QLabel('Descuento calculado')
        amounts.addWidget(self.order_discount_caption, 2, 0)
        amounts.addWidget(self.order_discount, 2, 1)
        amounts.addWidget(self.order_exception, 3, 0, 1, 2)
        self.correct_charge_button = QPushButton('Corregir cargo real')
        self.correct_charge_button.clicked.connect(self._correct_existing_order_charge)
        self.correct_charge_button.hide()
        amounts.addWidget(self.correct_charge_button, 4, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
        self.manual_edit_id = None
        self.manual_expected_concepts = None
        self.manual_dialog.rejected.connect(self._cancel_manual_edit)
        self.manual_concepts = QTableWidget(0, 3)
        self.manual_concepts.setAccessibleName('Conceptos: descripción, importe y persona o reparto compartido')
        self.manual_concepts.setHorizontalHeaderLabels(['Concepto', 'Importe (MXN)', 'Persona / Dividir'])
        self.manual_concepts.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.manual_concepts.setColumnWidth(0, 220)
        self.manual_concepts.setColumnWidth(1, 125)
        self.manual_concepts.setColumnWidth(2, 270)
        self.manual_concepts.horizontalHeader().setStretchLastSection(True)
        self.manual_concepts.setWordWrap(True)
        self.manual_concepts.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.manual_concepts.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.manual_concepts.setMinimumHeight(180)
        self.manual_concepts.verticalHeader().hide()
        concept_section, concept_body = warm_section('Conceptos y reparto')
        self.manual_concept_section = concept_section
        concept_body.addWidget(self.manual_concepts)
        layout.addWidget(concept_section)
        concepts_actions = QHBoxLayout()
        add_concept = QPushButton('Agregar concepto')
        add_concept.clicked.connect(lambda: self._add_manual_concept())
        remove_concept = QPushButton('Eliminar concepto seleccionado')
        remove_concept.clicked.connect(self._remove_manual_concept)
        concepts_actions.addWidget(add_concept)
        concepts_actions.addWidget(remove_concept)
        concept_body.addLayout(concepts_actions)
        summary_section, summary_body = warm_section('Importes y reparto que se guardarán')
        summary_body.addLayout(amounts)
        layout.addWidget(summary_section)
        self.manual_concepts.itemChanged.connect(self._update_manual_concepts)

        self.order_allocation_label = QLabel('Reparto por persona')
        summary_body.addWidget(self.order_allocation_label)
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
        summary_body.addWidget(self.order_allocations_table)
        # Compatibility-only editor for callers of the previous API. It is
        # intentionally not added to the redesigned layout.
        self.order_amount = MxnLineEdit()
        self.order_user = QComboBox()
        self.order_summary = FinancialSummary()
        self.order_summary.setObjectName("orderSummary")
        self.order_summary.setWordWrap(True)
        summary_body.addWidget(self.order_summary)
        self.save_order_button = QPushButton("Guardar gasto")
        self.save_order_button.setObjectName("primaryAction")
        self.save_order_button.clicked.connect(self._save_order)
        scroll.setWidget(content)
        dialog_root.addWidget(scroll, 1)
        footer = QHBoxLayout()
        self.cancel_manual_button = QPushButton('Cerrar y conservar borrador')
        self.cancel_manual_button.clicked.connect(self.manual_dialog.reject)
        self.manual_review_button = QPushButton('Resumen')
        self.manual_review_button.setAccessibleName('Ir al resumen de importes y reparto, sin guardar')
        self.manual_review_button.setToolTip('Revisa los importes y el reparto sin modificar la captura.')
        self.manual_review_button.clicked.connect(lambda: self.manual_scroll.ensureWidgetVisible(summary_section))
        footer.addWidget(self.manual_review_button)
        footer.addStretch()
        footer.addWidget(self.cancel_manual_button)
        footer.addWidget(self.save_order_button)
        self.save_order_button.setIcon(line_icon('receipt', '#fffaf4'))
        self.cancel_manual_button.setIcon(line_icon('receipt'))
        dialog_root.addLayout(footer)
        QWidget.setTabOrder(self.manual_review_button, self.cancel_manual_button)
        QWidget.setTabOrder(self.cancel_manual_button, self.save_order_button)
        layout = outer

        self.order_filter = QComboBox()
        self.order_filter.setAccessibleName('Filtrar pedidos por estado')
        self.order_filter.addItem("Activos", "ACTIVE")
        self.order_filter.addItem("Anulados", "CANCELLED")
        self.order_filter.addItem("Todos", "ALL")
        self.order_filter.currentIndexChanged.connect(self._refresh_orders)
        toolbar.addWidget(QLabel('Mostrar:'))
        toolbar.addWidget(self.order_filter)
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
        self.orders_table.setMinimumHeight(72)
        self.orders_table.verticalHeader().hide()
        self.orders_table.setAlternatingRowColors(True)
        self.orders_table.setWordWrap(False)
        self.orders_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        for column in range(1, 8):
            self.orders_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.orders_table.itemSelectionChanged.connect(self._show_order_detail)
        layout.addWidget(self.orders_table)
        self.orders_empty_notice = QLabel()
        self.orders_empty_notice.setObjectName('secondaryText')
        self.orders_empty_notice.setWordWrap(True)
        layout.addWidget(self.orders_empty_notice)
        self.cancel_order_button = QPushButton("Anular pedido seleccionado")
        self.cancel_order_button.setObjectName('dangerAction')
        self.cancel_order_button.clicked.connect(self._cancel_selected_order)
        self.edit_order_button = QPushButton("Editar comercio")
        self.edit_order_button.clicked.connect(self._edit_order_merchant)
        self.accredit_refund_button = QPushButton('Acreditar devolución pendiente')
        self.accredit_refund_button.clicked.connect(self._confirm_pending_product_refund)
        self.accredit_refund_button.setEnabled(False)
        self.repurchase_button = QPushButton('Lo compré de nuevo')
        self.repurchase_button.clicked.connect(self._register_product_repurchase)
        self.repurchase_button.setEnabled(False)
        self.edit_concepts_button = QPushButton('Editar conceptos y reparto')
        self.edit_concepts_button.clicked.connect(self._edit_manual_expense)
        self.msi_button = QPushButton('MSI / mensualidades')
        self.msi_button.clicked.connect(self._msi_dialog)
        self.order_actions_grid = QGridLayout()
        self.order_action_groups = []
        for caption, buttons in [('Editar', (self.edit_order_button, self.edit_concepts_button)),
                                 ('Devoluciones y recompra', (self.accredit_refund_button, self.repurchase_button)),
                                 ('Financiamiento', (self.msi_button,)),
                                 ('Acción delicada', (self.cancel_order_button,))]:
            group, body = warm_section(caption)
            for button in buttons:
                button.setIcon(line_icon('calendar' if button is self.msi_button else 'receipt'))
                body.addWidget(button)
            body.addStretch()
            self.order_action_groups.append(group)
            self.order_actions_grid.addWidget(group, len(self.order_action_groups)-1, 0)
        layout.addLayout(self.order_actions_grid)
        self.order_detail = QTextEdit()
        self.order_detail.setObjectName("orderDetail")
        self.order_detail.setReadOnly(True)
        self.order_detail.setPlaceholderText('Selecciona un pedido para consultar compra, devolución, participaciones y beneficio personal.')
        self.order_detail.setMinimumHeight(90)
        self.order_detail.setMaximumHeight(230)
        detail_section, detail_body = warm_section('Detalle del pedido seleccionado')
        self.order_payment_identity = PaymentIdentity()
        detail_body.addWidget(self.order_payment_identity)
        self.order_refund_tracking = QFrame()
        self.order_refund_tracking.setObjectName('refundTracking')
        tracking_body = QVBoxLayout(self.order_refund_tracking)
        tracking_body.setContentsMargins(0, 4, 0, 6)
        tracking_body.setSpacing(4)
        tracking_title = QLabel('Seguimiento del reembolso')
        tracking_title.setObjectName('sectionTitle')
        self.order_refund_tracking_text = QLabel()
        self.order_refund_tracking_text.setWordWrap(True)
        self.order_refund_tracking_text.setTextFormat(Qt.TextFormat.RichText)
        self.order_refund_tracking_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.order_refund_tracking_text.setAccessibleName('Seguimiento del reembolso registrado')
        tracking_body.addWidget(tracking_title)
        tracking_body.addWidget(self.order_refund_tracking_text)
        self.order_refund_tracking.hide()
        detail_body.addWidget(self.order_refund_tracking)
        detail_body.addWidget(self.order_detail)
        layout.addWidget(detail_section)
        layout.addStretch()
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
        self.manual_heading.setText('Editar conceptos y reparto' if self.manual_edit_id else 'Nuevo gasto')
        self.cancel_manual_button.setText('Descartar cambios' if self.manual_edit_id else 'Cerrar y conservar borrador')
        self.save_order_button.setText('Guardar conceptos y reparto' if self.manual_edit_id else 'Guardar gasto')
        self.manual_action_notice.setText(
            'Cerrar descarta los cambios sin guardar. Las correcciones de cargo ya confirmadas se conservan.'
            if self.manual_edit_id else
            'Al cerrar, este borrador se conserva mientras Valenza siga abierta.')
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
        from valenza.gui.pdf_import import ProductAssignment, pesos
        concept = concept or dict(description='', amount_cents=0, allocations={})
        row = self.manual_concepts.rowCount()
        with QSignalBlocker(self.manual_concepts):
            self.manual_concepts.insertRow(row)
            description = QTableWidgetItem(concept['description'])
            amount = QTableWidgetItem(pesos(concept['amount_cents']))
            amount.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
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
                    self.order_original.setText(f"{Decimal(sum(c['amount_cents'] for c in concepts)) / Decimal('100'):.2f}")
                with QSignalBlocker(self.order_allocations_table):
                    self._reset_order_allocations()
                    for row in range(self.order_allocations_table.rowCount()):
                        person = self.order_allocations_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                        self.order_allocations_table.item(row, 1).setText(f"{Decimal(totals.get(person, 0)) / Decimal('100'):.2f}")
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
        if not order:
            return
        if self.manual_concepts.rowCount() and self.manual_edit_id != order_id:
            if QMessageBox.question(self, 'Captura en proceso', '¿Descartar el borrador para editar este gasto?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
        self._clear_order_form()
        self.manual_edit_id = order_id
        self.order_discount_caption.setText('Descuento guardado')
        self.correct_charge_button.show()
        self.manual_expected_concepts = self.repository.editable_order_concepts(order)
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
        self.order_charged.setEnabled(True)
        self.order_charged.setToolTip('Escribe el cargo correcto. Al guardar se solicitarán motivo y confirmación; no cambia el descuento ni el reparto.')
        for concept in self.manual_expected_concepts:
            self._add_manual_concept(concept)
        self.manual_dialog.setWindowTitle('Editar conceptos y reparto')
        self._open_manual_expense()

    def _correct_existing_order_charge(self, _checked=False, *, use_editor_value=False):
        identity = self.manual_edit_id
        order = self.repository.get_order(identity) if identity else None
        if not order:
            return
        try:
            text = self.order_charged.text()
            draft = self._parse_mxn_to_cents(text)
            if not use_editor_value and draft == order['charged_cents']:
                text, accepted = QInputDialog.getText(self.manual_dialog, 'Corregir cargo real',
                    f"Cargo actual: {format_money(order['charged_cents'])}\nNuevo cargo real (MXN):",
                    QLineEdit.EchoMode.Normal, f"{Decimal(order['charged_cents']) / 100:.2f}")
                if not accepted:
                    return
            new = self._parse_mxn_to_cents(text)
            if new == order['charged_cents']:
                return True
            reason, accepted = QInputDialog.getText(self.manual_dialog, 'Motivo de corrección',
                'Motivo y referencia del cargo bancario correcto:')
            if not accepted:
                return
            if not reason.strip():
                raise ValueError('Indica el motivo de la corrección.')
            if QMessageBox.question(self.manual_dialog, 'Confirmar corrección bancaria',
                    f"Anterior: {format_money(order['charged_cents'])}\nNuevo: {format_money(new)}\n"
                    f"Diferencia en el saldo calculado de la tarjeta: {format_money(new-order['charged_cents'])}\n"
                    f"Importe original: {format_money(order['original_cents'])}\nDescuento conservado: {format_money(order['discount_cents'])}\n"
                    'Se conservan participaciones y pagos. Se registrará auditoría. ¿Guardar?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            self.repository.correct_order_charge(identity, new, expected_charged_cents=order['charged_cents'], reason=reason)
        except (ValueError, RuntimeError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        self.order_charged.setText(f"{Decimal(new) / 100:.2f}")
        self.data_changed.emit('orders')
        self.manual_action_notice.setText('Cargo real guardado. Los cambios de conceptos y reparto siguen sin guardar; cerrar solo descarta estos últimos.')
        self._show_information('Cargo real corregido; se conservaron el reparto y los pagos.')
        return True

    def _import_order_pdf(self) -> None:
        from valenza.ocr.order_import import read_receipt
        from valenza.gui.pdf_import import ImportPreview
        path, _ = QFileDialog.getOpenFileName(self, 'Importar comprobante', '', 'PDF (*.pdf)')
        if not path:
            return
        try:
            draft = read_receipt(Path(path))
            if ImportPreview(self.repository, draft, self).exec():
                self._refresh_visible_data()
                self._show_information('Pedido importado y guardado.')
        except (ValueError, RuntimeError, OSError) as error:
            self._show_error(self._safe_error(error))

    def _load_order_catalogs(self) -> None:
        self.order_institution.clear()
        for item in self.repository.list_institutions():
            self.order_institution.addItem(brand_icon(str(item["name"]), "institution"), str(item["name"]), item["id"])
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
            self.order_instrument.addItem(brand_icon(self.order_institution.currentText(), "institution"), str(item["alias"]), item["id"])

    def _show_order_detail(self) -> None:
        self.order_refund_tracking.hide()
        self.order_refund_tracking_text.clear()
        self.accredit_refund_button.setEnabled(False)
        self.repurchase_button.setEnabled(False)
        self.repurchase_button.setText('Lo compré de nuevo')
        rows = self.orders_table.selectionModel().selectedRows()
        if not rows:
            self.order_payment_identity.set_instrument(None)
            self.order_detail.clear()
            return
        order_id = self.orders_table.item(rows[0].row(), 8).text()
        order = self.repository.get_order(order_id)
        self.order_payment_identity.set_instrument(self._brand_instrument(order["instrument_id"]) if order else None)
        if order is None:
            return
        lines = [
            f"{order['merchant']} · {date_label(order['ordered_at'])}",
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
        from valenza.gui.refund_tracking import refund_tracking_html
        refund_source = (order if comparison['original_order_id'] == order_id else
                         self.repository.get_order(comparison['original_order_id']))
        if refund_source:
            linked_orders = {r['repurchase']['order_id']: self.repository.get_order(r['repurchase']['order_id'])
                             for r in refund_source.get('product_refunds', []) if r.get('repurchase')}
            tracking = refund_tracking_html(refund_source, linked_orders)
            if comparison['original_order_id'] != order_id and tracking:
                tracking = 'Reembolso del pedido original relacionado.<br>' + tracking
            if tracking:
                self.order_refund_tracking_text.setText(tracking)
                self.order_refund_tracking.show()
        if not evidence:
            lines.extend(['\n2. Devolución, recompra y compensación', 'Sin devolución de producto registrada.'])
        if comparison['original_order_id'] != order_id:
            lines.append(f"Recompra vinculada a {refund_source['merchant'] if refund_source else 'compra original'} · {date_label(refund_source['ordered_at']) if refund_source else 'fecha por consultar'}; "
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
        self.order_detail.setHtml(financial_text_html("\n".join(lines)))

    def _msi_dialog(self):
        identity = self._table_id(self.orders_table,8)
        order = self.repository.get_order(identity) if identity else None
        if not order or order['order_status']!='ACTIVE': return
        dialog,body,save = self._financial_dialog('MSI del pedido existente', save_text='Vincular plan MSI')
        notice = QLabel(f"{order['merchant']} · cargo original {format_money(order['charged_cents'])}. Este plan no crea otro cargo ni otro cobro familiar. Pagos bancarios y abonos familiares permanecen independientes.")
        notice.setWordWrap(True); body.addWidget(notice)
        error = QLabel(); error.setWordWrap(True)
        if not order['financing_plan']:
            form = QFormLayout(); form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            count = QSpinBox(); count.setRange(1,60); count.setValue(3)
            first = QLineEdit(); first.setPlaceholderText('AAAA-MM-DD, según tu banco')
            form.addRow('Plazo en meses',count); form.addRow('Primer vencimiento',first)
            body.addLayout(form)
            estimate = QLabel(); estimate.setWordWrap(True); body.addWidget(estimate)
            def preview():
                each,residual = divmod(order['charged_cents'],count.value())
                estimate.setText(f"Mensualidad prevista: {format_money(each)}" + (f"; {residual} cuota(s) con un centavo adicional." if residual else '.'))
            count.valueChanged.connect(preview); preview(); body.addWidget(error)
            def persist():
                save.setEnabled(False)
                try:
                    anchor = date.fromisoformat(first.text().strip())
                    dates = []
                    for offset in range(count.value()):
                        month_index = anchor.month-1+offset; year=anchor.year+month_index//12; month=month_index%12+1
                        dates.append(date(year,month,min(anchor.day,monthrange(year,month)[1])).isoformat())
                    self.repository.link_order_to_msi(identity,tuple(dates))
                except (ValueError,*DATABASE_ERRORS) as exc:
                    error.setText(self._safe_error(exc)); save.setEnabled(True); return
                dialog.accept(); self.data_changed.emit('msi')
                self._show_information('Plan MSI vinculado al pedido.')
            save.clicked.connect(persist)
        else:
            save.setText('Cerrar'); save.clicked.connect(dialog.accept)
            # Closing remains available through this button, Escape and the title bar.
            dialog.cancel_button.hide()
            saved_notice = QLabel('Cada fecha o ajuste se guarda al aplicarlo. Cerrar no deshace los cambios guardados.')
            saved_notice.setWordWrap(True); body.addWidget(saved_notice)
            feedback = QLabel(); feedback.setObjectName('actionFeedback'); feedback.setWordWrap(True)
            body.addWidget(feedback)
            table = QTableWidget(0,5); table.setHorizontalHeaderLabels(['Cuota','Fecha','Previsto','Pago aplicado','Pendiente'])
            table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
            table.setItemDelegateForColumn(1, RecordedDateDelegate(table))
            table.setMinimumHeight(150); body.addWidget(table)
            total = QLabel(); total.setWordWrap(True); body.addWidget(total)
            records = []
            def refresh():
                records[:] = [i for i in self.repository.list_installments(order['instrument_id']) if i['order_id']==identity]
                table.setRowCount(len(records))
                for row,item in enumerate(records):
                    values=[item['number'],item['due_date'] or 'Por confirmar',format_money(item['principal_cents']+item['interest_cents']),format_money(item['applied_cents']),format_money(item['remaining_cents'])]
                    for column,value in enumerate(values): table.setItem(row,column,QTableWidgetItem(str(value)))
                total.setText(f"Saldo de cuotas previsto: {format_money(sum(i['remaining_cents'] for i in records))}. Solo los pagos bancarios realmente registrados y aplicados cubren estas cuotas. El saldo real de la tarjeta se consulta en Tarjetas.")
                from valenza.finance.monthly import month_totals
                buckets = month_totals([dict(due_date=i['due_date'], amount_cents=i['remaining_cents']) for i in records], self._forecast_date())
                total.setText(total.text() + f"\nPeriodo de vencimiento {self._forecast_date():%Y-%m}: {format_money(buckets['current_cents'])} · Meses futuros: {format_money(buckets['future_cents'])} · Anteriores: {format_money(buckets['overdue_cents'])} · Sin fecha: {format_money(buckets['undated_cents'])}. Previsión; no es el pago confirmado del banco.")
            refresh()
            date_button = QPushButton('Editar fecha de la cuota seleccionada'); body.addWidget(date_button)
            def correct_date():
                feedback.clear()
                row = table.currentRow()
                if row<0: error.setText('Selecciona una cuota.'); return
                value,ok = QInputDialog.getText(dialog,'Guardar fecha de cuota','Fecha AAAA-MM-DD (se guarda al aceptar):',text=records[row]['due_date'] or '')
                if not ok: return
                try: self.repository.correct_installment_due_date(installment_id=records[row]['id'],due_date=value)
                except (ValueError,*DATABASE_ERRORS) as exc: error.setText(self._safe_error(exc)); return
                error.clear(); refresh(); self.data_changed.emit('msi')
                feedback.setText('Fecha de cuota guardada.')
            date_button.clicked.connect(correct_date)
            adjustment = self._money_input(sum(i['remaining_cents'] for i in records))
            reason = QLineEdit(); reason.setPlaceholderText('Motivo: devolución o corrección confirmada')
            form=QFormLayout(); form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            form.addRow('Nuevo saldo previsto',adjustment); form.addRow('Motivo',reason); body.addLayout(form)
            adjust = QPushButton('Aplicar ajuste solo a cuotas previstas'); body.addWidget(adjust)
            def apply_adjustment():
                feedback.clear()
                adjust.setEnabled(False)
                try: self.repository.adjust_msi_remaining(identity,self._read_mxn(adjustment),reason.text())
                except (ValueError,*DATABASE_ERRORS) as exc: error.setText(self._safe_error(exc)); adjust.setEnabled(True); return
                error.clear(); refresh(); self.data_changed.emit('msi'); adjust.setEnabled(True)
                feedback.setText('Ajuste de cuotas previstas guardado.')
            adjust.clicked.connect(apply_adjustment)
            explanation = QLabel('Un ajuste de previsión no acredita dinero ni cambia repartos. Las devoluciones reales siguen registrándose con destino y estado en el pedido.')
            explanation.setWordWrap(True); body.addWidget(explanation); body.addWidget(error)
        dialog.exec()

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
        from valenza.gui.pdf_import import RefundRepurchaseDialog
        refund = refunds[choices.index(selection)]
        result = RefundRepurchaseDialog(self.repository, refund, self).exec()
        self._refresh_visible_data()
        if result:
            self._show_information('Reparto de devolución y recompra guardado.' if refund.get('repurchase') else 'Recompra guardada.')

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
        self._show_information('Devolución acreditada.')

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
            self.purchase_institution.addItem(brand_icon(str(item["name"]), "institution"), str(item["name"]), item["id"])
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
            self.purchase_instrument.addItem(brand_icon(self.purchase_institution.currentText(), "institution"), str(item["alias"]), item["id"])

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

    def _order_input_cents(self, widget: QLineEdit, label: str, *, allow_empty=False) -> int:
        text = widget.text().strip()
        if not text:
            if allow_empty:
                return 0
            raise ValueError(f'{label}: captura el importe; un campo vacío no significa cero.')
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

    def _order_amount_multiplier(self):
        return (self.order_installments.value()
                if self.order_purchase_mode.currentData() == 'MSI'
                and getattr(self, 'order_amount_basis', None) is not None
                and self.order_amount_basis.currentData() == 'INSTALLMENT' else 1)

    def _order_total_inputs(self):
        multiplier = self._order_amount_multiplier()
        original = self._order_input_cents(self.order_original, 'El importe original') * multiplier
        charged = self._order_input_cents(self.order_charged, 'El cargo real') * multiplier
        if hasattr(self, 'manual_concepts') and self.manual_concepts.rowCount():
            totals = {identity:0 for identity, person in self._order_people_catalog().items() if person['active']}
            for concept in self._read_manual_concepts():
                for identity, amount in concept['allocations'].items():
                    totals[identity] = totals.get(identity, 0) + amount
            allocations = tuple(dict(user_id=identity, amount_cents=amount * multiplier)
                                for identity, amount in totals.items())
        else:
            allocations = tuple(dict(a, amount_cents=a['amount_cents'] * multiplier)
                                for a in self._read_order_allocations())
        return original, charged, allocations

    def _update_order_preview(self) -> None:
        if not hasattr(self, "order_summary"):
            return
        try:
            original, charged, allocations = self._order_total_inputs()
        except ValueError:
            self.order_discount.setText('Por confirmar')
            self.order_summary.setText("Completa los importes del pedido, incluido el cargo real.")
            self.save_order_button.setEnabled(False)
            return
        discount = max(original - charged, 0)
        if getattr(self, 'manual_edit_id', None):
            stored = self.repository.get_order(self.manual_edit_id)
            if stored:
                discount = stored['discount_cents']
        self.order_discount.setText(format_money(discount))
        self.order_exception.setText(
            "Cargo superior al original: revisa el total y el cargo antes de guardar."
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
            f"Sin repartir: {format_money(recover - distributed)} · "
            f"Propietario: {format_money(owner)} · "
            f"Cuentas por cobrar: {format_money(receivables)}"
        )
        summary += '\nReparto que se guardará: ' + ' · '.join(
            f"{catalog[str(a['user_id'])]['name']}{' (Yo)' if catalog[str(a['user_id'])]['is_owner'] else ''}: {format_money(a['amount_cents'])}"
            for a in allocations if str(a['user_id']) in catalog)
        if self.order_purchase_mode.currentData() == 'MSI':
            try:
                interest = self._order_input_cents(self.order_interest, 'Intereses', allow_empty=True)
            except ValueError:
                self.order_summary.setText('Revisa los intereses del plan.')
                self.save_order_button.setEnabled(False)
                return
            each, residual = divmod(charged + interest, self.order_installments.value())
            summary = (f'Total de la compra: {format_money(original)} · Principal: {format_money(charged)}'
                       f' · Intereses del plan: {format_money(interest)} · Total del plan: {format_money(charged + interest)}'
                       f' · {self.order_installments.value()} cuotas: {format_money(each)}'
                       + (f' (primeras {residual} cuotas con un centavo adicional)' if residual else '')
                       + '\n' + summary)
        if catalog_issue:
            summary += f"\n{catalog_issue}"
        self.order_summary.setText(summary)
        try:
            date.fromisoformat(self.order_date.text().strip())
            if self.order_purchase_mode.currentData() == "MSI" and not getattr(self, 'manual_edit_id', None):
                date.fromisoformat(self.order_first_due_date.text().strip())
                self._order_input_cents(self.order_interest, "Intereses", allow_empty=True)
            dates_valid = True
        except ValueError:
            dates_valid = False
        self.save_order_button.setEnabled(
            original > 0 and distributed == recover and catalog_issue is None
            and bool(self.order_merchant.text().strip()) and dates_valid
            and self.order_instrument.currentData() is not None
            and charged <= original
            and (self.order_purchase_mode.currentData() != 'MSI' or charged > 0)
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
                order = self.repository.get_order(self.manual_edit_id)
                if self._parse_mxn_to_cents(self.order_charged.text()) != order['charged_cents']:
                    if not self._correct_existing_order_charge(use_editor_value=True):
                        return
                self.repository.update_manual_concepts(self.manual_edit_id, self._read_manual_concepts(),
                    expected_concepts=self.manual_expected_concepts)
                self.data_changed.emit('orders')
                self._show_saved_information('Conceptos y reparto guardados.', 'Pedidos: '+order['merchant']+' · '+date_label(order['ordered_at'])+' · detalle del pedido.')
                self.manual_dialog.accept()
                self._clear_order_form()
                return
            original, charged, allocations = self._order_total_inputs()
            discount = max(original - charged, 0)
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
                    self.order_interest, "Los intereses del plan", allow_empty=True
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
            concepts = self._read_manual_concepts() if self.manual_concepts.rowCount() else None
            if concepts is not None:
                multiplier = self._order_amount_multiplier()
                concepts = [dict(c, amount_cents=c['amount_cents'] * multiplier,
                                 allocations={p: v * multiplier for p, v in c['allocations'].items()})
                            for c in concepts]
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
                concepts=concepts,
            )
        except (ValueError, *DATABASE_ERRORS) as error:
            self._show_error(self._safe_error(error))
            return
        finally:
            self._order_save_in_progress = False
            self._update_order_preview()
        self.data_changed.emit("orders")
        self._show_saved_information("Gasto guardado.", 'Pedidos: '+merchant_widget.text().strip()+' · '+date_label(date_widget.text().strip())+' · detalle del pedido.')
        self.manual_dialog.accept()
        self._clear_order_form()

    def _clear_order_form(self) -> None:
        self.correct_charge_button.hide()
        self.order_discount_caption.setText('Descuento calculado')
        self._manual_started = False
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
        self.order_merchant.clear()
        self.order_original.clear()
        self.order_charged.clear()
        self.order_discount.setText("Por confirmar")
        self.order_exception.clear()
        self._reset_order_allocations()
        self.order_purchase_mode.setCurrentIndex(0)
        self.order_amount_basis.setCurrentIndex(0)
        self.order_first_due_date.clear()
        self.order_interest.clear()

    def _toggle_msi_fields(self) -> None:
        if not hasattr(self, "order_purchase_mode"):
            return
        visible = self.order_purchase_mode.currentData() == "MSI"
        if hasattr(self, 'order_amount_basis'):
            self.order_amount_basis.setVisible(visible)
            self.order_amount_basis.setEnabled(visible and not getattr(self, 'manual_edit_id', None))
            self.order_basis_label.setVisible(visible)
            self.order_basis_note.setVisible(visible)
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
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if column in (2, 3, 4, 5, 6):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.orders_table.setItem(row, column, item)
            if str(order["id"]) == selected_id:
                self.orders_table.selectRow(row)
        blocker.unblock()
        self.orders_empty_notice.setText('No hay pedidos en este filtro. Cambia el filtro, registra un gasto o importa un comprobante.')
        self.orders_empty_notice.setVisible(self.orders_table.rowCount() == 0)
        self._show_order_detail()
        self._reflow_orders()

    def _reflow_orders(self):
        if not hasattr(self, 'order_action_groups'):
            return
        width = self.orders_scroll.viewport().width()
        columns = 4 if width >= 1200 else 2 if width >= 760 else 1
        for index, group in enumerate(self.order_action_groups):
            self.order_actions_grid.removeWidget(group)
            self.order_actions_grid.addWidget(group, index // columns, index % columns, Qt.AlignmentFlag.AlignTop)
            group.setMaximumHeight(group.sizeHint().height())
        table = self.orders_table
        height = table.horizontalHeader().sizeHint().height() + sum(table.rowHeight(row) for row in range(min(7, table.rowCount()))) + 8
        if table.horizontalScrollBar().maximum():
            height += table.horizontalScrollBar().sizeHint().height()
        table.setFixedHeight(max(76, height))

    def _reflow_manual_information(self):
        if not hasattr(self, 'manual_information_sections'):
            return
        columns = 2 if self.manual_scroll.viewport().width() >= 700 else 1
        for index, section in enumerate(self.manual_information_sections):
            self.manual_information_grid.removeWidget(section)
            self.manual_information_grid.addWidget(section, index // columns, index % columns)

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
        self.people_summary.setText(f"Personas activas: {sum(bool(p['active']) for p in people)} · Inactivas: {sum(not p['active'] for p in people)}")
        self.people_empty.setVisible(not people)
        self.people_table.setVisible(bool(people))
        self.people_table.setFixedHeight(min(260, 48 + len(people) * 32))
        self.people_table.setRowCount(0)
        for person in people:
            row = self.people_table.rowCount()
            self.people_table.insertRow(row)
            self.people_table.setItem(row, 0, QTableWidgetItem(str(person["id"])))
            self.people_table.setItem(row, 1, QTableWidgetItem(str(person["name"])))
            owner = "Propietario" if person["is_owner"] else "Familiar"
            self.people_table.setItem(row, 2, QTableWidgetItem(owner))
            self.people_table.item(row, 2).setForeground(QColor('#9b583b' if person['is_owner'] else '#565d55'))
            self.people_table.setItem(row, 3, QTableWidgetItem(
                "Activo" if person["active"] else "Desactivado"
            ))
            if selected_id == person["id"]:
                self.people_table.selectRow(row)
        blocker.unblock()
        self.people_table.resizeColumnsToContents()
        self.people_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

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
        person = self.repository.get_person(person_id)
        if person and bool(person['is_owner']) != self.person_owner.isChecked():
            if QMessageBox.question(self, 'Confirmar identidad de propietario',
                'Se cambiará la marca de propietario de esta persona. Los identificadores, movimientos y deudas históricas se conservan. Para configurar un único propietario utiliza Configuración. ¿Guardar?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
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
            "¿Desactivar la persona seleccionada? Ya no estará disponible para nuevas participaciones. "
            "Su identificador, historial y deudas se conservan; sus movimientos no se reasignan.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
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
        return user_error(error)

    def _show_error(self, message: str) -> None:
        self.statusBar().clearMessage()
        if hasattr(self, 'action_feedback'):
            self.action_feedback.clear()
            self.action_feedback.hide()
        QMessageBox.critical(self, "No se pudo completar la operación", message)

    @staticmethod
    def _safe_error(error):
        return user_error(error)

    def _show_saved_information(self, message, location):
        self._show_information(message)
        self.action_feedback.setText(message+'\nDónde encontrarlo: '+location)
        self.action_feedback.show()

    def _show_information(self, message: str, *, location: str | None = None) -> None:
        self.statusBar().showMessage(message, 10000)
        if hasattr(self, 'action_feedback'):
            index = self.pages.currentIndex()
            page = self.PAGES[index] if 0 <= index < len(self.PAGES) else 'Cobros'
            destination = {
                'Pedidos': 'Pedidos: selecciona el comercio para ver su detalle.',
                'Cobros': 'Cobros: consulta el abono en Ver historial.',
                'Tarjetas': 'Tarjetas: selecciona la cuenta; pagos en Pagos reales e historial, cuentas en Administración bancaria y consultas en Ver historial de consultas.',
                'Suscripciones': 'Suscripciones: selecciona el servicio para consultar sus datos.',
                'Usuarios': 'Usuarios: selecciona la persona en la lista.',
                'Configuración': 'Configuración: consulta Mostrar resultados.',
            }.get(page, 'Consulta el registro en su sección de origen.')
            destination = location or destination
            saved = any(word in message.casefold() for word in ('guardad', 'registrad', 'actualiz', 'cread', 'corregid', 'vinculad', 'aplicad', 'generad'))
            self.action_feedback.setText(message + ('\nDónde encontrarlo: '+destination if saved else ''))
            self.action_feedback.show()

    def _make_dashboard(self) -> QWidget:
        page = QWidget()
        page.setObjectName('valenzaHome')
        page.setStyleSheet(HOME_STYLE)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        self.dashboard_scroll = scroll
        scroll.viewport().installEventFilter(self)
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName('homeContent')
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self.dashboard_header_grid = QGridLayout()
        layout.addLayout(self.dashboard_header_grid)
        self.dashboard_heading = QWidget()
        header = QHBoxLayout(self.dashboard_heading)
        header.setContentsMargins(0, 0, 0, 0)
        self.dashboard_brand = QLabel()
        self.dashboard_brand.setObjectName('valenzaHeaderLogo')
        logo = QPixmap(str(Path(__file__).parent / 'assets' / 'logo_horizontal.png'))
        if not logo.isNull():
            self.dashboard_brand.setPixmap(logo.scaled(180, 45, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            header.addWidget(self.dashboard_brand)
        self.dashboard_brand.hide()  # The sidebar already displays the application logo.
        self.dashboard_brand.setToolTip('Valenza · Finanzas compartidas')
        title = QLabel("Inicio")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        self.dashboard_period = QLabel()
        header.addWidget(self.dashboard_period)
        self.dashboard_period.hide()
        self.dashboard_period_picker = self._make_period_picker()
        self.dashboard_period_picker.setAccessibleName('Mes de compromisos y programación en Inicio; no filtra los saldos actuales')
        self.dashboard_period_picker.setToolTip('Mes de compromisos y programación. Los saldos actuales y acumulados no se filtran por este selector.')
        period_control = QWidget()
        period_layout = QVBoxLayout(period_control)
        period_layout.setContentsMargins(0,0,0,0)
        period_layout.setSpacing(0)
        period_caption = QLabel('Mes de compromisos')
        period_caption.setObjectName('secondaryText')
        period_caption.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        period_caption.setBuddy(self.dashboard_period_picker)
        period_layout.addWidget(period_caption)
        period_layout.addWidget(self.dashboard_period_picker)
        header.addWidget(period_control)
        self.dashboard_heading.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.dashboard_header_actions = QWidget()
        access_layout = FlowLayout(self.dashboard_header_actions)
        access_layout.setContentsMargins(0, 0, 0, 0)
        self.prepare_payment_button = QPushButton('Revisar efectivo')
        self.prepare_payment_button.setEnabled(self.repository is not None)
        self.prepare_payment_button.clicked.connect(self._prepare_month_payment)
        access_layout.addWidget(self.prepare_payment_button)
        for caption, destination in [('Pedidos', 'Pedidos'), ('Cobros', 'Cobros'), ('Tarjetas', 'Tarjetas')]:
            button = QPushButton(caption)
            button.clicked.connect(lambda checked=False, name=destination: self._show_page(self.PAGES.index(name)))
            access_layout.addWidget(button)
        self.dashboard_header_grid.addWidget(self.dashboard_heading, 0, 0)
        self.dashboard_header_grid.addWidget(self.dashboard_header_actions, 0, 1)
        self.dashboard_scope_note = QLabel('Mes seleccionado: compromisos, calendario y gráfica mensual. Los pendientes totales, descuentos y resultado son actuales o acumulados; no son saldos históricos del mes.')
        self.dashboard_scope_note.setWordWrap(True)
        self.dashboard_scope_note.setObjectName('secondaryText')
        layout.addWidget(self.dashboard_scope_note)
        banner = QLabel(
            "MODO DEMOSTRACIÓN · Los importes son sintéticos y no se guardan."
            if self.repository is None else
            "Operaciones de la base activa. La deuda registrada no sustituye "
            "el saldo confirmado por el banco. Mi parte, Cobros familiares y "
            "pagos a tarjetas se mantienen separados."
        )
        banner.setWordWrap(True)
        title.setToolTip(banner.text())
        # Demo/test status is already displayed by the window banner.

        cards = QGridLayout()
        self.dashboard_indicator_grid = cards
        self.dashboard_personal = self._make_card("Mi parte pendiente", "")
        self.dashboard_receivables = self._make_card("Cobros familiares pendientes", "")
        self.dashboard_debt = self._make_card("Compromisos del mes · tarjetas", "")
        self.dashboard_debt.setObjectName('monthCommitments')
        self.dashboard_debt.layout().itemAt(0).widget().setText('Compromisos del mes · tarjetas')
        self.dashboard_debt.setToolTip('Deuda pendiente menos MSI futuros, cuotas anteriores y cuotas sin fecha, con mínimo cero por tarjeta. Los pagos bancarios ya están descontados.')
        self.dashboard_discount = self._make_card("Descuentos personales", "")
        self.dashboard_msi = self._make_card('Deuda total pendiente', '')
        for widget, kind, color in ((self.dashboard_personal, 'people', '#cc785c'),
                                     (self.dashboard_receivables, 'people', '#8ca99a'),
                                     (self.dashboard_msi, 'card', '#8bafc2'),
                                     (self.dashboard_discount, 'card', '#c29668')):
            caption = widget.layout().itemAt(0).widget()
            caption_layout = QHBoxLayout()
            icon = QLabel()
            icon.setPixmap(line_icon(kind, color).pixmap(24, 24))
            widget.layout().removeWidget(caption)
            caption_layout.addWidget(icon)
            caption_layout.addWidget(caption, 1)
            widget.layout().insertLayout(0, caption_layout)
        layout.addWidget(self.dashboard_debt)
        cards.addWidget(self.dashboard_personal, 0, 0)
        cards.addWidget(self.dashboard_receivables, 0, 1)
        cards.addWidget(self.dashboard_msi, 0, 2)
        cards.addWidget(self.dashboard_discount, 0, 3)
        layout.addLayout(cards)
        self.dashboard_balance_scope = QLabel('Saldos actuales: mi parte, cobros familiares y deuda total. Acumulados de pedidos activos: descuentos y resultado personal previsto.')
        self.dashboard_balance_scope.setWordWrap(True)
        self.dashboard_balance_scope.setObjectName('secondaryText')
        layout.addWidget(self.dashboard_balance_scope)
        self.dashboard_monthly_installments = QLabel()
        self.dashboard_monthly_installments.setWordWrap(True)
        self.dashboard_summary_details = QWidget()
        summary_layout = QVBoxLayout(self.dashboard_summary_details)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.addWidget(self.dashboard_monthly_installments)
        self.dashboard_discount.setToolTip("Ahorro acumulado del propietario en pedidos activos; ya considerado en el costo efectivo. No es dinero cobrado.")
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
                summary_layout.addWidget(label)
        self.dashboard_expected.setToolTip('Resultado de pedidos activos antes de abonos personales. Incluye cada recompra vinculada una vez; excluye intereses y comisiones. No es dinero cobrado.')
        self.dashboard_summary_toggle = QPushButton('Ver desglose')
        self.dashboard_summary_toggle.setCheckable(True)
        self.dashboard_summary_toggle.toggled.connect(self.dashboard_summary_details.setVisible)
        principal_amount = self.dashboard_debt.findChild(QLabel, 'summaryAmount')
        self.dashboard_debt.layout().removeWidget(principal_amount)
        principal_row = QHBoxLayout()
        principal_row.addWidget(principal_amount, 1)
        principal_row.addWidget(self.dashboard_summary_toggle)
        self.dashboard_debt.layout().addLayout(principal_row)
        self.dashboard_debt.layout().setContentsMargins(6, 4, 6, 4)
        period_note = QLabel('Periodo actual · según fechas capturadas; no es la deuda total de todos los meses.')
        self.dashboard_period_note = period_note
        period_note.setObjectName('secondaryText')
        period_note.setWordWrap(True)
        self.dashboard_debt.layout().addWidget(period_note)
        self.dashboard_month_accounts = QLabel()
        self.dashboard_month_accounts.setWordWrap(True)
        self.dashboard_month_accounts.setTextFormat(Qt.TextFormat.PlainText)
        self.dashboard_debt.layout().addWidget(self.dashboard_month_accounts)
        self.dashboard_summary_details.hide()
        layout.addWidget(self.dashboard_summary_details)
        self.dashboard_privacy = QPushButton('👁 Mostrar importes')
        self.dashboard_privacy.setCheckable(True)
        self.dashboard_privacy.setAccessibleName('Mostrar importes personales')
        self.dashboard_privacy.toggled.connect(self._toggle_personal_privacy)
        expected_row.addWidget(self.dashboard_privacy)
        self.dashboard_result_toggle = QPushButton('Ver cómo se calcula')
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
        self.dashboard_charts_grid = QGridLayout()
        self.dashboard_bar_chart = FinanceChart('bars')
        self.dashboard_donut_chart = PeopleMonthChart()
        self.dashboard_donut_chart.monthStep.connect(
            lambda step: self.dashboard_period_picker.setDate(self.dashboard_period_picker.date().addMonths(step)))
        self.dashboard_donut_chart.personSelected.connect(self._select_chart_person)
        self.dashboard_donut_chart.detailsRequested.connect(lambda label: self._select_chart_person(label, details=True))
        self.dashboard_charts_grid.addWidget(self.dashboard_bar_chart, 0, 0, 1, 2)
        self.dashboard_charts_grid.addWidget(self.dashboard_donut_chart, 1, 0, 1, 2)
        layout.addLayout(self.dashboard_charts_grid)
        self.dashboard_donut_chart.setToolTip('Pendiente registrado de cada persona, igual que en la tabla. No incluye previsiones ni añade la deuda bancaria.')
        calendar_header = QHBoxLayout()
        calendar_caption = QLabel('Mensualidades · cuotas por mes')
        calendar_caption.setWordWrap(True)
        calendar_header.addWidget(calendar_caption, 1)
        calendar_header.addStretch()
        self.dashboard_calendar_toggle = QPushButton('Ver calendario completo')
        self.dashboard_calendar_toggle.setCheckable(True)
        self.dashboard_calendar_toggle.toggled.connect(self._refresh_dashboard_calendar)
        calendar_header.addWidget(self.dashboard_calendar_toggle)
        layout.addLayout(calendar_header)
        self.dashboard_calendar_grid = QGridLayout()
        self.dashboard_calendar_cards = []
        layout.addLayout(self.dashboard_calendar_grid)
        self.dashboard_calendar_total = QLabel()
        self.dashboard_calendar_total.setWordWrap(True)
        layout.addWidget(self.dashboard_calendar_total)
        self.dashboard_received.setToolTip('Dinero registrado como abonos familiares activos, contado una vez por abono. Aportaciones personales y reembolsos son conceptos distintos.')
        self.dashboard_tables_grid = QGridLayout()
        layout.addLayout(self.dashboard_tables_grid)
        self.dashboard_card_section = QWidget()
        card_layout = QVBoxLayout(self.dashboard_card_section)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_header = QHBoxLayout()
        card_header.addWidget(QLabel('Conciliación bancaria · cuentas'))
        card_header.addStretch()
        self.dashboard_bank_toggle = QPushButton('Detalle bancario')
        self.dashboard_bank_toggle.setCheckable(True)
        card_header.addWidget(self.dashboard_bank_toggle)
        card_layout.addLayout(card_header)
        self.dashboard_cards = QTableWidget(0, 6)
        self.dashboard_cards.setHorizontalHeaderLabels(['Tarjeta / institución', 'Deuda total Valenza', 'Deuda total banco', 'Consultado', 'Diferencia'])
        self.dashboard_cards.horizontalHeaderItem(1).setText('Deuda total actual Valenza')
        self.dashboard_cards.setHorizontalHeaderItem(5, QTableWidgetItem('Total pendiente'))
        for column, explanation in ((1, 'Deuda total actual calculada, incluye principal MSI futuro.'),
                                     (2, 'Saldo total consultado manualmente al banco; no es un compromiso mensual.'),
                                     (4, 'Diferencia histórica contra la deuda fotografiada al guardar, no contra la deuda actual.'),
                                     (5, 'Deuda completa registrada, incluidas mensualidades futuras.')):
            self.dashboard_cards.horizontalHeaderItem(column).setToolTip(explanation)
        self.dashboard_cards.setHorizontalHeaderItem(2, QTableWidgetItem('Último saldo banco'))
        self.dashboard_cards.setHorizontalHeaderItem(4, QTableWidgetItem('Diferencia histórica'))
        self.dashboard_cards.horizontalHeaderItem(2).setToolTip('Saldo manual de la última consulta; su tipo aparece indicado si no equivale a deuda total.')
        self.dashboard_bank_toggle.toggled.connect(self._toggle_dashboard_bank_details)
        self.dashboard_cards.setColumnHidden(5, True)
        self.dashboard_cards.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.dashboard_cards.setAlternatingRowColors(True)
        self.dashboard_cards.verticalHeader().hide()
        self.dashboard_cards.verticalHeader().setDefaultSectionSize(26)
        self.dashboard_cards.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.dashboard_cards.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        card_layout.addWidget(self.dashboard_cards)
        self.dashboard_cards_total = QLabel()
        self.dashboard_cards_total.setWordWrap(True)
        card_layout.addWidget(self.dashboard_cards_total)
        self.dashboard_bank_notes=QLabel()
        self.dashboard_bank_notes.setWordWrap(True)
        self.dashboard_bank_notes.hide()
        card_layout.addWidget(self.dashboard_bank_notes)

        person_actions = QGridLayout()
        self.dashboard_person_header = person_actions
        self.dashboard_person_section = QWidget()
        person_layout = QVBoxLayout(self.dashboard_person_section)
        person_layout.setContentsMargins(0, 0, 0, 0)
        person_title = QLabel('Deuda total por persona · MXN')
        person_title.setObjectName('sectionTitle')
        person_actions.addWidget(person_title, 0, 0)
        details = QPushButton('Ver desglose')
        self.dashboard_person_toggle = details
        details.setCheckable(True)
        self.dashboard_person_pdf = QPushButton('Generar PDF')
        self.dashboard_person_pdf.clicked.connect(lambda:self._export_family_pdf(self._table_id(self.dashboard_people,5)))
        person_actions.addWidget(details, 0, 1); person_actions.addWidget(self.dashboard_person_pdf, 0, 2)
        person_layout.addLayout(person_actions)
        self.dashboard_people = QTableWidget(0,6)
        self.dashboard_people.setHorizontalHeaderLabels(['Persona','Pendiente','Abonado','Suscr. prev.','MSI por fecha','ID'])
        self.dashboard_people.setColumnHidden(5,True)
        self.dashboard_people.setColumnHidden(3,True)
        self.dashboard_people.setColumnHidden(4,True)
        self.dashboard_people.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.dashboard_people.setAlternatingRowColors(True)
        self.dashboard_people.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.dashboard_people.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.dashboard_people.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.dashboard_people.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        delegate = CompactMoneyDelegate(self.dashboard_people)
        for column in range(1,5):
            self.dashboard_people.setItemDelegateForColumn(column,delegate)
            self.dashboard_people.horizontalHeader().setSectionResizeMode(column,QHeaderView.ResizeMode.Interactive)
            self.dashboard_people.setColumnWidth(column,85)
        self.dashboard_people.verticalHeader().hide()
        self.dashboard_people.verticalHeader().setDefaultSectionSize(26)
        self.dashboard_people.setToolTip('MSI: V = meses vencidos, M = mes seleccionado, F = meses futuros. Ya incluidos en el pendiente; no se suman otra vez. Suscripción prevista todavía no crea deuda.')
        self.dashboard_people.itemSelectionChanged.connect(self._show_person_statement)
        person_layout.addWidget(self.dashboard_people)
        self.dashboard_people_total = QLabel(); self.dashboard_people_total.setWordWrap(True)
        person_layout.addWidget(self.dashboard_people_total)
        self.dashboard_person_details = HomePeopleBreakdown()
        self.dashboard_person_details.hide()
        details.toggled.connect(self._toggle_person_breakdown)
        self.dashboard_person_details.person_selected.connect(self._select_breakdown_person)
        person_layout.addWidget(self.dashboard_person_details)
        self.dashboard_tables_grid.addWidget(self.dashboard_card_section, 0, 0)
        self.dashboard_tables_grid.addWidget(self.dashboard_person_section, 0, 1)
        self.dashboard_tables_grid.setColumnStretch(0, 1)
        self.dashboard_tables_grid.setColumnStretch(1, 1)
        self.dashboard_upcoming = QListWidget(); self.dashboard_upcoming.setMaximumHeight(100)
        self.dashboard_upcoming.setMinimumHeight(0); layout.addWidget(self.dashboard_upcoming)
        self.dashboard_calendar_toggle.toggled.connect(lambda checked: self.dashboard_upcoming.setVisible(checked and self.dashboard_upcoming.count() > 0))

        movements_header = QHBoxLayout()
        movements_header.addWidget(QLabel('Movimientos recientes · últimos cinco'))
        movements_header.addStretch()
        self.dashboard_movements_toggle = QPushButton('Ver todos los recientes')
        self.dashboard_movements_toggle.setCheckable(True)
        self.dashboard_movements_toggle.toggled.connect(self._compact_dashboard_movements)
        movements_header.addWidget(self.dashboard_movements_toggle)
        layout.addLayout(movements_header)
        self.dashboard_movements = QListWidget()
        self.dashboard_movements.setObjectName("recentMovements")
        self.dashboard_movements.setItemDelegate(MovementDelegate(self.dashboard_movements))
        self.dashboard_movements.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.dashboard_movements)
        layout.addStretch()
        for button in page.findChildren(QPushButton):
            if button is self.dashboard_privacy:
                continue
            label = button.text()
            icon = ('calendar' if 'calendario' in label else 'people' if label in ('Cobros', 'Ver desglose')
                    else 'card' if label in ('Tarjetas', 'Detalle bancario', 'Detalles financieros') else 'receipt')
            button.setIcon(line_icon(icon))
        for label in page.findChildren(QLabel):
            if label.text().startswith(('Mensualidades ·', 'Deudas por tarjeta ·', 'Deudas por persona ·', 'Movimientos recientes ·')):
                label.setObjectName('sectionTitle')
                label.setStyleSheet('font-weight: 600; color: #292724;')
            elif label in (self.dashboard_people_total, self.dashboard_cards_total, self.dashboard_calendar_total):
                label.setObjectName('secondaryText')
        for table in (self.dashboard_cards, self.dashboard_people):
            table.verticalHeader().setDefaultSectionSize(max(28, table.fontMetrics().height() + 12))
            table.setWordWrap(False)
        self.dashboard_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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
            summary['bank_comparisons'] = self.repository.list_bank_comparisons(as_of=self._forecast_date())
            self._dashboard_forecast_accounts = summary['bank_comparisons']
            home_month = home_month_summary(self.repository, summary['bank_comparisons'], self._forecast_date())
            summary['scheduled_month_cents'] = home_month['msi_month_cents']
            self.dashboard_monthly_installments.setText(
                f"Suma de cuotas MSI previstas este mes: {format_money(summary['scheduled_month_cents'])}. "
                f"Periodo {self._forecast_date():%Y-%m}. Incluidas en la deuda total; no se suman otra vez. Previsión según fechas capturadas.")
            monthly_collections = self.repository.collection_monthly_summaries(as_of=self._forecast_date())
            family_ids = {item['receivable_id'] for item in self.repository.list_collection_items()
                          if item['participant_role'] == 'FAMILY'}
            family_msi = [value for key, value in monthly_collections.items()
                          if key in family_ids and value['is_msi']]
            self.dashboard_monthly_installments.setText(
                self.dashboard_monthly_installments.text()
                + '\nMSI por cobrar a familiares este mes: '
                + format_money(sum(value['current_cents'] for value in family_msi))
                + '\n' + home_month_text(home_month, format_money))
            net_pending = int(summary['personal_pending_less_discounts_cents'])
            expected = int(summary['personal_expected_result_cents'])
            received = int(summary['family_received_cents'])
            for comparison in summary['bank_comparisons']:
                row = self.dashboard_cards.rowCount()
                self.dashboard_cards.insertRow(row)
                values = [f"{comparison['alias']} · {comparison['institution_name']}",
                          format_money(comparison['calculated_cents']),
                          reported_text(comparison['last_query'],format_money),
                          comparison['consulted_at'] or 'Sin consulta',
                          difference_text(comparison['difference_cents'],format_money) if comparison['last_query'] else 'Sin consulta',
                          format_money(comparison['calculated_cents'])]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(query_text(comparison['last_query'],format_money)+'\n'+' '.join(comparison['warnings']))
                    if column in (1, 2, 4, 5):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    if column == 0:
                        item.setIcon(brand_icon(comparison["institution_name"], "institution"))
                    self.dashboard_cards.setItem(row, column, item)
            discount = int(summary['discount_benefit_cents'])
            personal = int(summary["personal_pending_cents"])
            receivables = int(summary["receivables_cents"])
            debt = home_month['current_cents']
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
                    f"{date_label(str(item['occurred_at'])[:10])} · {item['kind']} · "
                    f"{item['description']} · {format_money(int(item['amount_cents']))}{state}"
                )
                movement = self.dashboard_movements.item(self.dashboard_movements.count() - 1)
                movement.setData(Qt.ItemDataRole.UserRole, dict(item))
                movement.setToolTip(movement.text())
            if not summary["recent_movements"]:
                self.dashboard_movements.addItem("Todavía no hay movimientos registrados.")
        self.dashboard_receivables.findChild(QLabel, "summaryAmount").setText(format_money(receivables))
        self.dashboard_personal.findChild(QLabel, "summaryAmount").setText(format_money(personal))
        self.dashboard_debt.findChild(QLabel, "summaryAmount").setText(format_money(debt))
        self.dashboard_month_commitments = debt
        self.dashboard_discount.findChild(QLabel, 'summaryAmount').setText(format_money(discount))
        self.dashboard_msi.findChild(QLabel, 'summaryAmount').setText(
            format_money(sum(c['calculated_cents'] for c in summary['bank_comparisons'])) if self.repository else format_money(debt))
        self.dashboard_msi.setToolTip('Deuda bancaria total pendiente: incluye las cuotas de todos los meses. No se suma al importe mensual.')
        if not self.repository:
            self.dashboard_donut_chart.set_data([('Mi parte', personal), ('Familiares', receivables)], 'Mi parte')
        months = ('Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre')
        today = self._forecast_date()
        self.dashboard_period.setText(f'{months[today.month - 1]} {today.year}')
        if self.repository:
            self.dashboard_period_note.setText(f"{period_label(home_month['period'])} · No sustituye el pago informado por el banco."
                + ('\nSaldos pendientes actuales; no es un saldo histórico.'
                   if today.strftime('%Y-%m') != date.today().strftime('%Y-%m') else ''))
            history = self.repository.list_bank_reconciliation_history()
            account_lines = []
            for account, restored_account in zip(summary['bank_comparisons'],home_month['accounts']):
                account_lines.append(f"{account['alias']}: {format_money(restored_account['current_cents'])}")
                official = official_period_query(history,account,home_month['period'])
                if official:
                    account_lines.append(official_text(official,format_money,compact=True))
            self.dashboard_month_accounts.setText('\n'.join(account_lines))
            self.dashboard_month_accounts.setToolTip('\n\n'.join(a['alias']+'\n'+home_month_text(dict(a,period=home_month['period']),format_money) for a in home_month['accounts']))
        self.dashboard_net_pending.setText(f'Mi parte pendiente menos descuentos: {format_money(net_pending)} · comparación, sin modificar deudas.')
        self.dashboard_expected.setText(f"Resultado personal previsto {result_label(expected)}: {format_money(abs(expected))} · antes de abonos personales.")
        if not self.dashboard_privacy.isChecked():
            self.dashboard_discount.findChild(QLabel, 'summaryAmount').setText('••••')
            self.dashboard_expected.setText('Resultado personal previsto: ••••')
            self.dashboard_net_pending.setText('Comparación personal: importes ocultos')
            self.dashboard_result_details.setPlainText('Importes personales ocultos. ' + EXPLANATION)
        self._fit_dashboard_table(self.dashboard_cards)
        self.dashboard_received.setText(f'Abonos familiares realmente recibidos: {format_money(received)} · descuentos = ahorro; resultado previsto ≠ dinero cobrado.')
        bank_total=sum(c['calculated_cents'] for c in summary['bank_comparisons']) if self.repository else 0
        self.dashboard_cards_total.setText(f'Deuda bancaria total calculada: {format_money(bank_total)} · cada cuenta / línea una vez. Diferencias históricas a la fecha de consulta; no se comparan con la deuda actual.')
        self.dashboard_bank_notes.setText('\n\n'.join(c['alias']+' · '+query_text(c['last_query'],format_money)+'\n'+' '.join(c['warnings']) for c in summary['bank_comparisons']) if self.repository else 'Sin consulta')
        self.dashboard_credit.setVisible(bool(self.dashboard_credit.text()))
        self.dashboard_unclassified.setVisible(bool(self.dashboard_unclassified.text()))
        if self.dashboard_result_toggle.isChecked():
            self._show_result_breakdown(True)
        self._refresh_people_dashboard()
        self._refresh_dashboard_calendar()
        self._compact_dashboard_movements()
        self._reflow_dashboard()

    def _refresh_people_dashboard(self):
        selected = self._table_id(self.dashboard_people,5)
        people = self.repository.people_debt_summary() if self.repository else []
        msi_by_person = {}
        if self.repository:
            shares = self.repository.list_collection_items()
            periods = self.repository.collection_monthly_summaries(as_of=self._forecast_date())
            for share in shares:
                buckets = periods[share['receivable_id']]
                if buckets['is_msi']:
                    totals = msi_by_person.setdefault(share['user_id'], dict(overdue_cents=0,current_cents=0,future_cents=0,undated_cents=0))
                    for key in totals: totals[key] += buckets[key]
        if self.repository:
            chart_people = sorted(people, key=lambda person: not person['is_owner'])
            chart_period = self._forecast_date().strftime('%Y-%m')
            from valenza.gui.home_people_month import people_month_breakdown
            chart_breakdown = people_month_breakdown(self.repository, self._forecast_date())
            self._dashboard_chart_breakdown = chart_breakdown
            person_month = chart_breakdown['amounts']
            chart_values = [(('Mi parte · ' if p['is_owner'] else '') + p['name'], person_month.get(p['id'], 0))
                            for p in chart_people]
            self._dashboard_chart_people = {label: p['id'] for (label, _), p in zip(chart_values, chart_people)}
            owner_label = next((label for (label, _), person in zip(chart_values, chart_people)
                                if person['is_owner']), '')
            self.dashboard_donut_chart.set_data(chart_values, owner_label, period=chart_period)
            self.dashboard_donut_chart.empty.setText(
                'Hay pendientes sin fecha o calendario. Revisa el detalle antes de interpretar el total.'
                if chart_breakdown['warnings'] else 'Sin pendientes en este mes')
            if chart_breakdown['warnings']:
                self.dashboard_donut_chart.total.setText(self.dashboard_donut_chart.total.text()
                                                       + '\nImporte incompleto: hay fechas o calendarios por revisar.')
            self.dashboard_donut_chart.setToolTip(
                'Compras normales pendientes hasta el mes seleccionado y solo las cuotas MSI de ese mes, después de abonos. '
                'No incluye compras posteriores ni MSI futuros o anteriores. Usa saldos actuales; no reconstruye saldos históricos. '
                'No es el pago solicitado por el banco.\n'
                + '\n'.join(chart_breakdown['warnings']) + '\n'
                + self.dashboard_donut_chart.toolTip())
            for label, person in zip((label for label, _ in chart_values), chart_people):
                detail = '\n'.join(f"{s['source_name']} · {s['basis']}: {format_money(s['amount_cents'])}"
                                   for s in chart_breakdown['sources'].get(person['id'], []))
                chart_row = self.dashboard_donut_chart.rows.get(label)
                if chart_row is not None:
                    chart_row.setToolTip(chart_row.accessibleName() + ('\n' + detail if detail else ''))
            self.dashboard_donut_chart.setAccessibleName('Pendiente por persona · ' + period_label(chart_period))
            self.dashboard_donut_chart.setAccessibleDescription(self.dashboard_donut_chart.toolTip())
        with QSignalBlocker(self.dashboard_people):
            self.dashboard_people.setRowCount(0)
            for person in people:
                row = self.dashboard_people.rowCount(); self.dashboard_people.insertRow(row)
                values = [person['name']+(' (Yo)' if person['is_owner'] else ''),format_money(person['remaining_cents']),
                    format_money(person['paid_cents']),format_money(person['subscription_forecast_cents']),
                    format_money(person['next_msi_cents']),person['id']]
                buckets = msi_by_person.get(person['id'], {})
                values[4] = ' · '.join(label+' '+format_money(buckets.get(key,0)) for label,key in
                    (('V','overdue_cents'),('M','current_cents'),('F','future_cents')))
                for column,value in enumerate(values):
                    item = QTableWidgetItem(str(value)); item.setToolTip(str(value))
                    if column == 4:
                        item.setToolTip('MSI pendientes por mes seleccionado: vencidos / actuales / futuros.\n'+str(value)
                            +'\nSin fecha: '+format_money(buckets.get('undated_cents',0))+'. No se suman al pendiente otra vez.')
                    if column in (1, 2, 3, 4):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    if column == 0:
                        item.setIcon(line_icon('home' if person['is_owner'] else 'people', '#b96847' if person['is_owner'] else '#668474'))
                        font = item.font()
                        font.setBold(bool(person['is_owner']))
                        item.setFont(font)
                    self.dashboard_people.setItem(row,column,item)
                if person['id']==selected: self.dashboard_people.selectRow(row)
            if people and self._table_id(self.dashboard_people,5) is None:
                self.dashboard_people.selectRow(next((i for i,p in enumerate(people) if p['is_owner']),0))
        own = sum(p['remaining_cents'] for p in people if p['is_owner'])
        family = sum(p['remaining_cents'] for p in people if not p['is_owner'])
        self.dashboard_people_total.setText(f'Mi pendiente: {format_money(own)} · Otras personas: {format_money(family)} · Total registrado: {format_money(own+family)}. Previsiones excluidas del total.')
        for column in range(1, 5):
            metrics = self.dashboard_people.fontMetrics()
            width = metrics.horizontalAdvance(self.dashboard_people.horizontalHeaderItem(column).text()) + 24
            for row in range(self.dashboard_people.rowCount()):
                item = self.dashboard_people.item(row, column)
                width = max(width, metrics.horizontalAdvance(item.text().removesuffix(' MXN')) + 20)
            self.dashboard_people.setColumnWidth(column, width)
        self._fit_dashboard_table(self.dashboard_people)
        self._show_person_statement()
        if self.dashboard_person_toggle.isChecked():
            self.dashboard_person_details.set_data(people, self.repository.list_collection_items() if self.repository else [])
        planned = self.repository.upcoming_obligations() if self.repository else []
        self.dashboard_upcoming.clear()
        for item in planned:
            name = next((p['name'] for p in people if p['id']==item['user_id']),item['user_id'])
            self.dashboard_upcoming.addItem(f"{item['due_date'] or 'Fecha por confirmar'} · {name} · {item['description']} · {format_money(item['amount_cents'])}" + (' · incluido en pendiente' if item['included_in_pending'] else ' · previsto, sin cargo'))
        self.dashboard_upcoming.setVisible(bool(planned))
        bank_installments = self.repository.upcoming_bank_installments() if self.repository else []
        for item in bank_installments:
            self.dashboard_upcoming.addItem(f"{item['due_date'] or 'Fecha por confirmar'} · Banco: {item['alias']} · {item['merchant']} · cuota {item['number']} · {format_money(item['amount_cents'])} · desglose de tarjeta, no nuevo cargo")
        self.dashboard_upcoming.setVisible(self.dashboard_calendar_toggle.isChecked() and bool(planned or bank_installments))

    @staticmethod
    def _fit_dashboard_table(table):
        rows = min(table.rowCount(), 6)
        horizontal = sum(table.columnWidth(c) for c in range(table.columnCount()) if not table.isColumnHidden(c)) > table.viewport().width()
        table.setFixedHeight(table.horizontalHeader().sizeHint().height()
                             + sum(table.rowHeight(row) for row in range(rows)) + 4
                             + (table.horizontalScrollBar().sizeHint().height() if horizontal else 0))

    def _toggle_dashboard_bank_details(self, checked):
        self.dashboard_bank_notes.setVisible(checked)
        self._fit_dashboard_table(self.dashboard_cards)

    def _compact_dashboard_movements(self, *_):
        count = self.dashboard_movements.count()
        expanded = self.dashboard_movements_toggle.isChecked()
        for row in range(count):
            self.dashboard_movements.item(row).setHidden(not expanded and row >= 5)
        visible = min(count, 10 if expanded else 5)
        self.dashboard_movements.setFixedHeight(max(36, visible * max(24, self.dashboard_movements.sizeHintForRow(0)) + 6))
        self.dashboard_movements_toggle.setVisible(count > 5)

    def _refresh_dashboard_calendar(self, *_):
        if not hasattr(self, 'dashboard_calendar_grid'):
            return
        while self.dashboard_calendar_grid.count():
            item = self.dashboard_calendar_grid.takeAt(0)
            item.widget().hide()
            item.widget().deleteLater()
        self.dashboard_calendar_cards = []
        accounts = getattr(self, '_dashboard_forecast_accounts', []) if self.repository else []
        entries = [dict(e,alias=a['alias'],requires_review=not e['confirmed'])
                   for a in accounts for e in a['monthly_forecast']['entries'] if e['kind']=='MSI']
        today = self._forecast_date()
        periods = {}
        for offset in range(3):
            index = today.year * 12 + today.month - 1 + offset
            periods[f'{index // 12:04d}-{index % 12 + 1:02d}'] = []
        for entry in entries:
            key = str(entry['due_date'])[:7] if entry['due_date'] else 'Sin fecha'
            periods.setdefault(key, []).append(entry)
        current = today.strftime('%Y-%m')
        keys = sorted(periods, key=lambda key: (key == 'Sin fecha', key))
        if not self.dashboard_calendar_toggle.isChecked():
            keys = [key for key in keys if key >= current and key != 'Sin fecha'][:3]
        month_names = ('Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic')
        for key in keys:
            group = periods[key]
            caption = key if key == 'Sin fecha' else f'{month_names[int(key[5:7]) - 1]} {key[:4]}'
            if key == current:
                caption += ' · actual'
            elif key == 'Sin fecha':
                caption = 'Sin fecha · por confirmar'
            elif key < current:
                caption += ' · anteriores por confirmar' if any(e.get('requires_review') for e in group) else ' · vencidas según calendario'
            else:
                caption += ' · futuras'
            card = self._make_card(caption, format_money(sum(int(e['amount_cents']) for e in group)))
            if key == current:
                card.setStyleSheet('QFrame#summaryCard { background: #fbe7d5; border: 1px solid #d18a5d; }')
            elif key == 'Sin fecha' or key < current:
                card.setStyleSheet('QFrame#summaryCard { background: #f7e8e2; border: 1px solid #dab6a5; }')
            else:
                card.setStyleSheet('QFrame#summaryCard { background: #edf3f4; border: 1px solid #d4e0e4; }')
            card.layout().setContentsMargins(6, 4, 6, 4)
            card.layout().itemAt(0).widget().setText(f'{caption} · {len(group)} cuota(s)')
            unconfirmed = any(e.get('requires_review') for e in group)
            status_note = QLabel('Programado antes de pagos · calendario por confirmar' if unconfirmed else 'Programado antes de pagos' if group else 'Sin cuotas previstas')
            status_note.setObjectName('secondaryText')
            status_note.setWordWrap(True)
            card.layout().addWidget(status_note)
            card.setToolTip('\n'.join(f"{e['alias']} · {e['merchant']} · cuota {e['number']} · {format_money(e['amount_cents'])}" + (' · calendario por confirmar' if e.get('requires_review') else '') for e in group) or 'Sin cuotas previstas.')
            self.dashboard_calendar_cards.append(card)
        # Restore the original future bars: pending bank installments only,
        # not the newer Cards forecast of normal purchases and extra charges.
        chart_periods = {}
        for offset in range(3):
            index = today.year*12+today.month-1+offset
            chart_periods[f'{index//12:04d}-{index%12+1:02d}'] = 0
        for entry in self.repository.upcoming_bank_installments() if self.repository else []:
            if entry['due_date']:
                key = entry['due_date'][:7]
                chart_periods[key] = chart_periods.get(key,0)+entry['amount_cents']
        chart_keys = [key for key in sorted(chart_periods) if key>=current][:6]
        chart_values = [(key,self.dashboard_month_commitments if key==current else chart_periods[key]) for key in chart_keys]
        self.dashboard_bar_chart.set_data(chart_values, current)
        self.dashboard_bar_chart.setToolTip('Mes seleccionado: mismo pendiente que el indicador principal. Meses futuros: solo MSI pendientes. Usa saldos actuales; no reconstruye saldos históricos.\n' + self.dashboard_bar_chart.toolTip())
        total = sum(int(e['amount_cents']) for e in entries)
        self.dashboard_calendar_total.setText(f'MSI programados vigentes: {format_money(total)} · Pendiente conocido actualmente: {format_money(sum(e["remaining_cents"] for e in entries))}. Incluye todos los periodos; no se suma otra vez al mes.')
        self._reflow_dashboard()

    def _reflow_dashboard(self):
        if not hasattr(self, 'dashboard_tables_grid'):
            return
        width = self.dashboard_scroll.viewport().width()
        for widget in (self.dashboard_bar_chart, self.dashboard_donut_chart):
            self.dashboard_charts_grid.removeWidget(widget)
        self.dashboard_charts_grid.addWidget(self.dashboard_bar_chart, 0, 0, 1, 2)
        self.dashboard_charts_grid.addWidget(self.dashboard_donut_chart, 1, 0, 1, 2)
        self._reflow_dashboard_header(width)
        columns = 4 if width >= 1000 else 2 if width >= 560 else 1
        for index, widget in enumerate((self.dashboard_personal, self.dashboard_receivables, self.dashboard_msi, self.dashboard_discount)):
            self.dashboard_indicator_grid.removeWidget(widget)
            self.dashboard_indicator_grid.addWidget(widget, index // columns, index % columns)
            widget.layout().setContentsMargins(6, 4, 6, 4)
        calendar_columns = 3 if width >= 800 else 2 if width >= 560 else 1
        for index, widget in enumerate(self.dashboard_calendar_cards):
            self.dashboard_calendar_grid.removeWidget(widget)
            self.dashboard_calendar_grid.addWidget(widget, index // calendar_columns, index % calendar_columns)
        wide = width >= 1150
        for widget in (self.dashboard_person_toggle, self.dashboard_person_pdf):
            self.dashboard_person_header.removeWidget(widget)
        self.dashboard_person_header.addWidget(self.dashboard_person_toggle, 0 if width >= 740 else 1, 1 if width >= 740 else 0)
        self.dashboard_person_header.addWidget(self.dashboard_person_pdf, 0 if width >= 740 else 1, 2 if width >= 740 else 1)
        self.dashboard_tables_grid.removeWidget(self.dashboard_card_section)
        self.dashboard_tables_grid.removeWidget(self.dashboard_person_section)
        self.dashboard_tables_grid.addWidget(self.dashboard_card_section, 0, 0)
        self.dashboard_tables_grid.addWidget(self.dashboard_person_section, 0 if wide else 1, 1 if wide else 0)
        self.dashboard_tables_grid.setColumnStretch(1, 1 if wide else 0)

    def _reflow_dashboard_header(self, viewport_width):
        """Give the action flow its complete row width, rather than its largest button."""
        grid = self.dashboard_header_grid
        actions = self.dashboard_header_actions
        flow = actions.layout()
        buttons = [flow.itemAt(i).widget() for i in range(flow.count())]
        row_width = sum(button.sizeHint().width() for button in buttons) + flow.spacing() * (len(buttons)-1)
        margins = self.dashboard_scroll.widget().layout().contentsMargins()
        available = max(0, viewport_width - margins.left() - margins.right())
        heading_width = self.dashboard_heading.minimumSizeHint().width()
        gap = max(0, grid.horizontalSpacing())
        inline = heading_width + gap + row_width <= available
        for widget in (self.dashboard_heading, actions):
            grid.removeWidget(widget)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        actions.setMinimumWidth(row_width if inline else 0)
        if inline:
            grid.addWidget(self.dashboard_heading, 0, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(actions, 0, 1, Qt.AlignmentFlag.AlignVCenter)
            action_width = available - heading_width - gap
        else:
            grid.addWidget(self.dashboard_heading, 0, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(actions, 1, 0, 1, 2)
            action_width = available
        actions.setFixedHeight(flow.heightForWidth(max(1, action_width)))

    def eventFilter(self, watched, event):
        if hasattr(self, 'cards_scroll') and watched is self.cards_scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._fit_card_tables()
        if hasattr(self, 'collection_history') and watched is self.collections_scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._reflow_collections()
            self._style_collection_table(self.collection_items, (3, 4, 5, 11, 12, 13))
            self._style_collection_table(self.collection_history, (3,))
        if hasattr(self, 'manual_scroll') and watched is self.manual_scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._reflow_manual_information()
        if hasattr(self, 'orders_scroll') and watched is self.orders_scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._reflow_orders()
        if hasattr(self, 'dashboard_scroll') and watched is self.dashboard_scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._reflow_dashboard()
        return super().eventFilter(watched, event)

    def _prepare_month_payment(self):
        from valenza.gui.cash_review import CashReviewDialog
        dialog = CashReviewDialog(self.repository, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            instrument_id = dialog.card.currentData()
            self._show_page(self.PAGES.index('Tarjetas'))
            index = self.card_instrument.findData(instrument_id)
            if index >= 0:
                self.card_instrument.setCurrentIndex(index)
        dialog.deleteLater()

    def _show_person_statement(self):
        identity = self._table_id(self.dashboard_people,5)
        self.dashboard_person_pdf.setEnabled(bool(identity))
        label = next((label for label, person_id in getattr(self, '_dashboard_chart_people', {}).items()
                      if person_id == identity), None)
        if label is not None:
            self.dashboard_donut_chart.select_person(label, emit=False)

    def _toggle_person_breakdown(self, checked):
        if checked:
            self.dashboard_person_details.set_data(
                self.repository.people_debt_summary() if self.repository else [],
                self.repository.list_collection_items() if self.repository else [])
        self.dashboard_person_details.setVisible(checked)
        for column in (3, 4):
            self.dashboard_people.setColumnHidden(column, not checked)
        self._fit_dashboard_table(self.dashboard_people)

    def _select_breakdown_person(self, identity):
        for row in range(self.dashboard_people.rowCount()):
            if self.dashboard_people.item(row, 5).text() == identity:
                self.dashboard_people.selectRow(row)
                break

    def _select_chart_person(self, label, *, details=False):
        identity = getattr(self, '_dashboard_chart_people', {}).get(label)
        if identity:
            self._select_breakdown_person(identity)
            if details:
                self.dashboard_person_toggle.setChecked(True)
                self.dashboard_scroll.ensureWidgetVisible(self.dashboard_person_section)

    @staticmethod
    def _make_card(label: str, value: str) -> QFrame:
        card = QFrame()
        card.setObjectName("summaryCard")
        layout = QVBoxLayout(card)
        caption = QLabel(label)
        caption.setWordWrap(True)
        amount = QLabel(value)
        amount.setObjectName("summaryAmount")
        amount.setWordWrap(True)
        amount.setMinimumWidth(0)
        amount.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(caption)
        layout.addWidget(amount)
        return card

    def _open_search(self):
        if self.repository is None:
            return
        if self._search_dialog is not None:
            self._search_dialog.raise_()
            self._search_dialog.input.setFocus()
            return
        dialog = SearchDialog(self.repository, self)
        self._search_dialog = dialog
        dialog.recordActivated.connect(self._open_search_result)
        dialog.finished.connect(lambda: setattr(self, '_search_dialog', None))
        dialog.open()

    @staticmethod
    def _search_select(table, column, identity):
        table.clearSelection()
        for row in range(table.rowCount()):
            if table.item(row, column).text() == identity:
                table.selectRow(row)
                table.scrollToItem(table.item(row, column))
                table.setFocus()
                return True
        return False

    def _open_search_result(self, result):
        kind, identity = result['kind'], result['id']
        tables = {'order': 'order_record', 'purchase': 'purchase', 'person': 'person',
                  'card': 'payment_instrument', 'bank_payment': 'institution_payment', 'receipt': 'user_payment'}
        if kind not in tables:
            return
        try:
            record = self.repository.database.connection.execute(
                'SELECT ' + ('id,instrument_id' if kind == 'bank_payment' else 'id')
                + ' FROM ' + tables[kind] + ' WHERE id=?', (identity,)).fetchone()
            if record is None:
                self._show_information('El registro ya no está disponible.')
                return
            page = {'order': 'Pedidos', 'purchase': 'Cobros', 'person': 'Usuarios',
                    'card': 'Tarjetas', 'bank_payment': 'Tarjetas', 'receipt': 'Cobros'}[kind]
            if kind in ('purchase','receipt'):self._remember_collection_draft()
            self.navigation.setCurrentRow(self.PAGES.index(page))
            selected = False
            if kind == 'order':
                self.order_filter.setCurrentIndex(self.order_filter.findData('ALL'))
                self._refresh_orders()
                selected = self._search_select(self.orders_table, 8, identity)
            elif kind == 'person':
                selected = self._search_select(self.people_table, 0, identity)
            elif kind in ('card', 'bank_payment'):
                card_id = identity if kind == 'card' else record['instrument_id']
                selected = self._search_select(self.cards_table, 12, card_id)
                if kind == 'bank_payment' and selected:
                    self.card_panels['payments'][0].setChecked(True)
                    selected = self._search_select(self.card_payment_history, 4, identity)
                    self.cards_scroll.ensureWidgetVisible(self.card_payment_history)
            elif kind == 'receipt':
                self.collection_filter.setCurrentIndex(self.collection_filter.findData('ALL'))
                self.collection_history_toggle.setChecked(True)
                self._refresh_collections()
                selected = self._search_select(self.collection_history, 6, identity)
                self.collections_scroll.ensureWidgetVisible(self.collection_history)
            elif kind == 'purchase':
                self._refresh_collection_items()
                entries=[entry for entry in self.repository.list_collection_items() if entry['source_id']==identity and entry['source_kind']=='Compra histórica']
                selected=next((self._search_select(self.collection_items,7,e['receivable_id']) for e in entries
                    if any(self.collection_items.item(r,7).text()==e['receivable_id'] for r in range(self.collection_items.rowCount()))),False)
                if not selected and entries:
                    self.collection_filter.setCurrentIndex(self.collection_filter.findData('ALL'))
                    selected=self._search_select(self.collection_items,7,entries[0]['receivable_id'])
                if selected:
                    self.collection_mode_notice.setText('Consultando participaciones de '+str(entries[0]['source_name'])+' · '+date_label(entries[0]['source_date'])+
                        '. Personas: '+', '.join(e['user_name'] for e in entries)+'. Selecciona una participación para preparar un abono.')
                    self.collection_return_button.show()
                    self.collections_scroll.ensureWidgetVisible(self.collection_items)
                else:
                    self._return_to_collection_draft()
                    self._show_information('Esta compra no tiene participaciones disponibles para consultar.')
                    return
            if not selected:
                self._show_information('Se abrió la sección. El registro no está disponible en esta vista.')
        except DATABASE_ERRORS as error:
            self._show_error(self._safe_error(error))

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
            "Suscripciones": self._refresh_subscriptions,
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

    def _brand_instrument(self, identity):
        return next((i for i in self.repository.list_all_instruments() if i['id'] == identity), None)

    def _fill_combo(self, combo: QComboBox, choices: list[tuple[str, object]]) -> None:
        selected = combo.currentData()
        institution_fields = ('order_institution', 'card_institution', 'purchase_institution', 'admin_institution', 'admin_card_institution')
        instrument_fields = ('order_instrument', 'card_instrument', 'purchase_instrument')
        brands = {}
        if any(combo is getattr(self, name, None) for name in institution_fields):
            brands = {i['id']: i['name'] for i in self.repository.list_all_institutions()}
        elif any(combo is getattr(self, name, None) for name in instrument_fields):
            brands = {i['id']: i['institution_name'] for i in self.repository.list_all_instruments()}
        with QSignalBlocker(combo):
            combo.clear()
            for label, value in choices:
                combo.addItem(label, value)
                if brands and value in brands:
                    combo.setItemIcon(combo.count()-1, brand_icon(brands[value], 'institution'))
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
            and not self._consulting_receipt
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
        self.edit_concepts_button.setEnabled(order is not None and order['order_status'] == 'ACTIVE')
        self.edit_order_button.setEnabled(order is not None and order["order_status"] == "ACTIVE")
        self.msi_button.setEnabled(order is not None and order['order_status']=='ACTIVE')
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
            if dirty and QMessageBox.question(self, 'Captura sin guardar', '¿Cerrar Valenza y descartar la captura sin guardar? Los cambios ya guardados se conservan.', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
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
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Valenza.Desktop')
        application = QApplication(argv if argv is not None else sys.argv)
        application.setWindowIcon(QIcon(str(Path(__file__).parent / 'assets' / 'icono_app_claro.png')))
    install_design_system(application)
    return application


def default_database_path(*, test_mode=False, home=None):
    """Use Valenza for new installations; retain existing legacy databases."""
    data_root = (Path(home) if home is not None else Path.home()) / 'AppData' / 'Local'
    preferred = data_root / 'Valenza' / ('valenza-test.db' if test_mode else 'valenza.db')
    legacy = data_root / 'SGCCC' / ('sgccc-test.db' if test_mode else 'sgccc.db')
    if preferred.exists():
        return preferred
    if legacy.exists():
        return legacy
    return preferred


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
    database_path = default_database_path(test_mode=test_mode)
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
    dialog = UnlockDialog()
    while True:
        database = None
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        password = dialog.take_password()
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
            dialog.show_error()


if __name__ == "__main__":
    raise SystemExit(main())
