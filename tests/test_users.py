from sgccc.persistence.database import SCHEMA_VERSION

import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QListWidget, QMessageBox, QInputDialog

from sgccc.gui import MainWindow as LazyMainWindow
from sgccc.gui.app import MainWindow, create_application, open_database_with_prompt
from sgccc.persistence.database import LocalDatabase
from sgccc.persistence.repository import FinanceRepository


@pytest.fixture
def application():
    app = create_application([])
    yield app
    app.quit()


@pytest.fixture
def encrypted_database(tmp_path):
    database = LocalDatabase.open(tmp_path / "users.db", "synthetic-test-password")
    database.migrate()
    yield database
    database.close()


def test_user_crud_persists_and_audits(encrypted_database, tmp_path):
    repository = FinanceRepository(encrypted_database)
    person_id = repository.create_person("Ana Ficticia", actor="test")
    repository.update_person(person_id, "Ana Editada", is_owner=True, actor="test")
    repository.deactivate_person(person_id, actor="test")
    encrypted_database.close()

    reopened = LocalDatabase.open(tmp_path / "users.db", "synthetic-test-password")
    try:
        person = FinanceRepository(reopened).get_person(person_id)
        assert person == {
            "id": person_id,
            "name": "Ana Editada",
            "is_owner": 1,
            "active": 0,
        }
        assert reopened.connection.execute(
            "SELECT COUNT(*) FROM audit_event WHERE entity_id = ?", (person_id,)
        ).fetchone()[0] == 3
    finally:
        reopened.close()


def test_duplicate_person_name_is_rejected(encrypted_database):
    repository = FinanceRepository(encrypted_database)
    repository.create_person("Persona Ficticia")
    with pytest.raises(ValueError, match="Ya existe"):
        repository.create_person("  persona ficticia  ")


def test_reactivation_preserves_id_and_audits(encrypted_database):
    repository = FinanceRepository(encrypted_database)
    person_id = repository.create_person("Persona Reactivable", actor="test")
    repository.deactivate_person(person_id, actor="test")
    repository.reactivate_person(person_id, actor="test")
    person = repository.get_person(person_id)
    assert person["id"] == person_id
    assert person["active"] == 1
    assert encrypted_database.connection.execute(
        "SELECT action FROM audit_event WHERE entity_id = ? ORDER BY occurred_at",
        (person_id,),
    ).fetchall()[-1][0] == "REACTIVATED"
    with pytest.raises(ValueError, match="ya está activa"):
        repository.reactivate_person(person_id)


def test_configure_owner_repairs_existing_catalog_atomically_and_preserves_references(
    encrypted_database, tmp_path
):
    repository = FinanceRepository(encrypted_database)
    yo_id = repository.create_person("Yo", actor="test")
    j_id = repository.create_person("J", actor="test")
    repository.ensure_demo_catalog()
    instrument_id = repository.list_instruments()[0]["id"]
    repository.create_purchase(
        purchase_id="existing-purchase",
        purchased_at="2026-10-10",
        merchant="Compra existente",
        instrument_id=str(instrument_id),
        products=(
            {
                "id": "existing-product",
                "description": "Producto existente",
                "quantity": 1,
                "unit_price_cents": 1000,
            },
        ),
        allocations=(
            {
                "product_id": "existing-product",
                "user_id": j_id,
                "method": "UNITS",
                "basis": 1,
            },
        ),
    )
    result = repository.configure_owner(j_id, actor="test")
    people = {person["id"]: person for person in repository.list_people()}
    assert people[yo_id]["is_owner"] == 0
    assert people[j_id]["is_owner"] == 1
    assert sum(int(person["active"] and person["is_owner"]) for person in people.values()) == 1
    assert result["owner_id"] == j_id
    assert result["historical_references"]["purchase_allocations"] == 1
    assert repository.get_purchase("existing-purchase")["owner_cents"] == 0
    assert repository.database.connection.execute(
        "SELECT COUNT(*) FROM audit_event WHERE action = 'OWNER_CONFIGURED'"
    ).fetchone()[0] == 1
    encrypted_database.close()
    reopened = LocalDatabase.open(tmp_path / "users.db", "synthetic-test-password")
    try:
        reopened_people = {
            person["id"]: person for person in FinanceRepository(reopened).list_people()
        }
        assert reopened_people[yo_id]["is_owner"] == 0
        assert reopened_people[j_id]["is_owner"] == 1
    finally:
        reopened.close()


def test_configure_owner_rejects_inactive_person_without_changes(encrypted_database):
    repository = FinanceRepository(encrypted_database)
    owner_id = repository.create_person("Propietario antiguo", is_owner=True)
    inactive_id = repository.create_person("Persona inactiva")
    repository.deactivate_person(inactive_id, actor="test")
    with pytest.raises(ValueError, match="activa"):
        repository.configure_owner(inactive_id, actor="test")
    assert repository.get_person(owner_id)["is_owner"] == 1
    assert repository.get_person(inactive_id)["is_owner"] == 0


def test_users_page_updates_table_for_create_edit_and_deactivate(
    application, encrypted_database, monkeypatch
):
    monkeypatch.setattr(MainWindow, "_show_information", lambda self, message: None)
    monkeypatch.setattr(MainWindow, "_show_error", lambda self, message: pytest.fail(message))
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window = MainWindow(database=encrypted_database)
    navigation = window.findChild(QListWidget, "navigation")
    navigation.setCurrentRow(1)

    window.person_name.setText("Luis Ficticio")
    window._create_person()
    assert window.people_table.rowCount() == 1
    assert window.people_table.item(0, 1).text() == "Luis Ficticio"

    window.people_table.selectRow(0)
    window.person_name.setText("Luis Editado")
    window._update_person()
    assert window.people_table.item(0, 1).text() == "Luis Editado"

    window._deactivate_person()
    assert window.people_table.item(0, 3).text() == "Desactivado"
    window._reactivate_person()
    assert window.people_table.item(0, 3).text() == "Activo"
    window.close()


def test_settings_configures_selected_owner_and_refreshes_orders(
    application, encrypted_database, monkeypatch
):
    monkeypatch.setattr(MainWindow, "_show_information", lambda self, message: None)
    monkeypatch.setattr(MainWindow, "_show_error", lambda self, message: pytest.fail(message))
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    repository = FinanceRepository(encrypted_database)
    yo_id = repository.create_person("Yo")
    j_id = repository.create_person("J")
    repository.ensure_demo_catalog()
    window = MainWindow(database=encrypted_database)
    people = {
        window.owner_people_table.item(row, 1).text(): row
        for row in range(window.owner_people_table.rowCount())
    }
    window.owner_people_table.selectRow(people["J"])
    window._configure_owner()
    assert repository.get_person(j_id)["is_owner"] == 1
    assert repository.get_person(yo_id)["is_owner"] == 0
    assert all(
        window.order_allocations_table.item(row, 1).text() == "0.00"
        for row in range(window.order_allocations_table.rowCount())
    )
    assert window.order_allocations_table.item(0, 0).text() == "J"
    window.close()


def test_users_flow_survives_window_close_and_reopen(
    application, tmp_path, monkeypatch
):
    monkeypatch.setattr(MainWindow, "_show_information", lambda self, message: None)
    monkeypatch.setattr(MainWindow, "_show_error", lambda self, message: pytest.fail(message))
    database_path = tmp_path / "restart.db"
    first_database = LocalDatabase.open(database_path, "restart-password")
    first_database.migrate()
    first_window = MainWindow(database=first_database)
    first_window.person_name.setText("Marta Persistente")
    first_window._create_person()
    person_id = first_window.people_table.item(0, 0).text()
    first_window.people_table.selectRow(0)
    first_window.person_name.setText("Marta Editada")
    first_window._update_person()
    first_window.close()

    second_database = LocalDatabase.open(database_path, "restart-password")
    second_window = MainWindow(database=second_database)
    assert second_window.people_table.rowCount() == 1
    assert second_window.people_table.item(0, 1).text() == "Marta Editada"
    second_window.people_table.selectRow(0)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    second_window._deactivate_person()
    assert second_window.people_table.item(0, 3).text() == "Desactivado"
    second_window.close()
    assert person_id


def test_gui_package_exports_are_lazy():
    assert LazyMainWindow is MainWindow


def test_wrong_password_can_retry_and_preserves_original_data(
    application, tmp_path, monkeypatch
):
    path = tmp_path / "protected.db"
    database = LocalDatabase.open(path, "correct-password")
    database.migrate()
    repository = FinanceRepository(database)
    repository.create_person("No se debe perder", actor="test")
    database.close()

    attempts = iter(
        [
            ("wrong-password", True),
            ("correct-password", True),
        ]
    )
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: next(attempts))
    decisions = iter([QMessageBox.StandardButton.Retry])
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: next(decisions))

    reopened = open_database_with_prompt(application, path)
    assert reopened is not None
    try:
        assert FinanceRepository(reopened).list_people()[0]["name"] == "No se debe perder"
    finally:
        reopened.close()


def test_wrong_password_can_be_cancelled_without_replacing_database(
    application, tmp_path, monkeypatch
):
    path = tmp_path / "protected.db"
    database = LocalDatabase.open(path, "correct-password")
    database.migrate()
    database.close()
    original_bytes = path.read_bytes()

    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *args, **kwargs: ("wrong-password", True),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )

    assert open_database_with_prompt(application, path) is None
    assert path.read_bytes() == original_bytes


def test_opening_old_synthetic_database_verifies_backup_before_upgrade(application, tmp_path, monkeypatch):
    path = tmp_path / "old-test.db"
    database = LocalDatabase.open(path, "synthetic-only")
    database.migrate(target=10)
    FinanceRepository(database).create_person("Conservar", actor="test")
    database.close()
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("synthetic-only", True))
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[2]))
    upgraded = open_database_with_prompt(application, path)
    assert upgraded is not None
    assert upgraded.connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert FinanceRepository(upgraded).list_people()[0]["name"] == "Conservar"
    upgraded.close()
    backups = list((tmp_path / "backups").glob("*.db"))
    assert len(backups) == 1 and messages
    backup = LocalDatabase.open(backups[0], "synthetic-only")
    assert backup.connection.execute("PRAGMA user_version").fetchone()[0] == 10
    assert FinanceRepository(backup).list_people()[0]["name"] == "Conservar"
    backup.close()
