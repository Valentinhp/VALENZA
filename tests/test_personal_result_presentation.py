import hashlib
import json

import pymupdf
import pytest
from PySide6.QtWidgets import QLabel, QPushButton
from PySide6.QtGui import QFont, QFontDatabase

from test_product_refunds import repository, purchase_args, repurchase_proposal
from test_personal_balance import reference_case
from valenza.gui.app import MainWindow, create_application, format_money
from valenza.gui.family_pdf import write_report
from valenza.gui.personal_result import personal_result, result_label


def snapshot(repo):
    connection = repo.database.connection
    tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {table: [tuple(r) for r in connection.execute('SELECT * FROM "'+table+'" ORDER BY rowid')] for table in tables}


@pytest.mark.parametrize('destination,linked,msi', [
    ('card', False, False), ('wallet', False, False),
    ('wallet', True, False), ('wallet', True, True), ('other', True, True),
])
def test_shared_result_encrypted_read_only(repository, tmp_path, destination, linked, msi):
    repo = repository
    args = purchase_args(destination=destination)
    if linked:
        proposal = repurchase_proposal()
        proposal['instrument_id'] = destination
        args['product_refunds'][0].update(repurchase=proposal, final_allocations=proposal['final_allocations'])
    repo.create_order(**args)
    if msi:
        repo.link_order_to_msi('order', ('2026-11-11', '2026-12-11', '2027-01-11'))
    repo.record_receipt(payment_id='own', receivable_id='order:order:owner', amount_cents=1000, received_at='2026-10-12')
    repo.record_receipt(payment_id='family', receivable_id='order:order:mama', amount_cents=1000, received_at='2026-10-12')
    before = snapshot(repo)
    changes = repo.database.connection.total_changes
    summary = repo.dashboard_summary()
    projection = personal_result(repo)
    assert len(projection['rows']) == 1
    assert sum(r['result_cents'] for r in projection['rows']) == summary['personal_expected_result_cents'] == projection['result_cents']
    assert projection['discount_cents'] == 6029
    row = projection['rows'][0]
    assert row['result_cents'] == row['family_cents'] - row['cost_cents']
    assert row['cost_cents'] == 54258 - 18657 + (12999 if linked else 0)
    app = create_application([])
    font = QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    assert font >= 0
    app.setFont(QFont(QFontDatabase.applicationFontFamilies(font)[0], 10))
    window = MainWindow(database=repo.database, test_mode=True)
    window.resize(1100, 760); window.show(); app.processEvents()
    assert not window.dashboard_summary_toggle.isChecked()
    assert window.dashboard_expected.isVisible() and window.dashboard_discount.isVisible()
    assert window.dashboard_result_toggle.isVisible()
    assert len([b for b in window.findChildren(QPushButton) if b.text() == 'Ver cómo se calcula']) == 1
    assert '••••' in window.dashboard_expected.text()
    window.dashboard_privacy.click(); app.processEvents()
    assert format_money(abs(projection['result_cents'])) in window.dashboard_expected.text()
    assert result_label(projection['result_cents']) in window.dashboard_expected.text()
    assert window.dashboard_discount.findChild(QLabel, 'summaryAmount').text() == format_money(projection['discount_cents'])
    window.grab().save(str(tmp_path / 'inicio.png'))
    window.dashboard_result_toggle.click(); app.processEvents()
    detail = window.dashboard_result_details.toPlainText()
    assert format_money(abs(projection['result_cents'])) in detail and 'exigible hoy' in detail
    assert 'Descuentos' not in detail  # Savings are informational on the single existing card.
    window.grab().save(str(tmp_path / 'desglose.png'))
    owner_path = tmp_path / 'owner.pdf'
    write_report(repo.family_statement('owner'), owner_path, issued_at='2026-10-13', repository=repo)
    with pymupdf.open(owner_path) as doc:
        text = ''.join(p.get_text() for p in doc)
        assert 'Resultado personal previsto '+result_label(projection['result_cents']) in text
        assert format_money(abs(projection['result_cents'])) in text
        assert format_money(projection['discount_cents']) in text and 'exigible hoy' in text
        for index, page in enumerate(doc):
            for x0,y0,x1,y1,*_ in page.get_text('blocks'):
                assert 30 <= x0 < x1 <= 582 and 20 <= y0 < y1 <= 782
            page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).save(tmp_path / f'owner-page-{index+1}.png')
    window.dashboard_summary_toggle.click(); window._refresh_dashboard(); app.processEvents()
    assert window.dashboard_expected.isVisible()
    assert snapshot(repo) == before and repo.database.connection.total_changes == changes
    window.close()


def test_family_pdf_identical_to_previous_renderer(repository, tmp_path):
    # Golden hashes captured from HEAD's renderer using this encrypted synthetic case.
    # Text includes positions and styles; pixels include the unchanged presentation.
    repository.create_order(**purchase_args(destination='wallet'))
    statement = repository.family_statement('mama')
    before = snapshot(repository)
    new_path = tmp_path/'family.pdf'
    write_report(statement, new_path, issued_at='2026-10-13', repository=repository)
    with pymupdf.open(new_path) as new:
        content = json.dumps([p.get_text('dict') for p in new],sort_keys=True,ensure_ascii=False,default=lambda b:b.hex()).encode()
        assert hashlib.sha256(content).hexdigest() == '2121baff688bad132127e7ad4f80a7570ed20061f6650f28a2a5071140a20201'
        assert [hashlib.sha256(p.get_pixmap().samples).hexdigest() for p in new] == [
            '0c2ef6db5d8c8d1a8df60a3de43cc73c02c99ac5a3bf5f62697626c92f59fda4']
    assert snapshot(repository) == before


@pytest.mark.parametrize('family,expected', [(10000,2000), (0,-8000)])
def test_sign_and_owner_relationship_with_arbitrary_names(repository,tmp_path,family,expected):
    repository.update_person('owner', 'Persona sintética propietaria', is_owner=True)
    repository.create_order(order_id='sign',ordered_at='2026-10-13',merchant='Operación sintética',instrument_id='card',
        original_cents=10000,discount_cents=2000,charged_cents=8000,
        allocations=({'user_id':'owner','amount_cents':10000-family},{'user_id':'mama','amount_cents':family}))
    projection = personal_result(repository)
    assert projection['result_cents'] == expected
    path=tmp_path/'sign.pdf'
    write_report(repository.family_statement('owner'),path,repository=repository)
    with pymupdf.open(path) as doc:
        text=''.join(p.get_text() for p in doc)
        assert 'Resultado personal previsto '+result_label(expected) in text
        assert '-$' not in text


def test_multiple_operations_compact_home_matches_owner_pdf(repository,tmp_path):
    reference_case(repository)
    before = snapshot(repository)
    projection = personal_result(repository)
    assert len(projection['rows']) == 2
    assert sum(r['result_cents'] for r in projection['rows']) == projection['result_cents'] == -37993
    assert [r['result_cents'] for r in projection['rows']] == [1907,-39900]
    app = create_application([])
    font=QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    app.setFont(QFont(QFontDatabase.applicationFontFamilies(font)[0],10))
    window=MainWindow(database=repository.database,test_mode=True)
    window.resize(680,600); window.show(); app.processEvents()
    assert window.dashboard_expected.isVisible() and window.dashboard_result_toggle.isVisible()
    assert not window.dashboard_scroll.horizontalScrollBar().isVisible()
    window.dashboard_privacy.click(); app.processEvents()
    assert '$379.93 MXN' in window.dashboard_expected.text()
    window.dashboard_scroll.ensureWidgetVisible(window.dashboard_expected)
    app.processEvents()
    window.grab().save(str(tmp_path/'inicio-compacto.png'))
    window.dashboard_result_toggle.click(); app.processEvents()
    detail=window.dashboard_result_details.toPlainText()
    assert '$19.07 MXN' in detail and '$399.00 MXN' in detail and '$379.93 MXN' in detail
    assert 'a favor' in detail and 'a tu cargo' in detail
    window.grab().save(str(tmp_path/'desglose-compacto.png'))
    path=tmp_path/'multiple.pdf'
    write_report(repository.family_statement('owner'),path,repository=repository)
    with pymupdf.open(path) as doc:
        text=''.join(p.get_text() for p in doc)
        assert 'Resultado personal previsto a tu cargo' in text and '$379.93 MXN' in text
        assert '$19.07 MXN' in text and '$399.00 MXN' in text
    assert snapshot(repository) == before
    window.close()
