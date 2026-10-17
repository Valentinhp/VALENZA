"""Portable preparation snapshots, separate from accounting and bank statements."""
import json
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path


FORMAT = 'valenza-preparation-v1'
MAX_CENTS = 999_999_999_999


def validate_record(record):
    if not isinstance(record, dict) or record.get('format') != FORMAT:
        raise ValueError('El archivo no es un corte de preparación de Valenza.')
    def money(value):
        if type(value) is not int or not 0 <= value <= MAX_CENTS:
            raise ValueError('El corte contiene un importe inválido.')
    def text(value):
        if not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise ValueError('El corte contiene un nombre o identificador inválido.')
    for key in ('name', 'card_id', 'card_label'):
        text(record.get(key))
    date.fromisoformat(record['date'])
    datetime.fromisoformat(record['saved_at'])
    for key in ('target_cents', 'own_cents'):
        money(record.get(key))
    rows = record.get('rows')
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError('La lista de pedidos del corte es inválida.')
    seen = set()
    for row in rows:
        item = row['item']
        for key in ('receivable_id', 'user_id', 'user_name', 'source_name', 'source_date'):
            text(item.get(key))
        if item['receivable_id'] in seen:
            raise ValueError('El corte contiene pedidos duplicados.')
        seen.add(item['receivable_id'])
        for key in ('sale_cents', 'paid_cents'):
            money(item.get(key))
        if type(item.get('remaining_cents')) is not int:
            raise ValueError('El pendiente registrado es inválido.')
        if item.get('is_msi'):
            date.fromisoformat(item['preparation_period'] + '-01')
            for key in ('total_sale_cents', 'total_paid_cents'):
                money(item.get(key))
            if item.get('installment_id') is not None:
                text(item['installment_id'])
                text(item.get('original_receivable_id'))
                date.fromisoformat(item['installment_due'])
                number, count = item.get('installment_number'), item.get('installment_count')
                if type(number) is not int or type(count) is not int or not 1 <= number <= count <= 60:
                    raise ValueError('El número de mensualidad es inválido.')
        contributions = row.get('contributions')
        if not isinstance(contributions, list) or len(contributions) > 1000:
            raise ValueError('La lista de aportaciones es inválida.')
        for contribution in contributions:
            money(contribution.get('amount_cents'))
            if type(contribution.get('included')) is not bool:
                raise ValueError('La selección de aportaciones es inválida.')
        if item.get('is_msi') and sum(c['amount_cents'] for c in contributions if c['included']) > item['remaining_cents']:
            raise ValueError('Las aportaciones superan el pendiente MSI del mes.')
        products = item.get('products', [])
        if not isinstance(products, list) or len(products) > 1000:
            raise ValueError('El desglose de productos es inválido.')
        if products and len(products) != len(contributions):
            raise ValueError('Las selecciones no corresponden al desglose de productos.')
        product_ids = set()
        for product, contribution in zip(products, contributions):
            text(product.get('product_id'))
            text(product.get('description'))
            if product['product_id'] in product_ids:
                raise ValueError('El corte contiene productos duplicados.')
            product_ids.add(product['product_id'])
            money(product.get('amount_cents'))
            quantity = product.get('quantity')
            if quantity is not None and (type(quantity) is not int or quantity <= 0):
                raise ValueError('La cantidad de un producto es inválida.')
            if contribution['amount_cents'] > product['amount_cents']:
                raise ValueError('Un importe parcial supera la participación del producto.')
    return record


def record_total(record):
    return record['own_cents'] + sum(c['amount_cents'] for row in record['rows']
                                    for c in row['contributions'] if c['included'])


def save_record(path, record):
    """Atomic file replacement; a failed save leaves the previous snapshot intact."""
    record = dict(record, saved_at=datetime.now(timezone.utc).isoformat())
    validate_record(record)
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.preparation-', suffix='.tmp', delete=False) as stream:
            temporary = stream.name
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return record


def load_record(path):
    try:
        if Path(path).stat().st_size > 10_000_000:
            raise ValueError('El archivo de preparación es demasiado grande.')
        with open(path, encoding='utf-8') as stream:
            return validate_record(json.load(stream))
    except (KeyError, TypeError, AttributeError, RecursionError) as error:
        raise ValueError('El archivo de preparación está incompleto o dañado.') from error
