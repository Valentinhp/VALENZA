import pytest
from test_product_refunds import repository
from test_personal_balance import reference_case
from test_subscriptions import subscription
from sgccc.gui.app import person_statement_html,write_family_pdf,MainWindow,create_application


def test_all_people_owner_and_same_real_balances(repository):
    reference_case(repository)
    repository.add_person('zero','Persona sin deuda')
    repository.deactivate_person('zero')
    subscription(repository)
    people=repository.people_debt_summary()
    assert {p['id'] for p in people}=={'owner','mama','zero'}
    summary=repository.dashboard_summary()
    assert sum(p['remaining_cents'] for p in people if p['is_owner'])==summary['personal_pending_cents']==39900
    assert sum(p['remaining_cents'] for p in people if not p['is_owner'])==summary['receivables_cents']==70507
    assert sum(p['subscription_forecast_cents'] for p in people)==10001
    assert sum(p['remaining_cents'] for p in people)==110407
    assert next(p for p in people if p['id']=='zero')['remaining_cents']==0


def test_person_pdf_matches_dashboard_and_receipts_are_independent(repository,tmp_path):
    import pymupdf
    reference_case(repository)
    repository.record_receipt(payment_id='personal',receivable_id='order:new:owner',amount_cents=5000,received_at='2026-10-11')
    repository.record_receipt(payment_id='family',receivable_id='order:new:mama',amount_cents=3000,received_at='2026-10-11')
    before=repository.dashboard_summary()['institutional_balance_cents']
    repository.record_institution_payment(payment_id='bank',instrument_id='card',paid_at='2026-10-11',amount_cents=1000)
    for person in repository.people_debt_summary():
        statement=repository.family_statement(person['id'])
        assert statement['remaining_cents']==person['remaining_cents']
        assert statement['paid_cents']==person['paid_cents']
        path=tmp_path/(person['id']+'.pdf'); write_family_pdf(statement,path)
        with pymupdf.open(path) as document:
            text=''.join(p.get_text() for p in document)
        from sgccc.gui.app import format_money
        assert format_money(person['remaining_cents']) in text
        assert format_money(person['paid_cents']) in text
        assert 'Pendiente' in text
        if person['id']=='mama':
            assert 'Recompra vinculada' in text and '$56.58 MXN' in text
    assert repository.dashboard_summary()['institutional_balance_cents']==before-1000


def test_dashboard_selection_owner_pdf_and_small_render(repository,tmp_path,monkeypatch):
    from PySide6.QtGui import QFont,QFontDatabase
    from PySide6.QtWidgets import QScrollArea
    reference_case(repository)
    app=create_application([])
    font=QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    if font>=0: app.setFont(QFont(QFontDatabase.applicationFontFamilies(font)[0],10))
    window=MainWindow(database=repository.database)
    window.show(); window.resize(680,480)
    assert window.dashboard_people.rowCount()==2
    assert window._table_id(window.dashboard_people,5)=='owner'
    path=tmp_path/'owner.pdf'
    monkeypatch.setattr('sgccc.gui.app.QFileDialog.getSaveFileName',lambda *args,**kwargs:(str(path),'PDF'))
    window.dashboard_person_pdf.click()
    assert path.exists()
    row=next(r for r in range(window.dashboard_people.rowCount()) if window.dashboard_people.item(r,5).text()=='mama')
    window.dashboard_people.selectRow(row)
    assert '$505.07 MXN' in window.dashboard_person_details.toPlainText()
    scroll=window.pages.widget(0).findChild(QScrollArea)
    scroll.ensureWidgetVisible(window.dashboard_people)
    app.processEvents(); window.grab().save(str(tmp_path/'people-small.png'))
    window.close(); app.processEvents()
