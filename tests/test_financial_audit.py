"""Read-only audit of projections on synthetic data; known gaps remain explicit."""
import pytest

from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository


@pytest.fixture
def audited_repo():
    db = LocalDatabase.open(':memory:', 'synthetic-audit', allow_synthetic_in_memory=True)
    db.migrate()
    repo = FinanceRepository(db)
    repo.add_person('valen', 'VALEN sintético', is_owner=True)
    repo.add_person('mama', 'MAMA sintética')
    repo.add_institution('bank', 'Banco sintético')
    repo.add_instrument('card', 'bank', 'Tarjeta sintética', 'CREDIT_CARD')
    yield repo
    db.close()


def order(repo, identity, original, charged, family, *, discount=None, dates=None):
    repo.create_order(order_id=identity, ordered_at='2026-10-11', merchant=identity,
        instrument_id='card', original_cents=original,
        discount_cents=original-charged if discount is None else discount,
        charged_cents=charged,
        allocations=({'user_id':'valen','amount_cents':original-family},
                     {'user_id':'mama','amount_cents':family}),
        purchase_mode='MSI' if dates else 'CASH', financing_specs=dates)


def test_third_party_real_installment_has_no_discount_or_profit(audited_repo):
    repo = audited_repo
    order(repo, 'monthly', 47466, 47466, 47466)
    snapshot = repo.database.connection.total_changes
    summary = repo.dashboard_summary()
    statement = repo.family_statement('mama')
    assert summary['personal_expected_result_cents'] == summary['discount_benefit_cents'] == 0
    assert summary['receivables_cents'] == summary['institutional_balance_cents'] == 47466
    assert statement['assigned_cents'] == statement['remaining_cents'] == 47466
    assert statement['paid_cents'] == 0
    assert repo.database.connection.total_changes == snapshot


def test_zero_charge_capture_reproduces_fictitious_benefit(audited_repo):
    repo = audited_repo
    order(repo, 'bad-capture', 47466, 0, 47466)
    summary = repo.dashboard_summary()
    assert summary['personal_expected_result_cents'] == summary['discount_benefit_cents'] == 47466
    assert summary['receivables_cents'] == 47466
    assert summary['institutional_balance_cents'] == 0
    # Changing classification alone does not create a bank charge.
    assert repo.get_order('bad-capture')['financing_plan'] is None


def test_legitimate_personal_discount_preserves_full_family_participation(audited_repo):
    repo = audited_repo
    order(repo, 'discount', 61125, 54031, 61125)
    before = repo.dashboard_summary()
    assert before['discount_benefit_cents'] == before['personal_expected_result_cents'] == 7094
    assert before['receivables_cents'] == 61125
    assert before['institutional_balance_cents'] == 54031
    assert before['family_received_cents'] == 0
    repo.record_receipt(payment_id='cash', receivable_id='order:discount:mama',
                        amount_cents=10000, received_at='2026-10-11')
    after = repo.dashboard_summary()
    assert after['family_received_cents'] == 10000 and after['receivables_cents'] == 51125
    assert after['personal_expected_result_cents'] == 7094
    assert after['institutional_balance_cents'] == 54031


def test_personal_4122_receipt_is_not_discount_or_bank_payment(audited_repo):
    repo = audited_repo
    order(repo, 'personal', 89052, 89052, 0)
    repo.record_receipt(payment_id='personal-receipt', receivable_id='order:personal:valen',
                        amount_cents=4122, received_at='2026-10-11')
    statement = repo.family_statement('valen')
    assert (statement['assigned_cents'], statement['paid_cents'], statement['remaining_cents']) == (89052, 4122, 84930)
    assert sum(r['amount_cents'] for row in statement['rows'] for r in row['receipts']) == 4122
    summary = repo.dashboard_summary()
    assert summary['family_received_cents'] == summary['discount_benefit_cents'] == 0
    assert summary['institutional_balance_cents'] == 89052
    assert summary['personal_expected_result_cents'] == -89052
    repo.cancel_user_payment('personal-receipt', reason='Cancelación sintética')
    assert repo.family_statement('valen')['paid_cents'] == 0
    assert repo.family_statement('valen')['remaining_cents'] == 89052


def test_msi_projects_original_debt_without_second_charge(audited_repo):
    repo = audited_repo
    order(repo, 'original', 94932, 94932, 94932, dates=('2026-11-11', '2026-12-11'))
    assert len(repo.list_orders()) == 1
    assert sum(r['amount_cents'] for r in repo.upcoming_obligations()) == 94932
    assert repo.dashboard_summary()['receivables_cents'] == 94932
    assert repo.dashboard_summary()['institutional_balance_cents'] == 94932
    repo.record_receipt(payment_id='family', receivable_id='order:original:mama',
                        amount_cents=47466, received_at='2026-10-11')
    assert sum(r['amount_cents'] for r in repo.upcoming_obligations()) == 47466
    assert repo.dashboard_summary()['institutional_balance_cents'] == 94932
    before = repo.dashboard_summary()
    repo.record_bank_balance('card', 94932, '2026-10-11')
    after = repo.dashboard_summary()
    assert after['institutional_balance_cents'] == before['institutional_balance_cents']
    assert after['bank_comparisons'][0]['difference_cents'] is None  # Date-only consultation is not contemporaneous.
    from datetime import datetime
    repo.record_bank_balance('card',94932,datetime.now().astimezone().isoformat())
    assert repo.dashboard_summary()['bank_comparisons'][0]['difference_cents'] == 0


def test_missing_manual_charge_requires_review():
    from valenza.gui.app import MainWindow
    class EmptyField:
        def text(self):
            return ''
    with pytest.raises(ValueError):
        MainWindow._order_input_cents(None, EmptyField(), 'Cargo real')


def test_repository_rejects_inconsistent_order_amounts(audited_repo):
    with pytest.raises(ValueError):
        order(audited_repo, 'inconsistent', 10000, 9000, 10000, discount=0)


def test_historical_purchase_has_different_summary_scope(audited_repo):
    repo = audited_repo
    repo.create_purchase(purchase_id='legacy', purchased_at='2026-10-11',
        merchant='Compra histórica sintética', instrument_id='card',
        products=({'id':'legacy-item','description':'Producto','quantity':2,'unit_price_cents':500},),
        allocations=({'product_id':'legacy-item','user_id':'valen','method':'UNITS','basis':1},
                     {'product_id':'legacy-item','user_id':'mama','method':'UNITS','basis':1}))
    summary = repo.dashboard_summary()
    assert summary['personal_pending_cents'] == summary['receivables_cents'] == 500
    assert repo.family_statement('valen')['assigned_cents'] == 500
    assert summary['institutional_balance_cents'] == summary['personal_expected_result_cents'] == 0


def test_cancelled_payment_with_unreversed_legacy_application_is_not_a_receipt(audited_repo):
    repo = audited_repo
    order(repo, 'legacy-receipt', 10000, 10000, 10000)
    repo.record_receipt(payment_id='legacy-cash', receivable_id='order:legacy-receipt:mama',
                       amount_cents=1000, received_at='2026-10-11')
    # Simulate inconsistent legacy state in a disposable in-memory database only.
    repo.database.connection.execute("UPDATE user_payment SET payment_status='CANCELLED' WHERE id='legacy-cash'")
    statement = repo.family_statement('mama')
    assert statement['rows'][0]['receipts'] == []
    assert statement['paid_cents'] == 0
    before = repo.database.connection.total_changes
    issues = repo.receipt_inconsistencies()
    assert len(issues) == 1 and issues[0]['payment_id'] == 'legacy-cash'
    assert repo.database.connection.total_changes == before
    assert repo.database.connection.execute(
        "SELECT application_status FROM receipt_application WHERE payment_id='legacy-cash'"
    ).fetchone()[0] == 'ACTIVE'  # Diagnose, never silently repair.


def test_legacy_cancelled_application_does_not_block_valid_new_receipt_or_edit(audited_repo):
    repo=audited_repo
    order(repo,'legacy-validation',10000,10000,10000)
    account='order:legacy-validation:mama'
    repo.record_receipt(payment_id='cancelled-legacy',receivable_id=account,amount_cents=1000,received_at='2026-10-11')
    repo.database.connection.execute("UPDATE user_payment SET payment_status='CANCELLED' WHERE id='cancelled-legacy'")
    repo.record_receipt(payment_id='valid-new',receivable_id=account,amount_cents=10000,received_at='2026-10-12')
    repo.update_user_payment('valid-new',amount_cents=9000,received_at='2026-10-12')
    repo.update_user_payment('valid-new',amount_cents=10000,received_at='2026-10-12')
    assert repo.family_statement('mama')['paid_cents']==10000
    assert repo.family_statement('mama')['remaining_cents']==0
    assert repo.database.connection.execute("SELECT application_status FROM receipt_application WHERE payment_id='cancelled-legacy'").fetchone()[0]=='ACTIVE'
    assert len(repo.receipt_inconsistencies())==1


@pytest.mark.parametrize('operation',['apply','cancel_order'])
def test_legacy_cancelled_application_is_ignored_by_other_receipt_guards(audited_repo,operation):
    repo=audited_repo
    order(repo,'legacy-guard',10000,10000,10000)
    account='order:legacy-guard:mama'
    repo.record_receipt(payment_id='cancelled-guard',receivable_id=account,amount_cents=1000,received_at='2026-10-11')
    repo.database.connection.execute("UPDATE user_payment SET payment_status='CANCELLED' WHERE id='cancelled-guard'")
    if operation=='apply':
        repo.add_user_payment('active-guard','mama','2026-10-12',10000)
        repo.apply_receipt('active-guard',account,10000)
        assert repo.family_statement('mama')['remaining_cents']==0
    else:
        repo.cancel_order('legacy-guard',reason='Synthetic explicit cancellation')
        assert repo.get_order('legacy-guard')['order_status']=='CANCELLED'
    assert repo.database.connection.execute("SELECT application_status FROM receipt_application WHERE payment_id='cancelled-guard'").fetchone()[0]=='ACTIVE'
    assert len(repo.receipt_inconsistencies())==1
