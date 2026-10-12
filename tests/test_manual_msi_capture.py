import pytest

from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository
from valenza.gui.app import MainWindow, create_application


@pytest.fixture
def capture(monkeypatch):
    app = create_application([])
    database = LocalDatabase.open(':memory:', 'synthetic', allow_synthetic_in_memory=True)
    database.migrate()
    repo = FinanceRepository(database)
    repo.add_person('valen', 'VALEN', is_owner=True)
    repo.add_person('joaquin', 'JOAQUÍN')
    repo.add_institution('nu', 'NuBank')
    repo.add_instrument('nu-card', 'nu', 'NuBank sintética', 'CREDIT_CARD')
    errors = []
    monkeypatch.setattr(MainWindow, '_show_error', lambda _, message: errors.append(message))
    monkeypatch.setattr(MainWindow, '_show_information', lambda *args: None)
    window = MainWindow(database=database)
    window._open_manual_expense()
    yield window, repo, errors
    window.manual_dialog.close()
    window.close()
    database.close()
    app.processEvents()


def plant_form(window, *, basis='INSTALLMENT', amount=47466):
    window.manual_concepts.removeRow(0)
    window._add_manual_concept(dict(description='PLANTA ELÉCTRICA', amount_cents=amount,
                                    allocations={'valen':0, 'joaquin':amount}))
    window.order_merchant.setText('MERCADO LIBRE')
    window.order_date.setText('2026-10-11')
    window.order_purchase_mode.setCurrentIndex(window.order_purchase_mode.findData('MSI'))
    window.order_installments.setValue(3)
    window.order_amount_basis.setCurrentIndex(window.order_amount_basis.findData(basis))
    window.order_first_due_date.setText('2026-11-11')
    window.order_charged.setText(f'{amount // 100}.{amount % 100:02d}')
    window.order_instrument.setCurrentIndex(window.order_instrument.findData('nu-card'))


@pytest.mark.parametrize('basis,amount', [('INSTALLMENT',47466), ('TOTAL',142398)])
def test_joaquin_plant_end_to_end_single_order_and_three_equal_installments(capture, basis, amount):
    window, repo, errors = capture
    plant_form(window, basis=basis, amount=amount)
    assert '$1,423.98 MXN' in window.order_summary.text()
    assert '3 cuotas: $474.66 MXN' in window.order_summary.text()
    assert window.order_discount.text() == '$0.00 MXN'
    assert window.save_order_button.isEnabled()
    assert repo.list_orders() == []
    window.save_order_button.click()
    assert not errors
    rows = repo.list_orders()
    assert len(rows) == 1
    order = repo.get_order(rows[0]['id'])
    assert order['merchant'] == 'MERCADO LIBRE' and order['instrument_id'] == 'nu-card'
    assert (order['original_cents'],order['charged_cents'],order['discount_cents']) == (142398,142398,0)
    assert order['manual_concepts'][0]['description'] == 'PLANTA ELÉCTRICA'
    assert order['manual_concepts'][0]['allocations']['joaquin'] == 142398
    assert order['financing_plan']['principal_cents'] == 142398
    assert [i['principal_cents'] for i in order['installments']] == [47466]*3
    assert repo.family_statement('joaquin')['remaining_cents'] == 142398
    summary = repo.dashboard_summary()
    assert summary['institutional_balance_cents'] == summary['receivables_cents'] == 142398
    assert summary['discount_benefit_cents'] == summary['personal_expected_result_cents'] == summary['personal_pending_cents'] == 0
    assert repo.database.connection.execute('SELECT COUNT(*) FROM institution_payment').fetchone()[0] == 0
    assert repo.database.connection.execute('SELECT COUNT(*) FROM institution_movement').fetchone()[0] == 0
    # A second click on the cleared form cannot create another purchase.
    window.save_order_button.click()
    assert len(repo.list_orders()) == 1
    with pytest.raises(ValueError):
        repo.link_order_to_msi(order['id'], ('2026-11-11','2026-12-11','2027-01-11'))
    assert len(repo.get_order(order['id'])['installments']) == 3


def test_blank_charge_blocks_preview_and_direct_save(capture):
    window, repo, errors = capture
    plant_form(window)
    window.order_charged.clear()
    assert window.order_discount.text() == 'Por confirmar'
    assert not window.save_order_button.isEnabled()
    window._save_order()
    assert errors and repo.list_orders() == []


def test_selected_joaquin_is_authoritative_even_if_hidden_allocation_is_stale(capture):
    window, repo, errors = capture
    plant_form(window)
    # A stale compatibility table must not override the visible product selector.
    for row in range(window.order_allocations_table.rowCount()):
        identity=window.order_allocations_table.item(row,0).data(256)
        window.order_allocations_table.item(row,1).setText('474.66' if identity=='valen' else '0.00')
    window._update_order_preview()
    assert 'JOAQUÍN: $1,423.98 MXN' in window.order_summary.text()
    assert 'VALEN (Yo): $0.00 MXN' in window.order_summary.text()
    assert 'Sin repartir: $0.00 MXN' in window.order_summary.text()
    window.save_order_button.click()
    assert not errors
    order=repo.list_orders()[0]
    row=next(i for i in range(window.orders_table.rowCount()) if window.orders_table.item(i,8).text()==order['id'])
    assert window.orders_table.item(row,5).text()=='$0.00 MXN'
    assert window.orders_table.item(row,6).text()=='$1,423.98 MXN'
    assert order['owner_cents']==0
    assert repo.family_statement('joaquin')['assigned_cents']==142398


def test_installment_discount_is_scaled_once_preserving_family_amount(capture):
    window, repo, errors = capture
    plant_form(window)
    window.order_charged.setText('450.00')
    assert window.order_discount.text() == '$73.98 MXN'
    window.save_order_button.click()
    assert not errors
    saved = repo.list_orders()[0]
    assert saved['original_cents'] == 142398 and saved['charged_cents'] == 135000
    assert saved['discount_cents'] == 7398
    assert repo.family_statement('joaquin')['assigned_cents'] == 142398


@pytest.mark.parametrize('charged,discount', [(0,47466),(47465,0),(47466.0,0),(None,0)])
def test_service_rejects_invalid_msi_without_partial_records(capture, charged, discount):
    _, repo, _ = capture
    with pytest.raises(ValueError):
        repo.create_order(order_id='invalid',ordered_at='2026-10-11',merchant='MERCADO LIBRE',
            instrument_id='nu-card',original_cents=47466,charged_cents=charged,discount_cents=discount,
            allocations=({'user_id':'valen','amount_cents':0},{'user_id':'joaquin','amount_cents':47466}),
            purchase_mode='MSI',financing_specs=('2026-11-11',)*3)
    for table in ('order_record','receivable','order_allocation','financing_plan','installment'):
        assert repo.database.connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
