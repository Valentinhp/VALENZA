"""Home accordion checks against real repository values in encrypted fixtures only."""
from pathlib import Path
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QScrollArea, QTextEdit, QLabel
from valenza.gui.app import MainWindow, create_application, format_money
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository
from test_personal_balance import reference_case


@pytest.fixture
def encrypted_repository(tmp_path):
    db = LocalDatabase.open(tmp_path / 'synthetic-home.db', 'synthetic-home-accordion')
    db.migrate()
    assert db.encrypted
    repo = FinanceRepository(db)
    repo.add_person('owner', 'Yo', is_owner=True)
    repo.add_person('mama', 'Joaquín (sintético)')
    repo.add_institution('bank', 'Banco ficticio')
    repo.add_institution('mp', 'Mercado Pago ficticio')
    repo.add_instrument('card', 'bank', 'Tarjeta ficticia', 'CREDIT_CARD')
    repo.add_instrument('wallet', 'mp', 'Billetera ficticia', 'WALLET_BALANCE')
    repo.add_instrument('other', 'mp', 'Otro destino ficticio', 'OTHER')
    yield repo
    db.close()


def seed_breakdown(repo):
    # Existing synthetic case includes discount, refund, repurchase and compensation.
    reference_case(repo)
    repo.add_person('empty', 'Persona sin pedidos')
    repo.add_person('settled', 'Persona con todo liquidado')
    repo.create_order(order_id='msi', ordered_at='2026-10-12', merchant='Escritorio · MSI',
        instrument_id='card', original_cents=60000, discount_cents=0, charged_cents=60000,
        allocations=({'user_id':'owner','amount_cents':30000}, {'user_id':'mama','amount_cents':30000}),
        purchase_mode='MSI', financing_specs=('2026-10-20','2026-11-20'))
    repo.record_receipt(payment_id='partial', receivable_id='order:msi:mama',
        received_at='2026-10-13', amount_cents=10000)
    for key, user, amount in [('paid','mama',2000), ('settled-order','settled',4000)]:
        repo.create_order(order_id=key, ordered_at='2026-10-13', merchant='Pedido liquidado · '+user,
            instrument_id='card', original_cents=amount, discount_cents=0, charged_cents=amount,
            allocations=({'user_id':'owner','amount_cents':0}, {'user_id':user,'amount_cents':amount}))
        repo.record_receipt(payment_id=key, receivable_id=f'order:{key}:{user}',
            received_at='2026-10-13', amount_cents=amount)
    repo.save_subscription(subscription_id='forecast', name='Previsión excluida', amount_cents=9999,
        instrument_id='card', next_due='2026-11-01',
        allocations=[dict(user_id='owner', amount_cents=0), dict(user_id='mama', amount_cents=9999)])


def make_window(repo):
    app = create_application([])
    for name in ('segoeui.ttf','segoeuib.ttf','georgia.ttf'):
        QFontDatabase.addApplicationFont(str(Path('C:/Windows/Fonts') / name))
    window = MainWindow(database=repo.database, test_mode=True)
    window.show(); app.processEvents()
    return app, window


def test_accordion_exact_balances_paid_separation_and_no_writes(encrypted_repository, monkeypatch):
    repo = encrypted_repository
    seed_breakdown(repo)
    before = repo.dashboard_summary(), repo.people_debt_summary(), [repo.family_statement(p['id']) for p in repo.list_people()]
    changes = repo.database.connection.total_changes
    app, window = make_window(repo)
    table_before = [[window.dashboard_people.item(r,c).text() for c in range(6)] for r in range(window.dashboard_people.rowCount())]
    window.dashboard_person_toggle.click(); app.processEvents()
    panel = window.dashboard_person_details
    assert panel.isVisible()
    assert not panel.findChildren(QTextEdit) and not panel.findChildren(QScrollArea)
    assert all(not section.toggle.isChecked() for section in panel.sections.values())
    for person in repo.people_debt_summary():
        section = panel.sections[person['id']]
        section.toggle.click(); app.processEvents()
        statement = repo.family_statement(person['id'])
        assert section.balance.text() == format_money(statement['remaining_cents'])
        rows = section.pending_rows + section.paid_rows
        for key in ('sale_cents', 'paid_cents', 'remaining_cents'):
            statement_key = 'assigned_cents' if key == 'sale_cents' else key
            assert sum(row.entry[key] for row in rows) == statement[statement_key]
            assert all(row.values[key].text() == format_money(row.entry[key]) for row in rows)
        assert len({r.entry['receivable_id'] for r in rows}) == len(rows)
        assert all(r.entry['remaining_cents'] != 0 for r in section.pending_rows)
        assert all(r.entry['remaining_cents'] == 0 for r in section.paid_rows)
        assert all(not r.isVisible() for r in section.paid_rows)
        if section.paid_toggle:
            section.paid_toggle.click(); app.processEvents()
            assert all(r.isVisible() for r in section.paid_rows)
        if person['id'] == 'empty':
            assert any(label.text() == 'Sin pedidos registrados.' for label in section.body.findChildren(QLabel))
        if person['id'] == 'settled':
            assert not section.pending_rows and len(section.paid_rows) == 1
        section.toggle.click()
    joaquin = panel.sections['mama']; joaquin.toggle.click(); app.processEvents()
    assert [r.entry['order_id'] for r in joaquin.pending_rows] == ['msi','new','order']
    msi = joaquin.pending_rows[0]
    assert [msi.entry[k] for k in ('sale_cents','paid_cents','remaining_cents')] == [30000,10000,20000]
    adjusted = joaquin.pending_rows[-1]
    assert adjusted.entry['sale_cents'] == 50507
    assert all('Previsión' not in r.title.text() for r in joaquin.pending_rows)
    assert window._table_id(window.dashboard_people,5) == 'mama'
    exported = []; monkeypatch.setattr(window, '_export_family_pdf', exported.append)
    window.dashboard_person_pdf.click(); assert exported == ['mama']
    window._refresh_people_dashboard(); app.processEvents()
    assert panel.sections['mama'].toggle.isChecked()
    assert [[window.dashboard_people.item(r,c).text() for c in range(6)] for r in range(window.dashboard_people.rowCount())] == table_before
    window.dashboard_person_toggle.click(); assert not panel.isVisible()
    assert before == (repo.dashboard_summary(), repo.people_debt_summary(), [repo.family_statement(p['id']) for p in repo.list_people()])
    assert repo.database.connection.total_changes == changes
    window.database = None; window.close(); app.processEvents()


@pytest.mark.parametrize('size', [(1080,760),(680,480),(680,600)])
def test_encrypted_accordion_small_layout_and_keyboard(encrypted_repository, tmp_path, size):
    repo = encrypted_repository; seed_breakdown(repo)
    app, window = make_window(repo)
    window.resize(*size); window.dashboard_person_toggle.click(); app.processEvents()
    section = window.dashboard_person_details.sections['mama']
    section.toggle.setFocus(); QTest.keyClick(section.toggle, Qt.Key.Key_Space); app.processEvents()
    assert section.body.isVisible()
    scroll = window.dashboard_scroll
    scroll.ensureWidgetVisible(window.dashboard_person_details); app.processEvents(); app.processEvents()
    assert window.size().width() == size[0]
    for row in section.pending_rows:
        assert row.width() <= window.dashboard_person_details.width()
        assert all(row.rect().contains(amount.rect().translated(amount.mapTo(row, amount.rect().topLeft())))
                   for amount in row.values.values())
    window.grab().save(str(tmp_path / f'accordion-{size[0]}.png'))
    QTest.keyClick(section.toggle, Qt.Key.Key_Space); app.processEvents()
    assert not section.body.isVisible()
    window.database = None; window.close(); app.processEvents()
