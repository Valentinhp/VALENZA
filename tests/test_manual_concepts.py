import copy
import pytest

from sgccc.persistence.database import LocalDatabase
from sgccc.persistence.repository import FinanceRepository


@pytest.fixture
def repository():
    db = LocalDatabase.open(':memory:', 'synthetic', allow_synthetic_in_memory=True)
    db.migrate()
    repo = FinanceRepository(db)
    repo.add_person('owner', 'Yo', is_owner=True)
    repo.add_person('family', 'Familiar ficticio')
    repo.add_institution('bank', 'Banco ficticio')
    repo.add_instrument('card', 'bank', 'Tarjeta ficticia', 'CREDIT_CARD')
    yield repo
    db.close()


def concepts():
    return [dict(description='Libro ficticio', amount_cents=10000, allocations={'owner': 10000, 'family': 0}),
            dict(description='Accesorio ficticio', amount_cents=20000, allocations={'owner': 0, 'family': 20000}),
            dict(description='Artículo compartido', amount_cents=5000, allocations={'owner': 2500, 'family': 2500})]


def save(repo, mode='CASH'):
    repo.create_order(order_id='amazon', ordered_at='2026-10-11', merchant='Amazon ficticio', instrument_id='card',
        original_cents=35000, discount_cents=3000, charged_cents=32000,
        allocations=({'user_id': 'owner', 'amount_cents': 12500}, {'user_id': 'family', 'amount_cents': 22500}),
        concepts=concepts(), purchase_mode=mode,
        financing_specs=('2026-11-11', '2026-12-11') if mode == 'MSI' else None)


@pytest.mark.parametrize('mode', ['CASH', 'MSI'])
def test_concepts_persist_and_edits_preserve_one_charge_and_financing(repository, mode):
    save(repository, mode)
    db = repository.database.connection
    original = repository.get_order('amazon')
    assert original['manual_concepts'] == concepts() and original['import_evidence'] is None
    assert db.execute("SELECT COUNT(*) FROM audit_event WHERE action='PDF_IMPORTED'").fetchone()[0] == 0
    cards = repository.list_card_summaries()
    plan = original['financing_plan']
    edited = concepts()
    edited[0]['description'] = 'Libro corregido'
    edited[0]['allocations'] = {'owner': 0, 'family': 10000}
    repository.update_manual_concepts('amazon', edited, expected_concepts=concepts())
    updated = repository.get_order('amazon')
    assert updated['manual_concepts'] == edited
    assert updated['charged_cents'] == 32000 and updated['discount_cents'] == 3000
    assert updated['financing_plan'] == plan and updated['installments'] == original['installments']
    assert repository.list_card_summaries() == cards
    assert len(repository.list_orders()) == 1
    accounts = {a['user_id']: a for a in repository.list_collection_items()}
    assert accounts['owner']['sale_cents'] == 2500 and accounts['family']['sale_cents'] == 32500
    assert sum(a['sale_cents'] for a in accounts.values()) == 35000
    audit = db.execute("SELECT old_value,new_value FROM audit_event WHERE action='MANUAL_CONCEPTS_SAVED' ORDER BY rowid DESC LIMIT 1").fetchone()
    assert 'Libro ficticio' in audit['old_value'] and 'Libro corregido' in audit['new_value']
    before = db.total_changes
    repository.update_manual_concepts('amazon', edited)
    assert db.total_changes == before


@pytest.mark.parametrize('problem', ['sum', 'split', 'description', 'inactive', 'fraction'])
def test_invalid_concepts_are_atomic(repository, problem):
    invalid = concepts()
    if problem == 'sum': invalid[0]['amount_cents'] += 1
    if problem == 'split': invalid[0]['allocations']['owner'] -= 1
    if problem == 'description': invalid[0]['description'] = ' '
    if problem == 'fraction': invalid[0]['amount_cents'] = 10000.5
    if problem == 'inactive': repository.deactivate_person('family')
    with pytest.raises(ValueError):
        repository.create_order(order_id='bad', ordered_at='2026-10-11', merchant='Ficticio', instrument_id='card',
            original_cents=35000, discount_cents=3000, charged_cents=32000,
            allocations=({'user_id': 'owner', 'amount_cents': 12500}, {'user_id': 'family', 'amount_cents': 22500}), concepts=invalid)
    assert repository.list_orders() == []
    assert repository.list_collection_items() == []


def test_paid_and_stale_edits_are_rejected_without_partial_changes(repository):
    save(repository)
    repository.record_receipt(payment_id='receipt', receivable_id='order:amazon:owner', amount_cents=10000, received_at='2026-10-11')
    changed = concepts()
    changed[0]['allocations'] = {'owner': 0, 'family': 10000}
    with pytest.raises(ValueError, match='abonos'):
        repository.update_manual_concepts('amazon', changed)
    assert repository.get_order('amazon')['manual_concepts'] == concepts()
    changed = concepts()
    changed[0]['description'] = 'Descripción corregida'
    repository.update_manual_concepts('amazon', changed)
    with pytest.raises(ValueError, match='cambiaron'):
        repository.update_manual_concepts('amazon', concepts(), expected_concepts=concepts())
    assert repository.dashboard_summary()['personal_pending_cents'] == 2500


def test_audit_failure_rolls_back_repartition(repository):
    save(repository)
    repository.database.connection.execute("""CREATE TRIGGER reject_manual_edit BEFORE INSERT ON audit_event
        WHEN NEW.action='MANUAL_CONCEPTS_SAVED' BEGIN SELECT RAISE(ABORT, 'synthetic audit failure'); END""")
    changed = concepts()
    changed[0]['allocations'] = {'owner': 0, 'family': 10000}
    with pytest.raises(Exception, match='synthetic audit failure'):
        repository.update_manual_concepts('amazon', changed)
    assert repository.get_order('amazon')['manual_concepts'] == concepts()
    assert repository.dashboard_summary()['personal_pending_cents'] == 12500


def test_repartition_to_new_person_adds_only_the_needed_participation(repository):
    save(repository)
    repository.add_person('other', 'Otra persona ficticia')
    changed = concepts()
    changed[0]['allocations'] = {'owner': 0, 'other': 10000}
    repository.update_manual_concepts('amazon', changed)
    assert sum(a['sale_cents'] for a in repository.list_collection_items()) == 35000
    assert repository.dashboard_summary()['institutional_balance_cents'] == 32000
    assert len(repository.list_orders()) == 1


def test_concepts_survive_encrypted_reopen(repository, tmp_path):
    save(repository)
    backup = tmp_path / 'synthetic-manual-concepts.db'
    database = LocalDatabase.open(backup, 'synthetic-password')
    database.migrate()
    target = FinanceRepository(database)
    target.add_person('owner', 'Yo', is_owner=True)
    target.add_person('family', 'Familiar ficticio')
    target.add_institution('bank', 'Banco ficticio')
    target.add_instrument('card', 'bank', 'Tarjeta ficticia', 'CREDIT_CARD')
    save(target)
    database.close()
    reopened = LocalDatabase.open(backup, 'synthetic-password')
    assert FinanceRepository(reopened).get_order('amazon')['manual_concepts'] == concepts()
    reopened.close()


@pytest.mark.parametrize('size', [(760, 580), (520, 320)])
def test_manual_dialog_draft_catalogs_save_and_edit(repository, monkeypatch, tmp_path, size):
    from sgccc.gui.app import MainWindow, create_application
    from PySide6.QtWidgets import QMessageBox
    from PySide6.QtGui import QFont, QFontDatabase
    app = create_application([])
    font = QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    if font >= 0:
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(font)[0], 10))
    errors = []
    monkeypatch.setattr(MainWindow, '_show_information', lambda *args: None)
    monkeypatch.setattr(MainWindow, '_show_error', lambda _, message: errors.append(message))
    window = MainWindow(database=repository.database)
    window.resize(820, 520)
    window.show()
    window._show_page(2)
    app.processEvents()
    assert not window.order_merchant.isVisible()
    assert window.new_expense_button.isVisible() and window.orders_table.isVisible()
    window.grab().save(str(tmp_path / 'orders-list.png'))
    window._open_manual_expense()
    window.manual_concepts.removeRow(0)
    for concept in concepts():
        window._add_manual_concept(concept)
    window.order_merchant.setText('Amazon ficticio')
    window.order_charged.setText('320.00')
    window.manual_dialog.resize(*size)
    app.processEvents()
    before = copy.deepcopy(window._read_manual_concepts())
    selected = window.order_instrument.currentData()
    repository.add_person('new', 'Persona nueva ficticia')
    window._sync_catalogs()
    after = window._read_manual_concepts()
    assert all(a['description'] == b['description'] and a['amount_cents'] == b['amount_cents']
               and {k: v for k, v in a['allocations'].items() if v} == {k: v for k, v in b['allocations'].items() if v}
               for a, b in zip(before, after))
    assert window.order_instrument.currentData() == selected
    assert window.manual_concepts.cellWidget(0, 2).person.findData('new') >= 0
    window.manual_scroll.verticalScrollBar().setValue(window.manual_scroll.verticalScrollBar().maximum())
    app.processEvents()
    assert window.save_order_button.isVisible() and window.cancel_manual_button.isVisible()
    assert window.save_order_button.mapTo(window.manual_dialog, window.save_order_button.rect().bottomRight()).y() < window.manual_dialog.height()
    window.manual_dialog.grab().save(str(tmp_path / 'manual-expense.png'))
    window.manual_concepts.horizontalScrollBar().setValue(window.manual_concepts.horizontalScrollBar().maximum())
    window.manual_concepts.verticalScrollBar().setValue(window.manual_concepts.verticalScrollBar().maximum())
    app.processEvents()
    split = window.manual_concepts.cellWidget(2, 2)
    assert split.divide.mapTo(window.manual_concepts.viewport(), split.divide.rect().bottomRight()).x() <= window.manual_concepts.viewport().width()
    assert window.save_order_button.isVisible()
    window.manual_dialog.grab().save(str(tmp_path / 'manual-split-scroll.png'))
    window.manual_concepts.item(0, 0).setText('')
    window._save_order()
    assert errors and window.manual_dialog.isVisible() and not repository.list_orders()
    errors.clear()
    window.manual_concepts.item(0, 0).setText('Libro ficticio')
    window.save_order_button.click()
    app.processEvents()
    assert not errors and not window.manual_dialog.isVisible()
    assert len(repository.list_orders()) == 1
    window.orders_table.selectRow(0)
    window._edit_manual_expense()
    window.manual_concepts.item(0, 0).setText('Libro editado después de guardar')
    assignment = window.manual_concepts.cellWidget(0, 2)
    assignment.person.setCurrentIndex(assignment.person.findData('family'))
    window._save_order()
    assert not errors and len(repository.list_orders()) == 1
    order = repository.get_order(repository.list_orders()[0]['id'])
    assert order['manual_concepts'][0]['description'] == 'Libro editado después de guardar'
    assert order['charged_cents'] == 32000 and order['owner_cents'] == 2500
    assert repository.dashboard_summary()['institutional_balance_cents'] == 32000
    assert 'Libro editado' in window.order_detail.toPlainText()
    window._edit_manual_expense()
    window.manual_concepts.item(0, 0).setText('Cambio cancelado')
    window.cancel_manual_button.click()
    assert window.manual_edit_id is None
    assert repository.get_order(order['id'])['manual_concepts'][0]['description'] == 'Libro editado después de guardar'
    window.close()
