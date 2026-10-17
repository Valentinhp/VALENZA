"""Bounded, read-only search of existing records. No amounts or stored index."""
from time import monotonic
import unicodedata

from valenza.persistence.database import DATABASE_ERRORS


def fold(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value or '').casefold())
                   if unicodedata.category(c) != 'Mn')


def search_records(repository, query, *, limit=5, budget_ms=180):
    words = fold(query[:100]).split()[:5]
    if len(''.join(words)) < 2:
        return dict(results=[], limited=False, timed_out=False)
    limit = max(1, min(int(limit), 5))
    patterns = tuple('%' + word.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%' for word in words)
    condition = ' AND '.join("search_fold(search_text) LIKE ? ESCAPE '\\'" for _ in words)
    conn = repository.database.connection
    conn.create_function('search_fold', 1, fold)
    deadline = monotonic() + max(0, budget_ms)/1000
    conn.set_progress_handler(lambda: int(monotonic() >= deadline), 1000)
    results, limited, timed_out = [], False, False
    # Only descriptive fields are read, including effective concept descriptions.
    specs = (
        ('person', 'Personas', """SELECT id, name title, '' date, '' context, '' parent_id,
            CASE WHEN active=1 THEN 'Persona' ELSE 'Persona inactiva' END state,
            name search_text FROM person"""),
        ('card', 'Tarjetas y cuentas', """SELECT p.id, p.alias title, '' date, i.name context, '' parent_id,
            CASE WHEN p.active=1 THEN 'Cuenta' ELSE 'Cuenta inactiva' END state,
            p.alias || ' ' || i.name search_text FROM payment_instrument p JOIN institution i ON i.id=p.institution_id"""),
        ('order', 'Pedidos', """WITH manual AS (
                SELECT entity_id, new_value, ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY rowid DESC) n
                FROM audit_event WHERE action='MANUAL_CONCEPTS_SAVED'),
            imported AS (
                SELECT entity_id, new_value, ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY occurred_at DESC, rowid DESC) n
                FROM audit_event WHERE action='PDF_IMPORTED')
            SELECT o.id, o.merchant title, o.ordered_at date, p.alias context, '' parent_id,
                CASE WHEN o.order_status='CANCELLED' THEN 'Anulado' ELSE 'Pedido' END state,
                o.merchant || ' ' || p.alias || ' ' || COALESCE((SELECT group_concat(json_extract(j.value,'$.description'),' ')
                    FROM json_each(CASE WHEN m.entity_id IS NOT NULL THEN m.new_value
                        ELSE COALESCE(json_extract(e.new_value,'$.products'),'[]') END) j),'') search_text
            FROM order_record o JOIN payment_instrument p ON p.id=o.instrument_id
            LEFT JOIN manual m ON m.entity_id=o.id AND m.n=1
            LEFT JOIN imported e ON e.entity_id=o.id AND e.n=1"""),
        ('purchase', 'Compras históricas', """SELECT p.id, p.merchant title, p.purchased_at date,
            i.alias context, '' parent_id, 'Abrir Cobros' state,
            p.merchant || ' ' || i.alias || ' ' || COALESCE((SELECT group_concat(description,' ')
                FROM purchase_product WHERE purchase_id=p.id),'') search_text
            FROM purchase p JOIN payment_instrument i ON i.id=p.instrument_id"""),
        ('bank_payment', 'Pagos y abonos', """SELECT b.id, p.alias title, b.paid_at date,
            COALESCE(b.reference,'Sin referencia') context, b.instrument_id parent_id,
            CASE WHEN b.payment_status='CANCELLED' THEN 'Pago al banco anulado' ELSE 'Pago al banco' END state,
            p.alias || ' ' || i.name || ' ' || COALESCE(b.reference,'') search_text
            FROM institution_payment b JOIN payment_instrument p ON p.id=b.instrument_id
            JOIN institution i ON i.id=p.institution_id"""),
        ('receipt', 'Pagos y abonos', """SELECT u.id, p.name title, u.received_at date,
            COALESCE(u.reference,'Sin referencia') context, '' parent_id,
            CASE WHEN u.payment_status='CANCELLED' THEN 'Abono anulado' ELSE 'Abono recibido' END state,
            p.name || ' ' || COALESCE(u.reference,'') search_text FROM user_payment u JOIN person p ON p.id=u.user_id"""),
    )
    try:
        for kind, category, source in specs:
            rows = conn.execute(f"SELECT id,title,date,context,parent_id,state FROM ({source}) WHERE {condition} ORDER BY date DESC, title, id LIMIT ?",
                                (*patterns, limit+1)).fetchall()
            limited |= len(rows) > limit
            results.extend(dict(row, kind=kind, category=category) for row in rows[:limit])
    except DATABASE_ERRORS:
        if monotonic() < deadline:
            raise
        timed_out = True
    finally:
        conn.set_progress_handler(None, 0)
    return dict(results=results, limited=limited, timed_out=timed_out)
