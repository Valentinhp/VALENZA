"""Brand matching must never reinterpret financial records or break popup navigation."""
import hashlib
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QComboBox, QDialog, QVBoxLayout, QFileDialog
from valenza.gui.app import create_application, MainWindow
from valenza.gui.branding import resolve_brand, brand_icon, ROOT, MANIFEST, PaymentIdentity
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository

@pytest.mark.parametrize('name,key,kind', [
    ('  SPOTIFY Premium  ', 'spotify', 'service'), ('YouTube / Premium', 'youtube', 'service'),
    ('Disney+', 'disney', 'service'), ('Apple Music', 'applemusic', 'service'),
    ('Nu / Nubank', 'nubank', 'institution'), ('Nú México', 'nubank', 'institution'),
    ('Mercado Pago', 'mercadopago', 'institution'), ('BBVA Bancomer', 'bbva', 'institution'),
    ('Banco Santander', 'santander', 'institution'), ('Banorte', 'banorte', 'institution'),
    ('HSBC', 'hsbc', 'institution'), ('1234', None, 'institution'),
    ('Tarjeta Netflix', None, 'institution'), ('Servicio desconocido', None, 'service'),
])
def test_normalized_aliases(name, key, kind):
    assert resolve_brand(name, kind) == key

def test_assets_are_local_and_verified():
    create_application([])
    for key, record in MANIFEST.items():
        assert hashlib.sha256((ROOT / f'{key}.svg').read_bytes()).hexdigest() == record['sha256']
        assert not brand_icon(record['title'], 'institution' if key in ('nubank','hsbc','mercadopago') else 'service').isNull()
    assert (ROOT / 'LICENSE.md').exists()
    assert not brand_icon('Unknown').isNull()

def test_popup_keyboard_and_qt_file_dialog():
    app = create_application([])
    installed_style = app.style()
    assert create_application([]).style() is installed_style
    dialog = QDialog(); layout = QVBoxLayout(dialog)
    combo = QComboBox(); combo.addItems(['Nu', 'Mercado Pago', 'BBVA']); layout.addWidget(combo)
    dialog.show(); app.processEvents(); combo.setFocus(); combo.showPopup(); app.processEvents()
    assert '#fffcf8' in combo.view().styleSheet()
    assert combo.view().isVisible()
    QTest.keyClick(combo.view(), Qt.Key.Key_Down)
    QTest.keyClick(combo.view(), Qt.Key.Key_Return)
    app.processEvents()
    assert combo.currentText() == 'Mercado Pago'
    file_dialog = QFileDialog(dialog)
    file_dialog.show(); app.processEvents()
    assert app.testAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
    assert file_dialog.labelText(QFileDialog.DialogLabel.LookIn) == 'Carpeta'
    assert file_dialog.labelText(QFileDialog.DialogLabel.Accept) == 'Abrir'
    file_dialog.deleteLater(); dialog.close()

def test_explicit_institution_wins_over_card_alias(tmp_path):
    app = create_application([])
    db = LocalDatabase.open(tmp_path / 'brands.db', 'synthetic-brands-only'); db.migrate()
    repo = FinanceRepository(db)
    repo.add_person('owner', 'Persona sintética', is_owner=True)
    repo.add_institution('nu', 'Nu')
    repo.add_institution('mp', 'Mercado Pago')
    repo.add_instrument('card', 'nu', 'Mercado Pago 1234', 'CREDIT_CARD')
    repo.add_instrument('wallet', 'mp', 'Billetera 1234', 'WALLET_BALANCE')
    repo.save_subscription(subscription_id='s', name='Spotify Premium', amount_cents=19900,
        instrument_id='card', next_due='2026-10-20', allocations=[dict(user_id='owner', amount_cents=19900)])
    before = repo.list_all_instruments(), repo.list_subscriptions(), repo.dashboard_summary()
    window = MainWindow(database=db); window.show(); app.processEvents()
    window.subscription_table.selectRow(0); app.processEvents()
    assert not window.subscription_table.item(0, 0).icon().isNull()
    assert window.subscription_payment_identity.caption.text() == 'Tarjeta: Mercado Pago 1234 · Nu'
    badge = PaymentIdentity(); badge.set_instrument(window._brand_instrument('wallet'))
    assert badge.caption.text() == 'Billetera: Billetera 1234 · Mercado Pago'
    window._sync_catalogs()
    for combo in (window.order_institution, window.card_institution, window.admin_card_institution):
        assert all(not combo.itemIcon(i).isNull() for i in range(combo.count()))
    assert before == (repo.list_all_instruments(), repo.list_subscriptions(), repo.dashboard_summary())
    window.close(); badge.close(); app.processEvents(); db.close()
