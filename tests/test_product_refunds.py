import copy
from pathlib import Path

import pytest

from sgccc.ocr.order_import import parse_receipt
from sgccc.persistence.database import LocalDatabase, SCHEMA_VERSION, DatabaseSecurityError
from sgccc.persistence.repository import FinanceRepository


@pytest.fixture
def repository():
    database = LocalDatabase.open(':memory:', 'synthetic', allow_synthetic_in_memory=True)
    database.migrate()
    repo = FinanceRepository(database)
    repo.add_person('owner', 'Yo', is_owner=True)
    repo.add_person('mama', 'MAMÁ')
    repo.add_institution('bank', 'Banco ficticio')
    repo.add_institution('mp', 'Mercado Pago ficticio')
    repo.add_instrument('card', 'bank', 'Tarjeta ficticia', 'CREDIT_CARD')
    repo.add_instrument('wallet', 'mp', 'Billetera ficticia', 'WALLET_BALANCE')
    repo.add_instrument('other', 'mp', 'Otro destino ficticio', 'OTHER')
    yield repo
    database.close()


def purchase_args(status='ACCREDITED', destination='card', absorbs='mama'):
    evidence = parse_receipt((Path(__file__).parent / 'fixtures_synthetic' / 'mp_openpdf.txt').read_text(encoding='utf-8'))
    evidence['fingerprint'] = 'anonymous-refund-document'
    for index, product in enumerate(evidence['products']):
        product['source_index'] = index
        product['allocations'] = {'owner': 0 if index == 4 else product['unit'],
                                  'mama': product['unit'] if index == 4 else 0}
    return dict(order_id='order', ordered_at=evidence['date'], merchant='Comercio ficticio',
        instrument_id='card', original_cents=60287, discount_cents=6029, charged_cents=54258,
        allocations=({'user_id': 'owner', 'amount_cents': 39508}, {'user_id': 'mama', 'amount_cents': 20779}),
        import_evidence=evidence,
        product_refunds=({'product_index': 4, 'amount_cents': 18657, 'destination_id': destination,
            'status': status, 'accredited_at': '2026-10-10' if status == 'ACCREDITED' else None,
            'final_allocations': {'owner': 2122 if absorbs == 'owner' else 0,
                                  'mama': 2122 if absorbs == 'mama' else 0}},))


def summaries(repo):
    return {item['instrument_id']: item for item in repo.list_card_summaries()}


def repurchase_proposal(apply=True, split=None):
    return dict(amount_cents=12999, ordered_at='2026-10-11', instrument_id='wallet',
                apply_surplus=apply, final_allocations=split or {'owner': 0, 'mama': 15121 if apply else 20779})


@pytest.mark.parametrize('existing', [False, True])
def test_complete_repurchase_case_preserves_refund_and_revises_2122_once(repository, existing):
    args = purchase_args(destination='wallet')
    if existing:
        repository.create_order(**args)
        refund_id = repository.list_product_refunds('order')[0]['id']
        assert repository.dashboard_summary()['receivables_cents'] == 2122
        linked_id = repository.register_refund_repurchase(refund_id, repurchase_proposal())
    else:
        args['product_refunds'][0]['repurchase'] = repurchase_proposal()
        args['product_refunds'][0]['final_allocations'] = {'owner': 0, 'mama': 15121}
        repository.create_order(**args)
        refund = repository.list_product_refunds('order')[0]
        refund_id, linked_id = refund['id'], refund['repurchase']['order_id']
    original = repository.get_order('order')
    assert original['discount_cents'] == 6029 and original['charged_cents'] == 54258
    assert next(a for a in original['allocations'] if a['user_id'] == 'mama')['amount_cents'] == 20779
    assert repository.dashboard_summary()['receivables_cents'] == 15121
    assert summaries(repository)['card']['remaining_cents'] == 54258
    assert summaries(repository)['wallet']['wallet_balance_cents'] == 5658

    linked = repository.get_order(linked_id)
    assert linked['charged_cents'] == 12999 and linked['instrument_id'] == 'wallet'
    assert all(r['remaining_cents'] == 0 for r in repository.list_collection_items() if r['order_id'] == linked_id)
    baseline = repository.database.connection.execute('SELECT * FROM product_refund_adjustment WHERE refund_id=? AND user_id=?',
                                                      (refund_id, 'mama')).fetchone()
    assert baseline['final_cents'] == 2122  # Audit history retained, not overwritten.
    assert original['product_refunds'][0]['repurchase']['applied_cents'] == 5658
    assert repository.database.connection.execute("SELECT COUNT(*) FROM institution_movement WHERE kind='REFUND'").fetchone()[0] == 1
    assert repository.database.connection.execute('SELECT COUNT(*) FROM institution_payment').fetchone()[0] == 0
    # A subsequent genuine payment only changes Nu. Its source is not invented.
    repository.record_institution_payment(payment_id='actual-transfer', instrument_id='card',
                                         paid_at='2026-10-11', amount_cents=5658)
    assert summaries(repository)['card']['remaining_cents'] == 48600
    assert repository.dashboard_summary()['receivables_cents'] == 15121
    with pytest.raises(ValueError, match='ya tiene'):
        repository.register_refund_repurchase(refund_id, repurchase_proposal())


@pytest.mark.parametrize('apply,split,expected_mama', [
    (False, {'owner': 0, 'mama': 20779}, 20779),
    (True, {'owner': 15121, 'mama': 0}, 0),
    (True, {'owner': 5121, 'mama': 10000}, 10000),
])
def test_repurchase_remaining_responsibility_is_explicit(repository, apply, split, expected_mama):
    repository.create_order(**purchase_args(destination='wallet'))
    refund_id = repository.list_product_refunds('order')[0]['id']
    repository.register_refund_repurchase(refund_id, repurchase_proposal(apply, split))
    assert repository.dashboard_summary()['receivables_cents'] == expected_mama
    assert summaries(repository)['wallet']['wallet_balance_cents'] == 5658
    assert summaries(repository)['card']['remaining_cents'] == 54258


@pytest.mark.parametrize('changes', [
    {'amount_cents': 18658}, {'amount_cents': 12999.5}, {'ordered_at': ''},
    {'ordered_at': '2026-10-09'}, {'instrument_id': 'card'},
    {'final_allocations': {'owner': 0, 'mama': 2122}},
])
def test_invalid_repurchase_does_not_leave_partial_records(repository, changes):
    repository.create_order(**purchase_args(destination='wallet'))
    refund_id = repository.list_product_refunds('order')[0]['id']
    before = repository.database.connection.total_changes
    with pytest.raises(ValueError):
        repository.register_refund_repurchase(refund_id, {**repurchase_proposal(), **changes})
    assert len(repository.list_orders()) == 1
    assert summaries(repository)['wallet']['wallet_balance_cents'] == 18657
    assert repository.dashboard_summary()['receivables_cents'] == 2122
    assert repository.database.connection.total_changes == before


def test_repurchase_failure_rolls_back_original_import_too(repository):
    args = purchase_args(destination='wallet')
    args['product_refunds'][0].update(repurchase=repurchase_proposal(), final_allocations={'owner': 0, 'mama': 15121})
    repository.database.connection.execute("""CREATE TRIGGER fail_repurchase BEFORE INSERT ON product_repurchase_adjustment
        BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
    with pytest.raises(Exception, match='synthetic failure'):
        repository.create_order(**args)
    for table in ('order_record', 'receivable', 'institution_movement', 'imported_product_refund',
                  'product_refund_repurchase', 'audit_event'):
        # Person/instrument configuration already has its own audit entries.
        if table != 'audit_event':
            assert repository.database.connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
    assert not repository.database.connection.execute("SELECT 1 FROM audit_event WHERE action='ORDER_CREATED'").fetchone()


def test_repurchase_requires_received_funds_and_preserves_pending_refund(repository):
    repository.create_order(**purchase_args(status='PENDING', destination='wallet'))
    refund_id = repository.list_product_refunds('order')[0]['id']
    with pytest.raises(ValueError, match='acreditada'):
        repository.register_refund_repurchase(refund_id, repurchase_proposal())
    assert repository.dashboard_summary()['receivables_cents'] == 20779
    assert len(repository.list_orders()) == 1


def test_migration_preserves_previous_refund_and_repurchase_history(repository):
    # The official migration adds only the link/revision tables, preserving v13 refunds.
    database = repository.database
    args = purchase_args(destination='wallet')
    repository.create_order(**args)
    refund_id = repository.list_product_refunds('order')[0]['id']
    database.migrate(13)
    row = dict(database.connection.execute('SELECT * FROM imported_product_refund WHERE id=?', (refund_id,)).fetchone())
    database.migrate()
    assert dict(database.connection.execute('SELECT * FROM imported_product_refund WHERE id=?', (refund_id,)).fetchone()) == row
    assert repository.dashboard_summary()['receivables_cents'] == 2122
    repository.register_refund_repurchase(refund_id, repurchase_proposal())
    assert repository.dashboard_summary()['receivables_cents'] == 15121


def participations(repo):
    return {item['user_id']: item for item in repo.list_collection_items()}


def test_original_product_discount_and_participations_preserved(repository):
    repository.create_order(**purchase_args())
    order = repository.get_order('order')
    assert (order['original_cents'], order['discount_cents'], order['charged_cents']) == (60287, 6029, 54258)
    assert {r['user_id']: r['amount_cents'] for r in order['allocations']} == {'owner': 39508, 'mama': 20779}
    product = order['import_evidence']['products'][4]
    assert product['unit'] == 20779 and product['allocations']['mama'] == 20779
    assert participations(repository)['mama']['remaining_cents'] == 2122
    assert participations(repository)['mama']['original_sale_cents'] == 20779
    assert participations(repository)['mama']['adjustment_cents'] == -18657
    assert summaries(repository)['card']['remaining_cents'] == 35601
    assert order['import_evidence']['paid'] == 35601
    assert order['product_refunds'][0]['amount_cents'] == 18657
    for table in ('user_payment', 'institution_payment', 'receipt_application'):
        assert repository.database.connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
    assert repository.database.connection.execute('SELECT amount_cents FROM institution_movement').fetchone()[0] == 18657
    assert repository.database.connection.execute("SELECT COUNT(*) FROM audit_event WHERE entity_type='refund'").fetchone()[0] == 1


def test_owner_can_absorb_remaining_cost_without_rewriting_original(repository):
    repository.create_order(**purchase_args(absorbs='owner'))
    people = participations(repository)
    assert people['mama']['remaining_cents'] == 0
    assert people['owner']['remaining_cents'] == 41630
    assert repository.dashboard_summary()['personal_pending_cents'] == 41630
    assert repository.dashboard_summary()['receivables_cents'] == 0


@pytest.mark.parametrize('destination,balance_field', [('wallet', 'wallet_balance_cents'), ('other', 'cash_balance_cents')])
def test_refund_to_noncredit_destination_never_reduces_card_debt(repository, destination, balance_field):
    repository.create_order(**purchase_args(destination=destination))
    cards = summaries(repository)
    assert cards['card']['remaining_cents'] == 54258
    assert cards[destination][balance_field] == 18657
    assert cards[destination]['remaining_cents'] == cards[destination]['credit_cents'] == 0
    summary = repository.dashboard_summary()
    assert summary['institutional_balance_cents'] == 54258
    assert summary['credit_cents'] == 0


def test_wallet_purchase_is_spending_not_credit_debt(repository):
    args = purchase_args(destination='wallet')
    args['instrument_id'] = 'wallet'
    repository.create_order(**args)
    assert summaries(repository)['wallet']['wallet_balance_cents'] == -35601
    assert repository.dashboard_summary()['institutional_balance_cents'] == 0


def test_pending_refund_has_no_balance_effect_and_accredits_once(repository):
    repository.create_order(**purchase_args(status='PENDING'))
    refund = repository.list_product_refunds('order')[0]
    assert refund['accredited_at'] is None and refund['movement_id'] is None
    assert participations(repository)['mama']['remaining_cents'] == 20779
    assert summaries(repository)['card']['remaining_cents'] == 54258
    assert repository.database.connection.execute('SELECT COUNT(*) FROM institution_movement').fetchone()[0] == 0
    repository.confirm_product_refund(refund['id'], '2026-10-10')
    repository.confirm_product_refund(refund['id'], '2026-10-10')
    assert participations(repository)['mama']['remaining_cents'] == 2122
    assert summaries(repository)['card']['remaining_cents'] == 35601
    assert repository.database.connection.execute('SELECT COUNT(*) FROM institution_movement').fetchone()[0] == 1
    assert repository.database.connection.execute("SELECT COUNT(*) FROM audit_event WHERE action='PRODUCT_REFUND_ACCREDITED'").fetchone()[0] == 1


@pytest.mark.parametrize('status,date', [('ACCREDITED', None), ('ACCREDITED', 'invalid'), ('PENDING', '2026-10-10')])
def test_date_must_be_real_and_pending_has_no_invented_date(repository, status, date):
    args = purchase_args(status=status)
    args['product_refunds'][0]['accredited_at'] = date
    with pytest.raises(ValueError):
        repository.create_order(**args)
    assert repository.list_orders() == []


@pytest.mark.parametrize('change', ['amount', 'destination', 'allocation', 'original_allocation', 'duplicate_product'])
def test_invalid_refund_rolls_back_whole_import(repository, change):
    args = purchase_args()
    refund = args['product_refunds'][0]
    if change == 'amount':
        refund['amount_cents'] += 1
    elif change == 'destination':
        refund['destination_id'] = 'unknown'
    elif change == 'allocation':
        refund['final_allocations']['mama'] += 1
    elif change == 'original_allocation':
        args['import_evidence']['products'][4]['allocations']['mama'] -= 1
    else:
        args['product_refunds'] = (refund, copy.deepcopy(refund))
    with pytest.raises(ValueError):
        repository.create_order(**args)
    for table in ('order_record', 'order_allocation', 'receivable', 'imported_product_refund',
                  'product_refund_adjustment', 'institution_movement'):
        assert repository.database.connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
    assert not repository.database.connection.execute("SELECT 1 FROM audit_event WHERE entity_type IN ('order','refund')").fetchone()


def test_database_failure_leaves_no_partial_import(repository):
    repository.database.connection.execute("CREATE TRIGGER reject_refund BEFORE INSERT ON product_refund_adjustment BEGIN SELECT RAISE(ABORT, 'forced test failure'); END")
    with pytest.raises(Exception, match='forced test failure'):
        repository.create_order(**purchase_args())
    assert not repository.list_orders()
    assert not repository.list_collection_items()
    assert not repository.database.connection.execute('SELECT 1 FROM institution_movement').fetchone()
    assert not repository.database.connection.execute('SELECT 1 FROM imported_product_refund').fetchone()


def test_duplicate_document_refund_cannot_be_forced(repository):
    repository.create_order(**purchase_args())
    args = purchase_args()
    args.update(order_id='second', allow_duplicate=True)
    args['import_evidence']['fingerprint'] = 'different-file-same-receipt'
    with pytest.raises(ValueError, match='no se duplicará'):
        repository.create_order(**args)
    assert len(repository.list_orders()) == 1
    assert repository.database.connection.execute('SELECT COUNT(*) FROM institution_movement').fetchone()[0] == 1


def test_fractional_cents_are_rejected_without_rounding(repository):
    args = purchase_args()
    args['product_refunds'][0]['amount_cents'] = 18657.5
    with pytest.raises(ValueError, match='enteros en centavos'):
        repository.create_order(**args)
    assert repository.list_orders() == []


def test_collections_respect_adjusted_balance(repository):
    repository.create_order(**purchase_args())
    with pytest.raises(ValueError, match='excede'):
        repository.record_receipt(payment_id='too-much', receivable_id='order:order:mama', amount_cents=2123, received_at='2026-10-10')
    repository.record_receipt(payment_id='partial', receivable_id='order:order:mama', amount_cents=1000, received_at='2026-10-10')
    with pytest.raises(ValueError, match='excede'):
        repository.update_user_payment('partial', received_at='2026-10-10', amount_cents=2123)
    assert participations(repository)['mama']['remaining_cents'] == 1122


def test_accreditation_blocks_conflicting_existing_collections_without_partial_writes(repository):
    repository.create_order(**purchase_args(status='PENDING', absorbs='owner'))
    repository.record_receipt(payment_id='partial', receivable_id='order:order:mama', amount_cents=1000, received_at='2026-10-10')
    refund = repository.list_product_refunds('order')[0]
    with pytest.raises(ValueError, match='abonos'):
        repository.confirm_product_refund(refund['id'], '2026-10-10')
    assert repository.list_product_refunds('order')[0]['status'] == 'PENDING'
    assert not repository.database.connection.execute('SELECT 1 FROM institution_movement').fetchone()
    assert participations(repository)['mama']['remaining_cents'] == 19779


def test_order_with_refund_cannot_be_cancelled_leaving_orphan_credit(repository):
    repository.create_order(**purchase_args())
    with pytest.raises(ValueError, match='devoluciones'):
        repository.cancel_order('order', reason='Cancelación ficticia')
    assert summaries(repository)['card']['remaining_cents'] == 35601


def test_migration_preserves_version_twelve_data_and_rolls_back_synthetic():
    database = LocalDatabase.open(':memory:', 'synthetic', allow_synthetic_in_memory=True)
    database.migrate(12)
    database.connection.execute("INSERT INTO person(id,name,is_owner) VALUES ('owner','Yo',1)")
    database.connection.commit()
    database.migrate()
    assert database.connection.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION
    assert database.connection.execute('SELECT name FROM person').fetchone()[0] == 'Yo'
    assert database.connection.execute('SELECT COUNT(*) FROM imported_product_refund').fetchone()[0] == 0
    database.migrate(12)
    assert database.connection.execute('SELECT name FROM person').fetchone()[0] == 'Yo'
    database.migrate()
    database.close()


def test_encrypted_upgrade_requires_existing_verified_backup(tmp_path):
    pytest.importorskip('sqlcipher3')
    database = LocalDatabase.open(tmp_path / 'synthetic.db', 'synthetic-password')
    database.migrate(12)
    with pytest.raises(DatabaseSecurityError, match='respaldo'):
        database.migrate()
    backup = tmp_path / 'synthetic-backup.db'
    database.prepare_migration_backup(backup, 'synthetic-password')
    database.migrate()
    database.close()
    restored = LocalDatabase.open(backup, 'synthetic-password')
    assert restored.connection.execute('PRAGMA user_version').fetchone()[0] == 12
    restored.close()


def saved_repurchase_assigned_to_owner(repository):
    args = purchase_args(destination='wallet')
    args['product_refunds'][0].update(repurchase=repurchase_proposal(split={'owner': 15121, 'mama': 0}),
                                      final_allocations={'owner': 15121, 'mama': 0})
    repository.create_order(**args)
    return repository.list_product_refunds('order')[0]


def test_correct_saved_repurchase_split_preserves_bank_events_and_originals(repository):
    import json
    refund = saved_repurchase_assigned_to_owner(repository)
    connection = repository.database.connection
    protected = ('order_record', 'order_allocation', 'receivable', 'institution_movement',
                 'imported_product_refund', 'product_refund_adjustment', 'product_refund_repurchase',
                 'institution_payment', 'user_payment', 'receipt_application')
    before = {table: [tuple(r) for r in connection.execute(f'SELECT * FROM {table} ORDER BY rowid')] for table in protected}
    funding = [tuple(r) for r in connection.execute('SELECT * FROM product_repurchase_adjustment WHERE order_id=?',
                                                  (refund['repurchase']['order_id'],))]
    repository.update_refund_repurchase_allocations(refund['id'], {'owner': 2122, 'mama': 12999},
                                                   expected_allocations={'owner': 15121, 'mama': 0})
    for table in protected:
        assert [tuple(r) for r in connection.execute(f'SELECT * FROM {table} ORDER BY rowid')] == before[table]
    assert [tuple(r) for r in connection.execute('SELECT * FROM product_repurchase_adjustment WHERE order_id=?',
                                                (refund['repurchase']['order_id'],))] == funding
    updated = repository.list_product_refunds('order')[0]
    final = {a['user_id']: a['effective_final_cents'] for a in updated['adjustments']}
    assert final == {'owner': 2122, 'mama': 12999} and sum(final.values()) == 15121
    assert summaries(repository)['card']['remaining_cents'] == 54258
    assert summaries(repository)['wallet']['wallet_balance_cents'] == 5658
    summary = repository.dashboard_summary()
    assert summary['receivables_cents'] == 12999 and summary['personal_pending_cents'] == 41630
    assert all(r['remaining_cents'] == 0 for r in repository.list_collection_items()
               if r['order_id'] == refund['repurchase']['order_id'])
    audit = connection.execute("SELECT * FROM audit_event WHERE action='PRODUCT_REFUND_REPARTITIONED'").fetchone()
    assert json.loads(audit['old_value'])['final_allocations'] == {'owner': 15121, 'mama': 0}
    assert json.loads(audit['new_value'])['correction_cents'] == {'owner': -12999, 'mama': 12999}
    changes = connection.total_changes
    repository.update_refund_repurchase_allocations(refund['id'], {'owner': 2122, 'mama': 12999})
    assert connection.total_changes == changes


@pytest.mark.parametrize('allocations', [
    {'owner': 2122, 'mama': 12998}, {'owner': -1, 'mama': 15122},
    {'owner': 2122.0, 'mama': 12999}, {'owner': 2122, 'unknown': 12999},
])
def test_invalid_saved_repurchase_repartition_never_writes(repository, allocations):
    refund = saved_repurchase_assigned_to_owner(repository)
    before = repository.database.connection.total_changes
    with pytest.raises(ValueError):
        repository.update_refund_repurchase_allocations(refund['id'], allocations)
    assert repository.database.connection.total_changes == before
    assert {a['user_id']: a['effective_final_cents'] for a in repository.list_product_refunds('order')[0]['adjustments']} == {
        'owner': 15121, 'mama': 0}


def test_saved_repurchase_repartition_rejects_stale_edit_and_incompatible_collections(repository):
    refund = saved_repurchase_assigned_to_owner(repository)
    repository.update_refund_repurchase_allocations(refund['id'], {'owner': 2122, 'mama': 12999})
    with pytest.raises(ValueError, match='cambió'):
        repository.update_refund_repurchase_allocations(refund['id'], {'owner': 15121, 'mama': 0},
                                                       expected_allocations={'owner': 15121, 'mama': 0})
    repository.record_receipt(payment_id='family-paid', receivable_id='order:order:mama',
                              amount_cents=12999, received_at='2026-10-11')
    with pytest.raises(ValueError, match='abonos'):
        repository.update_refund_repurchase_allocations(refund['id'], {'owner': 15121, 'mama': 0})
    assert repository.dashboard_summary()['receivables_cents'] == 0


def test_saved_repurchase_repartition_rolls_back_if_audit_fails(repository):
    refund = saved_repurchase_assigned_to_owner(repository)
    repository.database.connection.execute("""CREATE TRIGGER fail_repartition BEFORE INSERT ON audit_event
        WHEN NEW.action='PRODUCT_REFUND_REPARTITIONED'
        BEGIN SELECT RAISE(ABORT, 'synthetic audit failure'); END""")
    with pytest.raises(Exception, match='synthetic audit failure'):
        repository.update_refund_repurchase_allocations(refund['id'], {'owner': 2122, 'mama': 12999})
    assert {a['user_id']: a['effective_final_cents'] for a in repository.list_product_refunds('order')[0]['adjustments']} == {
        'owner': 15121, 'mama': 0}
    assert len(repository.list_orders()) == 2


def test_repartition_exact_anonymous_case_preserves_total_54629(repository):
    args = purchase_args(destination='wallet')
    for index, product in enumerate(args['import_evidence']['products']):
        product['allocations'] = {'owner': product['unit'] if index == 1 else 0,
                                  'mama': 0 if index == 1 else product['unit']}
    args['allocations'] = ({'user_id': 'owner', 'amount_cents': 2000},
                           {'user_id': 'mama', 'amount_cents': 58287})
    args['product_refunds'][0].update(repurchase=repurchase_proposal(split={'owner': 15121, 'mama': 0}),
                                      final_allocations={'owner': 15121, 'mama': 0})
    repository.create_order(**args)
    accounts = {r['user_id']: r for r in repository.list_collection_items() if r['order_id'] == 'order'}
    assert (accounts['owner']['remaining_cents'], accounts['mama']['remaining_cents']) == (17121, 37508)
    refund = repository.list_product_refunds('order')[0]
    repository.update_refund_repurchase_allocations(refund['id'], {'owner': 2122, 'mama': 12999})
    accounts = {r['user_id']: r for r in repository.list_collection_items() if r['order_id'] == 'order'}
    assert (accounts['owner']['remaining_cents'], accounts['mama']['remaining_cents']) == (4122, 50507)
    assert sum(r['remaining_cents'] for r in accounts.values()) == 54629
    assert summaries(repository)['card']['remaining_cents'] == 54258
    assert summaries(repository)['wallet']['wallet_balance_cents'] == 5658


def create_discount_comparison_case(repository):
    args = purchase_args(destination='wallet')
    for index, product in enumerate(args['import_evidence']['products']):
        product['allocations'] = {'owner': product['unit'] if index == 1 else 0,
                                  'mama': 0 if index == 1 else product['unit']}
    args['allocations'] = ({'user_id': 'owner', 'amount_cents': 2000},
                           {'user_id': 'mama', 'amount_cents': 58287})
    args['product_refunds'][0].update(
        repurchase=repurchase_proposal(split={'owner': 2122, 'mama': 12999}),
        final_allocations={'owner': 2122, 'mama': 12999})
    repository.create_order(**args)
    return repository.list_product_refunds('order')[0]['repurchase']['order_id']


def test_discount_comparison_counts_linked_orders_once_and_ignores_personal_receipts(repository):
    linked_id = create_discount_comparison_case(repository)
    before = repository.database.connection.total_changes
    comparison = repository.order_benefit_summary('order')
    assert comparison['discount_benefit_cents'] == 6029
    assert comparison['effective_purchase_cost_cents'] == 48600
    assert comparison['assigned_cents'] == 54629
    assert comparison['expected_result_cents'] == 1907
    assert comparison['family_received_cents'] == 0
    assert repository.order_benefit_summary(linked_id) == comparison
    assert repository.dashboard_summary()['discount_benefit_cents'] == 6029
    assert repository.database.connection.total_changes == before
    repository.record_receipt(payment_id='own-funding', receivable_id='order:order:owner',
                              amount_cents=4122, received_at='2026-10-11')
    after = repository.order_benefit_summary('order')
    assert after['expected_result_cents'] == 1907
    assert after['discount_benefit_cents'] == 6029 and after['family_received_cents'] == 0
    assert repository.dashboard_summary()['personal_pending_cents'] == 0
    assert repository.dashboard_summary()['receivables_cents'] == 50507
    assert summaries(repository)['card']['remaining_cents'] == 54258
    assert summaries(repository)['wallet']['wallet_balance_cents'] == 5658
    repository.record_receipt(payment_id='family-received', receivable_id='order:order:mama',
                              amount_cents=1000, received_at='2026-10-11')
    assert repository.order_benefit_summary('order')['family_received_cents'] == 1000
    assert repository.order_benefit_summary('order')['expected_result_cents'] == 1907


def test_pending_refund_is_not_cash_and_cancelled_discount_is_not_accumulated(repository):
    repository.create_order(**purchase_args(status='PENDING', destination='wallet'))
    assert repository.order_benefit_summary('order')['effective_purchase_cost_cents'] == 54258
    repository.create_order(order_id='cancel-me', ordered_at='2026-10-11', merchant='Ficticio',
                            instrument_id='card', original_cents=1000, discount_cents=100,
                            charged_cents=900, allocations=({'user_id': 'owner', 'amount_cents': 1000},))
    assert repository.dashboard_summary()['discount_benefit_cents'] == 6129
    repository.cancel_order('cancel-me', reason='Prueba sintética')
    assert repository.dashboard_summary()['discount_benefit_cents'] == 6029


def test_topup_in_another_bank_keeps_existing_refund_operation_unchanged(repository):
    create_discount_comparison_case(repository)
    before = repository.order_benefit_summary('order')
    repository.add_institution('other-bank', 'Otro banco ficticio')
    repository.add_instrument('topup-card', 'other-bank', 'Tarjeta de recargas ficticia', 'CREDIT_CARD')
    draft = parse_receipt((Path(__file__).parent / 'fixtures_synthetic' / 'mp_topup.txt').read_text(encoding='utf-8'))
    draft['fingerprint'] = 'synthetic-distinct-topup'
    repository.create_order(order_id='topup', ordered_at=draft['date'], merchant='Recarga Telcel',
                            instrument_id='topup-card', original_cents=20000, discount_cents=0,
                            charged_cents=20000, allocations=({'user_id': 'owner', 'amount_cents': 20000},),
                            import_evidence=draft)
    assert repository.order_benefit_summary('order') == before
    assert before['expected_result_cents'] == 1907 and before['assigned_cents'] == 54629
    assert summaries(repository)['card']['remaining_cents'] == 54258
    assert summaries(repository)['wallet']['wallet_balance_cents'] == 5658
    assert summaries(repository)['topup-card']['remaining_cents'] == 20000
    assert repository.dashboard_summary()['discount_benefit_cents'] == 6029
    assert repository.database.connection.execute("SELECT COUNT(*) FROM institution_movement WHERE kind='REFUND'").fetchone()[0] == 1
    assert repository.database.connection.execute('SELECT COUNT(*) FROM product_refund_repurchase').fetchone()[0] == 1


def test_discount_details_and_dashboard_render_compactly(repository, tmp_path):
    from PySide6.QtWidgets import QLabel
    from PySide6.QtGui import QFont, QFontDatabase
    from sgccc.gui.app import MainWindow, create_application
    application = create_application([])
    font_id = QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    if font_id >= 0:
        application.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    create_discount_comparison_case(repository)
    window = MainWindow(database=repository.database)
    window.resize(1100, 680)
    window.show()
    application.processEvents()
    assert '$60.29 MXN' in window.dashboard_discount.findChild(QLabel, 'summaryAmount').text()
    assert '$542.58 MXN' in window.dashboard_debt.findChild(QLabel, 'summaryAmount').text()
    assert '$505.07 MXN' in window.dashboard_receivables.findChild(QLabel, 'summaryAmount').text()
    window.grab().save(str(tmp_path / 'discount-home.png'))
    window._show_page(2)
    row = next(row for row in range(window.orders_table.rowCount())
               if window.orders_table.item(row, 8).text() == 'order')
    window.orders_table.selectRow(row)
    application.processEvents()
    assert '$41.22 MXN' == window.orders_table.item(row, 5).text()
    assert '$505.07 MXN' == window.orders_table.item(row, 6).text()
    linked_row = next(index for index in range(window.orders_table.rowCount()) if index != row)
    assert window.orders_table.item(linked_row, 5).text() == '$0.00 MXN'
    assert window.orders_table.item(linked_row, 6).text() == '$0.00 MXN'
    detail = window.order_detail.toPlainText()
    for amount in ('$60.29', '$186.57', '$129.99', '$56.58', '$486.00', '$546.29', '$19.07'):
        assert amount in detail
    assert 'no es dinero recibido' in detail
    assert [detail.index(f'{n}. ') for n in range(1, 5)] == sorted(detail.index(f'{n}. ') for n in range(1, 5))
    window.order_detail.verticalScrollBar().setValue(window.order_detail.verticalScrollBar().maximum())
    application.processEvents()
    window.grab().save(str(tmp_path / 'discount-order.png'))
    assert window.order_detail.verticalScrollBar().maximum() > 0
    window.resize(820, 520)
    application.processEvents()
    application.processEvents()
    assert window.height() == 520
    window.order_detail.verticalScrollBar().setValue(window.order_detail.verticalScrollBar().maximum())
    application.processEvents()
    window.grab().save(str(tmp_path / 'discount-order-small.png'))
    window.close()
