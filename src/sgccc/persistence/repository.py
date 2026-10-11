from __future__ import annotations

import json
from contextlib import nullcontext
from calendar import monthrange
from datetime import date, datetime, timezone
from uuid import uuid4

from sgccc.finance.models import AllocationMethod, ProductLine, RefundEvent
from sgccc.finance.rules import allocate_line_shares, validate_refund_event

from .database import LocalDatabase


class FinanceRepository:
    def __init__(self, database: LocalDatabase):
        self.database = database

    def add_person(self, person_id: str, name: str, *, is_owner: bool = False) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO person(id, name, is_owner) VALUES (?, ?, ?)",
                (person_id, name, int(is_owner)),
            )

    def list_people(self) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            "SELECT id, name, is_owner, active FROM person ORDER BY lower(name), id"
        ).fetchall()
        return [dict(row) for row in rows]

    def create_person(
        self,
        name: str,
        *,
        is_owner: bool = False,
        actor: str = "desktop",
        person_id: str | None = None,
    ) -> str:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("El nombre es obligatorio.")
        identifier = person_id or str(uuid4())
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    "INSERT INTO person(id, name, is_owner) VALUES (?, ?, ?)",
                    (identifier, normalized_name, int(is_owner)),
                )
                self._insert_person_audit(
                    connection,
                    identifier,
                    "CREATED",
                    actor,
                    None,
                    {"name": normalized_name, "is_owner": bool(is_owner), "active": True},
                )
        except Exception as error:
            if "UNIQUE constraint" in str(error):
                raise ValueError("Ya existe una persona con ese nombre.") from error
            raise
        return identifier

    def update_person(
        self,
        person_id: str,
        name: str,
        *,
        is_owner: bool = False,
        actor: str = "desktop",
    ) -> None:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("El nombre es obligatorio.")
        try:
            with self.database.transaction() as connection:
                row = connection.execute(
                    "SELECT name, is_owner, active FROM person WHERE id = ?",
                    (person_id,),
                ).fetchone()
                if row is None:
                    raise ValueError("La persona seleccionada ya no existe.")
                old_value = {
                    "name": row["name"],
                    "is_owner": bool(row["is_owner"]),
                    "active": bool(row["active"]),
                }
                connection.execute(
                    "UPDATE person SET name = ?, is_owner = ? WHERE id = ?",
                    (normalized_name, int(is_owner), person_id),
                )
                self._insert_person_audit(
                    connection,
                    person_id,
                    "UPDATED",
                    actor,
                    old_value,
                    {"name": normalized_name, "is_owner": bool(is_owner), "active": old_value["active"]},
                )
        except Exception as error:
            if "UNIQUE constraint" in str(error):
                raise ValueError("Ya existe una persona con ese nombre.") from error
            raise

    def deactivate_person(self, person_id: str, *, actor: str = "desktop") -> None:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT name, is_owner, active FROM person WHERE id = ?",
                (person_id,),
            ).fetchone()
            if row is None:
                raise ValueError("La persona seleccionada ya no existe.")
            if not row["active"]:
                raise ValueError("La persona ya está desactivada.")
            connection.execute("UPDATE person SET active = 0 WHERE id = ?", (person_id,))
            self._insert_person_audit(
                connection,
                person_id,
                "DEACTIVATED",
                actor,
                {"name": row["name"], "is_owner": bool(row["is_owner"]), "active": True},
                {"name": row["name"], "is_owner": bool(row["is_owner"]), "active": False},
            )

    def reactivate_person(self, person_id: str, *, actor: str = "desktop") -> None:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT name, is_owner, active FROM person WHERE id = ?",
                (person_id,),
            ).fetchone()
            if row is None:
                raise ValueError("La persona seleccionada ya no existe.")
            if row["active"]:
                raise ValueError("La persona ya está activa.")
            connection.execute("UPDATE person SET active = 1 WHERE id = ?", (person_id,))
            self._insert_person_audit(
                connection,
                person_id,
                "REACTIVATED",
                actor,
                {"name": row["name"], "is_owner": bool(row["is_owner"]), "active": False},
                {"name": row["name"], "is_owner": bool(row["is_owner"]), "active": True},
            )

    def configure_owner(
        self, person_id: str, *, actor: str = "desktop"
    ) -> dict[str, object]:
        """Set exactly one active owner without changing historical movements."""
        with self.database.transaction() as connection:
            selected = connection.execute(
                "SELECT id, name, is_owner, active FROM person WHERE id = ?",
                (person_id,),
            ).fetchone()
            if selected is None:
                raise ValueError("La persona seleccionada no existe.")
            if not selected["active"]:
                raise ValueError("El propietario debe ser una persona activa.")

            people = connection.execute(
                "SELECT id, name, is_owner, active FROM person"
            ).fetchall()
            changed: list[str] = []
            for person in people:
                should_be_owner = str(person["id"]) == str(person_id)
                if bool(person["is_owner"]) == should_be_owner:
                    continue
                connection.execute(
                    "UPDATE person SET is_owner = ? WHERE id = ?",
                    (int(should_be_owner), person["id"]),
                )
                changed.append(str(person["id"]))
                self._insert_person_audit(
                    connection,
                    str(person["id"]),
                    "OWNER_CONFIGURED",
                    actor,
                    {
                        "name": person["name"],
                        "is_owner": bool(person["is_owner"]),
                        "active": bool(person["active"]),
                    },
                    {
                        "name": person["name"],
                        "is_owner": should_be_owner,
                        "active": bool(person["active"]),
                        "selected_owner_id": str(person_id),
                    },
                )

            references = {
                "purchase_allocations": connection.execute(
                    "SELECT COUNT(*) FROM purchase_allocation WHERE user_id = ?",
                    (person_id,),
                ).fetchone()[0],
                "order_allocations": connection.execute(
                    "SELECT COUNT(*) FROM order_allocation WHERE user_id = ?",
                    (person_id,),
                ).fetchone()[0],
                "receivables": connection.execute(
                    "SELECT COUNT(*) FROM receivable WHERE user_id = ?",
                    (person_id,),
                ).fetchone()[0],
            }
            return {
                "owner_id": str(person_id),
                "changed_person_ids": tuple(changed),
                "historical_references": references,
            }

    @staticmethod
    def _insert_person_audit(
        connection,
        person_id: str,
        action: str,
        actor: str,
        old_value: object | None,
        new_value: object,
        entity_type: str = "person",
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_event
                (id, entity_type, entity_id, action, occurred_at, actor, reason,
                 old_value, new_value)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                entity_type,
                person_id,
                action,
                datetime.now(timezone.utc).isoformat(),
                actor,
                f"Operación de {entity_type}: {action}",
                json.dumps(old_value, sort_keys=True) if old_value is not None else None,
                json.dumps(new_value, sort_keys=True),
            ),
        )

    def add_institution(
        self, institution_id: str, name: str, *, actor: str = "desktop"
    ) -> None:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("El nombre de la institución es obligatorio.")
        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT id FROM institution WHERE lower(trim(name)) = lower(trim(?))",
                (normalized_name,),
            ).fetchone()
            if existing is not None:
                raise ValueError("Ya existe una institución con ese nombre.")
            try:
                connection.execute(
                    "INSERT INTO institution(id, name) VALUES (?, ?)",
                    (institution_id, normalized_name),
                )
            except Exception as error:
                if "UNIQUE constraint" in str(error):
                    raise ValueError("Ya existe una institución con ese nombre o ID.") from error
                raise
            self._insert_person_audit(
                connection,
                institution_id,
                "CREATED",
                actor,
                None,
                {"name": normalized_name, "active": True},
                entity_type="institution",
            )

    def add_instrument(
        self,
        instrument_id: str,
        institution_id: str,
        alias: str,
        instrument_type: str,
        *,
        last_four: str = '',
        description: str = '',
        actor: str = "desktop",
    ) -> None:
        normalized_alias = alias.strip()
        self._validate_instrument_profile(last_four, description)
        if not normalized_alias:
            raise ValueError("El nombre de la tarjeta es obligatorio.")
        if instrument_type not in {
            "CREDIT_LINE", "CREDIT_CARD", "WALLET_BALANCE", "OTHER"
        }:
            raise ValueError("El tipo de instrumento no es válido.")
        with self.database.transaction() as connection:
            institution = connection.execute(
                "SELECT active FROM institution WHERE id = ?",
                (institution_id,),
            ).fetchone()
            if institution is None:
                raise ValueError("La institución seleccionada no existe.")
            if not institution["active"]:
                raise ValueError("No puedes agregar una tarjeta a una institución inactiva.")
            try:
                connection.execute(
                    """
                    INSERT INTO payment_instrument
                        (id, institution_id, alias, instrument_type)
                    VALUES (?, ?, ?, ?)
                    """,
                    (instrument_id, institution_id, normalized_alias, instrument_type),
                )
            except Exception as error:
                if "UNIQUE constraint" in str(error):
                    raise ValueError("Ya existe una tarjeta con ese nombre en la institución.") from error
                raise
            self._insert_person_audit(
                connection,
                instrument_id,
                "CREATED",
                actor,
                None,
                {
                    "institution_id": institution_id,
                    "alias": normalized_alias,
                    "instrument_type": instrument_type,
                    "active": True,
                },
                entity_type="payment_instrument",
            )
            if last_four or description:
                self._insert_person_audit(connection, instrument_id, 'INSTRUMENT_PROFILE', actor, None,
                    dict(last_four=last_four, description=description.strip()), entity_type='payment_instrument')

    def update_institution(
        self, institution_id: str, name: str, *, actor: str = "desktop"
    ) -> None:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("El nombre de la institución es obligatorio.")
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT name, active FROM institution WHERE id = ?",
                (institution_id,),
            ).fetchone()
            if row is None:
                raise ValueError("La institución seleccionada no existe.")
            if connection.execute('SELECT 1 FROM institution WHERE id<>? AND lower(trim(name))=lower(trim(?))', (institution_id, normalized_name)).fetchone():
                raise ValueError('Ya existe una institución con ese nombre.')
            try:
                connection.execute(
                    "UPDATE institution SET name = ? WHERE id = ?",
                    (normalized_name, institution_id),
                )
            except Exception as error:
                if "UNIQUE constraint" in str(error):
                    raise ValueError("Ya existe una institución con ese nombre.") from error
                raise
            self._insert_person_audit(
                connection, institution_id, "UPDATED", actor,
                {"name": row["name"], "active": bool(row["active"])},
                {"name": normalized_name, "active": bool(row["active"])},
                entity_type="institution",
            )

    def set_institution_active(
        self,
        institution_id: str,
        active: bool,
        *,
        actor: str = "desktop",
    ) -> None:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT name, active FROM institution WHERE id = ?",
                (institution_id,),
            ).fetchone()
            if row is None:
                raise ValueError("La institución seleccionada no existe.")
            if bool(row["active"]) == active:
                raise ValueError(
                    "La institución ya está " + ("activa." if active else "inactiva.")
                )
            connection.execute(
                "UPDATE institution SET active = ? WHERE id = ?",
                (int(active), institution_id),
            )
            self._insert_person_audit(
                connection, institution_id,
                "REACTIVATED" if active else "DEACTIVATED",
                actor,
                {"name": row["name"], "active": bool(row["active"])},
                {"name": row["name"], "active": active},
                entity_type="institution",
            )

    def update_instrument(
        self,
        instrument_id: str,
        alias: str,
        instrument_type: str,
        *,
        institution_id: str | None = None,
        last_four: str | None = None,
        description: str | None = None,
        actor: str = "desktop",
    ) -> None:
        normalized_alias = alias.strip()
        if not normalized_alias:
            raise ValueError("El nombre de la tarjeta es obligatorio.")
        if instrument_type not in {
            "CREDIT_LINE", "CREDIT_CARD", "WALLET_BALANCE", "OTHER"
        }:
            raise ValueError("El tipo de instrumento no es válido.")
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT institution_id, alias, instrument_type, active
                FROM payment_instrument WHERE id = ?
                """,
                (instrument_id,),
            ).fetchone()
            if row is None:
                raise ValueError("La tarjeta seleccionada no existe.")
            target = row['institution_id'] if institution_id is None else institution_id
            institution = connection.execute('SELECT active FROM institution WHERE id=?', (target,)).fetchone()
            if institution is None or (target != row['institution_id'] and not institution['active']):
                raise ValueError('Selecciona una institución activa existente.')
            if instrument_type != row['instrument_type']:
                history = connection.execute('SELECT 1 FROM institution_movement WHERE instrument_id=? UNION ALL SELECT 1 FROM order_record WHERE instrument_id=? LIMIT 1', (instrument_id, instrument_id)).fetchone()
                history = history or any(connection.execute(f'SELECT 1 FROM {table} WHERE instrument_id=? LIMIT 1', (instrument_id,)).fetchone() for table in ('initial_balance', 'institution_payment', 'purchase', 'financing_plan'))
                if row['instrument_type'] == 'WALLET_BALANCE' or history:
                    raise ValueError('No se puede cambiar la naturaleza de una billetera o instrumento con historial.')
            self._validate_instrument_profile(last_four if last_four is not None else '', description if description is not None else '')
            try:
                connection.execute(
                    """
                    UPDATE payment_instrument
                    SET alias = ?, instrument_type = ?, institution_id = ?
                    WHERE id = ?
                    """,
                    (normalized_alias, instrument_type, target, instrument_id),
                )
            except Exception as error:
                if "UNIQUE constraint" in str(error):
                    raise ValueError("Ya existe una tarjeta con ese nombre en la institución.") from error
                raise
            self._insert_person_audit(
                connection, instrument_id, "UPDATED", actor,
                {
                    "institution_id": row["institution_id"],
                    "alias": row["alias"],
                    "instrument_type": row["instrument_type"],
                    "active": bool(row["active"]),
                },
                {
                    "institution_id": target,
                    "alias": normalized_alias,
                    "instrument_type": instrument_type,
                    "active": bool(row["active"]),
                },
                entity_type="payment_instrument",
            )
            if last_four is not None or description is not None:
                old = self.instrument_profile(instrument_id)
                new = dict(last_four=old['last_four'] if last_four is None else last_four,
                           description=old['description'] if description is None else description.strip())
                self._insert_person_audit(connection, instrument_id, 'INSTRUMENT_PROFILE', actor, old, new,
                                          entity_type='payment_instrument')

    @staticmethod
    def _validate_instrument_profile(last_four, description):
        if not isinstance(last_four, str) or not isinstance(description, str):
            raise ValueError('La terminación y descripción deben ser texto.')
        if last_four and (len(last_four) != 4 or not last_four.isascii() or not last_four.isdigit()):
            raise ValueError('La terminación debe contener cuatro dígitos o quedar vacía.')

    def instrument_profile(self, instrument_id):
        row = self.database.connection.execute("SELECT new_value FROM audit_event WHERE entity_id=? AND action='INSTRUMENT_PROFILE' AND entity_type='payment_instrument' ORDER BY rowid DESC LIMIT 1", (instrument_id,)).fetchone()
        return json.loads(row[0]) if row else dict(last_four='', description='')

    def expected_result_breakdown(self):
        roots = self.database.connection.execute("SELECT id FROM order_record WHERE order_status='ACTIVE' AND id NOT IN (SELECT order_id FROM product_refund_repurchase)").fetchall()
        result = []
        participations = self.list_collection_items()
        for row in roots:
            order = self.get_order(row['id'])
            benefit = self.order_benefit_summary(row['id'], participations=participations)
            result.append(dict(order_id=row['id'], merchant=order['merchant'], date=order['ordered_at'],
                               family_cents=sum(int(p['sale_cents']) for p in benefit['participations'] if p['participant_role']=='FAMILY'),
                               cost_cents=benefit['effective_purchase_cost_cents'], result_cents=benefit['expected_result_cents']))
        return result

    def family_statement(self, user_id):
        person = self.database.connection.execute('SELECT name FROM person WHERE id=?', (user_id,)).fetchone()
        if person is None:
            raise ValueError('Selecciona una persona registrada.')
        rows = []
        for item in self.list_collection_items():
            if item['user_id'] != user_id:
                continue
            concepts = []
            order = self.get_order(item['order_id']) if item.get('order_id') else None
            if order:
                products = order['manual_concepts'] or (order['import_evidence'] or {}).get('products', [])
                for product in products:
                    shares = product.get('allocations', {})
                    if isinstance(shares, list):
                        shares = {p['user_id']: p['amount_cents'] for p in shares}
                    amount = shares.get(user_id, 0)
                    if amount:
                        concepts.append(dict(description=product['description'], amount_cents=amount))
            elif item.get('purchase_id'):
                concepts = [dict(r) for r in self.database.connection.execute('SELECT p.description,SUM(a.share_cents) AS amount_cents FROM purchase_product p JOIN purchase_allocation a ON a.product_id=p.id WHERE p.purchase_id=? AND a.user_id=? GROUP BY p.id', (item['purchase_id'], user_id))]
            receipts = [dict(r) for r in self.database.connection.execute('SELECT u.received_at,a.amount_cents FROM receipt_application a JOIN user_payment u ON u.id=a.payment_id WHERE a.receivable_id=? AND a.application_status=\'ACTIVE\' AND u.payment_status=\'ACTIVE\' ORDER BY u.received_at', (item['receivable_id'],))]
            rows.append(dict(item, concepts=concepts, receipts=receipts,
                             concept_adjustment_cents=int(item['sale_cents'])-sum(c['amount_cents'] for c in concepts) if concepts else 0))
        return dict(person=person['name'], rows=rows,
                    assigned_cents=sum(int(r['sale_cents']) for r in rows),
                    paid_cents=sum(int(r['paid_cents']) for r in rows),
                    remaining_cents=sum(int(r['remaining_cents']) for r in rows))

    def set_instrument_active(
        self, instrument_id: str, active: bool, *, actor: str = "desktop"
    ) -> None:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT alias, instrument_type, active FROM payment_instrument WHERE id = ?",
                (instrument_id,),
            ).fetchone()
            if row is None:
                raise ValueError("La tarjeta seleccionada no existe.")
            if bool(row["active"]) == active:
                return
            connection.execute(
                "UPDATE payment_instrument SET active = ? WHERE id = ?",
                (int(active), instrument_id),
            )
            self._insert_person_audit(
                connection, instrument_id,
                "REACTIVATED" if active else "DEACTIVATED",
                actor,
                {"alias": row["alias"], "instrument_type": row["instrument_type"],
                 "active": bool(row["active"])},
                {"alias": row["alias"], "instrument_type": row["instrument_type"],
                 "active": active},
                entity_type="payment_instrument",
            )

    def list_institutions(self) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            "SELECT id, name FROM institution WHERE active = 1 ORDER BY lower(name)"
        ).fetchall()
        return [dict(row) for row in rows]

    def list_all_institutions(self) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            "SELECT id, name, active FROM institution ORDER BY lower(name), id"
        ).fetchall()
        return [dict(row) for row in rows]

    def list_all_instruments(self) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            """
            SELECT i.id, i.institution_id, inst.name AS institution_name,
                   i.alias, i.instrument_type, i.active
            FROM payment_instrument i
            JOIN institution inst ON inst.id = i.institution_id
            ORDER BY lower(inst.name), lower(i.alias), i.id
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def list_instruments(self, institution_id: str | None = None) -> list[dict[str, object]]:
        query = """
            SELECT id, institution_id, alias, instrument_type
            FROM payment_instrument WHERE active = 1
        """
        parameters: tuple[object, ...] = ()
        if institution_id is not None:
            query += " AND institution_id = ?"
            parameters = (institution_id,)
        rows = self.database.connection.execute(
            query + " ORDER BY lower(alias)", parameters
        ).fetchall()
        return [dict(row) for row in rows]

    def ensure_demo_catalog(self) -> None:
        if self.list_institutions() and self.list_instruments():
            return
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO institution(id, name) VALUES (?, ?)",
                ("demo-institution", "Institución demostración"),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO payment_instrument
                    (id, institution_id, alias, instrument_type)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "demo-instrument",
                    "demo-institution",
                    "Instrumento demostración",
                    "CREDIT_LINE",
                ),
            )

    def create_purchase(
        self,
        *,
        purchase_id: str,
        purchased_at: str,
        merchant: str,
        instrument_id: str,
        products: tuple[dict[str, object], ...],
        allocations: tuple[dict[str, object], ...],
        actor: str = "desktop",
    ) -> None:
        if not products:
            raise ValueError("La compra requiere al menos un producto.")
        if not merchant.strip():
            raise ValueError("El comercio es obligatorio.")
        product_results: list[tuple[ProductLine, tuple[object, ...]]] = []
        purchased_at = self._required_iso_date(purchased_at, 'La fecha de la compra')
        total_cents = 0
        owner_cents = 0
        with self.database.transaction() as connection:
            instrument = connection.execute(
                "SELECT id FROM payment_instrument WHERE id = ? AND active = 1",
                (instrument_id,),
            ).fetchone()
            if instrument is None:
                raise ValueError("El instrumento seleccionado no existe o está inactivo.")
            people = {
                row["id"]: row
                for row in connection.execute(
                    "SELECT id, is_owner, active FROM person"
                ).fetchall()
            }
            connection.execute(
                """
                INSERT INTO purchase
                    (id, purchased_at, merchant, instrument_id, total_cents, owner_cents)
                VALUES (?, ?, ?, ?, 0, 0)
                """,
                (purchase_id, purchased_at, merchant.strip(), instrument_id),
            )
            for product in products:
                product_id = str(product["id"])
                line = ProductLine(
                    id=product_id,
                    description=str(product["description"]).strip(),
                    quantity=int(product["quantity"]),
                    unit_price_cents=int(product["unit_price_cents"]),
                )
                line_allocations = tuple(
                    (
                        str(item["user_id"]),
                        AllocationMethod(str(item["method"])),
                        int(item["basis"]),
                    )
                    for item in allocations
                    if str(item["product_id"]) == product_id
                )
                if any(user_id not in people or not people[user_id]["active"]
                       for user_id, _, _ in line_allocations):
                    raise ValueError("Todas las asignaciones deben pertenecer a personas activas.")
                calculated = allocate_line_shares(line, line_allocations)
                connection.execute(
                    """
                    INSERT INTO purchase_product
                        (id, purchase_id, description, quantity, unit_price_cents)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        line.id,
                        purchase_id,
                        line.description,
                        line.quantity,
                        line.unit_price_cents,
                    ),
                )
                for allocation in calculated:
                    connection.execute(
                        """
                        INSERT INTO purchase_allocation
                            (product_id, user_id, method, quantity, percentage_basis, share_cents)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            allocation.line_id,
                            allocation.user_id,
                            allocation.method.value,
                            allocation.quantity,
                            allocation.percentage_basis,
                            allocation.share_cents,
                        ),
                    )
                    total_cents += allocation.share_cents
                    if people[allocation.user_id]["is_owner"]:
                        owner_cents += allocation.share_cents
                product_results.append((line, calculated))
            connection.execute(
                "UPDATE purchase SET total_cents = ?, owner_cents = ? WHERE id = ?",
                (total_cents, owner_cents, purchase_id),
            )
            by_user: dict[str, int] = {}
            for _, calculated in product_results:
                for allocation in calculated:
                    if not people[allocation.user_id]["is_owner"]:
                        by_user[allocation.user_id] = (
                            by_user.get(allocation.user_id, 0) + allocation.share_cents
                        )
            for user_id, amount in by_user.items():
                connection.execute(
                    """
                    INSERT INTO receivable
                        (id, user_id, purchase_id, sale_cents, attributable_cost_cents)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (f"{purchase_id}:{user_id}", user_id, purchase_id, amount, amount),
                )
            self._insert_person_audit(
                connection,
                purchase_id,
                "PURCHASE_CREATED",
                actor,
                None,
                {"total_cents": total_cents, "owner_cents": owner_cents},
                entity_type="purchase",
            )

    def list_purchases(self) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            """
            SELECT id, purchased_at, merchant, instrument_id, total_cents, owner_cents
            FROM purchase ORDER BY purchased_at DESC, id DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def get_purchase(self, purchase_id: str) -> dict[str, object] | None:
        purchase = self.database.connection.execute(
            "SELECT * FROM purchase WHERE id = ?", (purchase_id,)
        ).fetchone()
        if purchase is None:
            return None
        products = self.database.connection.execute(
            "SELECT * FROM purchase_product WHERE purchase_id = ? ORDER BY id",
            (purchase_id,),
        ).fetchall()
        result = dict(purchase)
        result["products"] = []
        for product in products:
            item = dict(product)
            item["allocations"] = [
                dict(row)
                for row in self.database.connection.execute(
                    "SELECT * FROM purchase_allocation WHERE product_id = ? ORDER BY user_id",
                    (product["id"],),
                ).fetchall()
            ]
            result["products"].append(item)
        result["receivables"] = [
            dict(row)
            for row in self.database.connection.execute(
                "SELECT * FROM receivable WHERE purchase_id = ? ORDER BY user_id",
                (purchase_id,),
            ).fetchall()
        ]
        return result

    def create_order(
        self,
        *,
        order_id: str,
        ordered_at: str,
        merchant: str,
        instrument_id: str,
        original_cents: int,
        discount_cents: int,
        charged_cents: int,
        allocations: tuple[dict[str, object], ...],
        purchase_mode: str = "CASH",
        financing_specs: tuple[str | None, ...] | None = None,
        interest_cents: int = 0,
        plan_id: str | None = None,
        actor: str = "desktop",
        import_evidence: dict | None = None,
        allow_duplicate: bool = False,
        product_refunds: tuple[dict[str, object], ...] = (),
        concepts: list[dict] | None = None,
        _connection=None,
    ) -> None:
        if not merchant.strip():
            raise ValueError("El comercio es obligatorio.")
        ordered_at = self._required_iso_date(ordered_at, 'La fecha del pedido')
        if original_cents < 0 or discount_cents < 0 or charged_cents < 0:
            raise ValueError("Los importes no pueden ser negativos.")
        if discount_cents > original_cents:
            raise ValueError("El descuento no puede exceder el importe original.")
        if purchase_mode not in {"CASH", "MSI"}:
            raise ValueError("El tipo de compra no es válido.")
        if interest_cents < 0:
            raise ValueError("Los intereses no pueden ser negativos.")
        if purchase_mode == "MSI" and not financing_specs:
            raise ValueError("Una compra MSI requiere las fechas de sus cuotas.")
        if purchase_mode == "CASH" and financing_specs:
            raise ValueError("Una compra de contado no puede tener cuotas MSI.")
        # Participants cover the original assigned amounts; discounts belong
        # to the owner and only reduce the institution charge.
        total_to_recover = original_cents
        if not allocations:
            raise ValueError("El pedido requiere al menos una asignación, incluida Yo.")
        with (self.database.transaction() if _connection is None else nullcontext(_connection)) as connection:
            if import_evidence is not None:
                from sgccc.ocr.order_import import validate
                if validate(import_evidence) != original_cents or import_evidence['discount'] != discount_cents or import_evidence['charged'] != charged_cents:
                    raise ValueError('Los importes del pedido no coinciden con la vista previa.')
                if self.find_import_duplicates(import_evidence) and not allow_duplicate:
                    raise ValueError('Posible comprobante duplicado; confirma explícitamente.')
            instrument = connection.execute(
                "SELECT id FROM payment_instrument WHERE id = ? AND active = 1",
                (instrument_id,),
            ).fetchone()
            if instrument is None:
                raise ValueError("El instrumento seleccionado no existe o está inactivo.")
            people = {
                row["id"]: row
                for row in connection.execute(
                    "SELECT id, is_owner, active FROM person"
                ).fetchall()
            }
            seen: set[str] = set()
            owner_cents = 0
            for allocation in allocations:
                user_id = str(allocation["user_id"])
                amount = int(allocation["amount_cents"])
                if user_id in seen:
                    raise ValueError("Una persona no puede repetirse en el pedido.")
                if user_id not in people or not people[user_id]["active"]:
                    raise ValueError("Todas las asignaciones deben pertenecer a personas activas.")
                if amount < 0:
                    raise ValueError("Una asignación no puede ser negativa.")
                seen.add(user_id)
                if people[user_id]["is_owner"]:
                    owner_cents += amount
            if not any(people[user_id]["is_owner"] for user_id in seen):
                raise ValueError("El pedido debe incluir la asignación visible de Yo.")
            if concepts is not None:
                if import_evidence is not None:
                    raise ValueError('Los conceptos manuales no son evidencia PDF.')
                concept_totals = self._validate_manual_concepts(concepts, original_cents, people)
                if any(concept_totals.get(str(a['user_id']), 0) != int(a['amount_cents']) for a in allocations) or any(
                        amount and person not in seen for person, amount in concept_totals.items()):
                    raise ValueError('Los conceptos no coinciden con el reparto del pedido.')
            assigned = sum(int(item["amount_cents"]) for item in allocations)
            if assigned != total_to_recover:
                raise ValueError(
                    f"La distribución debe sumar {total_to_recover} centavos; "
                    f"actualmente suma {assigned}."
                )
            try:
                connection.execute(
                    """
                    INSERT INTO order_record
                        (id, ordered_at, merchant, instrument_id, original_cents,
                         discount_cents, charged_cents, total_to_recover_cents, owner_cents,
                         purchase_mode, order_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
                    """,
                    (
                        order_id,
                        ordered_at,
                        merchant.strip(),
                        instrument_id,
                        original_cents,
                        discount_cents,
                        charged_cents,
                        total_to_recover,
                        owner_cents,
                        purchase_mode,
                    ),
                )
                for allocation in allocations:
                    user_id = str(allocation["user_id"])
                    amount = int(allocation["amount_cents"])
                    connection.execute(
                        """
                        INSERT INTO order_allocation(order_id, user_id, amount_cents)
                        VALUES (?, ?, ?)
                        """,
                        (order_id, user_id, amount),
                    )
                    if amount:
                        connection.execute(
                            """
                            INSERT INTO receivable
                                (id, user_id, purchase_id, order_id, source_type,
                                 sale_cents, attributable_cost_cents, participant_role)
                            VALUES (?, ?, ?, ?, 'ORDER', ?, ?, ?)
                            """,
                            (
                                f"order:{order_id}:{user_id}",
                                user_id,
                                order_id,
                                order_id,
                                amount,
                                amount,
                                "PERSONAL" if people[user_id]["is_owner"] else "FAMILY",
                            ),
                        )
                if purchase_mode == "MSI":
                    self._insert_financing_plan(
                        connection,
                        plan_id=plan_id or f"plan:{order_id}",
                        order_id=order_id,
                        instrument_id=instrument_id,
                        principal_cents=charged_cents,
                        interest_cents=interest_cents,
                        due_dates=financing_specs or (),
                    )
            except Exception as error:
                if "UNIQUE constraint" in str(error):
                    raise ValueError("El pedido ya existe o tiene una asignación duplicada.") from error
                raise
            self._insert_person_audit(
                connection,
                order_id,
                "ORDER_CREATED",
                actor,
                None,
                {
                    "original_cents": original_cents,
                    "discount_cents": discount_cents,
                    "charged_cents": charged_cents,
                    "total_to_recover_cents": total_to_recover,
                    "owner_cents": owner_cents,
                    "purchase_mode": purchase_mode,
                },
                entity_type="order",
            )

            if import_evidence is not None:
                self._insert_person_audit(connection, order_id, 'PDF_IMPORTED', actor,
                                          None, import_evidence, entity_type='order')
            if concepts is not None:
                self._insert_person_audit(connection, order_id, 'MANUAL_CONCEPTS_SAVED', actor,
                                          None, concepts, entity_type='order')
            if product_refunds:
                if import_evidence is None or purchase_mode != 'CASH':
                    raise ValueError('Las devoluciones por producto requieren un pedido importado de contado.')
                self._insert_product_refunds(connection, order_id, import_evidence, product_refunds, actor)

    def _insert_product_refunds(self, connection, order_id, evidence, refunds, actor):
        """Parte de create_order: no abre ni confirma otra transacción."""
        source_key = ('mercado_pago:' + str(evidence['number']).strip() if evidence.get('number')
                      else evidence.get('fingerprint'))
        if not source_key:
            raise ValueError('La devolución requiere la identidad del comprobante.')
        if any(type(item['amount_cents']) is not int or type(item['product_index']) is not int
               or any(type(value) is not int for value in item['final_allocations'].values()) for item in refunds):
            raise ValueError('Los importes de devolución y ajustes deben ser enteros en centavos.')
        if sum(int(item['amount_cents']) for item in refunds) > int(evidence['refund']):
            raise ValueError('Las devoluciones asignadas exceden la devolución incluida en el PDF.')
        products = {int(p.get('source_index', index)): p for index, p in enumerate(evidence['products'])}
        if len(products) != len(evidence['products']):
            raise ValueError('Los identificadores de productos importados no pueden repetirse.')
        people = {str(p['id']): p for p in self.list_people() if p['active']}
        assigned = {str(r['user_id']): int(r['amount_cents']) for r in connection.execute(
            'SELECT user_id, amount_cents FROM order_allocation WHERE order_id = ?', (order_id,))}
        for product in products.values():
            shares = product.get('allocations', {})
            if (sum(int(v) for v in shares.values()) != int(product['quantity']) * int(product['unit'])
                    or any(str(user) not in assigned or int(value) < 0 for user, value in shares.items())):
                raise ValueError('Revisa el reparto original de cada producto importado.')
        # La evidencia por producto debe explicar exactamente el reparto original del pedido.
        for user_id, amount in assigned.items():
            if sum(int(p.get('allocations', {}).get(user_id, 0)) for p in products.values()) != amount:
                raise ValueError('El reparto por producto no coincide con las participaciones originales.')
        for proposed in refunds:
            index = int(proposed['product_index'])
            if index not in products:
                raise ValueError('Selecciona un producto del comprobante importado.')
            product = products[index]
            gross = int(product['quantity']) * int(product['unit'])
            amount = int(proposed['amount_cents'])
            if not 0 < amount <= gross:
                raise ValueError('El reembolso debe ser positivo y no superar el valor original del producto.')
            before = {str(user): int(value) for user, value in product.get('allocations', {}).items()}
            after = {str(user): int(value) for user, value in proposed['final_allocations'].items()}
            repurchase = proposed.get('repurchase')
            if repurchase:
                # Baseline refund remains auditable. The linked purchase revises it
                # within this same transaction, rather than applying another refund.
                after = {user: 0 for user in before}
                remaining = gross - amount
                for user, share in before.items():
                    after[user] = min(share, remaining)
                    remaining -= after[user]
            if (sum(before.values()) != gross or sum(after.values()) != gross - amount
                    or any(v < 0 for v in (*before.values(), *after.values()))
                    or any(user not in people or user not in assigned for user in before.keys() | after.keys())):
                raise ValueError('Confirma el reparto del costo restante entre personas activas del pedido.')
            destination = connection.execute(
                'SELECT id FROM payment_instrument WHERE id = ? AND active = 1',
                (proposed['destination_id'],)).fetchone()
            if destination is None:
                raise ValueError('Selecciona el instrumento real de destino del reembolso.')
            status = proposed['status']
            if status not in ('PENDING', 'ACCREDITED'):
                raise ValueError('Confirma si el reembolso está acreditado o pendiente.')
            accredited = self._parse_iso_date(proposed.get('accredited_at'), 'La fecha de acreditación')
            if (status == 'ACCREDITED' and accredited is None) or (status == 'PENDING' and accredited is not None):
                raise ValueError('La acreditación requiere su fecha real; un reembolso pendiente no debe tenerla.')
            refund_id = str(uuid4())
            validate_refund_event(RefundEvent(refund_id, order_id, str(index), amount, amount,
                amount if status == 'ACCREDITED' else None, None, None, status,
                datetime.now(timezone.utc).isoformat(), source_key))
            if connection.execute('SELECT 1 FROM imported_product_refund WHERE source_key = ? AND product_index = ?',
                                  (source_key, index)).fetchone():
                raise ValueError('Esta devolución del comprobante ya está registrada; no se duplicará.')
            movement_id = None
            if status == 'ACCREDITED':
                movement_id = self._insert_refund_movement(connection, refund_id, proposed['destination_id'],
                    accredited.isoformat(), amount, f'Devolución: {product["description"]}')
            connection.execute('''INSERT INTO imported_product_refund
                (id, order_id, product_index, source_key, original_cents, amount_cents,
                 destination_id, status, accredited_at, created_at, movement_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (refund_id, order_id, index, source_key, gross, amount, proposed['destination_id'], status,
                 accredited.isoformat() if accredited else None, datetime.now(timezone.utc).isoformat(), movement_id))
            for user in before.keys() | after.keys():
                connection.execute('''INSERT INTO product_refund_adjustment
                    (refund_id, user_id, original_cents, final_cents, delta_cents) VALUES (?, ?, ?, ?, ?)''',
                    (refund_id, user, before.get(user, 0), after.get(user, 0), after.get(user, 0) - before.get(user, 0)))
            if status == 'ACCREDITED':
                self._materialize_refund_participations(connection, refund_id)
            self._insert_person_audit(connection, refund_id, 'PRODUCT_REFUND_REGISTERED', actor,
                {'allocations': before}, {**proposed, 'final_allocations': after, 'order_id': order_id},
                entity_type='refund')
            if repurchase:
                self._register_refund_repurchase(connection, refund_id,
                    {**repurchase, 'final_allocations': proposed['final_allocations']}, actor)

    def register_refund_repurchase(self, refund_id, proposal, *, actor='desktop'):
        with self.database.transaction() as connection:
            return self._register_refund_repurchase(connection, refund_id, proposal, actor)

    def _register_refund_repurchase(self, connection, refund_id, proposal, actor):
        refund = connection.execute('''SELECT f.*, o.merchant, o.order_status FROM imported_product_refund f
            JOIN order_record o ON o.id = f.order_id WHERE f.id = ?''', (refund_id,)).fetchone()
        if refund is None or refund['status'] != 'ACCREDITED' or refund['order_status'] != 'ACTIVE':
            raise ValueError('La recompra con el reembolso requiere una devolución acreditada de un pedido activo.')
        if connection.execute('SELECT 1 FROM product_refund_repurchase WHERE refund_id = ?', (refund_id,)).fetchone():
            raise ValueError('Esta devolución ya tiene una recompra vinculada.')
        amount = proposal['amount_cents']
        if type(amount) is not int or not 0 < amount <= refund['amount_cents']:
            raise ValueError('La recompra debe ser positiva y no superar el reembolso disponible; revisa la diferencia.')
        purchased = self._parse_iso_date(proposal.get('ordered_at'), 'La fecha de recompra')
        if purchased is None or purchased.isoformat() < refund['accredited_at']:
            raise ValueError('Confirma la fecha real de recompra, posterior o igual a la acreditación.')
        instrument = connection.execute('SELECT * FROM payment_instrument WHERE id = ? AND active = 1',
                                        (proposal.get('instrument_id'),)).fetchone()
        if (instrument is None or instrument['id'] != refund['destination_id']
                or instrument['instrument_type'] not in ('WALLET_BALANCE', 'OTHER')):
            raise ValueError('Esta recompra se financia con el reembolso: selecciona su misma billetera u otro saldo, no una tarjeta.')
        available = next(i for i in self.list_card_summaries() if i['instrument_id'] == instrument['id'])
        if max(available['wallet_balance_cents'], available['cash_balance_cents']) < amount:
            raise ValueError('El saldo registrado no cubre la recompra; revisa los movimientos reales.')
        if type(proposal.get('apply_surplus', False)) is not bool:
            raise ValueError('Confirma explícitamente si se aplica el sobrante.')
        applied = refund['amount_cents'] - amount if proposal.get('apply_surplus') else 0
        after = proposal['final_allocations']
        before = {r['user_id']: r['final_cents'] for r in connection.execute(
            'SELECT * FROM product_refund_adjustment WHERE refund_id = ?', (refund_id,))}
        people = {p['id']: p for p in self.list_people() if p['active']}
        allowed = {r['user_id'] for r in connection.execute('SELECT user_id FROM order_allocation WHERE order_id = ?',
                                                          (refund['order_id'],))}
        if (any(type(v) is not int or v < 0 for v in after.values())
                or sum(after.values()) != refund['original_cents'] - applied
                or any(user not in people or user not in allowed for user in before.keys() | after.keys())):
            raise ValueError('Reparte exactamente el pendiente del producto original entre las personas del pedido.')
        for user in before.keys() | after.keys():
            item = next((r for r in self.list_collection_items() if r['order_id'] == refund['order_id']
                         and r['user_id'] == user), None)
            if item and item['remaining_cents'] + after.get(user, 0) - before.get(user, 0) < 0:
                raise ValueError('Los abonos existentes exceden el nuevo reparto; revísalos antes de guardar.')
        owner = next(p['id'] for p in people.values() if p['is_owner'])
        order_id = str(uuid4())
        self.create_order(order_id=order_id, ordered_at=purchased.isoformat(), merchant=refund['merchant'] + ' · Recompra',
            instrument_id=instrument['id'], original_cents=amount, discount_cents=0, charged_cents=amount,
            allocations=({'user_id': owner, 'amount_cents': amount},), actor=actor, _connection=connection)
        connection.execute('INSERT INTO product_refund_repurchase VALUES (?, ?, ?)', (refund_id, order_id, applied))
        deltas = {user: after.get(user, 0) - before.get(user, 0) for user in before.keys() | after.keys()}
        for user, delta in deltas.items():
            connection.execute('INSERT INTO product_repurchase_adjustment VALUES (?, ?, ?, ?)',
                               (refund_id, refund['order_id'], user, delta))
            # Original allocation and any receivable remain untouched, including zero shares.
            allocation = connection.execute('SELECT amount_cents FROM order_allocation WHERE order_id = ? AND user_id = ?',
                                            (refund['order_id'], user)).fetchone()
            connection.execute('''INSERT OR IGNORE INTO receivable
                (id,user_id,purchase_id,order_id,source_type,sale_cents,attributable_cost_cents,participant_role)
                VALUES (?, ?, ?, ?, 'ORDER', ?, ?, ?)''',
                (f"order:{refund['order_id']}:{user}", user, refund['order_id'], refund['order_id'],
                 allocation['amount_cents'], allocation['amount_cents'], 'PERSONAL' if people[user]['is_owner'] else 'FAMILY'))
        connection.execute('INSERT INTO product_repurchase_adjustment VALUES (?, ?, ?, ?)',
                           (refund_id, order_id, owner, -amount))
        self._insert_person_audit(connection, refund_id, 'PRODUCT_REFUND_REPURCHASED', actor,
            {'final_allocations': before}, {**proposal, 'order_id': order_id, 'applied_cents': applied,
            'original_adjustment_revision': deltas, 'funded_cents': amount}, entity_type='refund')
        return order_id

    def update_refund_repurchase_allocations(self, refund_id, final_allocations, *,
                                            expected_allocations=None, actor='desktop'):
        """Revise family responsibility only; keep both orders and bank events."""
        if not isinstance(final_allocations, dict) or any(
                type(value) is not int or value < 0 for value in final_allocations.values()):
            raise ValueError('Introduce importes no negativos y exactos en centavos.')
        with self.database.transaction() as connection:
            source = connection.execute('''SELECT f.*, l.applied_cents, l.order_id AS repurchase_order_id,
                o.order_status, r.order_status AS repurchase_status
                FROM imported_product_refund f JOIN product_refund_repurchase l ON l.refund_id=f.id
                JOIN order_record o ON o.id=f.order_id JOIN order_record r ON r.id=l.order_id
                WHERE f.id=?''', (refund_id,)).fetchone()
            if (source is None or source['status'] != 'ACCREDITED'
                    or source['order_status'] != 'ACTIVE' or source['repurchase_status'] != 'ACTIVE'):
                raise ValueError('Selecciona una devolución acreditada con recompra activa ya registrada.')
            required = source['original_cents'] - source['applied_cents']
            if sum(final_allocations.values()) != required:
                raise ValueError('Las participaciones deben sumar exactamente el pendiente original después del sobrante.')
            allowed = {r['user_id']: int(r['amount_cents']) for r in connection.execute(
                'SELECT user_id, amount_cents FROM order_allocation WHERE order_id=?', (source['order_id'],))}
            active = {p['id'] for p in self.list_people() if p['active']}
            if any(user not in allowed or user not in active for user in final_allocations):
                raise ValueError('Reparte el pendiente entre personas activas del pedido original.')
            baseline = {r['user_id']: int(r['final_cents']) for r in connection.execute(
                'SELECT user_id, final_cents FROM product_refund_adjustment WHERE refund_id=?', (refund_id,))}
            revisions = {r['user_id']: int(r['delta_cents']) for r in connection.execute(
                'SELECT user_id, delta_cents FROM product_repurchase_adjustment WHERE refund_id=? AND order_id=?',
                (refund_id, source['order_id']))}
            users = baseline.keys() | revisions.keys() | final_allocations.keys()
            before = {user: baseline.get(user, 0) + revisions.get(user, 0) for user in users}
            after = {user: final_allocations.get(user, 0) for user in users}
            if expected_allocations is not None and any(
                    expected_allocations.get(user, 0) != before.get(user, 0)
                    for user in users | expected_allocations.keys()):
                raise ValueError('El reparto cambió mientras lo editabas; vuelve a abrirlo antes de guardar.')
            if sum(before.values()) != required:
                raise ValueError('El reparto registrado no concilia; revisa su historial antes de corregirlo.')
            if before == after:
                return  # Repeated save creates neither a second adjustment nor an audit event.
            deltas = {user: after[user] - before[user] for user in users}
            accounts = {r['user_id']: r for r in self.list_collection_items() if r['order_id'] == source['order_id']}
            for user, delta in deltas.items():
                if accounts.get(user) and accounts[user]['remaining_cents'] + delta < 0:
                    raise ValueError('Los abonos existentes excederían el nuevo reparto; revísalos antes de guardar.')
            for user in users:
                # This table stores the current cumulative revision. Each previous
                # value and the incremental correction are retained in the audit log.
                connection.execute('''INSERT INTO product_repurchase_adjustment
                    (refund_id, order_id, user_id, delta_cents) VALUES (?, ?, ?, ?)
                    ON CONFLICT(refund_id, order_id, user_id) DO UPDATE SET delta_cents=excluded.delta_cents''',
                    (refund_id, source['order_id'], user, after[user] - baseline.get(user, 0)))
                if after[user] and user not in accounts:
                    person = next(p for p in self.list_people() if p['id'] == user)
                    connection.execute('''INSERT INTO receivable
                        (id,user_id,purchase_id,order_id,source_type,sale_cents,attributable_cost_cents,participant_role)
                        VALUES (?, ?, ?, ?, 'ORDER', ?, ?, ?)''',
                        (f"order:{source['order_id']}:{user}", user, source['order_id'], source['order_id'],
                         allowed[user], allowed[user], 'PERSONAL' if person['is_owner'] else 'FAMILY'))
            self._insert_person_audit(connection, refund_id, 'PRODUCT_REFUND_REPARTITIONED', actor,
                {'final_allocations': before, 'revision_cents': revisions},
                {'final_allocations': after, 'correction_cents': deltas, 'order_id': source['order_id'],
                 'repurchase_order_id': source['repurchase_order_id'], 'pending_cents': required}, entity_type='refund')

    def _insert_refund_movement(self, connection, refund_id, destination_id, accredited_at, amount, description):
        movement_id = f'refund:{refund_id}'
        self._insert_institution_movement(connection, movement_id, destination_id, accredited_at,
                                          'REFUND', amount, description, movement_id)
        connection.execute("UPDATE institution_movement SET status = 'ACCEPTED' WHERE id = ?", (movement_id,))
        return movement_id

    @staticmethod
    def _materialize_refund_participations(connection, refund_id):
        rows = connection.execute('''SELECT f.order_id, a.user_id, p.is_owner, o.amount_cents
            FROM imported_product_refund f JOIN product_refund_adjustment a ON a.refund_id = f.id
            JOIN person p ON p.id = a.user_id
            JOIN order_allocation o ON o.order_id = f.order_id AND o.user_id = a.user_id
            WHERE f.id = ? AND a.delta_cents != 0''', (refund_id,)).fetchall()
        for row in rows:
            connection.execute('''INSERT INTO receivable
                (id, user_id, purchase_id, order_id, source_type, sale_cents, attributable_cost_cents, participant_role)
                SELECT ?, ?, ?, ?, 'ORDER', ?, ?, ?
                WHERE NOT EXISTS (SELECT 1 FROM receivable WHERE order_id = ? AND user_id = ?)''',
                (f'order:{row["order_id"]}:{row["user_id"]}', row['user_id'], row['order_id'], row['order_id'],
                 row['amount_cents'], row['amount_cents'], 'PERSONAL' if row['is_owner'] else 'FAMILY',
                 row['order_id'], row['user_id']))

    def list_product_refunds(self, order_id):
        result = []
        for row in self.database.connection.execute('''SELECT f.*, i.alias AS destination_name,
            i.instrument_type AS destination_type FROM imported_product_refund f
            JOIN payment_instrument i ON i.id = f.destination_id WHERE f.order_id = ? ORDER BY f.product_index''', (order_id,)):
            item = dict(row)
            item['adjustments'] = [dict(a) for a in self.database.connection.execute(
                'SELECT * FROM product_refund_adjustment WHERE refund_id = ? ORDER BY user_id', (row['id'],))]
            linked = self.database.connection.execute('''SELECT l.*, o.ordered_at, o.charged_cents, i.alias AS payment_name
                FROM product_refund_repurchase l JOIN order_record o ON o.id = l.order_id
                JOIN payment_instrument i ON i.id = o.instrument_id WHERE l.refund_id = ?''', (row['id'],)).fetchone()
            item['repurchase'] = dict(linked) if linked else None
            if linked:
                revisions = {r['user_id']: r['delta_cents'] for r in self.database.connection.execute(
                    'SELECT user_id, delta_cents FROM product_repurchase_adjustment WHERE refund_id=? AND order_id=?',
                    (row['id'], order_id))}
                known = {a['user_id'] for a in item['adjustments']}
                for user in revisions.keys() - known:
                    item['adjustments'].append(dict(refund_id=row['id'], user_id=user,
                        original_cents=0, final_cents=0, delta_cents=0))
                for adjustment in item['adjustments']:
                    adjustment['effective_final_cents'] = adjustment['final_cents'] + revisions.get(adjustment['user_id'], 0)
            result.append(item)
        return result

    def confirm_product_refund(self, refund_id, accredited_at, *, actor='desktop'):
        accredited = self._parse_iso_date(accredited_at, 'La fecha de acreditación')
        if accredited is None:
            raise ValueError('Indica la fecha real de acreditación.')
        with self.database.transaction() as connection:
            refund = connection.execute('''SELECT f.*, o.order_status FROM imported_product_refund f
                JOIN order_record o ON o.id = f.order_id WHERE f.id = ?''', (refund_id,)).fetchone()
            if refund is None or refund['order_status'] != 'ACTIVE':
                raise ValueError('La devolución no existe o el pedido está anulado.')
            if refund['status'] == 'ACCREDITED':
                if refund['accredited_at'] != accredited.isoformat():
                    raise ValueError('El reembolso ya fue acreditado con otra fecha.')
                return  # Confirmar de nuevo nunca genera un segundo movimiento.
            for adjustment in connection.execute('SELECT * FROM product_refund_adjustment WHERE refund_id = ?', (refund_id,)):
                item = next((i for i in self.list_collection_items() if i['order_id'] == refund['order_id']
                             and i['user_id'] == adjustment['user_id']), None)
                if item and int(item['remaining_cents']) + adjustment['delta_cents'] < 0:
                    raise ValueError('Hay abonos que excederían la participación ajustada; revisa esos abonos antes de acreditar.')
            movement_id = self._insert_refund_movement(connection, refund_id, refund['destination_id'],
                accredited.isoformat(), refund['amount_cents'], 'Devolución de producto importado')
            connection.execute("UPDATE imported_product_refund SET status = 'ACCREDITED', accredited_at = ?, movement_id = ? WHERE id = ?",
                               (accredited.isoformat(), movement_id, refund_id))
            self._materialize_refund_participations(connection, refund_id)
            self._insert_person_audit(connection, refund_id, 'PRODUCT_REFUND_ACCREDITED', actor,
                {'status': 'PENDING'}, {'status': 'ACCREDITED', 'accredited_at': accredited.isoformat(),
                'destination_id': refund['destination_id'], 'amount_cents': refund['amount_cents']}, entity_type='refund')

    def find_import_duplicates(self, evidence: dict) -> list[str]:
        matches = []
        for row in self.database.connection.execute(
            "SELECT entity_id, new_value FROM audit_event WHERE action = 'PDF_IMPORTED'"
        ):
            previous = json.loads(row['new_value'])
            if (previous.get('fingerprint') == evidence.get('fingerprint') and evidence.get('fingerprint')) or (
                evidence.get('number') and previous.get('number') == evidence['number']
            ) or (previous.get('date') == evidence.get('date') and previous.get('charged') == evidence.get('charged')):
                matches.append(row['entity_id'])
        return matches

    def list_orders(self, status: str = "ACTIVE") -> list[dict[str, object]]:
        if status not in {"ACTIVE", "CANCELLED", "ALL"}:
            raise ValueError("El filtro de pedidos no es válido.")
        condition = "" if status == "ALL" else "WHERE order_status = ?"
        parameters: tuple[object, ...] = () if status == "ALL" else (status,)
        rows = self.database.connection.execute(
            f"""
            SELECT id, ordered_at, merchant, instrument_id, original_cents,
                   discount_cents, charged_cents, total_to_recover_cents, owner_cents,
                   purchase_mode, order_status, cancelled_at, cancelled_by,
                   cancellation_reason
            FROM order_record {condition}
            ORDER BY ordered_at DESC, id DESC
            """,
            parameters,
        ).fetchall()
        return [dict(row) for row in rows]

    def update_order_merchant(self, order_id: str, merchant: str, *, actor: str = "desktop") -> None:
        merchant = merchant.strip()
        if not merchant:
            raise ValueError("El comercio es obligatorio.")
        with self.database.transaction() as connection:
            order = connection.execute("SELECT merchant, order_status FROM order_record WHERE id = ?",
                                       (order_id,)).fetchone()
            if order is None or order["order_status"] != "ACTIVE":
                raise ValueError("Selecciona un pedido activo para editar el comercio.")
            if order["merchant"] == merchant:
                return
            connection.execute("UPDATE order_record SET merchant = ? WHERE id = ?", (merchant, order_id))
            self._insert_person_audit(connection, order_id, "ORDER_MERCHANT_UPDATED", actor,
                                      {"merchant": order["merchant"]}, {"merchant": merchant},
                                      entity_type="order")

    def cancel_order(
        self,
        order_id: str,
        *,
        reason: str,
        actor: str = "desktop",
    ) -> None:
        reason = reason.strip()
        if not reason:
            raise ValueError("Indica el motivo de la anulación.")
        with self.database.transaction() as connection:
            order = connection.execute(
                "SELECT * FROM order_record WHERE id = ?", (order_id,)
            ).fetchone()
            if order is None:
                raise ValueError("El pedido no existe.")
            if order["order_status"] == "CANCELLED":
                raise ValueError("El pedido ya está anulado.")
            if (connection.execute('SELECT 1 FROM imported_product_refund WHERE order_id = ?', (order_id,)).fetchone()
                    or connection.execute('SELECT 1 FROM product_refund_repurchase WHERE order_id = ?', (order_id,)).fetchone()):
                raise ValueError('No se puede anular un pedido con devoluciones asociadas; conserva su historial.')
            applied_receipts = connection.execute(
                """
                SELECT COALESCE(SUM(ra.amount_cents), 0)
                FROM receipt_application ra
                JOIN receivable r ON r.id = ra.receivable_id
                WHERE r.order_id = ? AND ra.application_status = 'ACTIVE'
                """,
                (order_id,),
            ).fetchone()[0]
            applied_installments = connection.execute(
                """
                SELECT COUNT(*)
                FROM installment_payment_application ipa
                JOIN installment i ON i.id = ipa.installment_id
                JOIN financing_plan f ON f.id = i.plan_id
                WHERE f.order_id = ? AND ipa.application_status = 'ACTIVE'
                """,
                (order_id,),
            ).fetchone()[0]
            if int(applied_receipts) or int(applied_installments):
                raise ValueError(
                    "No se puede anular: el pedido tiene abonos personales o familiares "
                    "o pagos aplicados a cuotas. Revierte esas operaciones "
                    "explícitamente antes de intentarlo."
                )
            now = datetime.now(timezone.utc).isoformat()
            connection.execute(
                """
                UPDATE order_record
                SET order_status = 'CANCELLED', cancelled_at = ?,
                    cancelled_by = ?, cancellation_reason = ?
                WHERE id = ? AND order_status = 'ACTIVE'
                """,
                (now, actor, reason, order_id),
            )
            self._insert_person_audit(
                connection, order_id, "ORDER_CANCELLED", actor,
                {"order_status": "ACTIVE"},
                {"order_status": "CANCELLED", "reason": reason, "cancelled_at": now},
                entity_type="order",
            )

    def apply_institution_payment_to_installment(
        self,
        *,
        payment_id: str,
        installment_id: str,
        amount_cents: int,
        actor: str = "desktop",
    ) -> None:
        if amount_cents <= 0:
            raise ValueError("El importe aplicado debe ser mayor que cero.")
        with self.database.transaction() as connection:
            payment = connection.execute(
                "SELECT instrument_id, amount_cents, payment_status "
                "FROM institution_payment WHERE id = ?",
                (payment_id,),
            ).fetchone()
            installment = connection.execute(
                """
                SELECT i.*, f.instrument_id, f.order_id, o.order_status
                FROM installment i
                JOIN financing_plan f ON f.id = i.plan_id
                JOIN order_record o ON o.id = f.order_id
                WHERE i.id = ?
                """,
                (installment_id,),
            ).fetchone()
            if payment is None or installment is None:
                raise ValueError("El pago o la cuota no existe.")
            if payment["payment_status"] == "CANCELLED":
                raise ValueError("No se puede usar un pago anulado.")
            if installment["order_status"] == "CANCELLED":
                raise ValueError("No se puede aplicar un pago a un pedido anulado.")
            if payment["instrument_id"] != installment["instrument_id"]:
                raise ValueError("El pago y la cuota pertenecen a tarjetas distintas.")
            used_payment = connection.execute(
                """
                SELECT COALESCE(SUM(amount_cents), 0)
                FROM installment_payment_application
                WHERE payment_id = ? AND application_status = 'ACTIVE'
                """,
                (payment_id,),
            ).fetchone()[0]
            used_installment = connection.execute(
                """
                SELECT COALESCE(SUM(amount_cents), 0)
                FROM installment_payment_application
                WHERE installment_id = ? AND application_status = 'ACTIVE'
                """,
                (installment_id,),
            ).fetchone()[0]
            installment_total = int(installment["principal_cents"]) + int(
                installment["interest_cents"]
            )
            if int(used_payment) + amount_cents > int(payment["amount_cents"]):
                raise ValueError("La aplicación excede el pago disponible.")
            if int(used_installment) + amount_cents > installment_total:
                raise ValueError("La aplicación excede el saldo de la cuota.")
            applied_at = datetime.now(timezone.utc).isoformat()
            connection.execute(
                """
                INSERT INTO installment_payment_application
                    (payment_id, installment_id, amount_cents, applied_at)
                VALUES (?, ?, ?, ?)
                """,
                (payment_id, installment_id, amount_cents, applied_at),
            )
            # The legacy status CHECK has no PARTIAL value.  Partial payment
            # is represented by the auditable application sum; only a fully
            # covered installment changes to PAID.
            new_status = (
                "PAID" if int(used_installment) + amount_cents == installment_total
                else str(installment["status"])
            )
            connection.execute(
                "UPDATE installment SET status = ? WHERE id = ?",
                (new_status, installment_id),
            )
            self._insert_person_audit(
                connection, installment_id, "INSTALLMENT_PAYMENT_APPLIED", actor,
                {"applied_cents": int(used_installment)},
                {"applied_cents": int(used_installment) + amount_cents,
                 "payment_id": payment_id},
                entity_type="installment",
            )

    def list_installment_payment_applications(
        self, installment_id: str, *, include_reversed: bool = False
    ) -> list[dict[str, object]]:
        condition = "" if include_reversed else "AND application_status = 'ACTIVE'"
        rows = self.database.connection.execute(
            f"""
            SELECT payment_id, installment_id, amount_cents, applied_at,
                   application_status, reversed_at, reversal_reason
            FROM installment_payment_application
            WHERE installment_id = ? {condition}
            ORDER BY applied_at, payment_id
            """,
            (installment_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _validate_manual_concepts(concepts, original_cents, people):
        if not concepts:
            raise ValueError('Agrega al menos un concepto.')
        totals = {}
        for concept in concepts:
            amount = concept.get('amount_cents')
            shares = concept.get('allocations', {})
            if not isinstance(concept.get('description'), str) or not concept['description'].strip() or type(amount) is not int or amount <= 0:
                raise ValueError('Cada concepto necesita descripción e importe positivo en centavos.')
            if not isinstance(shares, dict) or not shares or any(type(value) is not int or value < 0 for value in shares.values()) or sum(shares.values()) != amount:
                raise ValueError('El reparto de cada concepto debe sumar exactamente su importe.')
            for person, value in shares.items():
                if person not in people or (value and not people[person]['active']):
                    raise ValueError('El reparto debe pertenecer a personas existentes y activas.')
                totals[person] = totals.get(person, 0) + value
        if sum(totals.values()) != original_cents:
            raise ValueError('Los conceptos deben sumar el importe original del pedido.')
        return totals

    def update_manual_concepts(self, order_id, concepts, *, expected_concepts=None, actor='desktop'):
        """Edit one manual order atomically; preserve its charge, plan and receipts."""
        with self.database.transaction() as connection:
            order = self.get_order(order_id)
            if not order or order['order_status'] != 'ACTIVE' or order['manual_concepts'] is None or order['import_evidence']:
                raise ValueError('Selecciona un gasto manual activo con conceptos.')
            if order['product_refunds']:
                raise ValueError('Este pedido tiene devoluciones; utiliza sus ajustes específicos.')
            if expected_concepts is not None and order['manual_concepts'] != expected_concepts:
                raise ValueError('Los conceptos cambiaron; vuelve a abrir el pedido.')
            people = {r['id']: dict(r) for r in connection.execute('SELECT id, active, is_owner FROM person')}
            for account in order['receivables']:
                expected_role = 'PERSONAL' if people[account['user_id']]['is_owner'] else 'FAMILY'
                if account['participant_role'] != expected_role:
                    raise ValueError('La configuración de Yo cambió; revisa las participaciones originales.')
            totals = self._validate_manual_concepts(concepts, order['original_cents'], people)
            for account in self.list_collection_items():
                if account['order_id'] == order_id and totals.get(account['user_id'], 0) < int(account['paid_cents']):
                    raise ValueError('El nuevo reparto es menor que los abonos ya registrados.')
            if concepts == order['manual_concepts']:
                return
            existing = {a['user_id'] for a in order['allocations']}
            owner_id = next((key for key, p in people.items() if p['active'] and p['is_owner']), None)
            if owner_id is None:
                raise ValueError('Configura Yo antes de editar el reparto.')
            for person in existing | set(totals) | {owner_id}:
                amount = totals.get(person, 0)
                connection.execute('''INSERT INTO order_allocation VALUES (?, ?, ?)
                    ON CONFLICT(order_id, user_id) DO UPDATE SET amount_cents=excluded.amount_cents''', (order_id, person, amount))
                role = 'PERSONAL' if people[person]['is_owner'] else 'FAMILY'
                connection.execute('''UPDATE receivable SET sale_cents=?, attributable_cost_cents=?
                    WHERE order_id=? AND user_id=?''', (amount, amount, order_id, person))
                if amount and not connection.execute('SELECT 1 FROM receivable WHERE order_id=? AND user_id=?', (order_id, person)).fetchone():
                    connection.execute('''INSERT INTO receivable
                        (id,user_id,purchase_id,order_id,source_type,sale_cents,attributable_cost_cents,participant_role)
                        VALUES (?, ?, ?, ?, 'ORDER', ?, ?, ?)''', (f'order:{order_id}:{person}', person, order_id, order_id, amount, amount, role))
            connection.execute('UPDATE order_record SET owner_cents=? WHERE id=?',
                               (sum(amount for key, amount in totals.items() if people[key]['is_owner']), order_id))
            self._insert_person_audit(connection, order_id, 'MANUAL_CONCEPTS_SAVED', actor,
                                      order['manual_concepts'], concepts, entity_type='order')

    def get_order(self, order_id: str) -> dict[str, object] | None:
        row = self.database.connection.execute(
            "SELECT * FROM order_record WHERE id = ?", (order_id,)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        manual = self.database.connection.execute(
            "SELECT new_value FROM audit_event WHERE entity_id=? AND action='MANUAL_CONCEPTS_SAVED' ORDER BY rowid DESC LIMIT 1",
            (order_id,),
        ).fetchone()
        result['manual_concepts'] = json.loads(manual['new_value']) if manual else None
        evidence = self.database.connection.execute(
            "SELECT new_value FROM audit_event WHERE entity_id = ? AND action = 'PDF_IMPORTED' ORDER BY occurred_at DESC LIMIT 1",
            (order_id,),
        ).fetchone()
        result['import_evidence'] = json.loads(evidence['new_value']) if evidence else None
        result['product_refunds'] = self.list_product_refunds(order_id)
        result["allocations"] = [
            dict(item)
            for item in self.database.connection.execute(
                "SELECT * FROM order_allocation WHERE order_id = ? ORDER BY user_id",
                (order_id,),
            ).fetchall()
        ]
        result["receivables"] = [
            dict(item)
            for item in self.database.connection.execute(
                "SELECT * FROM receivable WHERE order_id = ? ORDER BY user_id",
                (order_id,),
            ).fetchall()
        ]
        plan = self.database.connection.execute(
            "SELECT * FROM financing_plan WHERE order_id = ?", (order_id,)
        ).fetchone()
        result["financing_plan"] = dict(plan) if plan else None
        if plan:
            result["installments"] = [
                dict(item) for item in self.database.connection.execute(
                    """
                    SELECT i.*, a.period_key, a.status AS assignment_status,
                           a.requires_review
                    FROM installment i
                    LEFT JOIN installment_period_assignment a
                        ON a.installment_id = i.id
                    WHERE i.plan_id = ? ORDER BY i.number
                    """,
                    (plan["id"],),
                ).fetchall()
            ]
        else:
            result["installments"] = []
        return result

    @staticmethod
    def _parse_iso_date(value: str | None, label: str) -> date | None:
        if value is None or not str(value).strip():
            return None
        try:
            return date.fromisoformat(str(value))
        except ValueError as error:
            raise ValueError(f"{label}: usa el formato AAAA-MM-DD.") from error

    @classmethod
    def _required_iso_date(cls, value, label):
        parsed = cls._parse_iso_date(value, label)
        if parsed is None:
            raise ValueError(f'{label} es obligatoria; usa AAAA-MM-DD.')
        return parsed.isoformat()

    @staticmethod
    def _next_month(value: date) -> date:
        year, month = value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1
        return value.replace(year=year, month=month, day=1)

    @classmethod
    def _period_key(cls, due_date: date, closing_day: int) -> str:
        if due_date.day <= closing_day:
            return f"{due_date.year:04d}-{due_date.month:02d}"
        next_month = cls._next_month(due_date)
        return f"{next_month.year:04d}-{next_month.month:02d}"

    def _insert_financing_plan(
        self,
        connection,
        *,
        plan_id: str,
        order_id: str,
        instrument_id: str,
        principal_cents: int,
        interest_cents: int,
        due_dates: tuple[str | None, ...],
    ) -> None:
        if principal_cents < 0 or interest_cents < 0:
            raise ValueError("Los importes financiados no pueden ser negativos.")
        if not due_dates:
            raise ValueError("El plan MSI requiere al menos una cuota.")
        order = connection.execute(
            "SELECT ordered_at, purchase_mode FROM order_record WHERE id = ?",
            (order_id,),
        ).fetchone()
        if order is None:
            raise ValueError("El pedido no existe.")
        if order["purchase_mode"] != "MSI":
            raise ValueError("Solo los pedidos MSI pueden tener un plan.")
        if connection.execute(
            "SELECT 1 FROM financing_plan WHERE order_id = ?", (order_id,)
        ).fetchone():
            raise ValueError("El pedido ya tiene un plan de financiamiento.")
        purchase_date = self._parse_iso_date(order["ordered_at"], "La fecha del pedido")
        parsed_dates = tuple(
            self._parse_iso_date(value, f"La fecha de la cuota {number}")
            for number, value in enumerate(due_dates, 1)
        )
        if any(value is None for value in parsed_dates):
            status = "PENDING_CONFIRMATION"
        else:
            status = "CONFIRMED"
        plan_calendar = None
        if purchase_date is not None:
            plan_calendar = connection.execute(
                """
                SELECT * FROM instrument_calendar
                WHERE instrument_id = ? AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY revision DESC LIMIT 1
                """,
                (instrument_id, purchase_date.isoformat(), purchase_date.isoformat()),
            ).fetchone()
        principal_each, principal_residual = divmod(principal_cents, len(due_dates))
        interest_each, interest_residual = divmod(interest_cents, len(due_dates))
        connection.execute(
            """
            INSERT INTO financing_plan
                (id, order_id, instrument_id, principal_cents, interest_cents,
                 installment_count, first_due_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id, order_id, instrument_id, principal_cents, interest_cents,
                len(due_dates), parsed_dates[0].isoformat() if parsed_dates[0] else None,
                status if plan_calendar or status == "PENDING_CONFIRMATION" else "PENDING_CONFIRMATION",
            ),
        )
        for number, due_date in enumerate(parsed_dates, 1):
            installment_id = f"{plan_id}-{number}"
            principal = principal_each + (1 if number <= principal_residual else 0)
            interest = interest_each + (1 if number <= interest_residual else 0)
            connection.execute(
                """
                INSERT INTO installment
                    (id, plan_id, number, due_date, principal_cents, interest_cents)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    installment_id, plan_id, number,
                    due_date.isoformat() if due_date else None,
                    principal, interest,
                ),
            )
            period_key = None
            requires_review = 1
            calendar_id = None
            revision = None
            assignment_status = "PROPOSED"
            if plan_calendar and due_date:
                period_key = self._period_key(due_date, int(plan_calendar["closing_day"]))
                requires_review = 0
                calendar_id = plan_calendar["id"]
                revision = plan_calendar["revision"]
                assignment_status = "ACCEPTED"
            connection.execute(
                """
                INSERT INTO installment_period_assignment
                    (id, installment_id, calendar_id, period_key, source,
                     calendar_revision, status, requires_review)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"period:{installment_id}", installment_id, calendar_id,
                    period_key, "purchase-date-calendar", revision,
                    assignment_status, requires_review,
                ),
            )

    def create_financing_plan(
        self,
        *,
        plan_id: str,
        order_id: str,
        due_dates: tuple[str | None, ...],
        interest_cents: int = 0,
        actor: str = "desktop",
    ) -> None:
        with self.database.transaction() as connection:
            order = connection.execute(
                "SELECT instrument_id, charged_cents, purchase_mode FROM order_record WHERE id = ?",
                (order_id,),
            ).fetchone()
            if order is None:
                raise ValueError("El pedido no existe.")
            if order["purchase_mode"] != "MSI":
                raise ValueError("Primero clasifica el pedido como MSI.")
            self._insert_financing_plan(
                connection,
                plan_id=plan_id,
                order_id=order_id,
                instrument_id=order["instrument_id"],
                principal_cents=int(order["charged_cents"]),
                interest_cents=interest_cents,
                due_dates=due_dates,
            )
            self._insert_person_audit(
                connection, plan_id, "FINANCING_PLAN_CREATED", actor, None,
                {"order_id": order_id, "installments": len(due_dates),
                 "principal_cents": int(order["charged_cents"]),
                 "interest_cents": interest_cents},
                entity_type="financing_plan",
            )

    def list_installments(
        self, instrument_id: str, period_key: str | None = None
    ) -> list[dict[str, object]]:
        parameters: list[object] = [instrument_id]
        query = """
            SELECT i.id, i.number, i.due_date, i.principal_cents,
                   i.interest_cents, i.status, f.order_id, o.merchant,
                   a.period_key, a.requires_review, f.status AS plan_status
            FROM installment i
            JOIN financing_plan f ON f.id = i.plan_id
            JOIN order_record o ON o.id = f.order_id
            LEFT JOIN installment_period_assignment a ON a.installment_id = i.id
            WHERE f.instrument_id = ? AND o.order_status = 'ACTIVE'
        """
        if period_key is not None:
            query += " AND a.period_key = ?"
            parameters.append(period_key)
        query += " ORDER BY i.due_date IS NULL, i.due_date, i.number"
        result = []
        for row in self.database.connection.execute(query, parameters).fetchall():
            item = dict(row)
            item["applied_cents"] = sum(
                int(application["amount_cents"])
                for application in self.list_installment_payment_applications(
                    str(item["id"])
                )
            )
            total = int(item["principal_cents"]) + int(item["interest_cents"])
            item["remaining_cents"] = max(total - int(item["applied_cents"]), 0)
            item["payment_status"] = (
                "PAID" if item["remaining_cents"] == 0
                else "PARTIAL" if item["applied_cents"] else "PENDING"
            )
            result.append(item)
        return result

    def confirm_installment_period(
        self,
        *,
        assignment_id: str,
        period_key: str,
        actor: str = "desktop",
    ) -> None:
        try:
            year, month = (int(part) for part in period_key.split("-"))
            if not 1 <= month <= 12 or year < 1:
                raise ValueError
        except (ValueError, TypeError) as error:
            raise ValueError("El periodo debe tener formato AAAA-MM.") from error
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT period_key, requires_review
                FROM installment_period_assignment WHERE id = ?
                """,
                (assignment_id,),
            ).fetchone()
            if row is None:
                raise ValueError("La asignación de periodo no existe.")
            connection.execute(
                """
                UPDATE installment_period_assignment
                SET period_key = ?, status = 'ACCEPTED', requires_review = 0,
                    source = 'manual-confirmation'
                WHERE id = ?
                """,
                (period_key, assignment_id),
            )
            self._insert_person_audit(
                connection, assignment_id, "INSTALLMENT_PERIOD_CONFIRMED",
                actor,
                {"period_key": row["period_key"], "requires_review": bool(row["requires_review"])},
                {"period_key": period_key, "requires_review": False},
                entity_type="installment_period_assignment",
            )

    def correct_installment_due_date(
        self,
        *,
        installment_id: str,
        due_date: str,
        actor: str = "desktop",
    ) -> None:
        parsed = self._parse_iso_date(due_date, "La fecha de la cuota")
        if parsed is None:
            raise ValueError("La fecha de la cuota es obligatoria.")
        with self.database.transaction() as connection:
            installment = connection.execute(
                """
                SELECT i.due_date, f.instrument_id, o.order_status
                FROM installment i
                JOIN financing_plan f ON f.id = i.plan_id
                JOIN order_record o ON o.id = f.order_id
                WHERE i.id = ?
                """,
                (installment_id,),
            ).fetchone()
            if installment is None:
                raise ValueError("La cuota no existe.")
            if installment["order_status"] == "CANCELLED":
                raise ValueError("No se puede modificar una cuota de un pedido anulado.")
            old_date = installment["due_date"]
            calendar = connection.execute(
                """
                SELECT * FROM instrument_calendar
                WHERE instrument_id = ? AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY revision DESC LIMIT 1
                """,
                (installment["instrument_id"], parsed.isoformat(), parsed.isoformat()),
            ).fetchone()
            period_key = None
            requires_review = 1
            calendar_id = None
            revision = None
            status = "PROPOSED"
            if calendar:
                period_key = self._period_key(parsed, int(calendar["closing_day"]))
                requires_review = 0
                calendar_id = calendar["id"]
                revision = calendar["revision"]
                status = "ACCEPTED"
            connection.execute(
                "UPDATE installment SET due_date = ? WHERE id = ?",
                (parsed.isoformat(), installment_id),
            )
            connection.execute(
                """
                UPDATE installment_period_assignment
                SET calendar_id = ?, period_key = ?, source = 'manual-correction',
                    calendar_revision = ?, status = ?, requires_review = ?
                WHERE installment_id = ?
                """,
                (
                    calendar_id, period_key, revision, status, requires_review,
                    installment_id,
                ),
            )
            self._insert_person_audit(
                connection, installment_id, "INSTALLMENT_DUE_DATE_CORRECTED",
                actor, {"due_date": old_date},
                {"due_date": parsed.isoformat(), "period_key": period_key,
                 "requires_review": bool(requires_review)},
                entity_type="installment",
            )

    def add_institution_movement(
        self,
        movement_id: str,
        instrument_id: str,
        posted_at: str,
        kind: str,
        amount_cents: int,
        description: str,
        external_ref: str | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            self._insert_institution_movement(connection, movement_id, instrument_id, posted_at,
                                               kind, amount_cents, description, external_ref)

    @staticmethod
    def _insert_institution_movement(connection, movement_id, instrument_id, posted_at,
                                     kind, amount_cents, description, external_ref):
        connection.execute(
            """
            INSERT INTO institution_movement
                (id, instrument_id, posted_at, kind, amount_cents, description, external_ref)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (movement_id, instrument_id, posted_at, kind, amount_cents, description, external_ref),
        )

    def record_institution_payment(
        self,
        *,
        payment_id: str,
        instrument_id: str,
        paid_at: str,
        amount_cents: int,
        reference: str | None = None,
        actor: str = "desktop",
    ) -> None:
        if amount_cents <= 0:
            raise ValueError("El pago a la tarjeta debe ser mayor que cero.")
        parsed_paid_at = self._parse_iso_date(paid_at, "La fecha del pago")
        if parsed_paid_at is None:
            raise ValueError("La fecha del pago es obligatoria.")
        with self.database.transaction() as connection:
            instrument = connection.execute(
                "SELECT id, instrument_type FROM payment_instrument WHERE id = ? AND active = 1",
                (instrument_id,),
            ).fetchone()
            if instrument is None:
                raise ValueError("La tarjeta seleccionada no existe o está inactiva.")
            if instrument['instrument_type'] not in ('CREDIT_CARD', 'CREDIT_LINE'):
                raise ValueError('Un pago a tarjeta requiere un instrumento de crédito; una billetera no tiene deuda de crédito.')
            connection.execute(
                """
                INSERT INTO institution_payment
                    (id, instrument_id, paid_at, amount_cents, reference)
                VALUES (?, ?, ?, ?, ?)
                """,
                (payment_id, instrument_id, parsed_paid_at.isoformat(), amount_cents, reference),
            )
            self._insert_person_audit(
                connection,
                payment_id,
                "INSTITUTION_PAYMENT_RECORDED",
                actor,
                None,
                {
                    "instrument_id": instrument_id,
                    "paid_at": paid_at,
                    "amount_cents": amount_cents,
                    "reference": reference,
                },
                entity_type="institution_payment",
            )

    def update_institution_payment(
        self,
        payment_id: str,
        *,
        paid_at: str,
        amount_cents: int,
        reference: str | None = None,
        actor: str = "desktop",
    ) -> None:
        if amount_cents <= 0:
            raise ValueError("El pago a la tarjeta debe ser mayor que cero.")
        parsed_paid_at = self._parse_iso_date(paid_at, "La fecha del pago")
        if parsed_paid_at is None:
            raise ValueError("La fecha del pago es obligatoria.")
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM institution_payment WHERE id = ?", (payment_id,)
            ).fetchone()
            if row is None or row["payment_status"] == "CANCELLED":
                raise ValueError("El pago seleccionado no existe o está anulado.")
            applied = connection.execute(
                """
                SELECT COALESCE(SUM(amount_cents), 0)
                FROM installment_payment_application
                WHERE payment_id = ? AND application_status = 'ACTIVE'
                """,
                (payment_id,),
            ).fetchone()[0]
            if amount_cents < int(applied):
                raise ValueError(
                    "No puedes reducir el pago por debajo de lo ya aplicado a cuotas."
                )
            try:
                connection.execute(
                    """
                    UPDATE institution_payment
                    SET paid_at = ?, amount_cents = ?, reference = ?
                    WHERE id = ?
                    """,
                    (parsed_paid_at.isoformat(), amount_cents, reference, payment_id),
                )
            except Exception as error:
                if "UNIQUE constraint" in str(error):
                    raise ValueError("Ya existe otro pago con esa referencia.") from error
                raise
            self._insert_person_audit(
                connection, payment_id, "INSTITUTION_PAYMENT_UPDATED", actor,
                {"paid_at": row["paid_at"], "amount_cents": row["amount_cents"],
                 "reference": row["reference"]},
                {"paid_at": paid_at, "amount_cents": amount_cents, "reference": reference},
                entity_type="institution_payment",
            )

    def cancel_institution_payment(
        self,
        payment_id: str,
        *,
        reason: str,
        actor: str = "desktop",
    ) -> None:
        reason = reason.strip()
        if not reason:
            raise ValueError("Indica el motivo de la anulación del pago.")
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM institution_payment WHERE id = ?", (payment_id,)
            ).fetchone()
            if row is None:
                raise ValueError("El pago seleccionado no existe.")
            if row["payment_status"] == "CANCELLED":
                raise ValueError("El pago ya está anulado.")
            applications = connection.execute(
                """
                SELECT installment_id FROM installment_payment_application
                WHERE payment_id = ? AND application_status = 'ACTIVE'
                """,
                (payment_id,),
            ).fetchall()
            now = datetime.now(timezone.utc).isoformat()
            connection.execute(
                """
                UPDATE institution_payment
                SET payment_status = 'CANCELLED', cancelled_at = ?,
                    cancelled_by = ?, cancellation_reason = ?
                WHERE id = ?
                """,
                (now, actor, reason, payment_id),
            )
            for application in applications:
                connection.execute(
                    """
                    UPDATE installment_payment_application
                    SET application_status = 'REVERSED', reversed_at = ?,
                        reversed_by = ?, reversal_reason = ?
                    WHERE payment_id = ? AND installment_id = ?
                      AND application_status = 'ACTIVE'
                    """,
                    (now, actor, reason, payment_id, application["installment_id"]),
                )
                self._refresh_installment_payment_status(
                    connection, str(application["installment_id"])
                )
            self._insert_person_audit(
                connection, payment_id, "INSTITUTION_PAYMENT_CANCELLED", actor,
                {"payment_status": "ACTIVE", "applications_reversed": len(applications)},
                {"payment_status": "CANCELLED", "reason": reason, "cancelled_at": now},
                entity_type="institution_payment",
            )

    @staticmethod
    def _refresh_installment_payment_status(connection, installment_id: str) -> None:
        row = connection.execute(
            """
            SELECT principal_cents, interest_cents, status
            FROM installment WHERE id = ?
            """,
            (installment_id,),
        ).fetchone()
        if row is None:
            return
        applied = connection.execute(
            """
            SELECT COALESCE(SUM(amount_cents), 0)
            FROM installment_payment_application
            WHERE installment_id = ? AND application_status = 'ACTIVE'
            """,
            (installment_id,),
        ).fetchone()[0]
        total = int(row["principal_cents"]) + int(row["interest_cents"])
        status = "PAID" if int(applied) >= total else (
            "SCHEDULED" if row["status"] == "PAID" else row["status"]
        )
        connection.execute(
            "UPDATE installment SET status = ? WHERE id = ?",
            (status, installment_id),
        )

    def save_instrument_calendar(
        self,
        *,
        calendar_id: str,
        instrument_id: str,
        effective_from: str,
        closing_day: int,
        due_day: int,
        source: str = "manual",
        actor: str = "desktop",
    ) -> None:
        if not 1 <= closing_day <= 31 or not 1 <= due_day <= 31:
            raise ValueError("Los días de corte y pago deben estar entre 1 y 31.")
        effective_from = self._required_iso_date(effective_from, 'La fecha del calendario')
        with self.database.transaction() as connection:
            instrument = connection.execute(
                "SELECT id,instrument_type FROM payment_instrument WHERE id = ? AND active = 1",
                (instrument_id,),
            ).fetchone()
            if instrument is None:
                raise ValueError("La tarjeta seleccionada no existe o está inactiva.")
            if instrument['instrument_type'] not in ('CREDIT_CARD', 'CREDIT_LINE'):
                raise ValueError('Las fechas de corte y pago corresponden a crédito, no a una billetera u otro saldo.')
            current = connection.execute(
                """
                SELECT id, revision FROM instrument_calendar
                WHERE instrument_id = ? AND effective_to IS NULL
                """,
                (instrument_id,),
            ).fetchone()
            revision = int(current["revision"]) + 1 if current else 1
            if current:
                connection.execute(
                    "UPDATE instrument_calendar SET effective_to = ? WHERE id = ?",
                    (effective_from, current["id"]),
                )
            connection.execute(
                """
                INSERT INTO instrument_calendar
                    (id, instrument_id, effective_from, closing_day, due_day,
                     revision, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    calendar_id,
                    instrument_id,
                    effective_from,
                    closing_day,
                    due_day,
                    revision,
                    source,
                ),
            )
            self._insert_person_audit(
                connection,
                calendar_id,
                "INSTRUMENT_CALENDAR_SAVED",
                actor,
                {"previous_calendar_id": current["id"] if current else None},
                {
                    "instrument_id": instrument_id,
                    "effective_from": effective_from,
                    "closing_day": closing_day,
                    "due_day": due_day,
                    "revision": revision,
                },
                entity_type="instrument_calendar",
            )

    def list_card_summaries(
        self, *, include_inactive: bool = False
    ) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            """
            SELECT i.id AS instrument_id, i.alias, i.instrument_type, i.active,
                   inst.name AS institution_name,
                   c.effective_from, c.closing_day, c.due_day, c.revision,
                   COALESCE((
                       SELECT SUM(o.charged_cents)
                       FROM order_record o
                       WHERE o.instrument_id = i.id AND o.order_status = 'ACTIVE'
                   ), 0)
                   + COALESCE((
                       SELECT SUM(f.interest_cents)
                       FROM financing_plan f
                       JOIN order_record o ON o.id = f.order_id
                       WHERE f.instrument_id = i.id AND o.order_status = 'ACTIVE'
                   ), 0)
                   + COALESCE((
                       SELECT SUM(CASE
                           WHEN m.kind IN ('INTEREST', 'COMMISSION', 'ADJUSTMENT')
                               THEN m.amount_cents
                           WHEN m.kind IN ('REFUND', 'BONUS')
                               THEN -m.amount_cents
                           ELSE 0
                       END)
                       FROM institution_movement m
                       WHERE m.instrument_id = i.id
                   ), 0) AS charged_cents,
                   COALESCE((
                       SELECT SUM(p.amount_cents)
                       FROM institution_payment p
                       WHERE p.instrument_id = i.id
                         AND p.payment_status = 'ACTIVE'
                   ), 0) AS paid_cents
            FROM payment_instrument i
            JOIN institution inst ON inst.id = i.institution_id
            LEFT JOIN instrument_calendar c
                ON c.instrument_id = i.id AND c.effective_to IS NULL
            WHERE (? = 1 OR i.active = 1)
            ORDER BY lower(inst.name), lower(i.alias), i.id
            """,
            (int(include_inactive),),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            today = date.today()
            closing_day = int(item["closing_day"]) if item["closing_day"] else None
            due_day = int(item["due_day"]) if item["due_day"] else None
            item["next_cut"] = None
            item["next_due"] = None
            if closing_day and due_day:
                cut_year, cut_month = today.year, today.month
                if today.day > closing_day:
                    next_month = self._next_month(today)
                    cut_year, cut_month = next_month.year, next_month.month
                cut_day = min(closing_day, monthrange(cut_year, cut_month)[1])
                item["next_cut"] = date(cut_year, cut_month, cut_day).isoformat()
                due_year, due_month = cut_year, cut_month
                if due_day <= cut_day:
                    due_month_date = self._next_month(date(cut_year, cut_month, 1))
                    due_year, due_month = due_month_date.year, due_month_date.month
                item["next_due"] = date(
                    due_year, due_month, min(due_day, monthrange(due_year, due_month)[1])
                ).isoformat()
            installments = self.list_installments(str(item["instrument_id"]))
            current_period = (
                f"{today.year:04d}-{today.month:02d}"
                if closing_day
                else None
            )
            item["period_cents"] = sum(
                int(installment["remaining_cents"])
                for installment in installments
                if installment["period_key"] == current_period
                and not installment["requires_review"]
            )
            item["future_installments_cents"] = sum(
                int(installment["remaining_cents"])
                for installment in installments
                if current_period is not None
                and installment["period_key"] is not None
                and installment["period_key"] > current_period
                and installment["due_date"] is not None
                and installment["due_date"] > today.isoformat()
                and not installment["requires_review"]
            )
            item["pending_confirmation_cents"] = sum(
                int(installment["remaining_cents"])
                for installment in installments
                if installment["requires_review"]
            )
            item["remaining_cents"] = max(
                int(item["charged_cents"]) - int(item["paid_cents"]), 0
            )
            item["credit_cents"] = max(
                int(item["paid_cents"]) - int(item["charged_cents"]), 0
            )
            item['wallet_balance_cents'] = 0
            item['cash_balance_cents'] = 0
            if item['instrument_type'] not in ('CREDIT_CARD', 'CREDIT_LINE'):
                balance = int(item['paid_cents']) - int(item['charged_cents'])
                if item['instrument_type'] == 'WALLET_BALANCE':
                    item['wallet_balance_cents'] = balance
                else:
                    item['cash_balance_cents'] = balance
                item['remaining_cents'] = 0
                item['credit_cents'] = 0
            item["paid_to_installments_cents"] = sum(
                int(row["amount_cents"])
                for installment in installments
                for row in self.list_installment_payment_applications(
                    str(installment["id"])
                )
            )
            item["unassigned_payment_cents"] = max(
                int(item["paid_cents"]) - int(item["paid_to_installments_cents"]), 0
            )
            item["paid_installments_cents"] = sum(
                int(installment["principal_cents"]) + int(installment["interest_cents"])
                for installment in installments if installment["status"] == "PAID"
            )
            item["exigible_cents"] = sum(
                int(installment["remaining_cents"])
                for installment in installments
                if not installment["requires_review"]
                and installment["due_date"] is not None
                and installment["due_date"] <= today.isoformat()
            )
            result.append(item)
        return result

    def list_card_purchases(self, instrument_id: str) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            """
            SELECT id, ordered_at, merchant, charged_cents, discount_cents,
                   order_status
            FROM order_record
            WHERE instrument_id = ?
            ORDER BY ordered_at DESC, id DESC
            """,
            (instrument_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_institution_payments(self, instrument_id: str | None = None) -> list[dict[str, object]]:
        query = """
            SELECT p.id, p.instrument_id, i.alias, p.paid_at,
                   p.amount_cents, p.reference, p.payment_status,
                   p.cancelled_at, p.cancellation_reason
            FROM institution_payment p
            JOIN payment_instrument i ON i.id = p.instrument_id
        """
        parameters: tuple[object, ...] = ()
        if instrument_id is not None:
            query += " WHERE p.instrument_id = ?"
            parameters = (instrument_id,)
        rows = self.database.connection.execute(
            query + " ORDER BY p.paid_at DESC, p.id DESC", parameters
        ).fetchall()
        return [dict(row) for row in rows]

    def add_user_payment(
        self,
        payment_id: str,
        user_id: str,
        received_at: str,
        amount_cents: int,
        reference: str | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO user_payment(id, user_id, received_at, amount_cents, reference)
                VALUES (?, ?, ?, ?, ?)
                """,
                (payment_id, user_id, received_at, amount_cents, reference),
            )

    def add_receivable(
        self,
        receivable_id: str,
        user_id: str,
        purchase_id: str,
        sale_cents: int,
        attributable_cost_cents: int,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO receivable
                    (id, user_id, purchase_id, sale_cents, attributable_cost_cents)
                VALUES (?, ?, ?, ?, ?)
                """,
                (receivable_id, user_id, purchase_id, sale_cents, attributable_cost_cents),
            )

    def apply_receipt(
        self,
        payment_id: str,
        receivable_id: str,
        amount_cents: int,
    ) -> None:
        if amount_cents <= 0:
            raise ValueError("El importe aplicado debe ser mayor que cero.")
        with self.database.transaction() as connection:
            payment = connection.execute(
                "SELECT user_id, amount_cents, payment_status, payment_kind FROM user_payment WHERE id = ?",
                (payment_id,),
            ).fetchone()
            if payment is None:
                raise ValueError("Cobro o cuenta por cobrar inexistente")
            if payment["payment_status"] != "ACTIVE":
                raise ValueError("No se puede usar un abono anulado.")
            receivable = self._ensure_participation(connection, receivable_id, "desktop")
            existing_kinds = {
                item["payment_kind"] for item in self.list_receipt_history()
                if item["id"] == payment_id and item["receivable_id"] is not None
            }
            if payment["payment_kind"]:
                existing_kinds.add(payment["payment_kind"])
            if existing_kinds and existing_kinds != {receivable["participant_role"]}:
                raise ValueError("Un abono no puede mezclar Mi parte con cobros familiares o de origen sin clasificar.")
            self._require_active_receivable(connection, receivable_id)
            if payment["user_id"] != receivable["user_id"]:
                raise ValueError("El cobro y la cuenta pertenecen a usuarios distintos")
            used = connection.execute(
                "SELECT COALESCE(SUM(amount_cents), 0) FROM receipt_application "
                "WHERE payment_id = ? AND application_status = 'ACTIVE'",
                (payment_id,),
            ).fetchone()[0]
            if used + amount_cents > payment["amount_cents"]:
                raise ValueError("Las aplicaciones exceden el cobro")
            applied_to_receivable = connection.execute(
                "SELECT COALESCE(SUM(amount_cents), 0) FROM receipt_application "
                "WHERE receivable_id = ? AND application_status = 'ACTIVE'",
                (receivable_id,),
            ).fetchone()[0]
            if applied_to_receivable + amount_cents > receivable["sale_cents"]:
                raise ValueError("La aplicacion excede la cuenta por cobrar")
            connection.execute(
                """
                INSERT INTO receipt_application(payment_id, receivable_id, amount_cents)
                VALUES (?, ?, ?)
                """,
                (payment_id, receivable_id, amount_cents),
            )
            connection.execute("UPDATE user_payment SET payment_kind = ? WHERE id = ?",
                               (receivable["participant_role"], payment_id))
            self._insert_person_audit(
                connection, payment_id, "RECEIPT_APPLIED", "desktop", None,
                {"receivable_id": receivable_id, "amount_cents": amount_cents,
                 "payment_kind": receivable["participant_role"]}, entity_type="receipt",
            )

    def list_collection_items(self) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            """
            SELECT r.id AS receivable_id, r.user_id, p.name AS user_name,
                   r.participant_role, r.order_id, r.purchase_id,
                   COALESCE(r.order_id, r.purchase_id) AS source_id,
                   COALESCE(o.merchant, pu.merchant) AS source_name,
                   CASE WHEN o.id IS NOT NULL THEN 'Pedido'
                        WHEN pu.id IS NOT NULL THEN 'Compra histórica'
                        ELSE 'Origen por verificar' END AS source_kind,
                   COALESCE(o.ordered_at, pu.purchased_at) AS source_date,
                   r.sale_cents,
                   COALESCE((SELECT SUM(a.delta_cents) FROM product_refund_adjustment a
                       JOIN imported_product_refund f ON f.id = a.refund_id
                       WHERE f.order_id = r.order_id AND a.user_id = r.user_id
                         AND f.status = 'ACCREDITED'), 0)
                   + COALESCE((SELECT SUM(a.delta_cents) FROM product_repurchase_adjustment a
                       WHERE a.order_id = r.order_id AND a.user_id = r.user_id), 0) AS adjustment_cents,
                   COALESCE(SUM(ra.amount_cents), 0) AS paid_cents
            FROM receivable r
            JOIN person p ON p.id = r.user_id
            LEFT JOIN order_record o ON o.id = r.order_id
            LEFT JOIN purchase pu ON pu.id = r.purchase_id
            LEFT JOIN receipt_application ra
                ON ra.receivable_id = r.id AND ra.application_status = 'ACTIVE'
            WHERE r.order_id IS NULL OR o.order_status = 'ACTIVE'
            GROUP BY r.id, r.user_id, p.name, r.order_id, r.purchase_id,
                     o.merchant, pu.merchant, o.ordered_at, pu.purchased_at, r.sale_cents
            ORDER BY p.name, source_name, source_id
            """
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            canonical = (
                f"order:{item['order_id']}:{item['user_id']}" if item["order_id"] is not None
                else f"{item['purchase_id']}:{item['user_id']}"
            )
            item["participant_role"] = item["participant_role"] or (
                "FAMILY" if item["source_kind"] != "Origen por verificar"
                and item["receivable_id"] == canonical else "UNKNOWN"
            )
            item["virtual"] = False
            item['original_sale_cents'] = int(item['sale_cents'])
            item['sale_cents'] = int(item['sale_cents']) + int(item['adjustment_cents'])
            item["remaining_cents"] = int(item["sale_cents"]) - int(item["paid_cents"])
            item["status"] = (
                "Pagado"
                if item["remaining_cents"] == 0
                else "Pago parcial"
                if item["paid_cents"]
                else "Pendiente"
            )
            result.append(item)
        result.extend(self._historical_personal_participations(result))
        result.sort(key=lambda item: (str(item["user_name"]).casefold(),
                                     str(item["source_name"] or ""), str(item["source_id"])))
        return result

    def _historical_personal_participations(self, existing: list[dict[str, object]]) -> list[dict[str, object]]:
        """Proyección de repartos conservados; consultar no crea cuentas ni abonos."""
        allocations = self.database.connection.execute(
            """
            SELECT a.order_id AS source_id, a.user_id, p.name AS user_name,
                   a.amount_cents, o.owner_cents, o.total_to_recover_cents AS total_cents,
                   o.merchant AS source_name, o.ordered_at AS source_date, 'Pedido' AS source_kind
            FROM order_allocation a JOIN order_record o ON o.id = a.order_id
            JOIN person p ON p.id = a.user_id WHERE o.order_status = 'ACTIVE'
            UNION ALL
            SELECT pu.id, a.user_id, p.name, SUM(a.share_cents), pu.owner_cents,
                   pu.total_cents, pu.merchant, pu.purchased_at, 'Compra histórica'
            FROM purchase_allocation a JOIN purchase_product pr ON pr.id = a.product_id
            JOIN purchase pu ON pu.id = pr.purchase_id JOIN person p ON p.id = a.user_id
            GROUP BY pu.id, a.user_id
            """
        ).fetchall()
        groups: dict[tuple[str, str], list[dict[str, object]]] = {}
        for row in allocations:
            item = dict(row)
            groups.setdefault((str(item["source_kind"]), str(item["source_id"])), []).append(item)
        result = []
        for (kind, source_id), shares in groups.items():
            recorded = {str(i["user_id"]): i for i in existing
                        if i["source_id"] == source_id and i["source_kind"] == kind}
            missing = [a for a in shares if a["amount_cents"] > 0 and a["user_id"] not in recorded]
            tracked_personal = sum(int(a["amount_cents"]) for a in shares
                                   if a["user_id"] in recorded
                                   and recorded[a["user_id"]]["participant_role"] == "PERSONAL")
            if (len(missing) > 1
                    or sum(int(a["amount_cents"]) for a in shares) != int(shares[0]["total_cents"])
                    or sum(int(a["amount_cents"]) for a in missing) + tracked_personal != int(shares[0]["owner_cents"])):
                continue
            for share in missing:
                user_id = str(share["user_id"])
                receivable_id = f"order:{source_id}:{user_id}" if kind == "Pedido" else f"{source_id}:{user_id}"
                conflict = self.database.connection.execute(
                    "SELECT 1 FROM receivable WHERE id = ? OR "
                    "(user_id = ? AND (order_id = ? OR purchase_id = ?))",
                    (receivable_id, user_id, source_id, source_id),
                ).fetchone()
                if conflict is not None:
                    continue
                amount = int(share["amount_cents"])
                result.append({**share, "receivable_id": receivable_id, "sale_cents": amount,
                               "paid_cents": 0, "remaining_cents": amount, "status": "Pendiente",
                               "participant_role": "PERSONAL", "virtual": True,
                               "order_id": source_id if kind == "Pedido" else None,
                               "purchase_id": source_id})
        return result

    def _ensure_participation(self, connection, receivable_id: str, actor: str) -> dict[str, object]:
        item = next((i for i in self.list_collection_items() if i["receivable_id"] == receivable_id), None)
        if item is None:
            raise ValueError("La participación no existe o pertenece a un pedido anulado.")
        if item["virtual"]:
            connection.execute(
                """
                INSERT INTO receivable(id, user_id, purchase_id, order_id, source_type,
                                       sale_cents, attributable_cost_cents, participant_role)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'PERSONAL')
                """,
                (receivable_id, item["user_id"], item["purchase_id"], item["order_id"],
                 "ORDER" if item["order_id"] is not None else "PURCHASE", item["sale_cents"], item["sale_cents"]),
            )
            self._insert_person_audit(connection, receivable_id, "PARTICIPATION_TRACKING_STARTED", actor,
                                      None, {"source_id": item["source_id"], "user_id": item["user_id"],
                                             "amount_cents": item["sale_cents"], "participant_role": "PERSONAL"},
                                      entity_type="participation")
        return item

    def record_receipt(
        self,
        *,
        payment_id: str,
        receivable_id: str,
        amount_cents: int,
        received_at: str,
        reference: str | None = None,
        actor: str = "desktop",
    ) -> None:
        if amount_cents <= 0:
            raise ValueError("El abono debe ser mayor que cero.")
        parsed_received_at = self._parse_iso_date(received_at, "La fecha del abono")
        if parsed_received_at is None:
            raise ValueError("La fecha del abono es obligatoria.")
        with self.database.transaction() as connection:
            receivable = self._ensure_participation(connection, receivable_id, actor)
            self._require_active_receivable(connection, receivable_id)
            paid = connection.execute(
                "SELECT COALESCE(SUM(amount_cents), 0) "
                "FROM receipt_application "
                "WHERE receivable_id = ? AND application_status = 'ACTIVE'",
                (receivable_id,),
            ).fetchone()[0]
            if int(paid) + amount_cents > int(receivable["sale_cents"]):
                raise ValueError("El abono excede el saldo pendiente.")
            connection.execute(
                """
                INSERT INTO user_payment(id, user_id, received_at, amount_cents, reference, payment_kind)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payment_id, receivable["user_id"], parsed_received_at.isoformat(),
                    amount_cents, reference, receivable["participant_role"],
                ),
            )
            connection.execute(
                """
                INSERT INTO receipt_application(payment_id, receivable_id, amount_cents)
                VALUES (?, ?, ?)
                """,
                (payment_id, receivable_id, amount_cents),
            )
            self._insert_person_audit(
                connection,
                payment_id,
                "RECEIPT_RECORDED",
                actor,
                None,
                {
                    "receivable_id": receivable_id,
                    "user_id": receivable["user_id"],
                    "amount_cents": amount_cents,
                    "payment_kind": receivable["participant_role"],
                },
                entity_type="receipt",
            )

    def update_user_payment(
        self,
        payment_id: str,
        *,
        received_at: str,
        amount_cents: int,
        reference: str | None = None,
        actor: str = "desktop",
    ) -> None:
        if amount_cents <= 0:
            raise ValueError("El abono debe ser mayor que cero.")
        parsed_received_at = self._parse_iso_date(received_at, "La fecha del abono")
        if parsed_received_at is None:
            raise ValueError("La fecha del abono es obligatoria.")
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM user_payment WHERE id = ?", (payment_id,)
            ).fetchone()
            if row is None or row["payment_status"] == "CANCELLED":
                raise ValueError("El abono seleccionado no existe o está anulado.")
            applications = connection.execute(
                """
                SELECT receivable_id, amount_cents
                FROM receipt_application
                WHERE payment_id = ? AND application_status = 'ACTIVE'
                """,
                (payment_id,),
            ).fetchall()
            application_change = None
            if len(applications) == 1 and int(row["amount_cents"]) == int(applications[0]["amount_cents"]):
                application = applications[0]
                self._require_active_receivable(connection, application["receivable_id"])
                account = next(i for i in self.list_collection_items()
                               if i['receivable_id'] == application['receivable_id'])
                others = connection.execute(
                    "SELECT COALESCE(SUM(amount_cents), 0) FROM receipt_application "
                    "WHERE receivable_id = ? AND payment_id != ? AND application_status = 'ACTIVE'",
                    (application["receivable_id"], payment_id),
                ).fetchone()[0]
                if amount_cents + int(others) > int(account["sale_cents"]):
                    raise ValueError("El abono excede la participación pendiente.")
                connection.execute("UPDATE receipt_application SET amount_cents = ? "
                                   "WHERE payment_id = ? AND receivable_id = ? AND application_status = 'ACTIVE'",
                                   (amount_cents, payment_id, application["receivable_id"]))
                application_change = {"receivable_id": application["receivable_id"],
                                      "old_amount_cents": application["amount_cents"], "new_amount_cents": amount_cents}
            elif amount_cents < sum(int(a["amount_cents"]) for a in applications):
                raise ValueError(
                    "No puedes reducir el abono por debajo de lo ya aplicado."
                )
            connection.execute(
                """
                UPDATE user_payment
                SET received_at = ?, amount_cents = ?, reference = ?
                WHERE id = ?
                """,
                (parsed_received_at.isoformat(), amount_cents, reference, payment_id),
            )
            self._insert_person_audit(
                connection, payment_id, "RECEIPT_UPDATED", actor,
                {"received_at": row["received_at"], "amount_cents": row["amount_cents"],
                 "reference": row["reference"], "payment_kind": row["payment_kind"]},
                {"received_at": received_at, "amount_cents": amount_cents,
                 "reference": reference, "payment_kind": row["payment_kind"],
                 "application_change": application_change},
                entity_type="receipt",
            )

    def cancel_user_payment(
        self,
        payment_id: str,
        *,
        reason: str,
        actor: str = "desktop",
    ) -> None:
        reason = reason.strip()
        if not reason:
            raise ValueError("Indica el motivo de la anulación del abono.")
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM user_payment WHERE id = ?", (payment_id,)
            ).fetchone()
            if row is None:
                raise ValueError("El abono seleccionado no existe.")
            if row["payment_status"] == "CANCELLED":
                raise ValueError("El abono ya está anulado.")
            now = datetime.now(timezone.utc).isoformat()
            applications = connection.execute(
                """
                SELECT receivable_id FROM receipt_application
                WHERE payment_id = ? AND application_status = 'ACTIVE'
                """,
                (payment_id,),
            ).fetchall()
            connection.execute(
                """
                UPDATE user_payment
                SET payment_status = 'CANCELLED', cancelled_at = ?,
                    cancelled_by = ?, cancellation_reason = ?
                WHERE id = ?
                """,
                (now, actor, reason, payment_id),
            )
            for application in applications:
                connection.execute(
                    """
                    UPDATE receipt_application
                    SET application_status = 'REVERSED', reversed_at = ?,
                        reversed_by = ?, reversal_reason = ?
                    WHERE payment_id = ? AND receivable_id = ?
                      AND application_status = 'ACTIVE'
                    """,
                    (now, actor, reason, payment_id, application["receivable_id"]),
                )
            self._insert_person_audit(
                connection, payment_id, "RECEIPT_CANCELLED", actor,
                {"payment_status": "ACTIVE", "applications_reversed": len(applications)},
                {"payment_status": "CANCELLED", "reason": reason, "cancelled_at": now},
                entity_type="receipt",
            )

    def list_receipt_history(self) -> list[dict[str, object]]:
        roles = {i["receivable_id"]: i["participant_role"] for i in self.list_collection_items()}
        rows = self.database.connection.execute(
            """
            SELECT up.id, up.received_at, up.amount_cents, up.reference,
                   up.payment_status, up.cancelled_at, up.cancellation_reason, up.payment_kind,
                   p.name AS user_name, p.id AS user_id, ra.receivable_id,
                   r.participant_role, r.order_id, r.purchase_id,
                   COALESCE(o.merchant, pu.merchant, 'Sin pedido asignado') AS source_name
            FROM user_payment up
            JOIN person p ON p.id = up.user_id
            LEFT JOIN receipt_application ra
                ON ra.payment_id = up.id
            LEFT JOIN receivable r ON r.id = ra.receivable_id
            LEFT JOIN order_record o ON o.id = r.order_id
            LEFT JOIN purchase pu ON pu.id = r.purchase_id
            ORDER BY up.received_at DESC, up.id DESC
            """
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            historical_family = (
                item["receivable_id"] == f"order:{item['order_id']}:{item['user_id']}" if item["order_id"] is not None
                else item["receivable_id"] == f"{item['purchase_id']}:{item['user_id']}" and item["purchase_id"] is not None
            )
            item["payment_kind"] = item["payment_kind"] or roles.get(item["receivable_id"]) or item["participant_role"] or (
                "FAMILY" if historical_family else "UNKNOWN"
            )
            result.append(item)
        return result

    @staticmethod
    def _require_active_receivable(connection, receivable_id: str) -> None:
        row = connection.execute(
            """
            SELECT r.order_id, o.order_status
            FROM receivable r LEFT JOIN order_record o ON o.id = r.order_id
            WHERE r.id = ?
            """,
            (receivable_id,),
        ).fetchone()
        if row is not None and row["order_id"] is not None and row["order_status"] != "ACTIVE":
            raise ValueError("La cuenta pertenece a un pedido anulado o inexistente.")

    def order_benefit_summary(self, order_id: str, *, participations=None) -> dict[str, object]:
        """Read-only comparison of an original purchase and its linked replacements.

        Receipt applications settle participations; they do not change this
        comparison or turn a discount into cash income.
        """
        connection = self.database.connection
        parent = connection.execute(
            """SELECT r.order_id FROM product_refund_repurchase l
               JOIN imported_product_refund r ON r.id = l.refund_id
               WHERE l.order_id = ?""", (order_id,),
        ).fetchone()
        root_id = parent['order_id'] if parent else order_id
        original = self.get_order(root_id)
        if original is None:
            raise ValueError("Pedido inexistente.")
        orders = {root_id: original}
        for refund in original['product_refunds']:
            if refund.get('repurchase'):
                linked_id = refund['repurchase']['order_id']
                orders[linked_id] = self.get_order(linked_id)
        active = {key: item for key, item in orders.items() if item['order_status'] == 'ACTIVE'}
        refunds = [refund for item in active.values() for refund in item['product_refunds']]
        credited = sum(int(r['amount_cents']) for r in refunds if r['status'] == 'ACCREDITED')
        cost = sum(int(item['charged_cents']) for item in active.values()) - credited
        participations = [item for item in (self.list_collection_items() if participations is None else participations) if item['order_id'] in active]
        assigned = sum(int(item['sale_cents']) for item in participations)
        family = sum(int(item['sale_cents']) for item in participations if item['participant_role'] == 'FAMILY')
        return {
            'original_order_id': root_id,
            'discount_benefit_cents': sum(int(item['discount_cents']) for item in active.values()),
            'effective_purchase_cost_cents': cost,
            'assigned_cents': assigned,
            'expected_result_cents': family - cost,
            'unclassified_cents': sum(int(item['sale_cents']) for item in participations if item['participant_role'] == 'UNKNOWN'),
            'family_received_cents': sum(int(item['paid_cents']) for item in participations if item['participant_role'] == 'FAMILY'),
            'participations': participations,
        }

    def record_bank_balance(self, instrument_id, amount_cents, consulted_at, *, actor='desktop'):
        """A consultation is evidence, never an opening balance or a movement."""
        if type(amount_cents) is not int or amount_cents < 0:
            raise ValueError('El saldo adeudado total debe ser un importe no negativo en centavos.')
        consulted_at = date.fromisoformat(consulted_at).isoformat()
        with self.database.transaction() as connection:
            instrument = connection.execute('SELECT instrument_type FROM payment_instrument WHERE id=?', (instrument_id,)).fetchone()
            if instrument is None or instrument['instrument_type'] not in ('CREDIT_CARD', 'CREDIT_LINE'):
                raise ValueError('Selecciona una tarjeta o línea de crédito; una billetera no es deuda bancaria.')
            self._insert_person_audit(connection, instrument_id, 'BANK_BALANCE_QUERIED', actor, None,
                dict(amount_cents=amount_cents, consulted_at=consulted_at, currency='MXN'), entity_type='instrument')

    def list_bank_comparisons(self):
        queries = {}
        for row in self.database.connection.execute(
                "SELECT entity_id,new_value FROM audit_event WHERE entity_type='instrument' AND action='BANK_BALANCE_QUERIED' ORDER BY rowid"):
            value = json.loads(row['new_value'])
            value['consulted_at'] = date.fromisoformat(value['consulted_at']).isoformat()
            previous = queries.get(row['entity_id'])
            if previous is None or value['consulted_at'] >= previous['consulted_at']:
                queries[row['entity_id']] = value
        result = []
        for card in self.list_card_summaries(include_inactive=True):
            if card['instrument_type'] not in ('CREDIT_CARD', 'CREDIT_LINE'):
                continue
            query = queries.get(card['instrument_id'])
            result.append(dict(instrument_id=card['instrument_id'], alias=card['alias'],
                institution_name=card['institution_name'], calculated_cents=int(card['remaining_cents']),
                reported_cents=query['amount_cents'] if query else None,
                consulted_at=query['consulted_at'] if query else None,
                difference_cents=query['amount_cents'] - int(card['remaining_cents']) if query else None))
        return result

    def dashboard_summary(self) -> dict[str, object]:
        """Resumen de operaciones registradas; no sustituye un estado bancario."""
        cards = self.list_card_summaries(include_inactive=True)
        participations = self.list_collection_items()
        discount = int(self.database.connection.execute(
            "SELECT COALESCE(SUM(discount_cents),0) FROM order_record WHERE order_status='ACTIVE'"
        ).fetchone()[0])
        personal_pending = sum(int(i['remaining_cents']) for i in participations if i['participant_role'] == 'PERSONAL')
        roots = self.database.connection.execute("""SELECT id FROM order_record WHERE order_status='ACTIVE'
            AND id NOT IN (SELECT order_id FROM product_refund_repurchase)""").fetchall()
        expected = sum(int(self.order_benefit_summary(row['id'], participations=participations)['expected_result_cents']) for row in roots)
        family_received = int(self.database.connection.execute("""SELECT COALESCE(SUM(amount_cents),0)
            FROM user_payment WHERE payment_status='ACTIVE' AND payment_kind='FAMILY'""").fetchone()[0])
        payment_roles: dict[str, set[str]] = {}
        for receipt in self.list_receipt_history():
            payment_roles.setdefault(str(receipt["id"]), set()).add(str(receipt["payment_kind"]))
        recent = self.database.connection.execute(
            """
            SELECT * FROM (
                SELECT id, ordered_at AS occurred_at, 'Pedido' AS kind,
                       merchant AS description, charged_cents AS amount_cents,
                       order_status AS status FROM order_record
                UNION ALL
                SELECT up.id, up.received_at, 'Abono', p.name,
                       up.amount_cents, up.payment_status
                FROM user_payment up JOIN person p ON p.id = up.user_id
                UNION ALL
                SELECT ip.id, ip.paid_at, 'Pago a tarjeta', i.alias,
                       ip.amount_cents, ip.payment_status
                FROM institution_payment ip JOIN payment_instrument i ON i.id = ip.instrument_id
                UNION ALL
                SELECT e.id, e.received_at, 'Extra', e.description, e.amount_cents, 'ACTIVE'
                FROM cash_extra e
                UNION ALL
                SELECT f.id, f.incurred_at, 'Comisión de depósito', f.description,
                       f.amount_cents, 'ACTIVE' FROM deposit_fee f
            ) ORDER BY occurred_at DESC, kind, id LIMIT 10
            """
        ).fetchall()
        movements = [dict(row) for row in recent]
        for movement in movements:
            if movement["kind"] == "Abono":
                roles = payment_roles.get(str(movement["id"]), set())
                movement["kind"] = ("Abono personal" if roles == {"PERSONAL"} else
                                    "Abono familiar" if roles == {"FAMILY"} else "Abono histórico sin clasificar")
        return {
            'discount_benefit_cents': discount,
            'personal_pending_less_discounts_cents': personal_pending - discount,
            'personal_expected_result_cents': expected,
            'family_received_cents': family_received,
            'bank_comparisons': self.list_bank_comparisons(),
            "receivables_cents": sum(int(i["remaining_cents"]) for i in participations if i["participant_role"] == "FAMILY"),
            "personal_pending_cents": sum(int(i["remaining_cents"]) for i in participations if i["participant_role"] == "PERSONAL"),
            "unclassified_pending_cents": sum(int(i["remaining_cents"]) for i in participations if i["participant_role"] == "UNKNOWN"),
            "institutional_balance_cents": sum(int(item["remaining_cents"]) for item in cards),
            "credit_cents": sum(int(item["credit_cents"]) for item in cards),
            "recent_movements": movements,
        }

    def record_extra(
        self, *, extra_id: str, user_id: str, received_at: str,
        amount_cents: int, description: str, actor: str = "desktop"
    ) -> None:
        if amount_cents <= 0:
            raise ValueError("El extra debe ser mayor que cero.")
        if not description.strip():
            raise ValueError("El motivo del extra es obligatorio.")
        received_at = self._required_iso_date(received_at, 'La fecha del extra')
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO cash_extra(id, user_id, received_at, amount_cents, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                (extra_id, user_id, received_at, amount_cents, description.strip()),
            )
            self._insert_person_audit(
                connection, extra_id, "EXTRA_RECORDED", actor, None,
                {"user_id": user_id, "amount_cents": amount_cents},
                entity_type="extra",
            )

    def record_deposit_fee(
        self, *, fee_id: str, incurred_at: str, amount_cents: int,
        description: str, actor: str = "desktop"
    ) -> None:
        if amount_cents <= 0:
            raise ValueError("La comisión debe ser mayor que cero.")
        if not description.strip():
            raise ValueError("La descripción de la comisión es obligatoria.")
        incurred_at = self._required_iso_date(incurred_at, 'La fecha de la comisión')
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO deposit_fee(id, incurred_at, amount_cents, description)
                VALUES (?, ?, ?, ?)
                """,
                (fee_id, incurred_at, amount_cents, description.strip()),
            )
            self._insert_person_audit(
                connection, fee_id, "DEPOSIT_FEE_RECORDED", actor, None,
                {"amount_cents": amount_cents, "description": description},
                entity_type="deposit_fee",
            )

    def add_audit_event(
        self,
        event_id: str,
        entity_type: str,
        entity_id: str,
        action: str,
        occurred_at: str,
        actor: str,
        reason: str,
        old_value: object | None = None,
        new_value: object | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO audit_event
                    (id, entity_type, entity_id, action, occurred_at, actor, reason,
                     old_value, new_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    entity_type,
                    entity_id,
                    action,
                    occurred_at,
                    actor,
                    reason,
                    json.dumps(old_value, sort_keys=True) if old_value is not None else None,
                    json.dumps(new_value, sort_keys=True) if new_value is not None else None,
                ),
            )

    def get_person(self, person_id: str) -> dict[str, object] | None:
        row = self.database.connection.execute(
            "SELECT id, name, is_owner, active FROM person WHERE id = ?",
            (person_id,),
        ).fetchone()
        return dict(row) if row else None

    def count(self, table: str) -> int:
        allowed = {
            "person",
            "institution",
            "payment_instrument",
            "institution_movement",
            "user_payment",
            "receivable",
            "receipt_application",
            "audit_event",
            "purchase",
            "purchase_product",
            "purchase_allocation",
            "receivable",
            "cash_extra",
            "deposit_fee",
            "institution_payment",
            "instrument_calendar",
            "order_record",
            "order_allocation",
            "financing_plan",
            "installment",
            "installment_period_assignment",
        }
        if table not in allowed:
            raise ValueError("Tabla no permitida")
        return int(self.database.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
