"""Importación local conservadora: propuestas sin efectos financieros."""
from __future__ import annotations

from datetime import date, time
from pathlib import Path
import re
import shutil
import tempfile
from decimal import Decimal

from .local_extractors import fingerprint_file, read_pdf_text, run_tesseract
from .money import parse_amount_cents


def money(value: str) -> int:
    value = value.strip().removesuffix('MXN').strip()
    if not re.fullmatch(r'\$?\s*(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?', value):
        raise ValueError('Importe inválido: usa pesos y hasta dos decimales.')
    result = parse_amount_cents(value)
    if result is None:
        raise ValueError('Importe inválido.')
    return result


_SUPERSCRIPTS = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹', '0123456789')
RECEIPT_FIELD_NAMES = dict(discount='Descuento', refund='Devolución', charged='Cargo original',
                          paid='Neto pagado', total='Total', subtotal='Subtotal de productos',
                          products='Productos', date='Fecha', number='Referencia',
                          payment='Medio de pago', merchant='Comercio')


def document_money(value: str, *, adjustment: bool = False) -> int:
    """Read a whole, labelled monetary token. Never search bare IDs for prices."""
    value = value.strip().replace('\u00a0', ' ').replace('\u202f', ' ').replace('−', '-')
    value = re.sub(r'(?i)\s*MXN\s*$', '', value).strip()
    value = re.sub(r'([0-9])([⁰¹²³⁴⁵⁶⁷⁸⁹]{2})$',
                   lambda m: m[1] + '.' + m[2].translate(_SUPERSCRIPTS), value)
    negative = value.startswith('-') or value.startswith('(')
    if value.startswith('(') and value.endswith(')'):
        value = value[1:-1].strip()
    value = value.removeprefix('-').strip().removeprefix('$').strip()
    if value.startswith('-'):
        negative = True
        value = value[1:].strip()
    if negative and not adjustment:
        raise ValueError('Un precio o total no puede ser negativo.')
    # Space grouping is accepted only in complete groups of three digits.
    if re.fullmatch(r'\d{1,3}(?: \d{3})+(?:[.,]\d{1,2})?', value):
        value = value.replace(' ', '')
    if re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?', value):
        normalized = value.replace(',', '')
    elif re.fullmatch(r'(?:\d+|\d{1,3}(?:\.\d{3})+),\d{2}', value):
        normalized = value.replace('.', '').replace(',', '.')
    else:
        raise ValueError('Importe ambiguo o inválido: ' + value)
    return int(Decimal(normalized) * 100)


_LABELS = {
    'discount': r'descuentos?',
    'refund': r'devoluci[oó]n(?: parcial)?|reembolso(?: parcial)?',
    'charged': r'cargo bancario(?: original)?|cargo original|importe cobrado',
    'paid': r'total pagado(?: neto)?|neto pagado',
    'total': r'total(?!\s+pagado)',
    'subtotal': r'productos \(\d+\)|subtotal(?: de productos)?',
}


def _summary_values(lines: list[str], draft: dict) -> dict:
    """Anchor amounts to summary labels and keep conflicting evidence for review."""
    result = {}
    draft['source_amounts'] = {}
    for key, label in _LABELS.items():
        entries = []
        for index, line in enumerate(lines):
            match = re.fullmatch(r'(?:' + label + r')(?:\s*:\s*|\s+|$)(.*)', line, re.I)
            if not match:
                continue
            raw = match[1].strip()
            if not raw:
                # Some wallet receipts print the headline amount BEFORE Total pagado.
                previous_is_labelled = (index >= 2 and any(
                    re.fullmatch(r'(?:' + candidate + r')\s*:?', lines[index - 2], re.I)
                    for candidate in _LABELS.values()))
                if (key == 'paid' and index and lines[index - 1].startswith('$')
                        and not previous_is_labelled):
                    raw = lines[index - 1]
                elif index + 1 < len(lines):
                    raw = lines[index + 1]
            try:
                amount = document_money(raw, adjustment=key in ('discount', 'refund'))
            except ValueError:
                amount = None
            entries.append(dict(label=line, raw=raw, cents=amount))
        if not entries:
            continue
        draft['source_amounts'][key] = entries
        values = {entry['cents'] for entry in entries}
        if None in values or len(values) != 1:
            result[key] = None
            draft['review_fields'].append(key)
            draft['warnings'].append(f'Revisa {RECEIPT_FIELD_NAMES[key]}: ' + ' / '.join(entry['raw'] for entry in entries))
        else:
            result[key] = values.pop()
    return result


def _interpret_totals(draft: dict, amounts: dict) -> None:
    draft['provenance'] = {}
    for key in ('discount', 'refund'):
        draft[key] = amounts.get(key, 0)
        draft['provenance'][key] = 'explícito' if key in amounts else 'no indicado'
    complete = bool(draft['products']) and all(
        type(p['quantity']) is int and p['quantity'] > 0 and type(p['unit']) is int
        for p in draft['products'])
    gross = sum(p['quantity'] * p['unit'] for p in draft['products']) if complete else None
    if 'charged' in amounts:
        draft['charged'] = amounts['charged']
        draft['provenance']['charged'] = 'explícito'
    elif gross is not None and draft['discount'] is not None:
        draft['charged'] = gross - draft['discount']
        draft['provenance']['charged'] = 'calculado: productos − descuento'
    else:
        draft['charged'] = None
        draft['provenance']['charged'] = 'sin determinar'
    charged, refund = draft['charged'], draft['refund']
    candidates = [(key, amounts[key]) for key in ('paid', 'total') if key in amounts]
    net = charged - refund if charged is not None and refund is not None else None
    if candidates and all(value is not None for _, value in candidates):
        values = {value for _, value in candidates}
        if len(values) == 1:
            draft['paid'] = candidates[0][1]
            draft['provenance']['paid'] = 'explícito'
        elif refund and values == {charged, net}:
            draft['paid'] = net
            draft['provenance']['paid'] = 'calculado: cargo − devolución; totales explícitos antes y después'
        else:
            draft['paid'] = None
            draft['provenance']['paid'] = 'ambiguo'
            draft['review_fields'].append('paid')
            draft['warnings'].append('Los totales explícitos no coinciden; revisa su significado.')
        # Preserve the original amount separately when Total pagado is pre-refund.
        if refund and draft['paid'] == charged and net is not None:
            draft['paid'] = net
            draft['provenance']['paid'] = 'calculado: total original − devolución'
            draft['warnings'].append('El total del documento es anterior a la devolución; el neto se calcula por separado.')
    else:
        draft['paid'] = None
        draft['provenance']['paid'] = 'sin determinar'
    draft['declared_subtotal'] = amounts.get('subtotal')
    for key, origin in draft['provenance'].items():
        if origin.startswith('calculado'):
            draft['warnings'].append(f'{RECEIPT_FIELD_NAMES[key]}: {origin}.')


def _parse_mobile_topup(text: str) -> dict | None:
    """Recognize the explicit simple-service layout, without product heuristics."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    normalized = '\n'.join(lines)
    company = re.search(r'(?im)^Recarga de celular\n([^\n]+)$', normalized)
    if not company or not re.search(r'(?im)^Comprobante de pago$', normalized):
        return None
    total = re.search(r'(?im)^Total\s*pagado\n(\$\s*[\d,.]+)(?:\s*MXN)?$', normalized)
    if not total:
        raise ValueError('La recarga no contiene un total pagado reconocible.')
    amount = money(total[1])
    amounts = re.findall(r'(?im)^(\$\s*[\d,.]+)(?:\s*MXN)?$', normalized)
    if amount <= 0 or any(money(value) != amount for value in amounts):
        raise ValueError('Los importes de la recarga no coinciden; revisa el comprobante.')
    def field(label):
        found = re.search(r'(?im)^' + label + r'\s*:?\n([^\n]+)$', normalized)
        return found[1] if found else ''
    reference = re.search(r'(?m)^#([\w-]+)$', normalized)
    dated = field('Fecha')
    found = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{4})', dated)
    dated = date(int(found[3]), int(found[2]), int(found[1])).isoformat() if found else ''
    draft = dict(kind='MOBILE_TOPUP', service='Recarga de celular', company=company[1],
                 date=dated, time=field('Hora'), number=reference[1] if reference else field('Referencia'),
                 payment=field('Medios? de pago'), products=[dict(description='Recarga ' + company[1], quantity=1, unit=amount)],
                 discount=0, refund=0, paid=amount, charged=amount,
                 warnings=['Confirma la tarjeta o institución; la marca y terminación no identifican el banco.'])
    if draft['time']:
        time.fromisoformat(draft['time'])
    return draft


def parse_receipt(text: str, *, review: bool = False) -> dict:
    lines = [re.sub(r'[ \t]+', ' ', line.strip()).replace('\u00a0', ' ').replace('\u202f', ' ')
             for line in text.splitlines() if line.strip()]
    text = '\n'.join(lines)
    service = _parse_mobile_topup(text)
    if service is not None:
        return service
    wallet = bool(re.search(r'(?im)^Comprobante de pago$', text)
                  and re.search(r'(?im)^Compraste productos? a .+$', text)
                  and re.search(r'(?im)^Concepto$', text))
    if not wallet and ('mercado pago' not in text.casefold() or 'comprobante' not in text.casefold()):
        raise ValueError('Esta versión admite comprobantes de Mercado Pago con productos desglosados.')
    draft = dict(date='', number='', payment='', products=[], discount=0, refund=0,
                 paid=None, charged=None, warnings=[], review_fields=[])
    months = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
              'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')
    dated = re.search(r'\b(\d{1,2})[/-](\d{1,2}|' + '|'.join(months) + r')[/-](\d{4})\b', text, re.I)
    if dated:
        try:
            month = int(dated[2]) if dated[2].isdigit() else months.index(dated[2].casefold()) + 1
            draft['date'] = date(int(dated[3]), month, int(dated[1])).isoformat()
        except ValueError:
            draft['warnings'].append('Fecha inválida: ' + dated[0])
    hour = re.search(r'\b(\d{2}:\d{2}(?::\d{2})?)\b', text)
    if hour:
        try:
            time.fromisoformat(hour[1])
            draft['time'] = hour[1]
        except ValueError:
            draft['warnings'].append('Hora inválida: ' + hour[1])
    for key, label in [('number', r'n[uú]mero de comprobante|comprobante(?! de (?:pago|compra))(?:\s*(?:n[°ºo.]|#))?|referencia'),
                       ('payment', r'medios? de pago'), ('merchant', r'comercio|compraste productos? a')]:
        candidates = []
        for index, line in enumerate(lines):
            found = re.fullmatch(r'(?:' + label + r')(?:\s*:\s*|\s+|$)(.*)', line, re.I)
            if not found:
                continue
            value = found[1].strip()
            if not value and index + 1 < len(lines):
                value = lines[index + 1]
            if (not value or re.match(r'(?i)^(?:concepto|usuario|medios? de pago|total|fecha|comprobante)\b', value)
                    or key == 'number' and not re.fullmatch(r'[\w-]+', value)):
                continue
            candidates.append(value)
        if len(set(candidates)) == 1:
            draft[key] = candidates[0]
        elif candidates:
            draft['review_fields'].append(key)
            draft['warnings'].append(f'{RECEIPT_FIELD_NAMES[key]} tiene valores distintos: ' + ' / '.join(candidates))
    # Keep summaries above OR below the product block, excluding descriptions.
    concept_index = next((i for i, line in enumerate(lines) if line.casefold() == 'concepto'), None)
    concept_end = None
    if concept_index is not None:
        concept_end = next((i for i in range(concept_index + 1, len(lines))
                           if re.match(r'usuario\b|n[°º] de usuario\b|medios? de pago\b|comprobante\b', lines[i], re.I)
                           or any(re.fullmatch(r'(?:' + label + r')(?:\s*:\s*.*|\s+[$(\d-].*|\s*)', lines[i], re.I)
                                  for label in _LABELS.values())), len(lines))
    summary = (lines[:concept_index] + lines[concept_end:] if concept_index is not None
               else [line for line in lines if '|' not in line])
    amounts = _summary_values(summary, draft)
    counted = re.search(r'(?im)^Productos \((\d+)\)(?:\s|$)', text)
    if counted:
        draft['declared_count'] = int(counted[1])

    def add_product(description, quantity, raw_price, subtotal=None):
        try:
            quantity = int(quantity)
            if quantity <= 0:
                raise ValueError()
        except ValueError:
            quantity = None
        try:
            unit = document_money(raw_price)
        except ValueError:
            unit = None
        product = dict(description=description.strip(), quantity=quantity, unit=unit)
        if subtotal is not None:
            try:
                product['declared_subtotal'] = document_money(subtotal)
            except ValueError:
                draft['review_fields'].append('products')
                draft['warnings'].append('Subtotal de producto no reconocido: ' + subtotal)
        if quantity is None or unit is None or not product['description']:
            draft['review_fields'].append('products')
            draft['warnings'].append('Revisa cantidad y precio de ' + description + ': ' + raw_price)
        draft['products'].append(product)

    if concept_index is not None:
        description = []
        for line in lines[concept_index + 1:concept_end]:
            price = re.fullmatch(r'(\$\s*.+?)\s*[x×]\s*(\S+)\s+Unidad(?:es)?', line, re.I)
            if price:
                add_product(' '.join(description), price[2], price[1])
                description = []
            elif line.startswith('$'):
                # A price-looking row with unsupported quantity must not join the next item.
                add_product(' '.join(description), '', line)
                description = []
            else:
                description.append(line)
        if description:
            add_product(' '.join(description), '', '')
    else:
        for line in lines:
            cells = [cell.strip() for cell in line.split('|')]
            if len(cells) in (3, 4) and cells[1].casefold() != 'cantidad':
                add_product(cells[0], cells[1], cells[2], cells[3] if len(cells) == 4 else None)
            else:
                product = re.fullmatch(r'(.+?)\s+(\S+)\s*[x×]\s*(\$\s*.+)', line)
                if product:
                    add_product(product[1], product[2], product[3])
        if not draft['products']:
            # Labelled blocks: multiple description lines followed by explicit quantity/price.
            description = []
            index = 0
            while index < len(lines):
                line = lines[index]
                quantity = re.fullmatch(r'cantidad\s*:?\s*(.*)', line, re.I)
                if quantity:
                    raw_quantity = quantity[1]
                    if not raw_quantity and index + 1 < len(lines):
                        index += 1
                        raw_quantity = lines[index]
                    if index + 1 < len(lines):
                        unit = re.fullmatch(r'precio unitario\s*:?\s*(.*)', lines[index + 1], re.I)
                        if unit:
                            index += 1
                            raw_unit = unit[1]
                            if not raw_unit and index + 1 < len(lines):
                                index += 1
                                raw_unit = lines[index]
                            add_product(' '.join(description), raw_quantity, raw_unit)
                            description = []
                elif (re.match(r'(?i)^(?:mercado pago|comprobante|fecha|medio de pago|n[uú]mero|comercio|productos)', line)
                      or any(re.fullmatch(r'(?:' + label + r')\s*:?\s*.*', line, re.I) for label in _LABELS.values())):
                    description = []
                else:
                    description.append(line)
                index += 1
    if not draft['products']:
        draft['review_fields'].append('products')
        draft['warnings'].append('Desglose no reconocido; completa los productos en la vista previa.')
    _interpret_totals(draft, amounts)
    if not draft['date']:
        draft['review_fields'].append('date')
        draft['warnings'].append('Fecha no reconocida; revisa el documento.')
    try:
        validate(draft)
    except ValueError as error:
        draft['warnings'].append(str(error))
        if wallet and not review:
            raise
    return draft


def read_receipt(path: Path) -> dict:
    text = read_pdf_text(path)
    native_text = bool(text.strip())
    # OpenPDF dibuja centavos como un span menor junto a los pesos.
    # Solo insertar el punto cuando la tipografía y la posición lo acreditan.
    if text.strip():
        import pymupdf
        reconstructed = []
        with pymupdf.open(path) as document:
            for page in document:
                for block in page.get_text('dict')['blocks']:
                    for line in block.get('lines', []):
                        spans = line['spans']
                        parts = []
                        for index, span in enumerate(spans):
                            previous = spans[index - 1] if index else None
                            if (previous and re.fullmatch(r'(?:-\s*)?\$\s*-?\d[\d, ]*', ''.join(parts).strip())
                                and re.fullmatch(r'\d{2}', span['text'].strip())
                                and span['size'] < previous['size'] * .85
                                and abs(span['bbox'][0] - previous['bbox'][2]) < 2
                                and span['bbox'][3] < previous['bbox'][3]):
                                parts.append('.' + span['text'].strip())
                            else:
                                parts.append(span['text'])
                        reconstructed.append(''.join(parts))
        text = '\n'.join(reconstructed)
    if not text.strip():
        if not shutil.which('tesseract'):
            raise ValueError('El PDF no tiene texto utilizable. Se necesita OCR local (Tesseract).')
        import pymupdf
        with tempfile.TemporaryDirectory() as directory, pymupdf.open(path) as document:
            texts = []
            for index, page in enumerate(document):
                image = Path(directory) / f'{index}.png'
                page.get_pixmap(dpi=300).save(image)
                texts.append(run_tesseract(image))
            text = '\n'.join(texts)
    draft = parse_receipt(text, review=True)
    draft['extraction'] = 'texto nativo' if native_text else 'ocr'
    draft['fingerprint'] = fingerprint_file(path)
    return draft


def validate(draft: dict) -> int:
    date.fromisoformat(draft['date'])
    if draft.get('kind') == 'MOBILE_TOPUP':
        if draft.get('time'):
            time.fromisoformat(draft['time'])
        if (len(draft['products']) != 1 or draft['products'][0]['quantity'] != 1
                or draft['products'][0]['unit'] <= 0 or draft['discount'] != 0 or draft['refund'] != 0):
            raise ValueError('La recarga debe tener un solo concepto, sin descuentos ni devoluciones de productos.')
        if not draft.get('service', '').strip() or not draft.get('company', '').strip():
            raise ValueError('Confirma el servicio y la compañía de la recarga.')
    if not draft['products']:
        raise ValueError('Agrega al menos un producto.')
    for product in draft['products']:
        if (not product['description'].strip() or type(product['quantity']) is not int
                or product['quantity'] <= 0 or type(product['unit']) is not int or product['unit'] < 0):
            raise ValueError('Revisa descripción, cantidad y precio de cada producto.')
        if (product.get('declared_subtotal') is not None
                and product['declared_subtotal'] != product['quantity'] * product['unit']):
            raise ValueError('Subtotal de producto inconsistente: ' + product['description'])
    gross = sum(p['quantity'] * p['unit'] for p in draft['products'])
    if (draft.get('declared_count') is not None and len(draft['products']) != draft['declared_count']
            or draft.get('declared_subtotal') is not None and gross != draft['declared_subtotal']):
        raise ValueError('El desglose no coincide con el número o subtotal de productos del comprobante.')
    for key in ('discount', 'refund', 'paid', 'charged'):
        if type(draft[key]) is not int or draft[key] < 0:
            raise ValueError('Completa todos los importes sin valores negativos.')
    if gross - draft['discount'] != draft['charged'] or draft['charged'] - draft['refund'] != draft['paid']:
        raise ValueError('No cuadra: productos − descuento = cargo bancario; cargo − devolución = total pagado.')
    if draft.get('review_fields') and not draft.get('review_confirmed'):
        raise ValueError('Revisa los campos no reconocidos o ambiguos y confirma su corrección antes de guardar.')
    return gross
