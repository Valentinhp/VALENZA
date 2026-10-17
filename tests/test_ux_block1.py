"""Reading and keyboard regressions against encrypted, disposable databases only."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QAccessible, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QPushButton, QScrollArea, QLineEdit, QDialog

from valenza.gui.app import MainWindow, create_application
from valenza.gui.unlock import UnlockDialog
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository


def settle(app):
    for _ in range(8):
        app.processEvents()


def snapshot(db):
    tables = db.connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return {name: [tuple(row) for row in db.connection.execute('SELECT * FROM "' + name + '" ORDER BY rowid')]
            for (name,) in tables.fetchall()}


@pytest.fixture
def window(tmp_path):
    app = create_application([])
    # The offscreen Windows plugin does not discover system fonts itself.
    for font in ('segoeui.ttf', 'seguisb.ttf', 'georgia.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
    db = LocalDatabase.open(tmp_path / 'ux-block1-encrypted.db', 'synthetic-only')
    assert db.encrypted
    db.migrate()
    repo = FinanceRepository(db)
    repo.add_person('owner', 'Yo sintético', is_owner=True)
    repo.add_person('family', 'Familia sintética con nombre largo')
    repo.add_institution('bank', 'Banco sintético')
    repo.add_instrument('card', 'bank', 'Tarjeta sintética', 'CREDIT_CARD')
    repo.create_order(order_id='normal', ordered_at='2026-09-05', merchant='Compra normal sintética',
        instrument_id='card', original_cents=150000, discount_cents=0, charged_cents=150000,
        allocations=({'user_id': 'owner', 'amount_cents': 50000},
                     {'user_id': 'family', 'amount_cents': 100000}))
    repo.create_order(order_id='msi', ordered_at='2026-09-20', merchant='MSI sintético',
        instrument_id='card', original_cents=1200000, discount_cents=0, charged_cents=1200000,
        allocations=({'user_id': 'owner', 'amount_cents': 400000},
                     {'user_id': 'family', 'amount_cents': 800000}), purchase_mode='MSI',
        financing_specs=tuple(f'{2026 + (9+i)//12}-{(9+i)%12+1:02d}-15' for i in range(12)))
    repo.save_subscription(subscription_id='sub', name='Servicio sintético', amount_cents=10000,
        instrument_id='card', next_due='2026-10-20', allocations=[
            dict(user_id='owner', amount_cents=5000), dict(user_id='family', amount_cents=5000)])
    ui = MainWindow(database=db, test_mode=True)
    ui.show()
    settle(app)
    yield app, ui, db
    ui.close()
    settle(app)


@pytest.mark.parametrize('size', [(1100, 760), (680, 480), (820, 600), (1360, 900)])
def test_all_seven_pages_keep_controls_and_financial_data(window, size, tmp_path):
    app, ui, db = window
    before = snapshot(db)
    changes = db.connection.total_changes
    ui.resize(*size)
    settle(app)
    assert ui.size().toTuple() == size
    assert ui.navigation.count() == 7
    assert ui.navigation.horizontalScrollBar().maximum() == 0
    for index in range(7):
        ui.navigation.setCurrentRow(index)
        settle(app)
        page = ui.pages.widget(index)
        scrolls = ([page] if isinstance(page, QScrollArea) else []) + page.findChildren(QScrollArea)
        for scroll in scrolls:
            if scroll.isVisible():
                assert scroll.horizontalScrollBar().maximum() == 0, (ui.PAGES[index], scroll.objectName())
        assert ui.grab().save(str(tmp_path / f'{index}-{size[0]}.png'))
    # Tables keep their own scrolling; no columns or actions are removed to fit.
    ui.navigation.setCurrentRow(2)
    settle(app)
    assert ui.orders_table.rowCount() == 2
    assert ui.orders_table.columnCount() == 9
    for row in range(ui.orders_table.rowCount()):
        item = ui.orders_table.item(row, 0)
        assert ui.orders_table.columnWidth(0) >= ui.orders_table.fontMetrics().horizontalAdvance(item.text()) + 6
    assert not ui.new_expense_button.isHidden()
    assert not ui.order_filter.isHidden()
    assert all(not button.isHidden() for group in ui.order_action_groups for button in group.findChildren(QPushButton))
    if size[0] == 680:
        assert ui.orders_table.horizontalScrollBar().maximum() > 0
    ui.navigation.setCurrentRow(3)
    ui.collection_details_toggle.setChecked(True)
    ui.other_operations_toggle.setChecked(True)
    ui.collection_history_toggle.setChecked(True)
    settle(app)
    assert ui.collections_scroll.horizontalScrollBar().maximum() == 0
    panel = ui.person_receipt_panel
    assert all(not field.isHidden() for field in (panel.person, panel.amount, panel.received_date,
        panel.reference, panel.future, panel.undated, panel.register, panel.current, panel.all))
    ui.navigation.setCurrentRow(4)
    ui.cards_table.selectRow(0)
    for toggle, content in ui.card_panels.values():
        toggle.setChecked(True)
        for button in content.findChildren(QPushButton):
            if button.isCheckable():
                button.setChecked(True)
        settle(app)
        assert content.isVisible()
        assert ui.cards_scroll.horizontalScrollBar().maximum() == 0
        toggle.setChecked(False)
    assert snapshot(db) == before
    assert db.connection.total_changes == changes


@pytest.mark.parametrize('size', [(680, 480), (1100, 760)])
def test_long_summary_amounts_and_status_are_not_clipped(window, size):
    app, ui, db = window
    before = snapshot(db)
    ui.resize(*size)
    ui.navigation.setCurrentRow(4)
    settle(app)
    values = ('$123,456,789,012,345.67 MXN',
              'Total sin determinar · vencimiento pendiente de configurar o confirmar',
              '$987,654,321,098,765.43 MXN')
    for card, text in zip(ui.card_summary_cards, values):
        card.findChild(QLabel, 'summaryAmount').setText(text)
    settle(app)
    for card, text in zip(ui.card_summary_cards, values):
        ui.cards_scroll.ensureWidgetVisible(card)
        settle(app)
        label = card.findChild(QLabel, 'summaryAmount')
        assert label.text() == text
        assert label.wordWrap()
        assert label.height() >= label.heightForWidth(label.width())
        assert card.rect().contains(label.geometry())
        assert card.width() <= ui.cards_scroll.viewport().width()
    assert snapshot(db) == before


def test_keyboard_navigation_names_and_scrolled_focus(window):
    app, ui, db = window
    before = snapshot(db)
    ui.resize(680, 480)
    ui.navigation.setCurrentRow(0)
    ui.navigation.setFocus()
    for index in range(1, 7):
        QTest.keyClick(ui.navigation, Qt.Key.Key_Down)
        settle(app)
        assert ui.pages.currentIndex() == index
    for control in (ui.person_name, ui.order_filter, ui.collection_filter, ui.collection_amount,
                    ui.person_receipt_panel.person, ui.person_receipt_panel.amount,
                    ui.person_receipt_panel.received_date, ui.person_receipt_panel.reference):
        interface = QAccessible.queryAccessibleInterface(control)
        assert interface.text(QAccessible.Text.Name)
    ui.navigation.setCurrentRow(2)
    ui.new_expense_button.setFocus()
    QTest.keyClick(ui.new_expense_button, Qt.Key.Key_Tab)
    settle(app)
    assert app.focusWidget().text() == 'Importar PDF'
    QTest.keyClick(app.focusWidget(), Qt.Key.Key_Tab)
    assert ui.order_filter.hasFocus()
    ui.new_expense_button.setFocus()
    QTest.keyClick(ui.new_expense_button, Qt.Key.Key_Space)
    settle(app)
    assert ui.manual_dialog.isVisible()
    QTest.keyClick(ui.manual_dialog, Qt.Key.Key_Escape)
    assert not ui.manual_dialog.isVisible()
    ui.navigation.setCurrentRow(3)
    ui.activateWindow()
    settle(app)
    panel = ui.person_receipt_panel
    chain = (panel.person, panel.amount, panel.received_date, panel.reference, panel.future, panel.undated)
    panel.person.setFocus()
    for previous, following in zip(chain, chain[1:]):
        QTest.keyClick(previous, Qt.Key.Key_Tab)
        settle(app)
        assert following.hasFocus()
        viewport = ui.collections_scroll.viewport()
        point = following.mapTo(viewport, following.rect().center())
        assert viewport.rect().contains(point)
    ui.navigation.setCurrentRow(4)
    toggle, content = ui.card_panels['bank']
    toggle.setFocus()
    QTest.keyClick(toggle, Qt.Key.Key_Space)
    settle(app)
    assert content.isVisible()
    assert snapshot(db) == before


def test_unlock_visibility_is_in_tab_order_and_operates_with_space():
    app = create_application([])
    dialog = UnlockDialog()
    dialog.show()
    settle(app)
    dialog.password.setFocus()
    QTest.keyClick(dialog.password, Qt.Key.Key_Tab)
    assert dialog.visibility.hasFocus()
    QTest.keyClick(dialog.visibility, Qt.Key.Key_Space)
    assert dialog.password.echoMode() == QLineEdit.EchoMode.Normal
    # Existing behavior returns focus to the password after revealing it.
    assert dialog.password.hasFocus()
    QTest.keyClick(dialog.password, Qt.Key.Key_Tab)
    QTest.keyClick(dialog.visibility, Qt.Key.Key_Tab)
    assert dialog.cancel_button.hasFocus()
    QTest.keyClick(dialog.cancel_button, Qt.Key.Key_Tab)
    assert dialog.unlock_button.hasFocus()
    QTest.keyClick(dialog.unlock_button, Qt.Key.Key_Escape)
    assert dialog.result() == QDialog.DialogCode.Rejected
