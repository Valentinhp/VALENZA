"""Local presentation identities. Names and financial identifiers remain untouched."""
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel

ROOT = Path(__file__).parent / 'assets' / 'brands'
MANIFEST = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))

def normalize_name(name):
    text = unicodedata.normalize('NFKD', str(name)).casefold()
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in text if not unicodedata.combining(c))).strip()

SERVICE_ALIASES = {
    'spotify': ('spotify', 'spotify premium', 'spotify familiar', 'spotify duo', 'spotify premium familiar', 'spotify individual'),
    'youtube': ('youtube', 'youtube premium', 'youtube music', 'youtube music premium', 'yt premium', 'youtube premium familiar'),
    'netflix': ('netflix', 'netflix premium', 'netflix estandar', 'netflix basico'),
    'amazonprime': ('amazon prime', 'prime amazon', 'amazonprime'),
    'primevideo': ('prime video', 'amazon prime video', 'primevideo'),
    'disney': ('disney', 'disney plus', 'disney premium'),
    'applemusic': ('apple music', 'applemusic'),
}
INSTITUTION_ALIASES = {
    'nubank': ('nu', 'nubank', 'nu mexico', 'nu bank', 'nu nubank'),
    'mercadopago': ('mercado pago', 'mercadopago'),
    'bbva': ('bbva', 'bbva mexico', 'bbva bancomer', 'bancomer'),
    'santander': ('santander', 'banco santander', 'santander mexico'),
    'banorte': ('banorte', 'banco banorte'),
    'hsbc': ('hsbc', 'hsbc mexico'),
}
FALLBACK_LABELS = {'disney': 'D+', 'bbva': 'BBVA', 'santander': 'SAN', 'banorte': 'BAN'}

def resolve_brand(name, kind='service'):
    aliases = SERVICE_ALIASES if kind == 'service' else INSTITUTION_ALIASES
    normalized = normalize_name(name)
    return next((key for key, names in aliases.items() if normalized in names), None)

@lru_cache(maxsize=96)
def brand_icon(name, kind='service'):
    """Render original paths in published color, with equal transparent padding.

    Unavailable licensed marks use neutral text badges, never fabricated logos.
    Institution callers must pass an explicit institution, never a card alias.
    """
    key = resolve_brand(name, kind)
    pixmap = QPixmap(64, 64)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if key in MANIFEST:
        svg = (ROOT / f'{key}.svg').read_bytes()
        svg = svg.replace(b'<svg ', f'<svg fill="#{MANIFEST[key]["hex"]}" '.encode(), 1)
        QSvgRenderer(svg).render(painter, QRectF(5, 5, 22, 22))
    else:
        painter.setPen(QColor('#80543c'))
        painter.setBrush(QColor('#f3e6d8'))
        painter.drawRoundedRect(QRectF(2, 2, 28, 28), 7, 7)
        if key in FALLBACK_LABELS:
            painter.setFont(QFont('Segoe UI', 6 if key == 'bbva' else 7, QFont.Weight.DemiBold))
            painter.drawText(QRectF(2, 2, 28, 28), Qt.AlignmentFlag.AlignCenter, FALLBACK_LABELS[key])
        elif kind == 'service':
            painter.drawRoundedRect(QRectF(9, 7, 14, 18), 2, 2)
            painter.drawLine(12, 12, 20, 12)
            painter.drawLine(12, 17, 20, 17)
            painter.drawLine(12, 21, 17, 21)
        else:
            painter.drawRoundedRect(QRectF(7, 10, 18, 13), 2, 2)
            painter.drawLine(7, 14, 25, 14)
    painter.end()
    return QIcon(pixmap)


class PaymentIdentity(QWidget):
    """Identify the recorded funding instrument, keeping wallet and issuer distinct."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.mark = QLabel()
        self.mark.setFixedSize(28, 28)
        self.caption = QLabel()
        self.caption.setTextFormat(Qt.TextFormat.PlainText)
        self.caption.setWordWrap(True)
        layout.addWidget(self.mark)
        layout.addWidget(self.caption, 1)
        self.hide()

    def set_instrument(self, instrument):
        self.setVisible(bool(instrument))
        if not instrument:
            return
        kind = {'CREDIT_CARD': 'Tarjeta', 'CREDIT_LINE': 'Línea de crédito',
                'WALLET_BALANCE': 'Billetera', 'OTHER': 'Medio de pago'}.get(instrument['instrument_type'], 'Instrumento')
        name = instrument['institution_name']
        text = f"{kind}: {instrument['alias']} · {name}"
        self.mark.setPixmap(brand_icon(name, 'institution').pixmap(28, 28))
        self.mark.setToolTip(name)
        self.caption.setText(text)
        self.setAccessibleName(text)
