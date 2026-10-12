from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
from typing import Generator

try:
    from sqlcipher3 import dbapi2 as sqlcipher
except ImportError:
    sqlcipher = None

DATABASE_ERRORS = (sqlite3.Error,) if sqlcipher is None else (sqlite3.Error, sqlcipher.Error)


class DatabaseSecurityError(RuntimeError):
    """La base solicitada no cumple el requisito de cifrado."""


SCHEMA_VERSION = 15

MIGRATION_15_UP = """
CREATE TABLE subscription (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    instrument_id TEXT NOT NULL REFERENCES payment_instrument(id),
    next_due TEXT NOT NULL,
    billing_day INTEGER NOT NULL CHECK(billing_day BETWEEN 1 AND 31),
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','PAUSED','CANCELLED')),
    revision INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE subscription_allocation (
    subscription_id TEXT NOT NULL REFERENCES subscription(id),
    user_id TEXT NOT NULL REFERENCES person(id),
    amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
    surcharge_cents INTEGER NOT NULL DEFAULT 0 CHECK(surcharge_cents >= 0),
    PRIMARY KEY(subscription_id,user_id)
);
CREATE TABLE subscription_charge (
    subscription_id TEXT NOT NULL REFERENCES subscription(id),
    cycle_date TEXT NOT NULL,
    order_id TEXT NOT NULL UNIQUE REFERENCES order_record(id),
    PRIMARY KEY(subscription_id,cycle_date)
);
CREATE TABLE subscription_surcharge (
    order_id TEXT NOT NULL REFERENCES order_record(id),
    user_id TEXT NOT NULL REFERENCES person(id),
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    PRIMARY KEY(order_id,user_id)
);
"""
MIGRATION_15_DOWN = """
DROP TABLE IF EXISTS subscription_surcharge;
DROP TABLE IF EXISTS subscription_charge;
DROP TABLE IF EXISTS subscription_allocation;
DROP TABLE IF EXISTS subscription;
"""

MIGRATION_14_UP = """
CREATE TABLE product_refund_repurchase (
    refund_id TEXT PRIMARY KEY REFERENCES imported_product_refund(id),
    order_id TEXT NOT NULL UNIQUE REFERENCES order_record(id),
    applied_cents INTEGER NOT NULL CHECK (applied_cents >= 0)
);
CREATE TABLE product_repurchase_adjustment (
    refund_id TEXT NOT NULL REFERENCES product_refund_repurchase(refund_id),
    order_id TEXT NOT NULL REFERENCES order_record(id),
    user_id TEXT NOT NULL REFERENCES person(id),
    delta_cents INTEGER NOT NULL,
    PRIMARY KEY (refund_id, order_id, user_id)
);
"""
MIGRATION_14_DOWN = """
DROP TABLE IF EXISTS product_repurchase_adjustment;
DROP TABLE IF EXISTS product_refund_repurchase;
"""

MIGRATION_13_UP = """
CREATE TABLE imported_product_refund (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES order_record(id),
    product_index INTEGER NOT NULL CHECK (product_index >= 0),
    source_key TEXT NOT NULL,
    original_cents INTEGER NOT NULL CHECK (original_cents >= 0),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0 AND amount_cents <= original_cents),
    destination_id TEXT NOT NULL REFERENCES payment_instrument(id),
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'ACCREDITED')),
    accredited_at TEXT,
    created_at TEXT NOT NULL,
    movement_id TEXT UNIQUE REFERENCES institution_movement(id),
    CHECK ((status = 'PENDING' AND accredited_at IS NULL AND movement_id IS NULL)
        OR (status = 'ACCREDITED' AND accredited_at IS NOT NULL AND movement_id IS NOT NULL)),
    UNIQUE (source_key, product_index),
    UNIQUE (order_id, product_index)
);
CREATE TABLE product_refund_adjustment (
    refund_id TEXT NOT NULL REFERENCES imported_product_refund(id),
    user_id TEXT NOT NULL REFERENCES person(id),
    original_cents INTEGER NOT NULL CHECK (original_cents >= 0),
    final_cents INTEGER NOT NULL CHECK (final_cents >= 0),
    delta_cents INTEGER NOT NULL CHECK (delta_cents = final_cents - original_cents),
    PRIMARY KEY (refund_id, user_id)
);
"""

MIGRATION_13_DOWN = """
DROP TABLE IF EXISTS product_refund_adjustment;
DROP TABLE IF EXISTS imported_product_refund;
"""

MIGRATION_1_UP = """
CREATE TABLE person (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    is_owner INTEGER NOT NULL DEFAULT 0 CHECK (is_owner IN (0, 1)),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);
CREATE TABLE institution (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);
CREATE TABLE payment_instrument (
    id TEXT PRIMARY KEY,
    institution_id TEXT NOT NULL REFERENCES institution(id),
    alias TEXT NOT NULL CHECK (length(trim(alias)) > 0),
    instrument_type TEXT NOT NULL CHECK (
        instrument_type IN ('CREDIT_LINE', 'CREDIT_CARD', 'WALLET_BALANCE', 'OTHER')
    ),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    UNIQUE (institution_id, alias)
);
CREATE TABLE institution_movement (
    id TEXT PRIMARY KEY,
    instrument_id TEXT NOT NULL REFERENCES payment_instrument(id),
    posted_at TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (
        kind IN ('CHARGE', 'PAYMENT', 'INTEREST', 'COMMISSION', 'REFUND', 'BONUS', 'ADJUSTMENT')
    ),
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
    external_ref TEXT,
    source_document_id TEXT,
    status TEXT NOT NULL DEFAULT 'UNRECONCILED' CHECK (
        status IN ('UNRECONCILED', 'PROPOSED', 'ACCEPTED', 'REJECTED', 'DEFERRED')
    ),
    UNIQUE (instrument_id, external_ref)
);
CREATE TABLE initial_balance (
    id TEXT PRIMARY KEY,
    instrument_id TEXT NOT NULL REFERENCES payment_instrument(id),
    effective_date TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    currency TEXT NOT NULL CHECK (length(currency) = 3),
    source TEXT NOT NULL,
    notes TEXT,
    reconciliation_status TEXT NOT NULL DEFAULT 'UNRECONCILED'
);
CREATE TABLE audit_event (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT
);
"""

MIGRATION_2_UP = """
CREATE TABLE user_payment (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES person(id),
    received_at TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    reference TEXT
);
CREATE TABLE receivable (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES person(id),
    purchase_id TEXT NOT NULL,
    sale_cents INTEGER NOT NULL CHECK (sale_cents >= 0),
    attributable_cost_cents INTEGER NOT NULL CHECK (attributable_cost_cents >= 0),
    due_date TEXT
);
CREATE TABLE receipt_application (
    payment_id TEXT NOT NULL REFERENCES user_payment(id),
    receivable_id TEXT NOT NULL REFERENCES receivable(id),
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    PRIMARY KEY (payment_id, receivable_id)
);
CREATE TABLE match_suggestion (
    id TEXT PRIMARY KEY,
    source_a_id TEXT NOT NULL,
    source_b_id TEXT NOT NULL,
    evidence TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PROPOSED' CHECK (
        status IN ('UNRECONCILED', 'PROPOSED', 'ACCEPTED', 'REJECTED', 'DEFERRED')
    ),
    approved_by TEXT,
    approved_at TEXT,
    UNIQUE (source_a_id, source_b_id)
);
CREATE INDEX idx_movement_instrument_date
    ON institution_movement(instrument_id, posted_at);
CREATE INDEX idx_payment_user_date ON user_payment(user_id, received_at);
CREATE INDEX idx_receivable_user ON receivable(user_id);
"""

MIGRATION_2_DOWN = """
DROP INDEX IF EXISTS idx_receivable_user;
DROP INDEX IF EXISTS idx_payment_user_date;
DROP INDEX IF EXISTS idx_movement_instrument_date;
DROP TABLE IF EXISTS match_suggestion;
DROP TABLE IF EXISTS receipt_application;
DROP TABLE IF EXISTS receivable;
DROP TABLE IF EXISTS user_payment;
"""

MIGRATION_3_UP = """
CREATE UNIQUE INDEX uq_person_normalized_name
    ON person(lower(trim(name)));
"""

MIGRATION_3_DOWN = """
DROP INDEX IF EXISTS uq_person_normalized_name;
"""

MIGRATION_4_UP = """
CREATE TABLE purchase (
    id TEXT PRIMARY KEY,
    purchased_at TEXT NOT NULL,
    merchant TEXT NOT NULL CHECK (length(trim(merchant)) > 0),
    instrument_id TEXT NOT NULL REFERENCES payment_instrument(id),
    total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
    owner_cents INTEGER NOT NULL CHECK (owner_cents >= 0),
    UNIQUE (id)
);
CREATE TABLE purchase_product (
    id TEXT PRIMARY KEY,
    purchase_id TEXT NOT NULL REFERENCES purchase(id) ON DELETE CASCADE,
    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
    UNIQUE (purchase_id, id)
);
CREATE TABLE purchase_allocation (
    product_id TEXT NOT NULL REFERENCES purchase_product(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES person(id),
    method TEXT NOT NULL CHECK (method IN ('UNITS', 'PERCENT')),
    quantity INTEGER,
    percentage_basis INTEGER,
    share_cents INTEGER NOT NULL CHECK (share_cents >= 0),
    PRIMARY KEY (product_id, user_id)
);
CREATE INDEX idx_purchase_date ON purchase(purchased_at);
CREATE INDEX idx_purchase_product_purchase ON purchase_product(purchase_id);
CREATE UNIQUE INDEX uq_receivable_purchase_user
    ON receivable(purchase_id, user_id);
"""

MIGRATION_4_DOWN = """
DROP INDEX IF EXISTS uq_receivable_purchase_user;
DROP INDEX IF EXISTS idx_purchase_product_purchase;
DROP INDEX IF EXISTS idx_purchase_date;
DROP TABLE IF EXISTS purchase_allocation;
DROP TABLE IF EXISTS purchase_product;
DROP TABLE IF EXISTS purchase;
"""

MIGRATION_5_UP = """
CREATE TABLE order_record (
    id TEXT PRIMARY KEY,
    ordered_at TEXT NOT NULL,
    merchant TEXT NOT NULL CHECK (length(trim(merchant)) > 0),
    instrument_id TEXT NOT NULL REFERENCES payment_instrument(id),
    original_cents INTEGER NOT NULL CHECK (original_cents >= 0),
    discount_cents INTEGER NOT NULL CHECK (discount_cents >= 0),
    charged_cents INTEGER NOT NULL CHECK (charged_cents >= 0),
    total_to_recover_cents INTEGER NOT NULL CHECK (total_to_recover_cents >= 0),
    owner_cents INTEGER NOT NULL CHECK (owner_cents >= 0),
    UNIQUE (id),
    CHECK (discount_cents <= original_cents),
    CHECK (total_to_recover_cents = original_cents - discount_cents)
);
CREATE TABLE order_allocation (
    order_id TEXT NOT NULL REFERENCES order_record(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES person(id),
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    PRIMARY KEY (order_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_order_date ON order_record(ordered_at);
CREATE INDEX idx_order_allocation_order ON order_allocation(order_id);
"""

MIGRATION_5_DOWN = """
DROP INDEX IF EXISTS idx_order_allocation_order;
DROP INDEX IF EXISTS idx_order_date;
DROP INDEX IF EXISTS uq_receivable_order_user;
DROP TABLE IF EXISTS order_allocation;
DROP TABLE IF EXISTS order_record;
"""

MIGRATION_6_UP = """
CREATE TABLE order_record_v6 (
    id TEXT PRIMARY KEY,
    ordered_at TEXT NOT NULL,
    merchant TEXT NOT NULL CHECK (length(trim(merchant)) > 0),
    instrument_id TEXT NOT NULL REFERENCES payment_instrument(id),
    original_cents INTEGER NOT NULL CHECK (original_cents >= 0),
    discount_cents INTEGER NOT NULL CHECK (discount_cents >= 0),
    charged_cents INTEGER NOT NULL CHECK (charged_cents >= 0),
    total_to_recover_cents INTEGER NOT NULL CHECK (total_to_recover_cents >= 0),
    owner_cents INTEGER NOT NULL CHECK (owner_cents >= 0),
    UNIQUE (id),
    CHECK (discount_cents <= original_cents)
);
INSERT INTO order_record_v6
    (id, ordered_at, merchant, instrument_id, original_cents, discount_cents,
     charged_cents, total_to_recover_cents, owner_cents)
SELECT id, ordered_at, merchant, instrument_id, original_cents, discount_cents,
       charged_cents, total_to_recover_cents, owner_cents
FROM order_record;
DROP TABLE order_record;
ALTER TABLE order_record_v6 RENAME TO order_record;
CREATE INDEX IF NOT EXISTS idx_order_date ON order_record(ordered_at);
"""

MIGRATION_6_DOWN = """
DROP INDEX IF EXISTS idx_order_date;
"""

MIGRATION_7_UP = """
CREATE TABLE cash_extra (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES person(id),
    received_at TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    description TEXT NOT NULL CHECK (length(trim(description)) > 0)
);
CREATE TABLE deposit_fee (
    id TEXT PRIMARY KEY,
    incurred_at TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    description TEXT NOT NULL CHECK (length(trim(description)) > 0)
);
CREATE INDEX idx_cash_extra_received ON cash_extra(received_at);
CREATE INDEX idx_deposit_fee_incurred ON deposit_fee(incurred_at);
"""

MIGRATION_7_DOWN = """
DROP INDEX IF EXISTS idx_deposit_fee_incurred;
DROP INDEX IF EXISTS idx_cash_extra_received;
DROP TABLE IF EXISTS deposit_fee;
DROP TABLE IF EXISTS cash_extra;
"""

MIGRATION_8_UP = """
CREATE TABLE institution_payment (
    id TEXT PRIMARY KEY,
    instrument_id TEXT NOT NULL REFERENCES payment_instrument(id),
    paid_at TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    reference TEXT,
    UNIQUE (instrument_id, reference)
);
CREATE TABLE instrument_calendar (
    id TEXT PRIMARY KEY,
    instrument_id TEXT NOT NULL REFERENCES payment_instrument(id),
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    closing_day INTEGER NOT NULL CHECK (closing_day BETWEEN 1 AND 31),
    due_day INTEGER NOT NULL CHECK (due_day BETWEEN 1 AND 31),
    revision INTEGER NOT NULL CHECK (revision > 0),
    source TEXT NOT NULL,
    UNIQUE (instrument_id, revision)
);
CREATE UNIQUE INDEX uq_calendar_current
    ON instrument_calendar(instrument_id)
    WHERE effective_to IS NULL;
CREATE INDEX idx_institution_payment_instrument_date
    ON institution_payment(instrument_id, paid_at);
CREATE INDEX idx_calendar_instrument_date
    ON instrument_calendar(instrument_id, effective_from);
"""

MIGRATION_8_DOWN = """
DROP INDEX IF EXISTS idx_calendar_instrument_date;
DROP INDEX IF EXISTS idx_institution_payment_instrument_date;
DROP INDEX IF EXISTS uq_calendar_current;
DROP TABLE IF EXISTS instrument_calendar;
DROP TABLE IF EXISTS institution_payment;
"""

MIGRATION_9_UP = """
CREATE TABLE financing_plan (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL UNIQUE REFERENCES order_record(id),
    instrument_id TEXT NOT NULL REFERENCES payment_instrument(id),
    principal_cents INTEGER NOT NULL CHECK (principal_cents >= 0),
    interest_cents INTEGER NOT NULL CHECK (interest_cents >= 0),
    installment_count INTEGER NOT NULL CHECK (installment_count > 0),
    first_due_date TEXT,
    status TEXT NOT NULL DEFAULT 'CONFIRMED'
        CHECK (status IN ('CONFIRMED', 'PENDING_CONFIRMATION'))
);
CREATE TABLE installment (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES financing_plan(id) ON DELETE CASCADE,
    number INTEGER NOT NULL CHECK (number > 0),
    due_date TEXT,
    principal_cents INTEGER NOT NULL CHECK (principal_cents >= 0),
    interest_cents INTEGER NOT NULL CHECK (interest_cents >= 0),
    status TEXT NOT NULL DEFAULT 'SCHEDULED'
        CHECK (status IN ('SCHEDULED', 'DUE', 'PAID', 'OVERDUE', 'ADJUSTED')),
    UNIQUE (plan_id, number)
);
CREATE TABLE installment_period_assignment (
    id TEXT PRIMARY KEY,
    installment_id TEXT NOT NULL UNIQUE REFERENCES installment(id) ON DELETE CASCADE,
    calendar_id TEXT REFERENCES instrument_calendar(id),
    period_key TEXT,
    source TEXT NOT NULL,
    calendar_revision INTEGER,
    status TEXT NOT NULL DEFAULT 'PROPOSED'
        CHECK (status IN ('UNRECONCILED', 'PROPOSED', 'ACCEPTED', 'REJECTED', 'DEFERRED')),
    requires_review INTEGER NOT NULL DEFAULT 0 CHECK (requires_review IN (0, 1))
);
CREATE INDEX idx_financing_plan_instrument ON financing_plan(instrument_id);
CREATE INDEX idx_installment_due_date ON installment(due_date);
CREATE INDEX idx_installment_period ON installment_period_assignment(period_key);
"""

MIGRATION_9_DOWN = """
DROP INDEX IF EXISTS idx_installment_period;
DROP INDEX IF EXISTS idx_installment_due_date;
DROP INDEX IF EXISTS idx_financing_plan_instrument;
DROP TABLE IF EXISTS installment_period_assignment;
DROP TABLE IF EXISTS installment;
DROP TABLE IF EXISTS financing_plan;
"""

MIGRATION_10_UP = """
CREATE TABLE IF NOT EXISTS installment_payment_application (
    payment_id TEXT NOT NULL REFERENCES institution_payment(id),
    installment_id TEXT NOT NULL REFERENCES installment(id),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    applied_at TEXT NOT NULL,
    PRIMARY KEY (payment_id, installment_id)
);
CREATE INDEX IF NOT EXISTS idx_installment_payment_installment
    ON installment_payment_application(installment_id);
"""

MIGRATION_10_DOWN = """
DROP INDEX IF EXISTS idx_installment_payment_installment;
DROP TABLE IF EXISTS installment_payment_application;
"""

MIGRATION_11_UP = """
"""

MIGRATION_11_DOWN = """
"""

MIGRATION_1_DOWN = """
DROP TABLE IF EXISTS audit_event;
DROP TABLE IF EXISTS initial_balance;
DROP TABLE IF EXISTS institution_movement;
DROP TABLE IF EXISTS payment_instrument;
DROP TABLE IF EXISTS institution;
DROP TABLE IF EXISTS person;
"""


class LocalDatabase:
    def __init__(self, connection: sqlite3.Connection, *, synthetic: bool, encrypted: bool):
        self.connection = connection
        self.synthetic = synthetic
        self.encrypted = encrypted
        self._session_key = None
        self._migration_backup_state: tuple[int, int] | None = None
        self.connection.row_factory = sqlcipher.Row if encrypted else sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    @classmethod
    def open(
        cls,
        path: str | Path,
        password: str,
        *,
        allow_synthetic_in_memory: bool = False,
    ) -> LocalDatabase:
        if not password:
            raise DatabaseSecurityError("La contraseña de base es obligatoria")
        path_value = str(path)
        synthetic = path_value == ":memory:"
        if synthetic:
            if not allow_synthetic_in_memory:
                raise DatabaseSecurityError(
                    "La base en memoria requiere habilitacion explicita para pruebas sinteticas"
                )
            return cls(
                sqlite3.connect(":memory:"),
                synthetic=True,
                encrypted=False,
            )
        if sqlcipher is None:
            raise DatabaseSecurityError(
                "SQLCipher no esta disponible; se rechaza una base persistente"
            )
        connection = sqlcipher.connect(path_value)
        try:
            connection.execute(f"PRAGMA key = {_pragma_literal(password)}")
            cipher_version = connection.execute("PRAGMA cipher_version").fetchone()[0]
            if not cipher_version:
                raise DatabaseSecurityError(
                    "El backend no expone una version valida de SQLCipher"
                )
            connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except Exception as error:
            connection.close()
            raise DatabaseSecurityError(
                "No se pudo abrir la base cifrada. La contraseña puede ser "
                "incorrecta o la base puede estar dañada."
            ) from error
        database = cls(connection, synthetic=False, encrypted=True)
        database._session_key = password
        return database

    def close(self) -> None:
        self.connection.close()
        self._session_key = None

    def integrity_report(self):
        """Read-only storage/relationship checks, without financial corrections."""
        issues = []
        if self.encrypted and self.connection.execute('PRAGMA cipher_integrity_check').fetchall():
            issues.append('El cifrado no superó la comprobación de integridad.')
        if [r[0] for r in self.connection.execute('PRAGMA integrity_check')] != ['ok']:
            issues.append('La estructura de almacenamiento tiene inconsistencias.')
        missing = self.connection.execute('PRAGMA foreign_key_check').fetchall()
        if missing:
            issues.append(f'Relaciones inválidas: {len(missing)}. No se modificó información.')
        duplicates = self.connection.execute("SELECT COUNT(*) FROM (SELECT user_id,order_id FROM receivable WHERE order_id IS NOT NULL GROUP BY user_id,order_id HAVING COUNT(*)>1)").fetchone()[0]
        warnings = [f'Participaciones repetidas por revisar: {duplicates}. No se corrigió ningún registro.'] if duplicates else []
        invalid = 0
        for row in self.connection.execute('SELECT old_value,new_value FROM audit_event'):
            for value in row:
                if value is not None:
                    try:
                        json.loads(value)
                    except (TypeError, ValueError):
                        invalid += 1
        if invalid:
            issues.append(f'Metadatos de auditoría ilegibles: {invalid}.')
        return dict(ok=not issues, issues=issues, warnings=warnings, schema_version=int(self.connection.execute('PRAGMA user_version').fetchone()[0]))

    def create_backup(self, path):
        if not self.encrypted or not self._session_key:
            raise DatabaseSecurityError('Se requiere una sesión SQLCipher autenticada.')
        if self.connection.in_transaction:
            raise DatabaseSecurityError('Finaliza la operación en curso antes de respaldar.')
        return self.prepare_migration_backup(path, self._session_key)

    def _open_verified_backup(self, path):
        path = Path(path)
        if not self.encrypted or not self._session_key or not path.is_file():
            raise DatabaseSecurityError('Selecciona un respaldo cifrado existente de esta sesión.')
        current = self.connection.execute('PRAGMA database_list').fetchone()[2]
        if path.resolve() == Path(current).resolve() or path.samefile(current):
            raise DatabaseSecurityError('El respaldo debe ser un archivo diferente de la base activa.')
        backup = LocalDatabase.open(path, self._session_key)
        try:
            backup.connection.execute('PRAGMA query_only=ON')
            backup.connection.execute('BEGIN')
            if int(backup.connection.execute('PRAGMA user_version').fetchone()[0]) != SCHEMA_VERSION:
                raise DatabaseSecurityError('El respaldo debe tener la versión actual; no se migrará al restaurarlo.')
            if not backup.integrity_report()['ok']:
                raise DatabaseSecurityError('El respaldo no superó integridad y relaciones.')
            schema = "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
            if [tuple(r) for r in backup.connection.execute(schema)] != [tuple(r) for r in self.connection.execute(schema)]:
                raise DatabaseSecurityError('El respaldo no corresponde al esquema de esta aplicación.')
        except Exception:
            backup.close()
            raise
        return backup

    def verify_backup(self, path):
        backup = self._open_verified_backup(path)
        backup.close()

    def restore_backup(self, path, safety_path):
        if self.connection.in_transaction:
            raise DatabaseSecurityError('Finaliza la operación en curso antes de restaurar.')
        source = self._open_verified_backup(path)
        try:
            self.create_backup(safety_path)
            # SQLite backup commits the destination atomically, rolling back on failure.
            source.connection.backup(self.connection)
            self._migration_backup_state = None
        except Exception as error:
            raise DatabaseSecurityError('La restauración no terminó. Conserva el respaldo de seguridad; no vuelvas a guardar hasta revisar el estado.') from error
        finally:
            source.close()
        return Path(safety_path)

    @property
    def cipher_version(self) -> str | None:
        if not self.encrypted:
            return None
        row = self.connection.execute("PRAGMA cipher_version").fetchone()
        return row[0] if row else None

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        try:
            yield self.connection
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def migrate(self, target: int = SCHEMA_VERSION) -> None:
        if self.encrypted:
            current = int(self.connection.execute("PRAGMA user_version").fetchone()[0])
            if 0 < current < target and self._migration_backup_state != (current, self.connection.total_changes):
                raise DatabaseSecurityError(
                    "La actualización requiere un respaldo cifrado verificado. "
                    "No se modificó el esquema de la base."
                )
            try:
                self._migrate(target)
            except DatabaseSecurityError:
                raise
            except Exception as error:
                raise DatabaseSecurityError(
                    "No se pudo abrir la estructura de la base cifrada. "
                    "La contraseña puede ser incorrecta o la base puede estar dañada."
                ) from error
            return
        self._migrate(target)

    def prepare_migration_backup(self, path: str | Path, password: str) -> Path:
        """Copia cifrada independiente y verificada antes de actualizar el esquema."""
        try:
            return self._prepare_migration_backup(path, password)
        except DatabaseSecurityError:
            raise
        except Exception as error:
            raise DatabaseSecurityError(
                "No se pudo crear o verificar el respaldo cifrado; no se migrará la base."
            ) from error

    def _prepare_migration_backup(self, path: str | Path, password: str) -> Path:
        if not self.encrypted:
            raise DatabaseSecurityError("El respaldo de migración requiere SQLCipher.")
        backup_path = Path(path)
        if backup_path.exists():
            raise DatabaseSecurityError("El respaldo ya existe; no se reemplazará.")
        version = int(self.connection.execute("PRAGMA user_version").fetchone()[0])
        backup = LocalDatabase.open(backup_path, password)
        try:
            self.connection.backup(backup.connection)
        finally:
            backup.close()
        verified = LocalDatabase.open(backup_path, password)
        try:
            cipher_errors = verified.connection.execute("PRAGMA cipher_integrity_check").fetchall()
            integrity = verified.connection.execute("PRAGMA integrity_check").fetchall()
            if cipher_errors or [row[0] for row in integrity] != ["ok"]:
                raise DatabaseSecurityError("El respaldo no superó la comprobación de integridad.")
            if int(verified.connection.execute("PRAGMA user_version").fetchone()[0]) != version:
                raise DatabaseSecurityError("La versión del respaldo no coincide con la base.")
            schema_query = "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
            if [tuple(r) for r in self.connection.execute(schema_query)] != [
                tuple(r) for r in verified.connection.execute(schema_query)
            ]:
                raise DatabaseSecurityError("La estructura del respaldo no coincide con la base.")
            for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
                table = '"' + row[0].replace('"', '""') + '"'
                original = [tuple(r) for r in self.connection.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                copied = [tuple(r) for r in verified.connection.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                if original != copied:
                    raise DatabaseSecurityError("Los datos del respaldo no coinciden con la base.")
        finally:
            verified.close()
        self._migration_backup_state = (version, self.connection.total_changes)
        return backup_path

    def _migrate(self, target: int) -> None:
        if target not in range(0, SCHEMA_VERSION + 1):
            raise ValueError("Version de esquema no soportada")
        current = int(self.connection.execute("PRAGMA user_version").fetchone()[0])
        if current > SCHEMA_VERSION:
            raise DatabaseSecurityError("La base usa una versión más reciente; no se modificará.")
        if target > current:
            with self.transaction() as connection:
                if current < 1 <= target:
                    self._execute_script(connection, MIGRATION_1_UP)
                if current < 2 <= target:
                    self._execute_script(connection, MIGRATION_2_UP)
                if current < 3 <= target:
                    self._execute_script(connection, MIGRATION_3_UP)
                if current < 4 <= target:
                    self._execute_script(connection, MIGRATION_4_UP)
                if current < 5 <= target:
                    self._execute_script(connection, MIGRATION_5_UP)
                    self._ensure_column(
                        connection, "receivable", "order_id", "TEXT"
                    )
                    self._ensure_column(
                        connection,
                        "receivable",
                        "source_type",
                        "TEXT NOT NULL DEFAULT 'PURCHASE'",
                    )
                    connection.execute(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uq_receivable_order_user "
                        "ON receivable(order_id, user_id) WHERE order_id IS NOT NULL"
                    )
                if current < 6 <= target:
                    self._execute_script(connection, MIGRATION_6_UP)
                if current < 7 <= target:
                    self._execute_script(connection, MIGRATION_7_UP)
                if current < 8 <= target:
                    self._execute_script(connection, MIGRATION_8_UP)
                if current < 9 <= target:
                    self._ensure_column(
                        connection,
                        "order_record",
                        "purchase_mode",
                        "TEXT NOT NULL DEFAULT 'CASH' CHECK (purchase_mode IN ('CASH', 'MSI'))",
                    )
                    self._execute_script(connection, MIGRATION_9_UP)
                if current < 10 <= target:
                    self._ensure_column(
                        connection, "order_record", "order_status",
                        "TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (order_status IN ('ACTIVE', 'CANCELLED'))",
                    )
                    self._ensure_column(connection, "order_record", "cancelled_at", "TEXT")
                    self._ensure_column(connection, "order_record", "cancelled_by", "TEXT")
                    self._ensure_column(
                        connection, "order_record", "cancellation_reason", "TEXT"
                    )
                    self._execute_script(connection, MIGRATION_10_UP)
                if current < 11 <= target:
                    self._ensure_column(
                        connection, "user_payment", "payment_status",
                        "TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (payment_status IN ('ACTIVE', 'CANCELLED'))",
                    )
                    self._ensure_column(connection, "user_payment", "cancelled_at", "TEXT")
                    self._ensure_column(connection, "user_payment", "cancelled_by", "TEXT")
                    self._ensure_column(connection, "user_payment", "cancellation_reason", "TEXT")
                    self._ensure_column(
                        connection, "receipt_application", "application_status",
                        "TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (application_status IN ('ACTIVE', 'REVERSED'))",
                    )
                    self._ensure_column(
                        connection, "receipt_application", "reversed_at", "TEXT"
                    )
                    self._ensure_column(
                        connection, "receipt_application", "reversed_by", "TEXT"
                    )
                    self._ensure_column(
                        connection, "receipt_application", "reversal_reason", "TEXT"
                    )
                    self._ensure_column(
                        connection, "institution_payment", "payment_status",
                        "TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (payment_status IN ('ACTIVE', 'CANCELLED'))",
                    )
                    self._ensure_column(connection, "institution_payment", "cancelled_at", "TEXT")
                    self._ensure_column(connection, "institution_payment", "cancelled_by", "TEXT")
                    self._ensure_column(
                        connection, "institution_payment", "cancellation_reason", "TEXT"
                    )
                    self._ensure_column(
                        connection, "installment_payment_application", "application_status",
                        "TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (application_status IN ('ACTIVE', 'REVERSED'))",
                    )
                    self._ensure_column(
                        connection, "installment_payment_application", "reversed_at", "TEXT"
                    )
                    self._ensure_column(
                        connection, "installment_payment_application", "reversed_by", "TEXT"
                    )
                    self._ensure_column(
                        connection, "installment_payment_application", "reversal_reason",
                        "TEXT",
                    )
                    self._execute_script(connection, MIGRATION_11_UP)
                if current < 12 <= target:
                    self._ensure_column(
                        connection, "receivable", "participant_role",
                        "TEXT CHECK (participant_role IN ('PERSONAL', 'FAMILY', 'UNKNOWN'))",
                    )
                    self._ensure_column(
                        connection, "user_payment", "payment_kind",
                        "TEXT CHECK (payment_kind IN ('PERSONAL', 'FAMILY', 'UNKNOWN'))",
                    )
                if current < 13 <= target:
                    self._execute_script(connection, MIGRATION_13_UP)
                if current < 14 <= target:
                    self._execute_script(connection, MIGRATION_14_UP)
                if current < 15 <= target:
                    self._execute_script(connection, MIGRATION_15_UP)
                connection.execute(f"PRAGMA user_version = {target}")
        elif target < current:
            with self.transaction() as connection:
                if current >= 15 > target:
                    self._execute_script(connection, MIGRATION_15_DOWN)
                if current >= 14 > target:
                    self._execute_script(connection, MIGRATION_14_DOWN)
                if current >= 13 > target:
                    self._execute_script(connection, MIGRATION_13_DOWN)
                if current >= 10 > target:
                    self._execute_script(connection, MIGRATION_10_DOWN)
                if current >= 11 > target:
                    self._execute_script(connection, MIGRATION_11_DOWN)
                if current >= 9 > target:
                    self._execute_script(connection, MIGRATION_9_DOWN)
                if current >= 8 > target:
                    self._execute_script(connection, MIGRATION_8_DOWN)
                if current >= 7 > target:
                    self._execute_script(connection, MIGRATION_7_DOWN)
                if current >= 6 > target:
                    self._execute_script(connection, MIGRATION_6_DOWN)
                if current >= 5 > target:
                    self._execute_script(connection, MIGRATION_5_DOWN)
                if current >= 3 > target:
                    self._execute_script(connection, MIGRATION_3_DOWN)
                if current >= 4 > target:
                    self._execute_script(connection, MIGRATION_4_DOWN)
                if current >= 2 > target:
                    self._execute_script(connection, MIGRATION_2_DOWN)
                if current >= 1 > target:
                    self._execute_script(connection, MIGRATION_1_DOWN)
                connection.execute(f"PRAGMA user_version = {target}")

    @staticmethod
    def _execute_script(connection: sqlite3.Connection, script: str) -> None:
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                connection.execute(statement)

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {
            row[1]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
            )


def _pragma_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
