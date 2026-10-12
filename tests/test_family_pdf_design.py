import pytest
import pymupdf
from test_product_refunds import repository
from test_personal_balance import reference_case
from valenza.gui.app import write_family_pdf,format_money,person_statement_html


PRIVATE_WORDS=('Descuento','beneficio','Cargo real','Banco ficticio','Mercado Pago ficticio',
               'Tarjeta ficticia','Billetera ficticia','participación vigente','ajustes auditados',
               'compensación aplicada','sin segundo cobro familiar','Recompra vinculada')


@pytest.mark.parametrize('person',['owner','mama'])
def test_family_pdf_private_data_removed_same_person_balance(repository,tmp_path,person):
    reference_case(repository)
    repository.record_receipt(payment_id='family-payment',receivable_id='order:new:mama',amount_cents=5000,received_at='2026-10-11')
    repository.link_order_to_msi('new',('2026-11-11','2026-12-11','2027-01-11'))
    statement=repository.family_statement(person)
    screen_before=person_statement_html(statement)
    before=repository.database.connection.total_changes
    path=tmp_path/(person+'.pdf')
    write_family_pdf(statement,path,issued_at='2026-10-11',repository=repository)
    with pymupdf.open(path) as document:
        text=''.join(page.get_text() for page in document)
        assert all(page.rect.width==612 and page.rect.height==792 for page in document)
        for page in document:
            for x0,y0,x1,y1,*_ in page.get_text('blocks'):
                assert 30 <= x0 < x1 <= 582 and 20 <= y0 < y1 <= 782
    assert '11/10/2026' in text and statement['person'] in text
    assert 'Total a tu cargo' in text and 'Ya pagaste' in text and 'Te falta pagar' in text
    for key in ('assigned_cents','paid_cents','remaining_cents'):
        assert format_money(statement[key]) in text
    assert all(word.casefold() not in text.casefold() for word in PRIVATE_WORDS)
    assert '$60.29 MXN' not in text and '$542.58 MXN' not in text and '$186.57 MXN' not in text
    dashboard=next(p for p in repository.people_debt_summary() if p['id']==person)
    assert statement['remaining_cents']==dashboard['remaining_cents']
    assert statement['paid_cents']==dashboard['paid_cents']
    assert person_statement_html(statement)==screen_before
    assert repository.database.connection.total_changes==before


def test_long_product_names_pagination_and_synthetic_review_example(repository,tmp_path):
    concepts=[dict(description=f'Artículo {i:03d} — Set de organizadores reutilizables para cocina con tapas ajustables, diferentes tamaños y accesorios incluidos',
                   amount_cents=100,allocations={'mama':100}) for i in range(60)]
    repository.create_order(order_id='long',ordered_at='2026-10-11',merchant='Tienda de ejemplo',instrument_id='card',original_cents=6000,
        discount_cents=0,charged_cents=6000,allocations=({'user_id':'owner','amount_cents':0},{'user_id':'mama','amount_cents':6000}),concepts=concepts)
    path=tmp_path/'long.pdf'; write_family_pdf(repository.family_statement('mama'),path,issued_at='2026-10-11')
    with pymupdf.open(path) as document:
        text=''.join(page.get_text() for page in document)
        assert len(document)>1 and all(f'Artículo {i:03d}' in text for i in range(60))
        assert text.count('accesorios incluidos')==60
        assert '$60.00 MXN' in text
        for page in document:
            assert f'/ {len(document)}' in page.get_text()


def test_review_example_with_return_and_payment(repository,tmp_path):
    reference_case(repository)
    repository.record_receipt(payment_id='example-payment',receivable_id='order:new:mama',amount_cents=5000,received_at='2026-10-11')
    statement=repository.family_statement('mama')
    path=tmp_path/'estado-de-cuenta-ejemplo.pdf'
    write_family_pdf(statement,path,issued_at='2026-10-11',repository=repository)
    with pymupdf.open(path) as document:
        text=''.join(page.get_text() for page in document)
        assert '$655.07 MXN' in text and '$50.00 MXN' in text
        assert 'Cambio por devolución' not in text
        for page in document:
            words=page.get_text('words')
            for word in words:
                assert word[0] >= 30 and word[2] <= 582
        document[0].get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).save(tmp_path/'pdf-first-page.png')
