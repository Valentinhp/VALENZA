"""Investigation only: synthetic encrypted refunds, using unchanged public APIs."""
from pathlib import Path
import json
import pytest
import pymupdf
from PySide6.QtWidgets import QLabel, QListWidget
from valenza.gui.app import MainWindow, create_application, write_family_pdf, format_money
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository
from test_product_refunds import purchase_args, repurchase_proposal

@pytest.mark.parametrize('refund,replacement', [(18657,12999),(15000,10000),(20779,12999)])
def test_agreed_partial_refund_split(tmp_path,refund,replacement):
    db=LocalDatabase.open(tmp_path/'partial-synthetic.db','synthetic-only'); db.migrate()
    repo=FinanceRepository(db)
    repo.add_person('owner','Yo sintetico',is_owner=True); repo.add_person('mama','Mama sintetica')
    repo.add_institution('bank','Nu sintetico'); repo.add_institution('mp','MP sintetico')
    repo.add_instrument('card','bank','Nu sintetica','CREDIT_CARD')
    repo.add_instrument('wallet','mp','Wallet sintetica','WALLET_BALANCE')
    args=purchase_args(destination='wallet',absorbs='owner')
    for index,p in enumerate(args['import_evidence']['products']):
        p['allocations']={'owner':p['unit'] if index==1 else 0,'mama':0 if index==1 else p['unit']}
    args['allocations']=({'user_id':'owner','amount_cents':2000},{'user_id':'mama','amount_cents':58287})
    difference=20779-refund
    args['import_evidence']['refund']=refund
    args['import_evidence']['paid']=54258-refund
    args['product_refunds'][0].update(amount_cents=refund,final_allocations={'owner':difference,'mama':0})
    repo.create_order(**args)
    proposal=repurchase_proposal(split={'owner':difference,'mama':replacement})
    proposal['amount_cents']=replacement
    repo.register_refund_repurchase(repo.list_product_refunds('order')[0]['id'],proposal)
    accounts={i['user_id']:i for i in repo.list_collection_items() if i['order_id']=='order'}
    assert accounts['owner']['remaining_cents']==2000+difference
    assert accounts['mama']['remaining_cents']==37508+replacement
    assert next(c for c in repo.list_card_summaries() if c['instrument_id']=='card')['remaining_cents']==54258
    assert next(c for c in repo.list_card_summaries() if c['instrument_id']=='wallet')['wallet_balance_cents']==refund-replacement
    assert repo.count('user_payment')==repo.count('institution_payment')==0
    db.close()


def test_reproduce_exact_case_across_ui_pdf_and_reopen(tmp_path):
    app=create_application([])
    dbpath=tmp_path/'exact-case-synthetic.db'
    db=LocalDatabase.open(dbpath,'synthetic-only'); db.migrate()
    repo=FinanceRepository(db)
    repo.add_person('owner','Yo sintetico',is_owner=True); repo.add_person('mama','Mama sintetica')
    repo.add_institution('bank','Nu sintetico'); repo.add_institution('mp','MP sintetico')
    repo.add_instrument('card','bank','Nu sintetica','CREDIT_CARD')
    repo.add_instrument('wallet','mp','Wallet sintetica','WALLET_BALANCE')
    args=purchase_args(destination='wallet',absorbs='owner')
    for index,p in enumerate(args['import_evidence']['products']):
        p['allocations']={'owner':p['unit'] if index==1 else 0,'mama':0 if index==1 else p['unit']}
    args['allocations']=({'user_id':'owner','amount_cents':2000},{'user_id':'mama','amount_cents':58287})
    args['product_refunds'][0].update(repurchase=repurchase_proposal(split={'owner':0,'mama':15121}),
                                    final_allocations={'owner':0,'mama':15121})
    repo.create_order(**args)
    refund=repo.list_product_refunds('order')[0]
    preserved=('order_allocation','institution_movement','institution_payment','user_payment','product_refund_adjustment','product_refund_repurchase')
    before={t:[tuple(r) for r in db.connection.execute(f'SELECT * FROM {t} ORDER BY rowid')] for t in preserved}
    out=Path('output/refund-investigation');out.mkdir(parents=True,exist_ok=True)
    evidence={}
    windows=[]
    def inspect(stage,owner,mama):
        summary=repo.dashboard_summary()
        assert summary['personal_pending_cents']==owner and summary['receivables_cents']==mama
        assert summary['discount_benefit_cents']==6029
        accounts=repo.list_collection_items()
        assert sum(i['remaining_cents'] for i in accounts if i['order_id']==refund['repurchase']['order_id'])==0
        window=MainWindow(database=db,test_mode=True)
        windows.append(window)
        for page in ('Pedidos','Cobros','Inicio'):
            window.findChild(QListWidget,'navigation').setCurrentRow(window.PAGES.index(page))
            if page=='Pedidos':
                row=next(r for r in range(window.orders_table.rowCount()) if window.orders_table.item(r,8).text()=='order')
                window.orders_table.selectRow(row)
                assert format_money(mama) in window.order_detail.toPlainText()
            elif page=='Cobros':
                assert window.collection_personal_card.findChild(QLabel,'summaryAmount').text()==format_money(owner)
                assert window.collection_family_card.findChild(QLabel,'summaryAmount').text()==format_money(mama)
            else:
                assert window.dashboard_personal.findChild(QLabel,'summaryAmount').text()==format_money(owner)
                assert window.dashboard_receivables.findChild(QLabel,'summaryAmount').text()==format_money(mama)
        for person,amount in (('owner',owner),('mama',mama)):
            path=out/f'{stage}-{person}.pdf'
            write_family_pdf(repo.family_statement(person),path)
            with pymupdf.open(path) as pdf:
                assert format_money(amount) in ''.join(p.get_text() for p in pdf)
        evidence[stage]={'personal_cents':owner,'family_cents':mama,'discount_cents':summary['discount_benefit_cents'],
            'bank_cents':next(c for c in repo.list_card_summaries() if c['instrument_id']=='card')['remaining_cents'],
            'wallet_cents':next(c for c in repo.list_card_summaries() if c['instrument_id']=='wallet')['wallet_balance_cents']}
        window.hide();app.processEvents()
    inspect('all-to-family',2000,52629)
    repo.update_refund_repurchase_allocations(refund['id'],{'owner':2122,'mama':12999},expected_allocations={'owner':0,'mama':15121})
    inspect('agreed-split',4122,50507)
    assert {t:[tuple(r) for r in db.connection.execute(f'SELECT * FROM {t} ORDER BY rowid')] for t in preserved}==before
    assert repo.count('user_payment')==repo.count('institution_payment')==0
    assert db.connection.execute("SELECT COUNT(*) FROM audit_event WHERE action='PRODUCT_REFUND_REPARTITIONED'").fetchone()[0] == 1
    (out/'results.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    db.close()
    assert dbpath.read_bytes()[:16] != b'SQLite format 3\x00'
    db=LocalDatabase.open(dbpath,'synthetic-only');repo=FinanceRepository(db)
    assert repo.dashboard_summary()['receivables_cents']==50507
    assert repo.dashboard_summary()['personal_pending_cents']==4122
    db.close()
