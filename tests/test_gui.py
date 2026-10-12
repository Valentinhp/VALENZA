import pytest


import subprocess
import sys

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QListWidget

from sgccc.gui.app import MainWindow, create_application
from sgccc.persistence.database import LocalDatabase
from sgccc.persistence.repository import FinanceRepository


@pytest.fixture
def application():
    app = create_application([])
    yield app
    from PySide6.QtCore import QCoreApplication,QEvent
    # Close demo windows too and complete WA_DeleteOnClose before Python exits.
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    for widget in app.topLevelWidgets():
        if isinstance(widget,MainWindow):
            widget.close()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    app.processEvents()
    app.quit()


def test_personal_collection_filter_and_immediate_balances(application, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QLabel, QMessageBox
    database = LocalDatabase.open(tmp_path / "personal-ui.db", "synthetic-only")
    database.migrate()
    repository = FinanceRepository(database)
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_person("j", "J")
    repository.add_institution("bank", "Banco")
    repository.add_instrument("card", "bank", "Tarjeta", "CREDIT_CARD")
    repository.create_order(order_id="both", ordered_at="2026-10-10", merchant="Sintético",
                            instrument_id="card", original_cents=10000, discount_cents=1000,
                            charged_cents=9000,
                            allocations=({"user_id": "owner", "amount_cents": 4000},
                                         {"user_id": "j", "amount_cents": 6000}))
    monkeypatch.setattr(MainWindow, "_show_information", lambda *args: None)
    monkeypatch.setattr(MainWindow, "_show_error", lambda self, text: pytest.fail(text))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window = MainWindow(database=database, test_mode=True)
    assert window.collection_items.rowCount() == 2
    window.collection_filter.setCurrentIndex(1)
    assert window.collection_items.rowCount() == 1
    assert window.collection_items.item(0, 0).text() == "Yo"
    assert window.collection_items.item(0, 10).text() == "Mi parte"
    window.collection_items.selectRow(0)
    assert window.record_collection_button.text() == "Registrar abono personal"
    window.collection_amount.setText("10.00")
    window._record_collection()
    assert window.collection_items.item(0, 5).text() == "$30.00 MXN"
    assert window.dashboard_personal.findChild(QLabel, "summaryAmount").text() == "$30.00 MXN"
    assert window.dashboard_receivables.findChild(QLabel, "summaryAmount").text() == "$60.00 MXN"
    assert window.cards_table.item(0, 4).text() == "$90.00 MXN"
    assert window.collection_history.item(0, 7).text() == "Mi parte"
    assert any("Abono personal" in window.dashboard_movements.item(i).text()
               for i in range(window.dashboard_movements.count()))
    window.collection_history.selectRow(0)
    window.collection_amount.setText("5.00")
    window._edit_selected_receipt()
    assert window.collection_items.item(0, 5).text() == "$35.00 MXN"
    window.collection_history.selectRow(0)
    window._cancel_selected_receipt()
    assert window.collection_items.item(0, 5).text() == "$40.00 MXN"
    assert window.collection_history.item(0, 7).text() == "Mi parte"
    assert not window.edit_receipt_button.isEnabled()
    window.collection_filter.setCurrentIndex(2)
    assert window.collection_items.rowCount() == 1
    assert window.collection_items.item(0, 0).text() == "J"
    assert window.collection_history.rowCount() == 0
    assert repository.count("institution_payment") == 0
    window.close()
    database.close()


def test_main_window_starts_in_demo_mode(application):
    window = MainWindow()
    assert "demostración" in window.windowTitle()
    assert window.pages.count() == 8
    assert "Compras históricas" not in MainWindow.PAGES
    assert window.pages.currentIndex() == 0
    assert window.findChild(type(window.pages), "pages") is window.pages


def test_navigation_reaches_all_declared_screens(application):
    window = MainWindow()
    navigation = window.findChild(QListWidget, "navigation")
    assert navigation is not None
    for index, page_name in enumerate(MainWindow.PAGES):
        navigation.setCurrentRow(index)
        assert window.pages.currentIndex() == index
        assert page_name in navigation.item(index).text()


def test_dashboard_keeps_institutional_and_receivable_amounts_separate(application):
    window = MainWindow()
    dashboard = window.pages.widget(0)
    assert dashboard.findChild(QListWidget, "recentMovements") is not None
    assert window.demo_data.receivables_cents != window.demo_data.institutional_balance_cents


def test_gui_package_does_not_preload_application_module():
    result = subprocess.run(
        [
            sys.executable,
            "-W",
            "error",
            "-c",
            "import sys; import sgccc.gui; "
            "assert 'sgccc.gui.app' not in sys.modules",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stderr == ""


def test_orders_screen_refreshes_and_filters_cancelled_orders(application):
    database = LocalDatabase.open(
        ":memory:", "gui-test", allow_synthetic_in_memory=True
    )
    database.migrate()
    repository = FinanceRepository(database)
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_institution("inst", "Banco")
    repository.add_instrument("card", "inst", "Tarjeta", "CREDIT_CARD")
    repository.create_order(
        order_id="gui-order", ordered_at="2026-10-10", merchant="Comercio",
        instrument_id="card", original_cents=1000, discount_cents=0,
        charged_cents=1000,
        allocations=({"user_id": "owner", "amount_cents": 1000},),
    )
    window = MainWindow(database=database)
    window._show_page(MainWindow.PAGES.index("Pedidos"))
    assert window.orders_table.rowCount() == 1
    repository.cancel_order("gui-order", reason="Prueba GUI")
    window.data_changed.emit("orders")
    assert window.orders_table.rowCount() == 0
    window.order_filter.setCurrentIndex(1)
    assert window.orders_table.rowCount() == 1
    assert window.orders_table.item(0, 7).text() == "Anulado"
    window.close()


def test_card_installment_selector_and_cancelled_payment_availability(application, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    database = LocalDatabase.open(tmp_path / "card-ui.db", "synthetic-only")
    database.migrate()
    repository = FinanceRepository(database)
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_institution("bank", "Banco")
    repository.add_instrument("card", "bank", "Tarjeta", "CREDIT_CARD")
    repository.create_order(order_id="msi", ordered_at="2026-10-10", merchant="Comercio",
        instrument_id="card", original_cents=10000, discount_cents=0, charged_cents=10000,
        allocations=({"user_id":"owner", "amount_cents":10000},), purchase_mode="MSI",
        financing_specs=("2027-01-10",))
    repository.record_institution_payment(payment_id="payment", instrument_id="card",
        paid_at="2026-10-10", amount_cents=4000)
    window = MainWindow(database=database, test_mode=True)
    window.cards_table.selectRow(0)
    assert window.card_apply_installment.currentData() == "plan:msi-1"
    assert window.card_apply_payment.currentData() == "payment"
    monkeypatch.setattr(MainWindow, "_show_information", lambda *args: None)
    monkeypatch.setattr(MainWindow, "_show_error", lambda self, text: pytest.fail(text))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window._show_page(MainWindow.PAGES.index("Tarjetas"))
    window.cards_table.selectRow(0)
    window.card_apply_amount.setText("10.00")
    window._apply_card_payment()
    assert repository.list_installments("card")[0]["remaining_cents"] == 9000
    window.cards_table.selectRow(0)
    window.card_payment_history.selectRow(0)
    window._cancel_selected_card_payment()
    window.cards_table.selectRow(0)
    assert window.card_payment_history.item(0, 5).text() == "$0.00 MXN"
    assert window.card_apply_payment.count() == 0
    assert window.card_apply_installment.count() == 1
    assert repository.list_installments("card")[0]["remaining_cents"] == 10000
    window.close()


def test_persistent_dashboard_uses_active_operations_and_keeps_bank_debt_separate(application, tmp_path):
    from PySide6.QtWidgets import QLabel

    database = LocalDatabase.open(tmp_path / "dashboard.db", "synthetic-only")
    database.migrate()
    repository = FinanceRepository(database)
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_person("j", "J")
    repository.add_institution("bank", "Banco")
    repository.add_instrument("card", "bank", "Tarjeta", "CREDIT_CARD")
    window = MainWindow(database=database, test_mode=True)
    amount = lambda card: card.findChild(QLabel, "summaryAmount").text()
    assert amount(window.dashboard_receivables) == "$0.00 MXN"
    assert amount(window.dashboard_debt) == "$0.00 MXN"
    repository.create_order(order_id="a", ordered_at="2026-10-10", merchant="Comercio",
        instrument_id="card", original_cents=10000, discount_cents=0, charged_cents=8000,
        allocations=({"user_id":"owner", "amount_cents":4000},
                     {"user_id":"j", "amount_cents":6000}))
    window.data_changed.emit("orders")
    assert amount(window.dashboard_receivables) == "$60.00 MXN"
    assert amount(window.dashboard_debt) == "$80.00 MXN"
    repository.record_receipt(payment_id="receipt", receivable_id="order:a:j",
        amount_cents=2000, received_at="2026-10-10")
    window.data_changed.emit("collections")
    assert amount(window.dashboard_receivables) == "$40.00 MXN"
    assert amount(window.dashboard_debt) == "$80.00 MXN"
    repository.cancel_user_payment("receipt", reason="Prueba")
    repository.cancel_order("a", reason="Prueba")
    window.data_changed.emit("orders")
    assert amount(window.dashboard_receivables) == "$0.00 MXN"
    assert amount(window.dashboard_debt) == "$0.00 MXN"
    texts = [window.dashboard_movements.item(i).text() for i in range(window.dashboard_movements.count())]
    assert any("Anulado" in text for text in texts)
    assert not any("DEMO" in text for text in texts)
    window.close()


def test_persistent_window_is_not_labelled_demonstration(application, tmp_path):
    database = LocalDatabase.open(tmp_path / "operational.db", "synthetic-only")
    database.migrate()
    window = MainWindow(database=database)
    assert window.windowTitle() == "SGCCC"
    window.close()


def test_gui_operations_refresh_all_screens_and_preserve_unfinished_order(application, tmp_path, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel, QMessageBox

    database = LocalDatabase.open(tmp_path / "refresh.db", "synthetic-only")
    database.migrate()
    repository = FinanceRepository(database)
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_person("j", "J")
    repository.add_institution("bank", "Banco")
    repository.add_instrument("card", "bank", "Tarjeta", "CREDIT_CARD")
    monkeypatch.setattr(MainWindow, "_show_information", lambda *args: None)
    monkeypatch.setattr(MainWindow, "_show_error", lambda self, text: pytest.fail(text))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window = MainWindow(database=database, test_mode=True)
    window.order_merchant.setText("Comercio")
    window.order_original.setText("25.00")
    window.order_charged.setText("20.00")
    for row in range(window.order_allocations_table.rowCount()):
        user = window.order_allocations_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        window.order_allocations_table.item(row, 1).setText("10.00" if user == "owner" else "15.00")
    assert window.save_order_button.isEnabled()
    window._save_order()
    window.collection_filter.setCurrentIndex(2)
    assert window.orders_table.rowCount() == window.collection_items.rowCount() == 1
    assert window.cards_table.item(0, 4).text() == "$20.00 MXN"
    assert window.dashboard_receivables.findChild(QLabel, "summaryAmount").text() == "$15.00 MXN"
    window.order_merchant.setText("Borrador")
    window.order_original.setText("50.00")
    window.order_charged.setText("50.00")
    window.order_allocations_table.item(0, 1).setText("50.00")
    window.person_name.setText("Nueva persona")
    window._create_person()
    assert window.order_merchant.text() == "Borrador"
    assert window.order_original.text() == "50.00"
    assert window.order_allocations_table.rowCount() == 3
    assert window.order_allocations_table.item(0, 1).text() == "50.00"
    window.collection_items.selectRow(0)
    window.collection_amount.setText("5.00")
    assert window.record_collection_button.isEnabled()
    window._record_collection()
    assert window.collection_items.item(0, 5).text() == "$10.00 MXN"
    assert window.cards_table.item(0, 4).text() == "$20.00 MXN"
    window.orders_table.selectRow(0)
    assert not window.cancel_order_button.isEnabled()
    window.collection_history.selectRow(0)
    window._cancel_selected_receipt()
    assert window.collection_items.item(0, 5).text() == "$15.00 MXN"
    assert window.cancel_order_button.isEnabled()
    window._cancel_selected_order()
    assert window.orders_table.rowCount() == window.collection_items.rowCount() == 0
    assert window.cards_table.item(0, 4).text() == "$0.00 MXN"
    window.order_filter.setCurrentIndex(1)
    window.orders_table.selectRow(0)
    assert not window.cancel_order_button.isEnabled()
    assert not window.edit_order_button.isEnabled()
    assert window.collection_items.isColumnHidden(1)
    assert window.owner_people_table.isColumnHidden(0)
    window.close()


def test_edit_order_merchant_preserves_amounts_and_refreshes_collections(application, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    database = LocalDatabase.open(tmp_path / "edit-order.db", "synthetic-only")
    database.migrate()
    repository = FinanceRepository(database)
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_person("j", "J")
    repository.add_institution("bank", "Banco")
    repository.add_instrument("card", "bank", "Tarjeta", "CREDIT_CARD")
    repository.create_order(order_id="a", ordered_at="2026-10-10", merchant="Original",
        instrument_id="card", original_cents=1000, discount_cents=0, charged_cents=1000,
        allocations=({"user_id":"owner", "amount_cents":0}, {"user_id":"j", "amount_cents":1000}))
    window = MainWindow(database=database, test_mode=True)
    window.orders_table.selectRow(0)
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Corregido", True))
    monkeypatch.setattr(MainWindow, "_show_information", lambda *args: None)
    window._edit_order_merchant()
    order = repository.get_order("a")
    assert order["merchant"] == "Corregido"
    assert order["charged_cents"] == order["receivables"][0]["sale_cents"] == 1000
    assert window.collection_items.item(0, 2).text() == "Corregido"
    assert database.connection.execute("SELECT COUNT(*) FROM audit_event WHERE action = 'ORDER_MERCHANT_UPDATED'").fetchone()[0] == 1
    window.close()


def test_demo_cli_does_not_open_any_database(monkeypatch):
    import sgccc.gui.app as module

    class DemoApplication:
        def exec(self):
            return 0

    class DemoWindow:
        def __init__(self, **kwargs):
            assert not kwargs

        def show(self):
            pass

    monkeypatch.setattr(sys, "argv", ["sgccc", "--demo"])
    monkeypatch.setattr(module, "create_application", lambda: DemoApplication())
    monkeypatch.setattr(module, "MainWindow", DemoWindow)
    monkeypatch.setattr(module, "open_database_with_prompt", lambda *args: pytest.fail("Se intentó abrir una base"))
    assert module.main() == 0
