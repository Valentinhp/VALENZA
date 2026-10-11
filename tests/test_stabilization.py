import pytest

from sgccc.persistence.database import DatabaseSecurityError, LocalDatabase
from sgccc.persistence.repository import FinanceRepository
from test_product_refunds import repository, create_discount_comparison_case
from test_personal_balance import reference_case


def finance_snapshot(repo):
    names = ('order_record', 'order_allocation', 'receivable', 'user_payment', 'receipt_application',
             'institution_movement', 'institution_payment', 'imported_product_refund',
             'product_refund_repurchase', 'product_refund_adjustment', 'product_repurchase_adjustment')
    return {name: [tuple(r) for r in repo.database.connection.execute(f'SELECT * FROM {name} ORDER BY rowid')] for name in names}


def test_move_card_with_history_preserves_every_financial_record(repository):
    create_discount_comparison_case(repository)
    repository.record_bank_balance('card', 55000, '2026-10-11')
    before = finance_snapshot(repository)
    repository.update_instrument('card', 'Cuenta corregida ficticia', 'CREDIT_CARD',
                                 institution_id='mp', last_four='0000', description='Dato descriptivo ficticio')
    assert finance_snapshot(repository) == before
    card = next(r for r in repository.list_all_instruments() if r['id']=='card')
    assert card['institution_id'] == 'mp'
    assert repository.instrument_profile('card')['last_four'] == '0000'
    comparison = next(r for r in repository.list_bank_comparisons() if r['instrument_id']=='card')
    assert comparison['calculated_cents'] == 54258 and comparison['reported_cents'] == 55000
    assert repository.order_benefit_summary('order')['expected_result_cents'] == 1907
    repository.update_instrument('wallet', 'Wallet corregida ficticia', 'WALLET_BALANCE', institution_id='bank')
    assert finance_snapshot(repository) == before
    with pytest.raises(ValueError, match='naturaleza'):
        repository.update_instrument('wallet', 'Wallet', 'CREDIT_CARD')
    assert all(r['instrument_id'] != 'wallet' for r in repository.list_bank_comparisons())


@pytest.mark.parametrize('tail', ['123', '12345', '１２３４', 0, False])
def test_bad_card_metadata_is_atomic(repository, tail):
    before = [tuple(r) for r in repository.database.connection.execute('SELECT * FROM payment_instrument')]
    with pytest.raises(ValueError):
        repository.update_instrument('card', 'No guardar', 'CREDIT_CARD', institution_id='mp', last_four=tail)
    assert [tuple(r) for r in repository.database.connection.execute('SELECT * FROM payment_instrument')] == before


def test_card_profile_failure_rolls_back_and_institution_duplicates_are_blocked(repository, monkeypatch):
    original = repository._insert_person_audit
    def fail(connection, identity, action, *args, **kwargs):
        if action == 'INSTRUMENT_PROFILE':
            raise RuntimeError('synthetic failure')
        return original(connection, identity, action, *args, **kwargs)
    monkeypatch.setattr(repository, '_insert_person_audit', fail)
    with pytest.raises(RuntimeError):
        repository.update_instrument('card', 'No guardar', 'CREDIT_CARD', institution_id='mp', last_four='0000')
    card = next(r for r in repository.list_all_instruments() if r['id']=='card')
    assert card['institution_id']=='bank' and card['alias']=='Tarjeta ficticia'
    with pytest.raises(ValueError, match='existe'):
        repository.update_institution('mp', ' banco FICTICIO ')
    with pytest.raises(ValueError):
        repository.add_instrument('bad', 'mp', 'No guardar', 'WALLET_BALANCE', last_four='123')
    assert not any(r['id']=='bad' for r in repository.list_all_instruments())


def test_family_pdf_concepts_receipts_and_bank_payment_stay_separate(repository, tmp_path):
    from sgccc.gui.app import write_family_pdf
    import pymupdf
    concepts = [dict(description='CFE octubre', amount_cents=20000, allocations={'mama': 20000}),
                dict(description='Amazon ficticio', amount_cents=13131, allocations={'owner': 13131})]
    repository.create_order(order_id='manual', ordered_at='2026-10-11', merchant='Comercio ficticio',
                            instrument_id='card', original_cents=33131, discount_cents=3000, charged_cents=30131,
                            concepts=concepts, allocations=({'user_id':'mama','amount_cents':20000}, {'user_id':'owner','amount_cents':13131}))
    repository.record_receipt(payment_id='receipt', receivable_id='order:manual:mama', amount_cents=5000, received_at='2026-10-11')
    assert repository.list_card_summaries()[0]['remaining_cents'] == 30131
    repository.record_institution_payment(payment_id='bank-payment', instrument_id='card', paid_at='2026-10-11', amount_cents=1000)
    before = finance_snapshot(repository)
    statement = repository.family_statement('mama')
    assert statement['assigned_cents']==20000 and statement['paid_cents']==5000 and statement['remaining_cents']==15000
    assert statement['rows'][0]['concepts'][0]['description']=='CFE octubre'
    path = tmp_path / 'anonymous-family.pdf'
    write_family_pdf(statement, path)
    with pymupdf.open(path) as pdf:
        text = ''.join(p.get_text() for p in pdf)
        assert 'CFE octubre' in text and '$150.00 MXN' in text and '$50.00 MXN' in text
    assert finance_snapshot(repository) == before
    assert repository.dashboard_summary()['institutional_balance_cents']==29131


def test_forecast_breakdown_and_refunded_family_report_never_count_repurchase_twice(repository):
    reference_case(repository)
    before = finance_snapshot(repository)
    breakdown = repository.expected_result_breakdown()
    assert len(breakdown)==2 and sum(r['result_cents'] for r in breakdown)==-37993
    assert next(r for r in breakdown if r['order_id']=='order')['result_cents']==1907
    statement = repository.family_statement('mama')
    assert statement['assigned_cents']==70507 and statement['remaining_cents']==70507
    row = next(r for r in statement['rows'] if r['order_id']=='order')
    assert sum(c['amount_cents'] for c in row['concepts'])+row['concept_adjustment_cents']==50507
    report = repository.database.integrity_report()
    assert report['ok']
    assert finance_snapshot(repository)==before


def encrypted_repo(path):
    db = LocalDatabase.open(path, 'synthetic-backup-key')
    db.migrate()
    repo = FinanceRepository(db)
    repo.add_person('owner', 'Persona ficticia', is_owner=True)
    return db, repo


def test_encrypted_backup_restore_and_reopen_with_safety_copy(tmp_path):
    db, repo = encrypted_repo(tmp_path / 'synthetic.db')
    backup = tmp_path / 'backup.db'
    db.create_backup(backup)
    assert not backup.read_bytes().startswith(b'SQLite format 3')
    repo.add_person('later', 'Otra persona ficticia')
    safety = tmp_path / 'safety.db'
    db.verify_backup(backup)
    db.restore_backup(backup, safety)
    assert len(repo.list_people())==1 and db.integrity_report()['ok']
    db.close()
    assert db._session_key is None
    reopened = LocalDatabase.open(tmp_path / 'synthetic.db', 'synthetic-backup-key')
    assert len(FinanceRepository(reopened).list_people())==1
    reopened.close()
    previous = LocalDatabase.open(safety, 'synthetic-backup-key')
    assert len(FinanceRepository(previous).list_people())==2
    previous.close()


@pytest.mark.parametrize('kind', ['corrupt', 'wrong-key', 'plaintext', 'self', 'old-version', 'safety-exists'])
def test_bad_restore_never_changes_active_records(tmp_path, kind):
    db, repo = encrypted_repo(tmp_path / 'synthetic.db')
    backup = tmp_path / 'source.db'
    if kind=='corrupt':
        backup.write_bytes(b'not a database')
    elif kind=='plaintext':
        import sqlite3
        connection=sqlite3.connect(backup)
        connection.execute('CREATE TABLE dummy(id)')
        connection.close()
    elif kind=='wrong-key':
        other=LocalDatabase.open(backup, 'different-synthetic-key')
        other.migrate()
        other.close()
    elif kind=='self':
        backup=tmp_path / 'synthetic.db'
    elif kind=='old-version':
        old=LocalDatabase.open(backup, 'synthetic-backup-key')
        old.migrate(10)
        old.close()
    else:
        db.create_backup(backup)
    safety=tmp_path/'safety.db'
    if kind=='safety-exists': safety.write_bytes(b'keep this file')
    before=[tuple(r) for r in db.connection.execute('SELECT * FROM person')]
    with pytest.raises(DatabaseSecurityError): db.restore_backup(backup, safety)
    assert [tuple(r) for r in db.connection.execute('SELECT * FROM person')]==before
    assert db.integrity_report()['ok']
    db.close()


def test_long_family_pdf_paginates_without_losing_concepts(repository, tmp_path):
    from sgccc.gui.app import write_family_pdf
    import pymupdf
    concepts=[dict(description=f'CFE octubre concepto ficticio {i:03d} & texto largo para revisar', amount_cents=100, allocations={'mama':100}) for i in range(80)]
    repository.create_order(order_id='long', ordered_at='2026-10-11', merchant='Ficticio', instrument_id='card',
                            original_cents=8000, charged_cents=8000, discount_cents=0,
                            concepts=concepts, allocations=({'user_id':'mama','amount_cents':8000}, {'user_id':'owner','amount_cents':0}))
    output=tmp_path/'long.pdf'
    write_family_pdf(repository.family_statement('mama'), output)
    with pymupdf.open(output) as document:
        text=''.join(page.get_text() for page in document)
        assert len(document)>1
        assert all(f'{i:03d}' in text for i in range(80))


def test_main_screens_and_manual_scroll_render_small(repository, tmp_path, monkeypatch):
    from sgccc.gui.app import MainWindow, create_application
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    app=create_application([])
    font=QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    if font>=0: app.setFont(QFont(QFontDatabase.applicationFontFamilies(font)[0], 10))
    reference_case(repository)
    window=MainWindow(database=repository.database)
    errors=[]
    monkeypatch.setattr(window, '_show_error', errors.append)
    window.show()
    for width,height in ((1100,680),(680,480)):
        window.resize(width,height)
        for page,name in ((0,'inicio'),(2,'pedidos'),(3,'cobros'),(4,'tarjetas'),(6,'configuracion')):
            window._show_page(page)
            app.processEvents()
            assert window.width()==width and window.height()==height
            if page == 2:
                assert window.orders_table.height() >= 140
                assert window.order_detail.height() >= 60
            window.grab().save(str(tmp_path/f'{name}-{width}.png'))
    window._show_page(0)
    window.dashboard_result_toggle.click()
    assert '$379.93 MXN' in window.dashboard_result_details.toPlainText()
    window._show_page(4)
    row=next(r for r in range(window.cards_table.rowCount()) if window.cards_table.item(r,12).text()=='card')
    window.cards_table.selectRow(row)
    window.admin_card_institution.setCurrentIndex(window.admin_card_institution.findData('mp'))
    window.admin_card_last_four.setText('0000')
    window._edit_instrument()
    assert repository.instrument_profile('card')['last_four']=='0000'
    window._show_page(2)
    window._open_manual_expense()
    window.manual_dialog.resize(520,320)
    window.manual_concepts.item(0,0).setText('Captura ficticia conservada')
    window.manual_scroll.verticalScrollBar().setValue(window.manual_scroll.verticalScrollBar().maximum())
    app.processEvents()
    assert window.save_order_button.isVisible() and window.cancel_manual_button.isVisible()
    window.manual_dialog.grab().save(str(tmp_path/'manual-small.png'))
    QTest.keyClick(window.manual_dialog, Qt.Key.Key_Escape)
    window._open_manual_expense()
    assert window.manual_concepts.item(0,0).text()=='Captura ficticia conservada'
    window.manual_dialog.reject()
    assert not errors
    window.close()
    app.processEvents()


@pytest.mark.parametrize('kind', ['order', 'purchase', 'calendar', 'extra', 'fee'])
def test_bad_dates_never_leave_partial_records(repository, kind):
    before=finance_snapshot(repository)
    counts={table:repository.database.connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('cash_extra','deposit_fee','instrument_calendar')}
    with pytest.raises(ValueError, match='fecha|Fecha'):
        if kind=='order':
            repository.create_order(order_id='bad', ordered_at='2026-02-30', merchant='Ficticio', instrument_id='card',
                                    original_cents=100, discount_cents=0, charged_cents=100,
                                    allocations=({'user_id':'owner','amount_cents':100},))
        elif kind=='purchase':
            repository.create_purchase(purchase_id='bad', purchased_at='', merchant='Ficticio', instrument_id='card',
                                       products=({'id':'p','description':'Ficticio','quantity':1,'unit_price_cents':100},), allocations=())
        elif kind=='calendar':
            repository.save_instrument_calendar(calendar_id='bad', instrument_id='card', effective_from='ayer', closing_day=10, due_day=20)
        elif kind=='extra':
            repository.record_extra(extra_id='bad', user_id='owner', received_at='mal', amount_cents=100, description='Ficticio')
        else:
            repository.record_deposit_fee(fee_id='bad', incurred_at='mal', amount_cents=100, description='Ficticio')
    assert finance_snapshot(repository)==before
    for table,count in counts.items(): assert repository.database.connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]==count


def test_wallet_calendar_and_initial_balance_type_changes_are_rejected(repository):
    with pytest.raises(ValueError, match='billetera'):
        repository.save_instrument_calendar(calendar_id='bad', instrument_id='wallet', effective_from='2026-10-11', closing_day=10, due_day=20)


def test_cancelled_restore_copy_keeps_active_database_and_safety(tmp_path, monkeypatch):
    db,repo=encrypted_repo(tmp_path/'synthetic.db')
    source=tmp_path/'source.db'
    db.create_backup(source)
    repo.add_person('later','Persona posterior ficticia')
    opened=db._open_verified_backup
    class FailedSource:
        def __init__(self, original): self.original=original; self.connection=self
        def backup(self, destination): raise RuntimeError('synthetic copy failure')
        def close(self): self.original.close()
    monkeypatch.setattr(db, '_open_verified_backup', lambda path: FailedSource(opened(path)))
    safety=tmp_path/'safety.db'
    with pytest.raises(DatabaseSecurityError): db.restore_backup(source,safety)
    assert len(repo.list_people())==2 and db.integrity_report()['ok']
    db.close()
    original=LocalDatabase.open(safety,'synthetic-backup-key')
    assert len(FinanceRepository(original).list_people())==2
    original.close()


def test_reentrant_manual_save_records_one_charge_and_keeps_error_draft(repository, monkeypatch):
    from sgccc.gui.app import MainWindow, create_application
    app=create_application([])
    window=MainWindow(database=repository.database)
    errors=[]
    monkeypatch.setattr(window, '_show_error', errors.append)
    window._open_manual_expense()
    window.order_merchant.setText('Ficticio')
    window.manual_concepts.item(0,0).setText('CFE octubre')
    window.manual_concepts.item(0,1).setText('200.00')
    window.order_charged.setText('200.00')
    window.order_date.setText('2026-02-30')
    window._save_order()
    assert errors and window.manual_dialog.isVisible()
    assert window.manual_concepts.item(0,0).text()=='CFE octubre'
    assert not repository.list_orders()
    window.order_date.setText('2026-10-11')
    original=repository.create_order
    def reentrant(**kwargs):
        window._save_order()
        return original(**kwargs)
    monkeypatch.setattr(window.repository, 'create_order', reentrant)
    window._save_order()
    assert len(repository.list_orders())==1
    assert repository.dashboard_summary()['institutional_balance_cents']==20000
    assert not window.manual_dialog.isVisible()
    window.close()
    app.processEvents()


def test_family_report_button_uses_selected_person_and_readonly_diagnostic(repository, monkeypatch, tmp_path):
    from sgccc.gui.app import MainWindow, create_application
    from PySide6.QtWidgets import QFileDialog
    import pymupdf
    app=create_application([])
    reference_case(repository)
    window=MainWindow(database=repository.database)
    window.show()
    window._show_page(3)
    row=next(r for r in range(window.collection_items.rowCount()) if window.collection_items.item(r,1).text()=='mama')
    window.collection_items.selectRow(row)
    path=tmp_path/'anonymous-report.pdf'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(path),'PDF'))
    before=finance_snapshot(repository)
    window.family_pdf_button.click()
    with pymupdf.open(path) as pdf:
        text=''.join(page.get_text() for page in pdf)
        assert 'MAMÁ' in text and '$705.07 MXN' in text
    window._show_page(6)
    window._run_integrity()
    assert 'correctas' in window.maintenance_result.toPlainText()
    assert finance_snapshot(repository)==before
    window.close()
    app.processEvents()


def test_authenticated_maintenance_ui_cancel_restore_and_reopen(tmp_path, monkeypatch):
    from sgccc.gui.app import MainWindow, create_application
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    app=create_application([])
    db,repo=encrypted_repo(tmp_path/'synthetic.db')
    window=MainWindow(database=db, test_mode=True)
    errors=[]
    monkeypatch.setattr(window,'_show_error',errors.append)
    window.show()
    window._show_page(6)
    backup=tmp_path/'backup.db'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(backup),'DB'))
    window._create_backup()
    assert backup.exists() and 'verificado' in window.maintenance_result.toPlainText()
    repo.add_person('later','Persona posterior ficticia')
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *args:(str(backup),'DB'))
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.No)
    window._restore_backup()
    assert len(repo.list_people())==2 and not (tmp_path/'backups').exists()
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
    window._restore_backup()
    assert len(repo.list_people())==1 and len(list((tmp_path/'backups').glob('*.db')))==1
    assert not errors
    window.close()
    app.processEvents()
    reopened=LocalDatabase.open(tmp_path/'synthetic.db','synthetic-backup-key')
    assert reopened.integrity_report()['ok'] and len(FinanceRepository(reopened).list_people())==1
    reopened.close()


def test_forecast_avoids_repeated_full_scans_for_growing_history(repository, monkeypatch):
    for index in range(60):
        repository.create_order(order_id=f'o-{index}', ordered_at='2026-10-11', merchant='Ficticio', instrument_id='card',
                                original_cents=1000, discount_cents=100, charged_cents=900,
                                allocations=({'user_id':'owner','amount_cents':500},{'user_id':'mama','amount_cents':500}))
    original=repository.list_collection_items
    calls=[]
    def counted(): calls.append(True); return original()
    monkeypatch.setattr(repository,'list_collection_items',counted)
    summary=repository.dashboard_summary()
    assert len(calls)<=2 and summary['personal_expected_result_cents']==-24000
    assert summary['discount_benefit_cents']==6000 and summary['institutional_balance_cents']==54000
