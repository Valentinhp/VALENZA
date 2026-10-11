from pathlib import Path
import secrets
import sqlite3

import pytest

from sgccc.persistence.database import DatabaseSecurityError, LocalDatabase, SCHEMA_VERSION
from sgccc.persistence.repository import FinanceRepository


def memory_repository() -> FinanceRepository:
    database = LocalDatabase.open(
        ":memory:",
        "synthetic-test-password",
        allow_synthetic_in_memory=True,
    )
    database.migrate()
    return FinanceRepository(database)


@pytest.mark.parametrize("owner_share", [500000, 0, 200000])
@pytest.mark.parametrize("mode", ["CASH", "MSI"])
def test_personal_and_family_participations_are_independent_of_bank(tmp_path, owner_share, mode):
    database = LocalDatabase.open(tmp_path / "participants.db", "synthetic-only")
    database.migrate()
    repository = FinanceRepository(database)
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_person("j", "J")
    repository.add_institution("bank", "Banco")
    repository.add_instrument("card", "bank", "Tarjeta", "CREDIT_CARD")
    repository.create_order(
        order_id="order", ordered_at="2026-10-10", merchant="Sintético",
        instrument_id="card", original_cents=500000, discount_cents=50000,
        charged_cents=450000, purchase_mode=mode,
        financing_specs=("2026-11-10", "2026-12-10") if mode == "MSI" else None,
        allocations=({"user_id": "owner", "amount_cents": owner_share},
                     {"user_id": "j", "amount_cents": 500000 - owner_share}),
    )
    items = repository.list_collection_items()
    assert sum(item["sale_cents"] for item in items) == 500000
    assert len(items) == (2 if 0 < owner_share < 500000 else 1)
    initial = repository.dashboard_summary()
    assert initial["personal_pending_cents"] == owner_share
    assert initial["receivables_cents"] == 500000 - owner_share
    bank_initial = repository.list_card_summaries()[0]["remaining_cents"]
    for item in items:
        payment_id = "receipt-" + item["user_id"]
        repository.record_receipt(payment_id=payment_id, receivable_id=item["receivable_id"],
                                  amount_cents=10000, received_at="2026-10-10")
        repository.update_user_payment(payment_id, received_at="2026-10-11", amount_cents=5000)
        assert next(i for i in repository.list_collection_items() if i["user_id"] == item["user_id"])["paid_cents"] == 5000
        repository.update_user_payment(payment_id, received_at="2026-10-11", amount_cents=15000)
        with pytest.raises(ValueError, match="excede"):
            repository.update_user_payment(payment_id, received_at="2026-10-11", amount_cents=item["sale_cents"] + 1)
        assert repository.list_card_summaries()[0]["remaining_cents"] == bank_initial
        with pytest.raises(ValueError):
            repository.cancel_order("order", reason="Aún tiene abonos")
    before_bank = [(i["receivable_id"], i["remaining_cents"]) for i in repository.list_collection_items()]
    repository.record_institution_payment(payment_id="bank-payment", instrument_id="card",
                                          paid_at="2026-10-11", amount_cents=20000)
    assert repository.list_card_summaries()[0]["remaining_cents"] == 430000
    assert [(i["receivable_id"], i["remaining_cents"]) for i in repository.list_collection_items()] == before_bank
    if mode == "MSI":
        assert sum(i["remaining_cents"] for i in repository.list_installments("card")) == 450000
        repository.apply_institution_payment_to_installment(
            payment_id="bank-payment", installment_id=repository.list_installments("card")[0]["id"],
            amount_cents=10000,
        )
        assert sum(i["remaining_cents"] for i in repository.list_installments("card")) == 440000
        assert [(i["receivable_id"], i["remaining_cents"]) for i in repository.list_collection_items()] == before_bank
    repository.cancel_institution_payment("bank-payment", reason="Prueba")
    if mode == "MSI":
        assert sum(i["remaining_cents"] for i in repository.list_installments("card")) == 450000
    for item in items:
        repository.cancel_user_payment("receipt-" + item["user_id"], reason="Prueba")
    restored = repository.dashboard_summary()
    assert restored["personal_pending_cents"] == owner_share
    assert restored["receivables_cents"] == 500000 - owner_share
    history = repository.list_receipt_history()
    assert {i["payment_kind"] for i in history} == {i["participant_role"] for i in items}
    assert all(i["payment_status"] == "CANCELLED" and i["source_name"] == "Sintético" for i in history)
    assert repository.count("institution_payment") == 1
    repository.cancel_order("order", reason="Prueba")
    assert repository.list_collection_items() == []
    assert len(repository.list_receipt_history()) == len(items)
    actions = {row[0] for row in database.connection.execute("SELECT action FROM audit_event")}
    assert {"RECEIPT_RECORDED", "RECEIPT_UPDATED", "RECEIPT_CANCELLED"} <= actions
    database.close()
    reopened = LocalDatabase.open(tmp_path / "participants.db", "synthetic-only")
    assert FinanceRepository(reopened).list_collection_items() == []
    assert len(FinanceRepository(reopened).list_receipt_history()) == len(items)
    reopened.close()


def test_historical_owner_projection_is_read_only_and_materializes_once(tmp_path):
    database = LocalDatabase.open(tmp_path / "history.db", "synthetic-only")
    database.migrate(target=11)
    repository = FinanceRepository(database)
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_person("j", "J")
    repository.add_institution("bank", "Banco")
    repository.add_instrument("card", "bank", "Tarjeta", "CREDIT_CARD")
    with database.transaction() as connection:
        connection.execute("INSERT INTO order_record(id, ordered_at, merchant, instrument_id, original_cents, discount_cents, charged_cents, total_to_recover_cents, owner_cents) VALUES ('old','2026-10-10','Histórico','card',500000,50000,450000,500000,200000)")
        connection.executemany("INSERT INTO order_allocation(order_id,user_id,amount_cents) VALUES ('old',?,?)", [("owner",200000),("j",300000)])
        connection.execute("INSERT INTO receivable(id,user_id,purchase_id,order_id,source_type,sale_cents,attributable_cost_cents) VALUES ('order:old:j','j','old','old','ORDER',300000,300000)")
    original = tuple(database.connection.execute("SELECT * FROM receivable").fetchone())
    database.prepare_migration_backup(tmp_path / "backup.db", "synthetic-only")
    database.migrate()
    assert tuple(database.connection.execute("SELECT * FROM receivable").fetchone())[:-1] == original
    assert database.connection.execute("SELECT participant_role FROM receivable").fetchone()[0] is None
    repository.configure_owner("j")
    changes = database.connection.total_changes
    for _ in range(3):
        items = {i["user_id"]: i for i in repository.list_collection_items()}
        assert items["owner"]["virtual"] and items["owner"]["sale_cents"] == 200000
        assert items["j"]["participant_role"] == "FAMILY"
        assert repository.dashboard_summary()["personal_pending_cents"] == 200000
    assert database.connection.total_changes == changes
    with pytest.raises(ValueError, match="excede"):
        repository.record_receipt(payment_id="invalid", receivable_id="order:old:owner", amount_cents=200001, received_at="2026-10-10")
    assert repository.count("receivable") == 1
    repository.record_receipt(payment_id="personal", receivable_id="order:old:owner", amount_cents=10000, received_at="2026-10-10")
    repository.record_receipt(payment_id="personal2", receivable_id="order:old:owner", amount_cents=5000, received_at="2026-10-10")
    assert repository.count("receivable") == 2
    assert database.connection.execute("SELECT COUNT(*) FROM audit_event WHERE action='PARTICIPATION_TRACKING_STARTED'").fetchone()[0] == 1
    repository.cancel_user_payment("personal", reason="Prueba")
    repository.cancel_user_payment("personal2", reason="Prueba")
    assert next(i for i in repository.list_collection_items() if i["user_id"] == "owner")["remaining_cents"] == 200000
    assert repository.count("institution_payment") == 0
    database.close()


def test_unclassified_historical_account_is_not_duplicated_or_counted_as_family(tmp_path):
    database = LocalDatabase.open(tmp_path / "unclassified.db", "synthetic-only")
    database.migrate()
    repository = FinanceRepository(database)
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_institution("bank", "Banco")
    repository.add_instrument("card", "bank", "Tarjeta", "CREDIT_CARD")
    repository.create_order(order_id="old", ordered_at="2026-10-10", merchant="Sintético",
                            instrument_id="card", original_cents=4000, discount_cents=0,
                            charged_cents=4000,
                            allocations=({"user_id": "owner", "amount_cents": 4000},))
    # Simula una relación histórica incompleta, sin atribuirla por nombre o propietario actual.
    with database.transaction() as connection:
        connection.execute("UPDATE receivable SET id='legacy', order_id=NULL, participant_role=NULL")
    changes = database.connection.total_changes
    items = repository.list_collection_items()
    assert len(items) == 1
    assert items[0]["receivable_id"] == "legacy" and items[0]["participant_role"] == "UNKNOWN"
    summary = repository.dashboard_summary()
    assert summary["personal_pending_cents"] == summary["receivables_cents"] == 0
    assert summary["unclassified_pending_cents"] == 4000
    assert database.connection.total_changes == changes
    assert repository.count("receivable") == 1
    database.close()


def test_receipt_application_classification_and_owner_change_preserve_history():
    repository = memory_repository()
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_person("j", "J")
    repository.add_institution("bank", "Banco")
    repository.add_instrument("card", "bank", "Tarjeta", "CREDIT_CARD")
    repository.create_order(order_id="one", ordered_at="2026-10-10", merchant="Sintético",
                            instrument_id="card", original_cents=10000, discount_cents=0,
                            charged_cents=10000,
                            allocations=({"user_id": "owner", "amount_cents": 4000},
                                         {"user_id": "j", "amount_cents": 6000}))
    repository.configure_owner("j")
    roles = {i["user_id"]: i["participant_role"] for i in repository.list_collection_items()}
    assert roles == {"owner": "PERSONAL", "j": "FAMILY"}
    repository.add_user_payment("personal", "owner", "2026-10-10", 2000)
    repository.apply_receipt("personal", "order:one:owner", 1000)
    assert repository.list_receipt_history()[0]["payment_kind"] == "PERSONAL"
    repository.create_order(order_id="two", ordered_at="2026-10-10", merchant="Otro",
                            instrument_id="card", original_cents=10000, discount_cents=0,
                            charged_cents=10000,
                            allocations=({"user_id": "owner", "amount_cents": 4000},
                                         {"user_id": "j", "amount_cents": 6000}))
    with pytest.raises(ValueError, match="mezclar"):
        repository.apply_receipt("personal", "order:two:owner", 1000)
    assert repository.count("receipt_application") == 1
    assert repository.count("institution_payment") == 0
    repository.database.close()


def test_persistent_database_is_rejected_without_sqlcipher(tmp_path: Path):
    try:
        from sqlcipher3 import dbapi2 as sqlcipher
    except ImportError:
        sqlcipher = None
    if sqlcipher is None:
        with pytest.raises(DatabaseSecurityError, match="SQLCipher"):
            LocalDatabase.open(tmp_path / "financial.db", "password")
    else:
        password = secrets.token_urlsafe(32)
        database = LocalDatabase.open(tmp_path / "financial.db", password)
        assert database.encrypted is True
        assert database.cipher_version
        database.close()


def test_encrypted_database_reopens_only_with_correct_key(tmp_path: Path):
    pytest.importorskip("sqlcipher3")
    password = secrets.token_urlsafe(32)
    path = tmp_path / "encrypted.db"

    database = LocalDatabase.open(path, password)
    database.migrate()
    repository = FinanceRepository(database)
    repository.add_person("owner", "Propietario", is_owner=True)
    cipher_version = database.cipher_version
    database.close()

    reopened = LocalDatabase.open(path, password)
    assert reopened.cipher_version == cipher_version
    assert FinanceRepository(reopened).count("person") == 1
    reopened.close()

    with pytest.raises(DatabaseSecurityError, match="contraseña|dañada"):
        LocalDatabase.open(path, secrets.token_urlsafe(32))

    standard = sqlite3.connect(path)
    try:
        with pytest.raises(Exception, match="not a database|file is encrypted"):
            standard.execute("SELECT count(*) FROM person").fetchone()
    finally:
        standard.close()


def test_memory_schema_migrates_and_rolls_back_on_failure():
    database = LocalDatabase.open(
        ":memory:",
        "synthetic",
        allow_synthetic_in_memory=True,
    )
    database.migrate()
    repository = FinanceRepository(database)
    repository.add_person("owner", "Propietario", is_owner=True)
    with pytest.raises(Exception):
        repository.add_person("owner", "Duplicado")
    assert repository.count("person") == 1


def test_migrations_can_roll_back_and_reapply_in_synthetic_database():
    database = LocalDatabase.open(
        ":memory:",
        "synthetic",
        allow_synthetic_in_memory=True,
    )
    database.migrate()
    database.migrate(target=1)
    assert database.connection.execute("PRAGMA user_version").fetchone()[0] == 1
    with pytest.raises(Exception):
        database.connection.execute("SELECT * FROM user_payment")
    database.migrate()
    assert database.connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert database.connection.execute("SELECT COUNT(*) FROM user_payment").fetchone()[0] == 0


def test_migration_ten_can_roll_back_to_eight_and_reapply():
    database = LocalDatabase.open(
        ":memory:", "synthetic", allow_synthetic_in_memory=True
    )
    database.migrate()
    database.migrate(target=8)
    assert database.connection.execute("PRAGMA user_version").fetchone()[0] == 8
    database.migrate()
    assert database.connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert database.connection.execute(
        "SELECT COUNT(*) FROM financing_plan"
    ).fetchone()[0] == 0


def _card_order_repository() -> FinanceRepository:
    repository = memory_repository()
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_person("ana", "Ana")
    repository.add_institution("inst", "Banco")
    repository.add_instrument("card", "inst", "555555 real", "CREDIT_CARD")
    return repository


def test_order_cancellation_is_audited_and_excluded_without_deleting_history():
    repository = _card_order_repository()
    repository.create_order(
        order_id="cancel-me", ordered_at="2026-10-10", merchant="ml",
        instrument_id="card", original_cents=500000, discount_cents=100,
        charged_cents=499900,
        allocations=(
            {"user_id": "owner", "amount_cents": 0},
            {"user_id": "ana", "amount_cents": 500000},
        ),
    )
    repository.cancel_order("cancel-me", reason="Pedido de prueba")
    order = repository.get_order("cancel-me")
    assert order is not None
    assert order["order_status"] == "CANCELLED"
    assert repository.list_card_summaries()[0]["charged_cents"] == 0
    assert repository.list_collection_items() == []
    with pytest.raises(ValueError, match="ya está anulado"):
        repository.cancel_order("cancel-me", reason="Segundo intento")


def test_order_cancellation_blocks_applied_family_receipts():
    repository = _card_order_repository()
    repository.create_order(
        order_id="blocked", ordered_at="2026-10-10", merchant="ml",
        instrument_id="card", original_cents=10000, discount_cents=0,
        charged_cents=10000,
        allocations=(
            {"user_id": "owner", "amount_cents": 0},
            {"user_id": "ana", "amount_cents": 10000},
        ),
    )
    repository.record_receipt(
        payment_id="family-payment", receivable_id="order:blocked:ana",
        amount_cents=100, received_at="2026-10-11",
    )
    with pytest.raises(ValueError, match="abonos personales o familiares"):
        repository.cancel_order("blocked", reason="No procede")
    assert repository.get_order("blocked")["order_status"] == "ACTIVE"


def test_installment_payment_application_is_partial_and_never_auto_assigned():
    repository = _card_order_repository()
    repository.create_order(
        order_id="msi", ordered_at="2026-10-10", merchant="ml",
        instrument_id="card", original_cents=10000, discount_cents=0,
        charged_cents=10000,
        allocations=({"user_id": "owner", "amount_cents": 10000},),
        purchase_mode="MSI", financing_specs=("2027-01-10", "2027-02-10"),
    )
    repository.record_institution_payment(
        payment_id="bank-payment", instrument_id="card",
        paid_at="2026-12-01", amount_cents=2500,
    )
    repository.apply_institution_payment_to_installment(
        payment_id="bank-payment", installment_id="plan:msi-1",
        amount_cents=2500,
    )
    installment = repository.list_installments("card")[0]
    assert installment["status"] == "SCHEDULED"
    assert repository.list_card_summaries()[0]["unassigned_payment_cents"] == 0
    with pytest.raises(ValueError, match="pago disponible"):
        repository.apply_institution_payment_to_installment(
            payment_id="bank-payment", installment_id="plan:msi-1",
            amount_cents=2501,
        )


def test_order_status_filters_and_survives_encrypted_reopen(tmp_path: Path):
    pytest.importorskip("sqlcipher3")
    path = tmp_path / "status.db"
    database = LocalDatabase.open(path, "test-password")
    database.migrate()
    repository = FinanceRepository(database)
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_institution("inst", "Banco")
    repository.add_instrument("card", "inst", "Tarjeta", "CREDIT_CARD")
    repository.create_order(
        order_id="persistent-order", ordered_at="2026-10-10", merchant="ml",
        instrument_id="card", original_cents=1000, discount_cents=0,
        charged_cents=1000,
        allocations=({"user_id": "owner", "amount_cents": 1000},),
    )
    repository.cancel_order("persistent-order", reason="Captura incorrecta")
    database.close()
    reopened = LocalDatabase.open(path, "test-password")
    reopened.migrate()
    reopened_repository = FinanceRepository(reopened)
    assert reopened_repository.list_orders("ACTIVE") == []
    assert [row["id"] for row in reopened_repository.list_orders("CANCELLED")] == [
        "persistent-order"
    ]
    assert reopened_repository.list_orders("ALL")[0]["order_status"] == "CANCELLED"
    reopened.close()


def test_receipt_cancellation_reverses_application_and_recalculates_balance():
    repository = memory_repository()
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_person("ana", "Ana")
    repository.add_institution("inst", "Banco")
    repository.add_instrument("card", "inst", "Tarjeta", "CREDIT_CARD")
    repository.create_order(
        order_id="receipt-order", ordered_at="2026-10-10", merchant="Comercio",
        instrument_id="card", original_cents=1000, discount_cents=0,
        charged_cents=1000,
        allocations=(
            {"user_id": "owner", "amount_cents": 0},
            {"user_id": "ana", "amount_cents": 1000},
        ),
    )
    repository.record_receipt(
        payment_id="receipt-1", receivable_id="order:receipt-order:ana",
        amount_cents=400, received_at="2026-10-10",
    )
    assert repository.list_collection_items()[0]["remaining_cents"] == 600
    repository.cancel_user_payment("receipt-1", reason="Abono equivocado")
    assert repository.list_collection_items()[0]["remaining_cents"] == 1000
    assert repository.list_receipt_history()[0]["payment_status"] == "CANCELLED"
    assert repository.list_receipt_history()[0]["receivable_id"] == "order:receipt-order:ana"
    assert repository.list_receipt_history()[0]["source_name"] == "Comercio"


def test_institution_payment_cancellation_reverses_msi_application():
    repository = _card_order_repository()
    repository.create_order(
        order_id="cancel-payment", ordered_at="2026-10-10", merchant="ml",
        instrument_id="card", original_cents=10000, discount_cents=0,
        charged_cents=10000,
        allocations=({"user_id": "owner", "amount_cents": 10000},),
        purchase_mode="MSI", financing_specs=("2027-01-10",),
    )
    repository.record_institution_payment(
        payment_id="payment-to-cancel", instrument_id="card",
        paid_at="2026-10-10", amount_cents=10000,
    )
    repository.apply_institution_payment_to_installment(
        payment_id="payment-to-cancel", installment_id="plan:cancel-payment-1",
        amount_cents=10000,
    )
    repository.cancel_institution_payment(
        "payment-to-cancel", reason="Pago capturado por error"
    )
    installment = repository.list_installments("card")[0]
    assert installment["payment_status"] == "PENDING"
    assert repository.list_card_summaries()[0]["paid_cents"] == 0
    assert repository.list_institution_payments("card")[0]["payment_status"] == "CANCELLED"


def test_collection_records_partial_and_full_receipts_without_auto_distribution():
    repository = memory_repository()
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_person("ana", "Ana")
    repository.add_institution("inst", "Institución")
    repository.add_instrument("instrument", "inst", "Tarjeta", "CREDIT_LINE")
    repository.create_order(
        order_id="order-1", ordered_at="2026-10-10", merchant="Comercio",
        instrument_id="instrument", original_cents=10000, discount_cents=0,
        charged_cents=10000,
        allocations=(
            {"user_id": "owner", "amount_cents": 0},
            {"user_id": "ana", "amount_cents": 10000},
        ),
    )
    items = repository.list_collection_items()
    assert items[0]["status"] == "Pendiente"
    repository.record_receipt(
        payment_id="payment-1", receivable_id="order:order-1:ana",
        amount_cents=4000, received_at="2026-10-11",
    )
    assert repository.list_collection_items()[0]["status"] == "Pago parcial"
    repository.record_receipt(
        payment_id="payment-2", receivable_id="order:order-1:ana",
        amount_cents=6000, received_at="2026-10-12",
    )
    item = repository.list_collection_items()[0]
    assert item["remaining_cents"] == 0
    assert item["status"] == "Pagado"
    assert len(repository.list_receipt_history()) == 2


def test_collection_rejects_overpayment_and_keeps_extra_and_fee_separate():
    repository = memory_repository()
    repository.add_person("ana", "Ana")
    repository.add_receivable("r-1", "ana", "purchase", 5000, 5000)
    with pytest.raises(ValueError, match="excede"):
        repository.record_receipt(
            payment_id="payment-over", receivable_id="r-1",
            amount_cents=5001, received_at="2026-10-10",
        )
    repository.record_extra(
        extra_id="extra-1", user_id="ana", received_at="2026-10-10",
        amount_cents=250, description="Propina",
    )
    repository.record_deposit_fee(
        fee_id="fee-1", incurred_at="2026-10-10",
        amount_cents=100, description="Depósito agrupado 1",
    )
    assert repository.count("user_payment") == 0
    assert repository.count("cash_extra") == 1
    assert repository.count("deposit_fee") == 1


def test_restart_like_reopen_is_not_claimed_for_unencrypted_storage():
    with pytest.raises(DatabaseSecurityError):
        LocalDatabase.open(":memory:", "synthetic")


def test_foreign_keys_and_idempotent_external_reference_protect_movements():
    repository = memory_repository()
    repository.add_institution("nu", "Nu")
    repository.add_instrument("nu-credit", "nu", "Principal", "CREDIT_LINE")
    repository.add_institution_movement(
        "movement-1", "nu-credit", "2026-10-10", "CHARGE", 10000, "Compra sintetica", "ref-1"
    )
    with pytest.raises(Exception):
        repository.add_institution_movement(
            "movement-2", "nu-credit", "2026-10-10", "CHARGE", 10000, "Reintento", "ref-1"
        )
    assert repository.count("institution_movement") == 1
    with pytest.raises(Exception):
        repository.add_instrument("orphan", "missing", "X", "CREDIT_LINE")


def test_user_payment_and_receivable_are_separate_and_application_is_bounded():
    repository = memory_repository()
    repository.add_person("carlos", "Carlos")
    repository.add_user_payment("payment", "carlos", "2026-10-10", 50000)
    repository.add_receivable("receivable", "carlos", "purchase", 100000, 80000)
    repository.apply_receipt("payment", "receivable", 50000)
    assert repository.count("user_payment") == 1
    assert repository.count("receivable") == 1
    assert repository.count("receipt_application") == 1
    with pytest.raises(ValueError, match="exceden"):
        repository.apply_receipt("payment", "receivable", 1)


def test_atomic_application_rejects_cross_user_without_partial_write():
    repository = memory_repository()
    repository.add_person("carlos", "Carlos")
    repository.add_person("ana", "Ana")
    repository.add_user_payment("payment", "carlos", "2026-10-10", 50000)
    repository.add_receivable("receivable", "ana", "purchase", 100000, 80000)
    with pytest.raises(ValueError, match="usuarios"):
        repository.apply_receipt("payment", "receivable", 50000)
    assert repository.count("receipt_application") == 0


def test_audit_values_are_persisted_as_json():
    repository = memory_repository()
    repository.add_audit_event(
        "audit-1",
        "installment_period",
        "assignment-1",
        "CORRECTED",
        "2026-10-10",
        "owner",
        "Estado oficial",
        {"period": "2026-11"},
        {"period": "2026-12"},
    )
    assert repository.count("audit_event") == 1


def test_card_summary_uses_real_order_charge_and_separates_card_payment():
    repository = memory_repository()
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_institution("inst", "Institución")
    repository.add_instrument("card", "inst", "Tarjeta", "CREDIT_CARD")
    repository.create_order(
        order_id="order-card",
        ordered_at="2026-10-10",
        merchant="Comercio",
        instrument_id="card",
        original_cents=10000,
        discount_cents=2000,
        charged_cents=8000,
        allocations=({"user_id": "owner", "amount_cents": 10000},),
    )
    repository.add_user_payment("family-payment", "owner", "2026-10-11", 3000)
    repository.record_institution_payment(
        payment_id="card-payment",
        instrument_id="card",
        paid_at="2026-10-12",
        amount_cents=2500,
    )
    repository.save_instrument_calendar(
        calendar_id="calendar",
        instrument_id="card",
        effective_from="2026-10-01",
        closing_day=23,
        due_day=3,
    )

    summary = repository.list_card_summaries()[0]
    assert summary["charged_cents"] == 8000
    assert summary["paid_cents"] == 2500
    assert summary["remaining_cents"] == 5500
    assert summary["closing_day"] == 23
    assert summary["due_day"] == 3
    assert repository.count("user_payment") == 1
    assert repository.count("institution_payment") == 1
    assert repository.count("institution_movement") == 0


def test_calendar_revisions_close_previous_calendar_without_losing_history():
    repository = memory_repository()
    repository.add_institution("inst", "Institución")
    repository.add_instrument("card", "inst", "Tarjeta", "CREDIT_CARD")
    repository.save_instrument_calendar(
        calendar_id="calendar-1", instrument_id="card",
        effective_from="2026-10-01", closing_day=23, due_day=3,
    )
    repository.save_instrument_calendar(
        calendar_id="calendar-2", instrument_id="card",
        effective_from="2027-01-01", closing_day=25, due_day=5,
    )
    rows = repository.database.connection.execute(
        "SELECT id, effective_to, revision FROM instrument_calendar "
        "WHERE instrument_id = ? ORDER BY revision",
        ("card",),
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["effective_to"] == "2027-01-01"
    assert rows[1]["effective_to"] is None
    assert rows[1]["revision"] == 2


def test_institution_and_instrument_lifecycle_preserves_history():
    repository = memory_repository()
    repository.add_institution("nu", "Nu")
    repository.add_instrument("nu-card", "nu", "Nu personal", "CREDIT_CARD")
    repository.add_institution_movement(
        "historical-movement", "nu-card", "2026-10-10",
        "CHARGE", 12000, "Cargo histórico",
    )

    repository.update_instrument("nu-card", "Nu real", "CREDIT_CARD")
    repository.set_instrument_active("nu-card", False)

    assert repository.list_instruments() == []
    historical = repository.list_all_instruments()
    assert historical[0]["alias"] == "Nu real"
    assert historical[0]["active"] == 0
    assert repository.count("institution_movement") == 1

    repository.set_instrument_active("nu-card", True)
    assert repository.list_instruments("nu")[0]["alias"] == "Nu real"
    repository.update_institution("nu", "Nu México")
    assert repository.list_all_institutions()[0]["name"] == "Nu México"


def test_institution_and_instrument_creation_rejects_duplicate_or_inactive_catalog():
    repository = memory_repository()
    repository.add_institution("nu", "Nu")
    with pytest.raises(ValueError, match="institución"):
        repository.add_institution("nu-2", " nu ")
    repository.add_instrument("card", "nu", "Principal", "CREDIT_CARD")
    with pytest.raises(ValueError, match="tarjeta"):
        repository.add_instrument("card-2", "nu", "Principal", "CREDIT_CARD")


def test_cash_order_has_no_financing_plan():
    repository = memory_repository()
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_institution("inst", "Institución")
    repository.add_instrument("card", "inst", "Tarjeta", "CREDIT_CARD")
    repository.create_order(
        order_id="cash-order", ordered_at="2026-01-31", merchant="Comercio",
        instrument_id="card", original_cents=10000, discount_cents=0,
        charged_cents=10000, allocations=({"user_id": "owner", "amount_cents": 10000},),
    )
    order = repository.get_order("cash-order")
    assert order["purchase_mode"] == "CASH"
    assert order["financing_plan"] is None
    assert order["installments"] == []


def test_msi_persists_exact_installments_and_periods_across_year_and_short_month(monkeypatch):
    from datetime import date

    class JanuaryDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 1, 31)

    monkeypatch.setattr("sgccc.persistence.repository.date", JanuaryDate)
    repository = memory_repository()
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_institution("inst", "Institución")
    repository.add_instrument("card", "inst", "Tarjeta", "CREDIT_CARD")
    repository.save_instrument_calendar(
        calendar_id="calendar-msi", instrument_id="card",
        effective_from="2026-01-01", closing_day=25, due_day=3,
    )
    repository.create_order(
        order_id="msi-order", ordered_at="2026-01-31", merchant="Comercio MSI",
        instrument_id="card", original_cents=10001, discount_cents=1,
        charged_cents=10000, allocations=({"user_id": "owner", "amount_cents": 10001},),
        purchase_mode="MSI",
        financing_specs=("2026-02-28", "2026-03-28", "2026-04-28"),
    )
    order = repository.get_order("msi-order")
    assert order["purchase_mode"] == "MSI"
    assert [item["principal_cents"] for item in order["installments"]] == [
        3334, 3333, 3333
    ]
    assert sum(item["principal_cents"] for item in order["installments"]) == 10000
    assert all(item["requires_review"] == 0 for item in order["installments"])
    assert [item["period_key"] for item in order["installments"]] == [
        "2026-03", "2026-04", "2026-05"
    ]
    summary = repository.list_card_summaries()[0]
    assert summary["charged_cents"] == 10000
    assert summary["future_installments_cents"] == 10000


def test_msi_without_calendar_stays_pending_until_explicit_confirmation():
    repository = memory_repository()
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_institution("inst", "Institución")
    repository.add_instrument("card", "inst", "Tarjeta", "CREDIT_CARD")
    repository.create_order(
        order_id="pending-msi", ordered_at="2026-10-10", merchant="Comercio",
        instrument_id="card", original_cents=9000, discount_cents=0,
        charged_cents=9000, allocations=({"user_id": "owner", "amount_cents": 9000},),
        purchase_mode="MSI",
        financing_specs=("2026-11-10", "2026-12-10", "2027-01-10"),
    )
    installment = repository.get_order("pending-msi")["installments"][0]
    assert installment["period_key"] is None
    assert installment["requires_review"] == 1
    repository.confirm_installment_period(
        assignment_id=f"period:plan:pending-msi-1",
        period_key="2026-11",
    )
    confirmed = repository.get_order("pending-msi")["installments"][0]
    assert confirmed["period_key"] == "2026-11"
    assert confirmed["requires_review"] == 0


def test_partial_card_payment_does_not_reduce_future_installments():
    repository = memory_repository()
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_institution("inst", "Institución")
    repository.add_instrument("card", "inst", "Tarjeta", "CREDIT_CARD")
    repository.create_order(
        order_id="paid-msi", ordered_at="2026-10-01", merchant="Comercio",
        instrument_id="card", original_cents=12000, discount_cents=0,
        charged_cents=12000, allocations=({"user_id": "owner", "amount_cents": 12000},),
        purchase_mode="MSI",
        financing_specs=("2026-11-01", "2026-12-01", "2027-01-01"),
    )
    repository.record_institution_payment(
        payment_id="advance", instrument_id="card", paid_at="2026-10-02",
        amount_cents=1000,
    )
    summary = repository.list_card_summaries()[0]
    assert summary["paid_cents"] == 1000
    assert summary["remaining_cents"] == 11000
    assert sum(
        item["principal_cents"] + item["interest_cents"]
        for item in repository.list_installments("card")
    ) == 12000


def test_reverted_receipt_allows_order_cancellation_and_preserves_history(tmp_path):
    database = LocalDatabase.open(tmp_path / "reverted.db", "synthetic-only")
    database.migrate()
    repository = FinanceRepository(database)
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_person("j", "J")
    repository.add_institution("bank", "Banco")
    repository.add_instrument("card", "bank", "Tarjeta", "CREDIT_CARD")
    repository.create_order(
        order_id="order", ordered_at="2026-10-10", merchant="ml",
        instrument_id="card", original_cents=10000, discount_cents=0, charged_cents=10000,
        allocations=({"user_id": "owner", "amount_cents": 4000},
                     {"user_id": "j", "amount_cents": 6000}),
    )
    repository.record_receipt(payment_id="receipt", receivable_id="order:order:j",
                              amount_cents=2000, received_at="2026-10-10")
    repository.cancel_user_payment("receipt", reason="Captura incorrecta")
    assert repository.list_collection_items()[0]["remaining_cents"] == 6000
    assert repository.list_collection_items()[0]["source_kind"] == "Pedido"
    assert repository.list_collection_items()[0]["source_date"] == "2026-10-10"
    repository.cancel_order("order", reason="Pedido cancelado")
    assert repository.list_collection_items() == []
    assert repository.list_card_summaries()[0]["remaining_cents"] == 0
    assert repository.list_receipt_history()[0]["source_name"] == "ml"
    assert repository.count("receivable") == 2
    assert repository.count("user_payment") == 1
    with pytest.raises(ValueError, match="anulado"):
        repository.record_receipt(payment_id="new", receivable_id="order:order:j",
                                  amount_cents=100, received_at="2026-10-10")
    with pytest.raises(ValueError, match="anulado"):
        repository.apply_receipt("receipt", "order:order:j", 100)
    database.close()
    reopened = LocalDatabase.open(tmp_path / "reverted.db", "synthetic-only")
    assert FinanceRepository(reopened).list_orders("CANCELLED")[0]["id"] == "order"
    reopened.close()


def test_msi_pending_totals_include_overdue_and_only_explicit_applications(tmp_path):
    from datetime import date

    database = LocalDatabase.open(tmp_path / "msi-balances.db", "synthetic-only")
    database.migrate()
    repository = FinanceRepository(database)
    repository.add_person("owner", "Yo", is_owner=True)
    repository.add_institution("bank", "Banco")
    repository.add_instrument("card", "bank", "Tarjeta", "CREDIT_CARD")
    repository.save_instrument_calendar(calendar_id="calendar", instrument_id="card",
        effective_from="2000-01-01", closing_day=20, due_day=10, source="Prueba")
    repository.create_order(order_id="msi", ordered_at="2000-01-01", merchant="Comercio",
        instrument_id="card", original_cents=9000, discount_cents=0, charged_cents=9000,
        allocations=({"user_id":"owner", "amount_cents":9000},), purchase_mode="MSI",
        financing_specs=("2000-02-10", date.today().isoformat(), "2099-01-10"))
    repository.record_institution_payment(payment_id="payment", instrument_id="card",
        paid_at=date.today().isoformat(), amount_cents=4000)
    assert repository.list_card_summaries()[0]["exigible_cents"] == 6000
    repository.apply_institution_payment_to_installment(payment_id="payment",
        installment_id="plan:msi-1", amount_cents=3000)
    repository.apply_institution_payment_to_installment(payment_id="payment",
        installment_id="plan:msi-2", amount_cents=1000)
    summary = repository.list_card_summaries()[0]
    assert summary["exigible_cents"] == 2000
    assert summary["future_installments_cents"] == 3000
    assert summary["remaining_cents"] == 5000
    repository.cancel_institution_payment("payment", reason="Prueba de reversión")
    assert repository.list_card_summaries()[0]["exigible_cents"] == 6000
    assert repository.list_card_summaries()[0]["remaining_cents"] == 9000
    database.close()


def test_existing_encrypted_database_requires_verified_backup_before_migration(tmp_path):
    path = tmp_path / "old.db"
    backup_path = tmp_path / "backup.db"
    database = LocalDatabase.open(path, "synthetic-only")
    database.migrate(target=10)
    repository = FinanceRepository(database)
    repository.add_person("owner", "Yo", is_owner=True)
    with pytest.raises(DatabaseSecurityError, match="respaldo"):
        database.migrate()
    assert database.connection.execute("PRAGMA user_version").fetchone()[0] == 10
    database.prepare_migration_backup(backup_path, "synthetic-only")
    database.migrate()
    assert database.connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    with pytest.raises(DatabaseSecurityError, match="existe"):
        database.prepare_migration_backup(backup_path, "synthetic-only")
    database.close()
    backup = LocalDatabase.open(backup_path, "synthetic-only")
    assert backup.connection.execute("PRAGMA user_version").fetchone()[0] == 10
    assert FinanceRepository(backup).get_person("owner")["name"] == "Yo"
    backup.close()
    standard = sqlite3.connect(backup_path)
    with pytest.raises(sqlite3.DatabaseError):
        standard.execute("SELECT * FROM person")
    standard.close()
    with pytest.raises(DatabaseSecurityError):
        LocalDatabase.open(backup_path, "incorrect-key")


def test_failed_backup_leaves_existing_schema_unchanged(tmp_path, monkeypatch):
    database = LocalDatabase.open(tmp_path / "old.db", "synthetic-only")
    database.migrate(target=10)
    monkeypatch.setattr(LocalDatabase, "_prepare_migration_backup",
                        lambda *args: (_ for _ in ()).throw(OSError("sin espacio")))
    with pytest.raises(DatabaseSecurityError, match="no se migrará"):
        database.prepare_migration_backup(tmp_path / "backup.db", "synthetic-only")
    with pytest.raises(DatabaseSecurityError, match="respaldo"):
        database.migrate()
    assert database.connection.execute("PRAGMA user_version").fetchone()[0] == 10
    database.close()
