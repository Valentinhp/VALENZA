"""Importación local conservadora: propuestas sin efectos financieros."""
from __future__ import annotations

from datetime import date, time
from pathlib import Path
import re
import shutil
import tempfile

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


def parse_receipt(text: str) -> dict:
    service = _parse_mobile_topup(text)
    if service is not None:
        return service
    receipt_layout = bool(re.search(r'(?im)^Comprobante de pago\s*$', text)
                          and re.search(r'(?im)^Compraste producto a .+$', text)
                          and re.search(r'(?im)^Productos \(\d+\)\s*$', text)
                          and re.search(r'(?im)^Concepto\s*$', text)
                          and re.search(r'(?im)^Medio de Pago\s*$', text))
    if not receipt_layout and ('mercado pago' not in text.casefold() or 'comprobante' not in text.casefold()):
        raise ValueError('Esta versión admite comprobantes de Mercado Pago con productos desglosados.')
    draft = dict(date='', number='', payment='', products=[], discount=0, refund=0,
                 paid=None, charged=None, warnings=[])
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # Unir etiquetas y valores que el PDF coloca en bloques distintos.
    text = '\n'.join(lines)
    if receipt_layout:
        months = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')
        found = re.search(r'(?im)^(\d{1,2})/(' + '|'.join(months) + r')/(\d{4})\b', text)
        if found:
            draft['date'] = date(int(found[3]), months.index(found[2].casefold()) + 1, int(found[1])).isoformat()
        number = re.search(r'(?im)^Comprobante\n([\w-]+)$', text)
        payment = re.search(r'(?im)^Medio de Pago\n([^\n]+)$', text)
        draft['number'] = number[1] if number else ''
        draft['payment'] = payment[1] if payment else ''
        for key, label in [('discount', 'Descuento'), ('refund', 'Devolución parcial'), ('paid', 'Total')]:
            found = re.search(r'(?im)^' + label + r'\n\$\s*(-?\d[\d,]*(?:\.\d{1,2})?)$', text)
            if found:
                draft[key] = money(found[1].lstrip('-'))
        concept = text.split('\nConcepto\n', 1)[1].split('\nUsuario\n', 1)[0]
        description = []
        for line in concept.splitlines():
            price = re.fullmatch(r'\$\s*([\d,.]+)\s*x\s*(\d+)\s+Unidad(?:es)?', line, re.I)
            if price:
                draft['products'].append(dict(description=' '.join(description), quantity=int(price[2]), unit=money(price[1])))
                description = []
            else:
                description.append(line)
        count = int(re.search(r'(?im)^Productos \((\d+)\)$', text)[1])
        subtotal = re.search(r'(?im)^Productos \(\d+\)\n\$\s*([\d,.]+)$', text)
        gross = sum(p['quantity'] * p['unit'] for p in draft['products'])
        if description or len(draft['products']) != count or not subtotal or money(subtotal[1]) != gross:
            raise ValueError('El desglose no coincide con el número o subtotal de productos del comprobante.')
        draft['charged'] = gross - draft['discount']
        draft['warnings'].append('Cargo bancario original propuesto a partir de productos menos descuento; verifica contra tu banco.')
        if draft['refund']:
            draft['warnings'].append('Devolución parcial sin asignar: no modifica participaciones.')
        validate(draft)
        return draft
    found = re.search(r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b', text)
    if found:
        draft['date'] = date(int(found[3]), int(found[2]), int(found[1])).isoformat()
    for key, pattern in [('number', r'(?:número de comprobante|numero de comprobante|comprobante\s*(?:n[°ºo.]|#))\s*:?\s*([\w-]+)'),
                         ('payment', r'(?:medio de pago)\s*:?\s*([^\n]+)')]:
        match = re.search(pattern, text, re.I)
        if match:
            draft[key] = match[1]
    amount = r'(\$?\s*\d[\d,]*(?:\.\d{1,2})?(?:\s*MXN)?)'
    for key, label in [('discount', 'descuento'), ('refund', 'devoluci[oó]n'),
                       ('paid', 'total pagado'), ('charged', 'cargo bancario')]:
        match = re.search(r'(?im)^' + label + r'\s*:?\s*' + amount + r'\s*$', text)
        if match:
            draft[key] = money(match[1])
    # Formato explícito: descripción | cantidad | precio unitario [| subtotal].
    for line in lines:
        cells = [cell.strip() for cell in line.split('|')]
        if len(cells) in (3, 4) and cells[1].isdigit():
            quantity = int(cells[1])
            unit = money(cells[2])
            if len(cells) == 4 and money(cells[3]) != quantity * unit:
                draft['warnings'].append('Subtotal de producto inconsistente: ' + cells[0])
            draft['products'].append(dict(description=cells[0], quantity=quantity, unit=unit))
        else:
            match = re.fullmatch(r'(.+?)\s+(\d+)\s*[x×]\s*\$\s*([\d,.]+)', line)
            if match:
                draft['products'].append(dict(description=match[1], quantity=int(match[2]), unit=money(match[3])))
    if draft['charged'] is None:
        draft['charged'] = draft['paid']
        draft['warnings'].append('Cargo bancario propuesto a partir del total pagado; verifica contra tu banco.')
    if not draft['products']:
        pattern = re.compile(r'(?im)^([^\n]+)\n(?:cantidad\s*:?\s*)(\d+)\s*\n(?:precio unitario\s*:?\s*)' + amount)
        for match in pattern.finditer(text):
            draft['products'].append(dict(description=match[1].strip(), quantity=int(match[2]), unit=money(match[3])))
    if not draft['products']:
        draft['warnings'].append('Desglose no reconocido; completa los productos en la vista previa.')
    if draft['refund']:
        draft['warnings'].append('Devolución sin asignación: no modifica participaciones. Verifica el cargo original y el neto pagado.')
    return draft


def read_receipt(path: Path) -> dict:
    text = read_pdf_text(path)
    # OpenPDF dibuja centavos como un span menor junto a los pesos.
    # Solo insertar el punto cuando la tipografía y la posición lo acreditan.
    if re.search(r'(?im)^Comprobante de pago\s*$', text):
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
                            if (previous and re.fullmatch(r'\$\s*-?\d[\d,]*', previous['text'].strip())
                                and re.fullmatch(r'\d{2}', span['text'].strip())
                                and span['size'] < previous['size'] * .85
                                and abs(span['bbox'][0] - previous['bbox'][2]) < 2
                                and span['bbox'][3] < previous['bbox'][3]):
                                parts.append('.' + span['text'].strip())
                            else:
                                parts.append(span['text'])
                        reconstructed.append(''.join(parts))
        text = '\n'.join(reconstructed)
    if len(re.sub(r'\W', '', text)) < 20:
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
    draft = parse_receipt(text)
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
        if not product['description'].strip() or product['quantity'] <= 0 or product['unit'] < 0:
            raise ValueError('Revisa descripción, cantidad y precio de cada producto.')
    gross = sum(p['quantity'] * p['unit'] for p in draft['products'])
    for key in ('discount', 'refund', 'paid', 'charged'):
        if draft[key] is None or draft[key] < 0:
            raise ValueError('Completa todos los importes sin valores negativos.')
    if gross - draft['discount'] != draft['charged'] or draft['charged'] - draft['refund'] != draft['paid']:
        raise ValueError('No cuadra: productos − descuento = cargo bancario; cargo − devolución = total pagado.')
    return gross
