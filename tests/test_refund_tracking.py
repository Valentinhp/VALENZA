import copy
import pytest
from PySide6.QtGui import QFont, QFontDatabase
from test_product_refunds import repository, purchase_args, repurchase_proposal
from test_bank_reconciliation import financial_snapshot
from test_cards_refund_ui import settle
from valenza.gui.app import MainWindow, create_application
from valenza.gui.refund_tracking import refund_tracking_html


@pytest.fixture(autouse=True)
def readable_font():
    app = create_application([])
    font = QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    if font >= 0:
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(font)[0], 10))


@pytest.mark.parametrize('case', ['pending', 'wallet', 'applied', 'unapplied', 'card', 'unassigned', 'none', 'linked'])
def test_tracking_states_read_only_normal_wide_maximized(repository, tmp_path, case):
    repo = repository
    args = purchase_args(status='PENDING' if case=='pending' else 'ACCREDITED', destination='card' if case=='card' else 'wallet')
    if case in ('unassigned', 'none'):
        args['product_refunds'] = ()
    if case=='none':
        args.pop('import_evidence')
    repo.create_order(**args)
    selected = 'order'
    if case in ('applied','unapplied','linked'):
        proposal = repurchase_proposal(apply=case!='unapplied')
        linked = repo.register_refund_repurchase(repo.list_product_refunds('order')[0]['id'], proposal)
        if case=='linked': selected=linked
    before = financial_snapshot(repo)
    audit = [tuple(r) for r in repo.database.connection.execute('SELECT * FROM audit_event ORDER BY rowid')]
    changes = repo.database.connection.total_changes
    app=create_application([])
    window=MainWindow(database=repo.database, test_mode=True)
    window.show(); window._show_page(2)
    row=next(r for r in range(window.orders_table.rowCount()) if window.orders_table.item(r,8).text()==selected)
    window.orders_table.selectRow(row); settle(app)
    try:
        html=window.order_refund_tracking_text.text()
        assert window.order_refund_tracking.isVisible() == (case!='none')
        if case=='pending':
            assert 'Pendiente de acreditación' in html and 'Remanente inicial' not in html
        if case in ('applied','unapplied','linked'):
            assert '$56.58 MXN' in html and '$129.99 MXN' in html
            assert ('<b>$0.00 MXN</b> (compensación' in html) == (case=='unapplied')
            assert 'no confirma dinero disponible hoy' in html
            assert 'no registra un cobro familiar ni paga Nu' in html
        if case=='card':
            assert 'no es un ingreso en Wallet' in html and 'Remanente inicial' not in html
        if case=='unassigned':
            assert 'destino, acreditación y uso no confirmados' in html and 'Acreditado' not in html
        if case=='linked': assert 'pedido original relacionado' in html
        for width,height in ((900,740),(1920,1080),(680,650),(900,740)):
            window.resize(width,height); settle(app)
            if case!='none':
                window.orders_scroll.ensureWidgetVisible(window.order_refund_tracking); settle(app)
                label=window.order_refund_tracking_text
                assert label.height() >= label.heightForWidth(label.width())
                assert window.order_refund_tracking.rect().contains(label.geometry())
                window.order_refund_tracking.grab().save(str(tmp_path/f'tracking-{case}-{width}.png'))
            window.grab().save(str(tmp_path/f'orders-{case}-{width}.png'))
            assert window.orders_scroll.horizontalScrollBar().maximum()==0
        window.showMaximized(); settle(app)
        window.grab().save(str(tmp_path/f'orders-{case}-maximized.png'))
        assert financial_snapshot(repo)==before
        assert [tuple(r) for r in repo.database.connection.execute('SELECT * FROM audit_event ORDER BY rowid')]==audit
        assert repo.database.connection.total_changes==changes
    finally:
        window.close(); settle(app)


@pytest.mark.parametrize('change', ['missing_order','different_source','cancelled','different_cost','excess_cost','unknown_status'])
def test_unknown_funding_never_confirms_remainder(repository, change):
    repo=repository; repo.create_order(**purchase_args(destination='wallet'))
    linked_id=repo.register_refund_repurchase(repo.list_product_refunds('order')[0]['id'],repurchase_proposal())
    order=copy.deepcopy(repo.get_order('order'))
    linked=copy.deepcopy(repo.get_order(linked_id))
    if change=='different_source': linked['instrument_id']='card'
    if change=='cancelled': linked['order_status']='CANCELLED'
    if change=='different_cost': linked['charged_cents']=1
    if change=='excess_cost': order['product_refunds'][0]['repurchase']['charged_cents']=99999
    if change=='unknown_status': order['product_refunds'][0]['status']='UNKNOWN'
    before=copy.deepcopy(order)
    html=refund_tracking_html(order,{} if change=='missing_order' else {linked_id:linked})
    assert 'Remanente: no calculable' in html and 'Remanente inicial tras' not in html
    assert order==before


def test_names_are_plain_data_and_no_historical_amount_is_invented():
    order={'product_refunds':[dict(amount_cents=12345,destination_name='<b>Destino</b>',status='PENDING')]}
    html=refund_tracking_html(order,{})
    assert '&lt;b&gt;Destino&lt;/b&gt;' in html
    assert '$123.45 MXN' in html and '56.58' not in html
