"""Cash counting revisions in the existing encrypted, append-only audit store.

No bank allocations, receipt creation or schema migration. History is never summed.
"""
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

FORMAT = 'valenza-cash-review-v1'
MAX_CENTS = 999_999_999_999


def source_key(payment_id, receivable_id):
    return json.dumps([payment_id, receivable_id], separators=(',', ':'))


def receipt_sources(repo, card_id):
    rows = repo.database.connection.execute(
        """SELECT up.id AS payment_id, ra.receivable_id, ra.amount_cents,
                  up.amount_cents AS payment_cents, up.received_at,
                  up.reference, r.user_id, r.order_id, r.purchase_id,
                  COALESCE(o.instrument_id, pu.instrument_id) AS instrument_id
           FROM receipt_application ra JOIN user_payment up ON up.id=ra.payment_id
           JOIN receivable r ON r.id=ra.receivable_id
           LEFT JOIN order_record o ON o.id=r.order_id
           LEFT JOIN purchase pu ON pu.id=r.purchase_id
           WHERE up.payment_status='ACTIVE' AND ra.application_status='ACTIVE'
             AND (o.id IS NULL OR o.order_status='ACTIVE')
           ORDER BY up.received_at, up.id, ra.receivable_id"""
    ).fetchall()
    totals = {}
    for row in rows:
        totals[row['payment_id']] = totals.get(row['payment_id'], 0) + row['amount_cents']
    result = {}
    for row in rows:
        if row['instrument_id'] != card_id:
            continue
        item = dict(row)
        item['key'] = source_key(item['payment_id'], item['receivable_id'])
        item['fingerprint'] = hashlib.sha256(json.dumps(
            [item[k] for k in ('payment_id','receivable_id','amount_cents','payment_cents','received_at')]
        ).encode()).hexdigest()
        item['inconsistent'] = totals[item['payment_id']] > item['payment_cents']
        result[item['key']] = item
    return result


def latest(repo, card_id):
    row = repo.database.connection.execute(
        """SELECT rowid, new_value FROM audit_event
           WHERE entity_type='cash_review' AND entity_id=? AND action='SAVED'
           ORDER BY rowid DESC LIMIT 1""", (card_id,)
    ).fetchone()
    return (row[0], json.loads(row[1])) if row else (0, None)


def history(repo, card_id):
    return [dict(row) for row in repo.database.connection.execute(
        """SELECT rowid AS revision,occurred_at,new_value FROM audit_event
           WHERE entity_type='cash_review' AND entity_id=? AND action='SAVED'
           ORDER BY rowid DESC""", (card_id,))]


def validate_snapshot(data):
    if not isinstance(data, dict) or data.get('format') != FORMAT:
        raise ValueError('El corte no es una revisión de efectivo compatible.')
    for key in ('physical_cents', 'extra_cents'):
        value = data.get(key)
        if type(value) is not int or not 0 <= value <= MAX_CENTS:
            raise ValueError('Usa importes no negativos de hasta dos decimales.')
    if not isinstance(data.get('card_id'), str) or not data['card_id']:
        raise ValueError('La revisión necesita una tarjeta.')
    if 'review_period' in data:
        from datetime import date
        period=data['review_period']
        try:
            if not isinstance(period,str) or len(period)!=7:raise ValueError()
            date.fromisoformat(period+'-01')
        except ValueError as error:
            raise ValueError('El mes de la revisión es inválido.') from error
    if 'resumed_cut' in data:
        from valenza.gui.preparation_record import validate_record
        try:
            cut=validate_record(data['resumed_cut'])
        except (KeyError,TypeError,AttributeError) as error:
            raise ValueError('El corte retomado está incompleto.') from error
        if cut['card_id']!=data['card_id']:
            raise ValueError('El corte retomado pertenece a otra tarjeta.')
    entries = data.get('entries')
    manual=data.get('manual_counts')
    if manual is not None:
        if not isinstance(manual,list) or len(manual)>10000 or entries!=[]:
            raise ValueError('El conteo independiente no puede mezclarse con aplicaciones de abonos.')
        keys=set()
        for item in manual:
            if (not isinstance(item,dict) or not isinstance(item.get('receivable_id'),str)
                    or not item['receivable_id'] or item['receivable_id'] in keys
                    or type(item.get('amount_cents')) is not int or not 0<item['amount_cents']<=MAX_CENTS
                    or not isinstance(item.get('label'),str) or len(item['label'])>2000):
                raise ValueError('La marca del conteo independiente es inválida.')
            if item.get('selection_mode','LEGACY') not in ('LEGACY','FULL','PARTIAL'):
                raise ValueError('La selección del conteo es inválida.')
            keys.add(item['receivable_id'])
    checked = data.get('checked_products', [])
    if (not isinstance(checked, list) or len(checked) > 10000
            or any(not isinstance(key,str) or not key or len(key)>2000 for key in checked)
            or len(set(checked)) != len(checked)):
        raise ValueError('Las marcas de productos son inválidas.')
    if not isinstance(entries, list) or len(entries) > 10000:
        raise ValueError('La lista de contabilizaciones es inválida.')
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('key'), str):
            raise ValueError('Origen de contabilización inválido.')
        if entry['key'] in seen:
            raise ValueError('El mismo origen está contabilizado dos veces.')
        seen.add(entry['key'])
        if (type(entry.get('amount_cents')) is not int
                or not 0 < entry['amount_cents'] <= MAX_CENTS
                or not isinstance(entry.get('fingerprint'), str)):
            raise ValueError('Importe u origen de contabilización inválido.')
    return data


def stale_entries(data, sources):
    return [e for e in data.get('entries', []) if e['key'] not in sources
            or sources[e['key']]['fingerprint'] != e['fingerprint']
            or sources[e['key']]['inconsistent']
            or e['amount_cents'] > sources[e['key']]['amount_cents']]


def save(repo, data, expected_revision):
    validate_snapshot(data)
    c = repo.database.connection
    if c.in_transaction:
        raise ValueError('Finaliza la operación actual antes de guardar la revisión.')
    with repo.database.transaction():
        c.execute('BEGIN IMMEDIATE')
        revision, previous = latest(repo, data['card_id'])
        if revision != expected_revision:
            raise ValueError('La revisión cambió en otra ventana. Vuelve a abrirla antes de guardar.')
        if not c.execute('SELECT 1 FROM payment_instrument WHERE id=?', (data['card_id'],)).fetchone():
            raise ValueError('La tarjeta no existe en esta base.')
        if 'manual_counts' not in data and stale_entries(data, receipt_sources(repo, data['card_id'])):
            raise ValueError('Hay abonos editados, anulados o inconsistentes. Revisa sus marcas antes de guardar.')
        if previous == data:
            return revision
        c.execute(
            """INSERT INTO audit_event(id,entity_type,entity_id,action,occurred_at,actor,reason,old_value,new_value)
               VALUES (?,'cash_review',?,'SAVED',?,'desktop',?,?,?)""",
            (str(uuid4()),data['card_id'],datetime.now(timezone.utc).isoformat(),
             'Revisión de efectivo; no es un cobro ni un pago bancario',
             json.dumps(previous,sort_keys=True) if previous else None, json.dumps(data,sort_keys=True)))
        return c.execute('SELECT last_insert_rowid()').fetchone()[0]
