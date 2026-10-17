from datetime import date

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QLabel, QPushButton

from valenza.gui.app import MainWindow, create_application, format_money
from valenza.gui.warm_finance import period_label
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository


@pytest.fixture
def synthetic(tmp_path):
    app = create_application([])
    font = QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    if font >= 0:
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(font)[0], 10))
    db = LocalDatabase.open(tmp_path / 'synthetic-home.db', 'synthetic-home-test')
    assert db.encrypted
    db.migrate()
    repo = FinanceRepository(db)
    for key, name in [('owner', 'Yo'), ('ana', 'Ana'), ('luis', 'Luis'), ('sofia', 'Sofía · familiar con nombre largo')]:
        repo.add_person(key, name, is_owner=key == 'owner')
    repo.add_institution('bank', 'Banco sintético')
    for key, label in [('card1', 'Tarjeta principal'), ('card2', 'Tarjeta familiar con un nombre extenso'), ('card3', 'Tarjeta de reserva')]:
        repo.add_instrument(key, 'bank', label, 'CREDIT_CARD')
    yield app, repo
    db.close()


def seed(repo):
    today = date.today()
    def period(offset):
        index = today.year * 12 + today.month - 1 + offset
        return date(index // 12, index % 12 + 1, 15).isoformat()
    repo.create_order(order_id='msi', ordered_at=today.isoformat(), merchant='Compra MSI · datos sintéticos',
        instrument_id='card1', original_cents=142398, charged_cents=142398, discount_cents=0,
        allocations=({'user_id': 'owner', 'amount_cents': 47466}, {'user_id': 'ana', 'amount_cents': 94932}),
        purchase_mode='MSI', financing_specs=tuple(period(i) for i in range(3)))
    repo.create_order(order_id='past', ordered_at=period(-1), merchant='Cuota anterior · datos sintéticos',
        instrument_id='card2', original_cents=18000, charged_cents=18000, discount_cents=0,
        allocations=({'user_id': 'owner', 'amount_cents': 0}, {'user_id': 'luis', 'amount_cents': 18000}),
        purchase_mode='MSI', financing_specs=(period(-1),))
    repo.create_order(order_id='undated', ordered_at=today.isoformat(), merchant='Calendario pendiente · datos sintéticos',
        instrument_id='card2', original_cents=8000, charged_cents=8000, discount_cents=0,
        allocations=({'user_id': 'owner', 'amount_cents': 0}, {'user_id': 'sofia', 'amount_cents': 8000}), purchase_mode='MSI', financing_specs=(None,))
    repo.create_order(order_id='cash', ordered_at=today.isoformat(), merchant='Compra compartida · datos sintéticos',
        instrument_id='card3', original_cents=25000, charged_cents=23000, discount_cents=2000,
        allocations=({'user_id': 'owner', 'amount_cents': 10000}, {'user_id': 'luis', 'amount_cents': 15000}))
    repo.record_receipt(payment_id='receipt', receivable_id='order:cash:luis', received_at=today.isoformat(), amount_cents=4000)
    for index in range(4):
        repo.record_extra(extra_id=f'extra{index}', user_id='owner', received_at=today.isoformat(), amount_cents=12000+index*1000,
                          description=f'Ingreso adicional sintético {index+1}')


@pytest.mark.parametrize('size', [(1536, 1024), (1366, 768), (900, 700), (640, 600)])
def test_representative_home_polish(synthetic, size, tmp_path):
    app, repo = synthetic
    seed(repo)
    before = repo.dashboard_summary()
    changes = repo.database.connection.total_changes
    window = MainWindow(database=repo.database, test_mode=True)
    window.resize(*size)
    window.show()
    app.processEvents()
    amount = lambda widget: widget.findChild(QLabel, 'summaryAmount').text()
    assert amount(window.dashboard_debt) == '$704.66 MXN'  # Original residual includes the normal purchase.
    assert amount(window.dashboard_personal) == format_money(before['personal_pending_cents'])
    assert amount(window.dashboard_receivables) == format_money(before['receivables_cents'])
    assert amount(window.dashboard_msi) == format_money(before['institutional_balance_cents'])
    assert window.dashboard_bar_chart.values[0][1] == window.dashboard_month_commitments
    amounts = [card.findChild(QLabel, 'summaryAmount').text() for card in window.dashboard_calendar_cards]
    assert amounts == ['$474.66 MXN'] * 3
    assert 'calendario por confirmar' in window.dashboard_calendar_cards[0].toolTip()
    assert window.dashboard_people.rowCount() == 4 and window.dashboard_cards.rowCount() == 3
    assert not window.dashboard_scroll.horizontalScrollBar().isVisible()
    assert window.dashboard_scroll.widget().width() <= window.dashboard_scroll.viewport().width()
    for row in range(window.dashboard_movements.count()):
        item = window.dashboard_movements.item(row)
        assert item.data(Qt.ItemDataRole.UserRole)['amount_cents'] == before['recent_movements'][row]['amount_cents']
        assert item.toolTip() == item.text()
    for name in ('Pedidos', 'Cobros', 'Tarjetas'):
        button = next(b for b in window.dashboard_header_actions.findChildren(QPushButton) if b.text() == name)
        button.click()
        assert window.pages.currentIndex() == window.PAGES.index(name)
        window._show_page(0)
    window.dashboard_calendar_toggle.click()
    captions = [card.layout().itemAt(0).widget().text() for card in window.dashboard_calendar_cards]
    assert any('anteriores por confirmar' in text for text in captions)
    assert any('Sin fecha' in text for text in captions)
    window.dashboard_calendar_toggle.click()
    app.processEvents()
    window.dashboard_scroll.verticalScrollBar().setValue(0)
    app.processEvents()
    window.grab().save(str(tmp_path / 'inicio-superior.png'))
    window.dashboard_scroll.verticalScrollBar().setValue(window.dashboard_scroll.verticalScrollBar().maximum())
    app.processEvents()
    window.grab().save(str(tmp_path / 'inicio-inferior.png'))
    window.dashboard_scroll.widget().grab().save(str(tmp_path / 'inicio-completo.png'))
    assert repo.dashboard_summary() == before
    assert repo.database.connection.total_changes == changes
    window.close()


def test_empty_home_has_no_fictitious_charts(synthetic):
    app, repo = synthetic
    window = MainWindow(database=repo.database, test_mode=True)
    window.resize(1366, 768)
    window.show()
    app.processEvents()
    assert not any(value for _, value in window.dashboard_bar_chart.values)
    assert not any(value for _, value in window.dashboard_donut_chart.values)
    assert window.dashboard_bar_chart.height() == 110
    assert window.dashboard_donut_chart.body.isHidden()
    assert not window.dashboard_donut_chart.empty.isHidden()
    assert window.dashboard_movements.count() == 1
    assert 'Todavía no hay movimientos' in window.dashboard_movements.item(0).text()
    assert not window.dashboard_movements_toggle.isVisible()
    assert period_label('2026-10') == 'Oct 2026'
    window.close()


def test_paid_obligations_use_empty_distribution(synthetic):
    app, repo = synthetic
    today = date.today().isoformat()
    repo.create_order(order_id='paid', ordered_at=today, merchant='Compra saldada sintética',
                      instrument_id='card1', original_cents=10000, charged_cents=10000, discount_cents=0,
                      allocations=({'user_id': 'owner', 'amount_cents': 6000}, {'user_id': 'ana', 'amount_cents': 4000}))
    for user, amount in [('owner', 6000), ('ana', 4000)]:
        repo.record_receipt(payment_id=user, receivable_id=f'order:paid:{user}', received_at=today, amount_cents=amount)
    repo.record_institution_payment(payment_id='bank-paid', instrument_id='card1', paid_at=today, amount_cents=10000)
    before = repo.dashboard_summary()
    window = MainWindow(database=repo.database, test_mode=True)
    assert window.dashboard_donut_chart.values == [(('Mi parte · ' if p['is_owner'] else '') + p['name'], 0)
        for p in sorted(repo.people_debt_summary(), key=lambda p: not p['is_owner'])]
    assert window.dashboard_donut_chart.body.isHidden()
    assert not window.dashboard_donut_chart.empty.isHidden()
    assert repo.dashboard_summary() == before
    window.close()


def test_six_periods_remain_readable_in_narrow_chart(synthetic):
    app, repo = synthetic
    today = date.today()
    dates = []
    for offset in range(6):
        index = today.year * 12 + today.month - 1 + offset
        dates.append(date(index // 12, index % 12 + 1, 15).isoformat())
    repo.create_order(order_id='six', ordered_at=today.isoformat(), merchant='Plan sintético de seis cuotas',
                      instrument_id='card1', original_cents=60000, charged_cents=60000, discount_cents=0,
                      allocations=({'user_id': 'owner', 'amount_cents': 60000},),
                      purchase_mode='MSI', financing_specs=tuple(dates))
    window = MainWindow(database=repo.database, test_mode=True)
    window.resize(640, 600)
    window.show()
    app.processEvents()
    assert len(window.dashboard_bar_chart.values) == 6
    assert [value for _, value in window.dashboard_bar_chart.values] == [10000] * 6
    assert window.dashboard_bar_chart.height() >= 244
    assert not window.dashboard_bar_chart.grab().isNull()
    window.close()
