from pathlib import Path
import pytest
from test_product_refunds import repository,create_discount_comparison_case
from valenza.ocr.order_import import read_receipt
from valenza.gui.app import write_family_pdf,format_money


def test_native_topup_import_subscription_link_duplicate_and_pdf(repository,tmp_path):
    import pymupdf
    source=tmp_path/'anonymous-topup.pdf'
    text=(Path(__file__).parent/'fixtures_synthetic'/'mp_topup.txt').read_text(encoding='utf-8')
    with pymupdf.open() as doc:
        page=doc.new_page(); page.insert_text((40,40),text,fontsize=12); doc.save(source)
    evidence=read_receipt(source)
    assert evidence['date']=='2026-09-10' and evidence['time']=='08:19:34'
    evidence['products'][0]['allocations']={'owner':0,'mama':20000}
    args=dict(order_id='topup',ordered_at=evidence['date'],merchant='Recarga Telcel',instrument_id='card',original_cents=20000,
        discount_cents=0,charged_cents=20000,allocations=({'user_id':'owner','amount_cents':0},{'user_id':'mama','amount_cents':20000}),import_evidence=evidence)
    repository.create_order(**args)
    repository.save_subscription(subscription_id='telcel',name='Recarga Telcel',amount_cents=20000,instrument_id='card',next_due='2026-09-10',allocations=list(args['allocations']))
    repository.record_subscription_charge('telcel',cycle_date='2026-09-10',order_id='topup')
    with pytest.raises(ValueError,match='duplicado'):
        repository.create_order(**dict(args,order_id='second'))
    assert len(repository.list_orders())==1
    assert repository.dashboard_summary()['institutional_balance_cents']==20000
    assert repository.dashboard_summary()['receivables_cents']==20000
    assert repository.dashboard_summary()['discount_benefit_cents']==0
    statement=repository.family_statement('mama')
    output=tmp_path/'person.pdf'; write_family_pdf(statement,output)
    with pymupdf.open(output) as doc:
        result=''.join(page.get_text() for page in doc)
    assert 'Recarga Telcel' in result and 'suscripciones' in result and '$200.00 MXN' in result
    assert statement['remaining_cents']==repository.people_debt_summary()[0]['remaining_cents']
    assert len(statement['forecasts'])==1 and statement['forecasts'][0]['due_date']=='2026-10-10'


def test_products_discount_repurchase_msi_pdf_matches_real_balances(repository,tmp_path):
    import pymupdf
    create_discount_comparison_case(repository)
    before=repository.dashboard_summary()
    repository.link_order_to_msi('order',('2026-11-10','2026-12-10','2027-01-10'))
    after=repository.dashboard_summary()
    for key in ('institutional_balance_cents','receivables_cents','personal_pending_cents','discount_benefit_cents','personal_expected_result_cents'):
        assert before[key]==after[key]
    assert after['institutional_balance_cents']==54258 and after['discount_benefit_cents']==6029
    for person in repository.people_debt_summary():
        statement=repository.family_statement(person['id'])
        assert statement['remaining_cents']==person['remaining_cents']
        path=tmp_path/(person['id']+'.pdf'); write_family_pdf(statement,path,repository=repository)
        with pymupdf.open(path) as doc:
            text=''.join(page.get_text() for page in doc)
        assert format_money(person['remaining_cents']) in text
        if not person['is_owner']:
            assert '$129.99 MXN' in text and '$56.58 MXN' not in text
    assert repository.order_benefit_summary('order')['expected_result_cents']==1907
    assert repository.database.integrity_report()['ok']
