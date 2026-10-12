import pytest
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository
from valenza.gui.app import MainWindow, create_application


@pytest.mark.parametrize('msi', [False, True])
def test_cancelled_purchase_disappears_from_card_detail_but_remains_in_history(msi):
    app=create_application([])
    db=LocalDatabase.open(':memory:','synthetic',allow_synthetic_in_memory=True)
    db.migrate()
    repo=FinanceRepository(db)
    repo.add_person('owner','Yo sintético',is_owner=True)
    repo.add_institution('bank','Banco sintético')
    repo.add_instrument('card','bank','Tarjeta sintética','CREDIT_CARD')
    for identity,amount in [('keep',10000),('cancel',30000)]:
        repo.create_order(order_id=identity,ordered_at='2026-10-11',merchant=identity,
            instrument_id='card',original_cents=amount,charged_cents=amount,discount_cents=0,
            allocations=({'user_id':'owner','amount_cents':amount},),
            purchase_mode='MSI' if msi else 'CASH',
            financing_specs=('2026-11-11','2026-12-11','2027-01-11') if msi else None)
    window=MainWindow(database=db)
    window._show_page(MainWindow.PAGES.index('Tarjetas'))
    window.cards_table.selectRow(0)
    assert 'cancel' in window.card_detail.text()
    repo.cancel_order('cancel',reason='Anulación sintética')
    changes=db.connection.total_changes
    window._refresh_visible_data('orders')
    assert [p['id'] for p in repo.list_card_purchases('card')]==['keep']
    assert len(repo.list_card_purchases('card',include_cancelled=True))==2
    assert repo.get_order('cancel')['order_status']=='CANCELLED'
    assert 'cancel' not in window.card_detail.text()
    assert 'keep' in window.card_detail.text()
    assert repo.list_card_summaries()[0]['remaining_cents']==10000
    assert repo.dashboard_summary()['institutional_balance_cents']==10000
    assert repo.family_statement('owner')['remaining_cents']==10000
    if msi:
        assert all(item['order_id']=='keep' for item in repo.list_installments('card'))
        assert '$100.00 MXN' not in window.card_detail.text().split('Mensualidades:')[1]
    assert db.connection.total_changes==changes
    repo.cancel_order('keep',reason='Anulación final sintética')
    window._refresh_visible_data('orders')
    assert repo.list_card_purchases('card')==[]
    assert 'Esta tarjeta aún no tiene compras asociadas.' in window.card_detail.text()
    assert 'Mensualidades:' not in window.card_detail.text()
    assert repo.dashboard_summary()['institutional_balance_cents']==0
    window.close()
    app.processEvents()
