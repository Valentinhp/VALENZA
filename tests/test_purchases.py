import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QMessageBox

from valenza.finance.models import AllocationMethod, ProductLine
from valenza.finance.rules import allocate_line_shares
from valenza.gui.app import MainWindow, create_application
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository


@pytest.fixture
def application():
    app = create_application([])
    yield app
    app.quit()


@pytest.fixture
def repository(tmp_path):
    database = LocalDatabase.open(tmp_path / "purchases.db", "purchase-password")
    database.migrate()
    repository = FinanceRepository(database)
    repository.create_person("Propietario Ficticio", is_owner=True)
    repository.create_person("Cliente Ficticio")
    repository.ensure_demo_catalog()
    yield repository
    database.close()


def test_unit_and_percentage_shares_use_exact_cents():
    line = ProductLine("line", "Producto", 3, 100)
    units = allocate_line_shares(
        line,
        (("owner", AllocationMethod.UNITS, 1), ("client", AllocationMethod.UNITS, 2)),
    )
    assert [item.share_cents for item in units] == [100, 200]

    uneven = ProductLine("line-2", "Producto", 1, 100)
    percentages = allocate_line_shares(
        uneven,
        (("owner", AllocationMethod.PERCENT, 3333),
         ("client", AllocationMethod.PERCENT, 6667)),
    )
    assert sum(item.share_cents for item in percentages) == 100
    assert [item.share_cents for item in percentages] == [33, 67]


@pytest.mark.parametrize(
    ("value", "expected"),
    [("10.00", 1000), ("99.90", 9990), ("1250.50", 125050)],
)
def test_mxn_input_converts_to_cents_without_float(value, expected):
    assert MainWindow._parse_mxn_to_cents(value) == expected


def test_mxn_input_rejects_more_than_two_decimals():
    with pytest.raises(ValueError, match="dos decimales"):
        MainWindow._parse_mxn_to_cents("10.001")


def _create_purchase(repository):
    instrument_id = repository.list_instruments()[0]["id"]
    people = {person["name"]: person["id"] for person in repository.list_people()}
    repository.create_purchase(
        purchase_id="purchase-1",
        purchased_at="2026-10-10",
        merchant="Comercio Ficticio",
        instrument_id=str(instrument_id),
        products=(
            {"id": "product-1", "description": "Producto A", "quantity": 3,
             "unit_price_cents": 1000},
        ),
        allocations=(
            {"product_id": "product-1", "user_id": people["Propietario Ficticio"],
             "method": "UNITS", "basis": 1},
            {"product_id": "product-1", "user_id": people["Cliente Ficticio"],
             "method": "UNITS", "basis": 2},
        ),
    )


def test_purchase_persists_products_allocations_receivable_and_audit(repository, tmp_path):
    _create_purchase(repository)
    purchase = repository.get_purchase("purchase-1")
    assert purchase["total_cents"] == 3000
    assert purchase["owner_cents"] == 1000
    assert sorted(
        item["share_cents"] for item in purchase["products"][0]["allocations"]
    ) == [1000, 2000]
    assert purchase["receivables"][0]["sale_cents"] == 2000
    assert repository.count("audit_event") == 3
    changes = repository.database.connection.total_changes
    collection = {item["user_id"]: item for item in repository.list_collection_items()}
    owner_id = next(person["id"] for person in repository.list_people() if person["is_owner"])
    assert collection[owner_id]["participant_role"] == "PERSONAL"
    assert collection[owner_id]["virtual"] is True
    assert collection[owner_id]["sale_cents"] == 1000
    assert repository.database.connection.total_changes == changes

    database = repository.database
    database.close()
    reopened = LocalDatabase.open(tmp_path / "purchases.db", "purchase-password")
    try:
        recovered = FinanceRepository(reopened).get_purchase("purchase-1")
        assert recovered["merchant"] == "Comercio Ficticio"
        assert recovered["products"][0]["description"] == "Producto A"
        assert sorted(
            item["share_cents"] for item in recovered["products"][0]["allocations"]
        ) == [1000, 2000]
    finally:
        reopened.close()


def test_order_can_be_saved_without_products_and_reopened(repository, tmp_path):
    instrument_id = repository.list_instruments()[0]["id"]
    people = {person["name"]: person["id"] for person in repository.list_people()}
    repository.create_order(
        order_id="order-direct-1",
        ordered_at="2026-10-10",
        merchant="Pedido total ficticio",
        instrument_id=str(instrument_id),
        original_cents=500000,
        discount_cents=0,
        charged_cents=500000,
        allocations=(
            {"user_id": people["Propietario Ficticio"], "amount_cents": 150000},
            {"user_id": people["Cliente Ficticio"], "amount_cents": 350000},
        ),
    )
    saved = repository.get_order("order-direct-1")
    assert saved["total_to_recover_cents"] == 500000
    assert saved["owner_cents"] == 150000
    assert 350000 in [item["sale_cents"] for item in saved["receivables"]]
    repository.database.close()
    reopened = LocalDatabase.open(tmp_path / "purchases.db", "purchase-password")
    try:
        recovered = FinanceRepository(reopened).get_order("order-direct-1")
        assert recovered["allocations"][0]["amount_cents"] in (150000, 350000)
        assert recovered["receivables"][0]["source_type"] == "ORDER"
    finally:
        reopened.close()


def test_collections_table_selects_by_stable_receivable_id_and_prefills_balance(
    application, repository
):
    instrument_id = repository.list_instruments()[0]["id"]
    people = {person["name"]: person["id"] for person in repository.list_people()}
    repository.create_order(
        order_id="collection-order-ui",
        ordered_at="2026-10-10",
        merchant="Comercio Cobro UI",
        instrument_id=str(instrument_id),
        original_cents=6000,
        discount_cents=0,
        charged_cents=6000,
        allocations=(
            {"user_id": people["Propietario Ficticio"], "amount_cents": 0},
            {"user_id": people["Cliente Ficticio"], "amount_cents": 6000},
        ),
    )
    window = MainWindow(database=repository.database)
    assert window.collection_items.rowCount() == 1
    window.collection_items.sortItems(1, Qt.SortOrder.DescendingOrder)
    window.collection_items.selectRow(0)
    assert window.collection_amount.text() == "60.00"
    assert "60.00" in window.collection_current_balance.text()
    assert people["Cliente Ficticio"] in window.collection_items.item(0, 1).text()
    window.close()


def test_collections_screen_keeps_paid_rows_and_blocks_reentrant_receipt(
    application, repository, monkeypatch
):
    instrument_id = repository.list_instruments()[0]["id"]
    people = {person["name"]: person["id"] for person in repository.list_people()}
    repository.create_order(
        order_id="collection-order-paid-ui",
        ordered_at="2026-10-10",
        merchant="Comercio Pagado UI",
        instrument_id=str(instrument_id),
        original_cents=2000,
        discount_cents=0,
        charged_cents=2000,
        allocations=(
            {"user_id": people["Propietario Ficticio"], "amount_cents": 0},
            {"user_id": people["Cliente Ficticio"], "amount_cents": 2000},
        ),
    )
    repository.record_receipt(
        payment_id="paid-ui-payment",
        receivable_id="order:collection-order-paid-ui:"
        + str(people["Cliente Ficticio"]),
        amount_cents=2000,
        received_at="2026-10-10",
    )
    window = MainWindow(database=repository.database)
    assert window.collection_items.rowCount() == 1
    assert window.collection_items.item(0, 6).text() == "Pagado"
    calls = []
    monkeypatch.setattr(
        repository, "record_receipt",
        lambda **kwargs: calls.append(kwargs),
    )
    window._collection_receipt_in_progress = True
    window._record_collection()
    assert calls == []
    window.close()


def test_order_discount_is_separate_from_card_charge_and_requires_exact_distribution(
    repository,
):
    instrument_id = repository.list_instruments()[0]["id"]
    people = {person["name"]: person["id"] for person in repository.list_people()}
    repository.create_order(
        order_id="order-discount-1",
        ordered_at="2026-10-10",
        merchant="Pedido con descuento",
        instrument_id=str(instrument_id),
        original_cents=10000,
        discount_cents=1000,
        charged_cents=9000,
        allocations=(
            {"user_id": people["Propietario Ficticio"], "amount_cents": 1000},
            {"user_id": people["Cliente Ficticio"], "amount_cents": 9000},
        ),
    )
    order = repository.get_order("order-discount-1")
    assert order["discount_cents"] == 1000
    assert order["charged_cents"] == 9000
    assert order["total_to_recover_cents"] == 10000
    assert order["owner_cents"] == 1000
    assert 9000 in [item["sale_cents"] for item in order["receivables"]]


def test_order_discount_with_zero_owner_still_recovers_original_amount(repository):
    instrument_id = repository.list_instruments()[0]["id"]
    client_id = next(
        person["id"] for person in repository.list_people() if not person["is_owner"]
    )
    owner_id = next(
        person["id"] for person in repository.list_people() if person["is_owner"]
    )
    repository.create_order(
        order_id="order-discount-no-owner-share",
        ordered_at="2026-10-10",
        merchant="Pedido sin parte personal",
        instrument_id=str(instrument_id),
        original_cents=200000,
        discount_cents=30000,
        charged_cents=170000,
        allocations=(
            {"user_id": owner_id, "amount_cents": 0},
            {"user_id": client_id, "amount_cents": 200000},
        ),
    )
    order = repository.get_order("order-discount-no-owner-share")
    assert order["total_to_recover_cents"] == 200000
    assert order["owner_cents"] == 0
    assert order["receivables"][0]["sale_cents"] == 200000


def test_order_without_discount_recovers_original_amount(repository):
    instrument_id = repository.list_instruments()[0]["id"]
    people = {person["name"]: person["id"] for person in repository.list_people()}
    repository.create_order(
        order_id="order-no-discount",
        ordered_at="2026-10-10",
        merchant="Pedido sin descuento",
        instrument_id=str(instrument_id),
        original_cents=10000,
        discount_cents=0,
        charged_cents=10000,
        allocations=(
            {"user_id": people["Propietario Ficticio"], "amount_cents": 2500},
            {"user_id": people["Cliente Ficticio"], "amount_cents": 7500},
        ),
    )
    order = repository.get_order("order-no-discount")
    assert order["total_to_recover_cents"] == 10000
    assert 7500 in [item["sale_cents"] for item in order["receivables"]]


def test_order_rejects_duplicate_or_incomplete_allocations(repository):
    instrument_id = repository.list_instruments()[0]["id"]
    people = {person["name"]: person["id"] for person in repository.list_people()}
    with pytest.raises(ValueError, match="sumar"):
        repository.create_order(
            order_id="order-invalid-1",
            ordered_at="2026-10-10",
            merchant="Pedido incompleto",
            instrument_id=str(instrument_id),
            original_cents=10000,
            discount_cents=0,
            charged_cents=10000,
            allocations=(
                {"user_id": people["Propietario Ficticio"], "amount_cents": 0},
                {"user_id": people["Cliente Ficticio"], "amount_cents": 9999},
            ),
        )
    with pytest.raises(ValueError, match="repetirse"):
        repository.create_order(
            order_id="order-invalid-2",
            ordered_at="2026-10-10",
            merchant="Pedido duplicado",
            instrument_id=str(instrument_id),
            original_cents=10000,
            discount_cents=0,
            charged_cents=10000,
            allocations=(
                {"user_id": people["Propietario Ficticio"], "amount_cents": 5000},
                {"user_id": people["Propietario Ficticio"], "amount_cents": 5000},
            ),
        )


def test_order_screen_saves_direct_distribution_without_products(
    application, repository, monkeypatch
):
    monkeypatch.setattr(MainWindow, "_show_information", lambda self, message: None)
    monkeypatch.setattr(MainWindow, "_show_error", lambda self, message: pytest.fail(message)    )
    window = MainWindow(database=repository.database)
    window.purchase_merchant.setText("Pedido UI directo")
    window.order_original.setText("5000.00")
    window.order_discount.setText("0.00")
    window.order_charged.setText("5000.00")
    owner_id = next(
        person["id"] for person in repository.list_people() if person["is_owner"]
    )
    client_id = next(
        person["id"] for person in repository.list_people() if not person["is_owner"]
    )
    window.order_user.setCurrentIndex(window.order_user.findData(client_id))
    window.order_amount.setText("3500.00")
    window._add_order_allocation()
    window.order_allocations_table.selectRow(0)
    window.order_user.setCurrentIndex(window.order_user.findData(owner_id))
    window.order_amount.setText("1500.00")
    window._edit_order_allocation()
    window._save_order()
    assert repository.list_orders()[0]["total_to_recover_cents"] == 500000
    assert repository.get_order(repository.list_orders()[0]["id"])["allocations"]
    window.close()


def test_order_screen_uses_direct_editable_rows_and_updates_summary(
    application, repository, monkeypatch
):
    monkeypatch.setattr(MainWindow, "_show_information", lambda self, message: None)
    monkeypatch.setattr(
        MainWindow, "_show_error", lambda self, message: pytest.fail(message)
    )
    window = MainWindow(database=repository.database)
    window.order_merchant.setText("Pedido rediseñado ficticio")
    window.order_original.setText("5000.00")
    window.order_charged.setText("4700.00")

    rows_by_name = {
        window.order_allocations_table.item(row, 0).text(): row
        for row in range(window.order_allocations_table.rowCount())
    }
    assert "Propietario Ficticio" in rows_by_name
    assert all(
        window.order_allocations_table.item(row, 1).text() == "0.00"
        for row in rows_by_name.values()
    )
    owner_row = next(
        row
        for row in rows_by_name.values()
        if window.order_allocations_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        in {
            str(person["id"])
            for person in repository.list_people()
            if person["is_owner"]
        }
    )
    other_row = next(row for row in rows_by_name.values() if row != owner_row)
    window.order_allocations_table.item(owner_row, 1).setText("1500.00")
    window.order_allocations_table.item(other_row, 1).setText("3500.00")
    assert "Sin repartir: $0.00 MXN" in window.order_summary.text()
    assert "Descuento calculado" not in window.order_summary.text()
    assert window.order_discount.text() == "$300.00 MXN"
    window._save_order()
    assert window.orders_table.rowCount() == 1
    window.orders_table.selectRow(0)
    assert window.order_detail.toPlainText().count("$1,500.00 MXN") == 1
    window.close()


def test_order_screen_shows_reconciliation_exception_without_negative_discount(
    application, repository
):
    window = MainWindow(database=repository.database)
    window.order_original.setText("100.00")
    window.order_charged.setText("125.00")
    assert window.order_discount.text() == "$0.00 MXN"
    assert "Cargo superior al original" in window.order_exception.text()
    window.close()


def test_order_exact_yo_and_j_case_uses_persistent_owner_id(
    application, repository, monkeypatch
):
    monkeypatch.setattr(MainWindow, "_show_information", lambda self, message: None)
    monkeypatch.setattr(
        MainWindow, "_show_error", lambda self, message: pytest.fail(message)
    )
    owner_id = next(person["id"] for person in repository.list_people() if person["is_owner"])
    client_id = next(person["id"] for person in repository.list_people() if not person["is_owner"])
    repository.update_person(owner_id, "Yo", is_owner=True)
    repository.update_person(client_id, "J", is_owner=False)
    window = MainWindow(database=repository.database)
    _configure_order(
        window,
        400000,
        387500,
        {str(owner_id): 399900, str(client_id): 100},
    )
    assert "Propietario: $3,999.00 MXN" in window.order_summary.text()
    assert "Cuentas por cobrar: $1.00 MXN" in window.order_summary.text()
    window._save_order()
    saved = repository.get_order(repository.list_orders()[0]["id"])
    assert saved["owner_cents"] == 399900
    assert sorted(item["sale_cents"] for item in saved["receivables"]) == [100, 399900]
    window.close()


def test_order_reports_visible_yo_when_persistent_owner_is_different(
    application, repository
):
    owner_id = next(person["id"] for person in repository.list_people() if person["is_owner"])
    client_id = next(person["id"] for person in repository.list_people() if not person["is_owner"])
    repository.update_person(client_id, "Yo", is_owner=False)
    window = MainWindow(database=repository.database)
    _configure_order(
        window,
        400000,
        387500,
        {str(owner_id): 0, str(client_id): 400000},
    )
    assert "Inconsistencia de catálogo" in window.order_summary.text()
    assert "Yo no es" in window.order_summary.text()
    assert "is_owner" not in window.order_summary.text()
    assert str(client_id) not in window.order_summary.text()
    assert window.save_order_button.isEnabled() is False
    window.close()


def _order_rows_by_user_id(window):
    return {
        str(window.order_allocations_table.item(row, 0).data(Qt.ItemDataRole.UserRole)): row
        for row in range(window.order_allocations_table.rowCount())
    }


def _configure_order(window, original, charged, amounts_by_user_id):
    window.order_merchant.setText("Pedido exacto ficticio")
    window.order_original.setText(f"{original / 100:.2f}")
    window.order_charged.setText(f"{charged / 100:.2f}")
    rows = _order_rows_by_user_id(window)
    for user_id, amount in amounts_by_user_id.items():
        window.order_allocations_table.item(rows[user_id], 1).setText(
            f"{amount / 100:.2f}"
        )


def test_order_screen_saves_owner_only_5000_without_false_missing_owner(
    application, repository, monkeypatch
):
    monkeypatch.setattr(MainWindow, "_show_information", lambda self, message: None)
    monkeypatch.setattr(
        MainWindow, "_show_error", lambda self, message: pytest.fail(message)
    )
    window = MainWindow(database=repository.database)
    owner_id = next(person["id"] for person in repository.list_people() if person["is_owner"])
    client_id = next(person["id"] for person in repository.list_people() if not person["is_owner"])
    assert str(
        window.order_allocations_table.item(0, 0).data(Qt.ItemDataRole.UserRole)
    ) == str(owner_id)
    window.order_allocations_table.sortItems(0, Qt.SortOrder.AscendingOrder)
    _configure_order(
        window,
        500000,
        345600,
        {str(owner_id): 500000, str(client_id): 0},
    )
    assert "Propietario: $5,000.00 MXN" in window.order_summary.text()
    assert "Cuentas por cobrar: $0.00 MXN" in window.order_summary.text()
    window._save_order()
    saved = repository.get_order(repository.list_orders()[0]["id"])
    assert saved["owner_cents"] == 500000
    assert len(saved["receivables"]) == 1
    assert saved["receivables"][0]["participant_role"] == "PERSONAL"
    assert saved["receivables"][0]["sale_cents"] == 500000
    window.close()


def test_order_screen_mixed_and_third_party_only_distributions(
    application, repository, monkeypatch
):
    monkeypatch.setattr(MainWindow, "_show_information", lambda self, message: None)
    monkeypatch.setattr(
        MainWindow, "_show_error", lambda self, message: pytest.fail(message)
    )
    owner_id = next(person["id"] for person in repository.list_people() if person["is_owner"])
    client_id = next(person["id"] for person in repository.list_people() if not person["is_owner"])

    first = MainWindow(database=repository.database)
    _configure_order(first, 500000, 500000, {str(owner_id): 0, str(client_id): 500000})
    assert "Propietario: $0.00 MXN" in first.order_summary.text()
    assert "Cuentas por cobrar: $5,000.00 MXN" in first.order_summary.text()
    first._save_order()
    first._clear_order_form()
    _configure_order(first, 500000, 500000, {str(owner_id): 200000, str(client_id): 300000})
    assert "Propietario: $2,000.00 MXN" in first.order_summary.text()
    assert "Cuentas por cobrar: $3,000.00 MXN" in first.order_summary.text()
    first._save_order()
    orders = repository.list_orders()
    assert {item["owner_cents"] for item in orders} == {0, 200000}
    assert all(
        amount["sale_cents"] > 0
        for order in (repository.get_order(item["id"]) for item in orders)
        for amount in order["receivables"]
    )
    first.close()


def test_purchase_transaction_rolls_back_when_allocation_is_invalid(repository):
    instrument_id = repository.list_instruments()[0]["id"]
    with pytest.raises(ValueError):
        repository.create_purchase(
            purchase_id="purchase-invalid",
            purchased_at="2026-10-10",
            merchant="Comercio Ficticio",
            instrument_id=str(instrument_id),
            products=(
                {"id": "product-invalid", "description": "Producto", "quantity": 2,
                 "unit_price_cents": 1000},
            ),
            allocations=(
                {"product_id": "product-invalid",
                 "user_id": repository.list_people()[0]["id"],
                 "method": "UNITS", "basis": 1},
            ),
        )
    assert repository.count("purchase") == 0
    assert repository.count("purchase_product") == 0


def test_purchase_screen_saves_and_lists_purchase(
    application, repository, monkeypatch
):
    monkeypatch.setattr(MainWindow, "_show_information", lambda self, message: None)
    monkeypatch.setattr(MainWindow, "_show_error", lambda self, message: pytest.fail(message))
    window = MainWindow(database=repository.database)
    navigation = window.findChild(QListWidget, "navigation")
    navigation.setCurrentRow(2)
    window.purchase_merchant.setText("Comercio UI Ficticio")
    window.product_description.setText("Producto UI")
    window.product_quantity.setValue(2)
    window.product_unit_price.setValue(1250)
    window._add_product_row()
    owner_id = next(
        person["id"] for person in repository.list_people() if person["is_owner"]
    )
    window.allocation_user.setCurrentIndex(window.allocation_user.findData(owner_id))
    window.allocation_basis.setValue(1)
    window._add_allocation_row()
    client_id = next(
        person["id"] for person in repository.list_people() if not person["is_owner"]
    )
    window.allocation_user.setCurrentIndex(window.allocation_user.findData(client_id))
    window.allocation_basis.setValue(1)
    window._add_allocation_row()
    window._save_purchase()
    assert window.purchases_table.rowCount() == 1
    assert "Comercio UI Ficticio" in window.purchases_table.item(0, 1).text()
    window.purchases_table.selectRow(0)
    assert "Producto UI" in window.purchase_detail.toPlainText()
    window.close()


def test_purchase_screen_prevents_duplicate_updates_and_deletes_assignments(
    application, repository, monkeypatch
):
    monkeypatch.setattr(MainWindow, "_show_information", lambda self, message: None)
    errors = []
    monkeypatch.setattr(MainWindow, "_show_error", lambda self, message: errors.append(message))
    window = MainWindow(database=repository.database)
    window.product_description.setText("Producto")
    window.product_unit_price.setText("10.00")
    window.product_quantity.setValue(10)
    window._add_product_row()
    window.allocation_basis.setValue(10)
    window._add_allocation_row()
    window._add_allocation_row()
    assert window.allocations_table.rowCount() == 1
    assert errors
    window.allocations_table.selectRow(0)
    window.allocation_basis.setValue(5)
    window._edit_allocation_row()
    assert window.allocations_table.item(0, 3).text() == "5"
    window._delete_allocation_row()
    assert window.allocations_table.rowCount() == 0
    window.close()


def test_purchase_screen_saves_ten_units_at_ten_mxn_to_owner(
    application, repository, monkeypatch
):
    monkeypatch.setattr(MainWindow, "_show_information", lambda self, message: None)
    monkeypatch.setattr(MainWindow, "_show_error", lambda self, message: pytest.fail(message))
    window = MainWindow(database=repository.database)
    window.purchase_merchant.setText("Comercio propietario ficticio")
    window.product_description.setText("Producto completo")
    window.product_quantity.setValue(10)
    window.product_unit_price.setText("10.00")
    window._add_product_row()
    owner_id = next(
        person["id"] for person in repository.list_people() if person["is_owner"]
    )
    window.allocation_user.setCurrentIndex(window.allocation_user.findData(owner_id))
    window.allocation_basis.setValue(10)
    window._add_allocation_row()
    window._save_purchase()
    purchase = repository.list_purchases()[0]
    assert purchase["total_cents"] == 10000
    assert purchase["owner_cents"] == 10000
    assert repository.get_purchase(purchase["id"])["receivables"] == []
    items = repository.list_collection_items()
    assert len(items) == 1
    assert items[0]["participant_role"] == "PERSONAL"
    repository.record_receipt(payment_id="legacy-owner", receivable_id=items[0]["receivable_id"],
                              amount_cents=1000, received_at="2026-10-10")
    assert repository.list_collection_items()[0]["remaining_cents"] == 9000
    assert repository.count("institution_payment") == 0
    window.close()
