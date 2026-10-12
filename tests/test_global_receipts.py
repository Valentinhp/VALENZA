"""Encrypted synthetic person accounts; never opens the user's database."""
from datetime import date
from pathlib import Path
import pytest
import pymupdf
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QListWidget
from valenza.gui.app import MainWindow,create_application,write_family_pdf
from valenza.gui.person_receipts import ReceiptPreview
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository
import valenza.persistence.repository as repository_module

@pytest.fixture
def repo(tmp_path,monkeypatch):
 class FixedDate(date):
  @classmethod
  def today(cls):return cls(2026,10,12)
 monkeypatch.setattr(repository_module,'date',FixedDate)
 db=LocalDatabase.open(tmp_path/'global-synthetic.db','synthetic-only');db.migrate();r=FinanceRepository(db)
 r.add_person('owner','Yo sintético',is_owner=True);r.add_person('mama','Mamá sintética')
 r.add_institution('bank','Nu sintético');r.add_instrument('card','bank','Nu sintética','CREDIT_CARD')
 for identity,amount,ordered in [('old',20000,'2026-08-01'),('new',10000,'2026-09-01'),('msi',30000,'2026-10-01')]:
  r.create_order(order_id=identity,ordered_at=ordered,merchant=f'Pedido sintético {identity}',instrument_id='card',
   original_cents=amount,charged_cents=amount,discount_cents=0,allocations=({'user_id':'mama','amount_cents':amount},{'user_id':'owner','amount_cents':0}),
   purchase_mode='MSI' if identity=='msi' else 'CASH',financing_specs=('2026-10-20','2026-11-20','2026-12-20') if identity=='msi' else None)
 yield r
 db.close()


def record(repo,identity='global',amount=35000,future=False,applications=None):
 accounts=repo.person_receipt_accounts('mama',include_future=future)
 remain=amount;chosen={}
 for a in accounts:
  used=min(remain,a['eligible_cents']);remain-=used;chosen[a['receivable_id']]=used
 return repo.record_global_receipt(payment_id=identity,user_id='mama',amount_cents=amount,received_at='2026-10-12',
  reference='Transferencia sintética',applications=applications or chosen,
  expected_balances={a['receivable_id']:a['remaining_cents'] for a in accounts},include_future=future)


def test_one_payment_audit_pdf_and_full_cancellation(repo,tmp_path):
 audit_before=repo.count('audit_event');bank=repo.list_card_summaries()
 assert record(repo)
 assert repo.count('audit_event')==audit_before+1
 assert repo.count('user_payment')==1 and repo.count('receipt_application')==3
 assert repo.people_debt_summary()[1]['remaining_cents'] in (0,25000)
 applications={a['receivable_id']:a['amount_cents'] for a in repo.database.connection.execute('SELECT * FROM receipt_application')}
 assert applications=={'order:old:mama':20000,'order:new:mama':10000,'order:msi:mama':5000}
 assert repo.list_card_summaries()==bank
 summary=repo.dashboard_summary();assert summary['family_received_cents']==35000 and summary['receivables_cents']==25000
 monthly=repo.collection_monthly_summaries()['order:msi:mama'];assert monthly['current_cents']==5000 and monthly['future_cents']==20000
 statement=repo.family_statement('mama');assert statement['paid_cents']==35000 and statement['remaining_cents']==25000
 path=tmp_path/'global.pdf';write_family_pdf(statement,path,repository=repo)
 with pymupdf.open(path) as pdf:
  text=''.join(p.get_text() for p in pdf)
  assert text.count('$350.00 MXN')==2 # summary + one real transfer, not three rows
  assert '$250.00 MXN' in text
 repo.update_user_payment('global',received_at='2026-10-11',amount_cents=35000,reference='Referencia corregida')
 with pytest.raises(ValueError,match='global'):repo.update_user_payment('global',received_at='2026-10-11',amount_cents=34000)
 repo.cancel_user_payment('global',reason='Corrección sintética')
 assert repo.family_statement('mama')['remaining_cents']==60000
 assert repo.dashboard_summary()['family_received_cents']==0
 assert repo.list_card_summaries()==bank
 assert all(r['application_status']=='REVERSED' for r in repo.database.connection.execute('SELECT * FROM receipt_application'))


def test_futures_require_explicit_consent(repo):
 with pytest.raises(ValueError,match='elegible'):record(repo,amount=60000,applications={
  'order:old:mama':20000,'order:new:mama':10000,'order:msi:mama':30000})
 assert repo.count('user_payment')==0
 record(repo,amount=60000,future=True)
 assert repo.family_statement('mama')['remaining_cents']==0


def test_double_submission_and_conflicting_id(repo):
 record(repo)
 assert record(repo,applications={'order:old:mama':20000,'order:new:mama':10000,'order:msi:mama':5000}) is False
 assert repo.count('user_payment')==1
 with pytest.raises(ValueError,match='identificador'):record(repo,amount=1000)


def test_rollback_mid_application_and_audit_failure(repo,monkeypatch):
 repo.database.connection.execute("CREATE TRIGGER synthetic_fail BEFORE INSERT ON receipt_application WHEN NEW.receivable_id='order:new:mama' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
 before=repo.dashboard_summary()
 with pytest.raises(Exception):record(repo)
 assert repo.count('user_payment')==repo.count('receipt_application')==0
 assert repo.dashboard_summary()==before
 repo.database.connection.execute('DROP TRIGGER synthetic_fail')
 def fail(*a,**k):raise RuntimeError('synthetic audit failure')
 monkeypatch.setattr(repo,'_insert_person_audit',fail)
 with pytest.raises(RuntimeError):record(repo)
 assert repo.count('user_payment')==repo.count('receipt_application')==0
 assert repo.dashboard_summary()==before


def test_stale_balance_and_cross_person_blocked(repo):
 accounts=repo.person_receipt_accounts('mama');expected={a['receivable_id']:a['remaining_cents'] for a in accounts}
 repo.record_receipt(payment_id='individual',receivable_id='order:old:mama',amount_cents=1000,received_at='2026-10-12')
 with pytest.raises(ValueError,match='cambiaron'):repo.record_global_receipt(payment_id='new',user_id='mama',amount_cents=1000,received_at='2026-10-12',
  applications={'order:old:mama':1000},expected_balances=expected)
 with pytest.raises(ValueError,match='mezclar'):repo.record_global_receipt(payment_id='new',user_id='owner',amount_cents=1000,received_at='2026-10-12',
  applications={'order:new:mama':1000},expected_balances=expected)
 assert repo.count('user_payment')==1


def test_visual_manual_preview_and_history(repo):
 app=create_application([]);QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
 w=MainWindow(database=repo.database,test_mode=True);w.resize(round(1360/app.devicePixelRatio()),round(960/app.devicePixelRatio()))
 w.findChild(QListWidget,'navigation').setCurrentRow(3);w.show();app.processEvents()
 panel=w.person_receipt_panel;panel.person.setCurrentIndex(panel.person.findData('mama'))
 assert '$600.00 MXN' in panel.summary.text() and '$400.00 MXN' in panel.summary.text() and '$200.00 MXN' in panel.summary.text()
 panel.received_date.setText('2026-10-12');panel.reference.setText('Transferencia sintética');panel.amount.setText('350.00')
 preview=ReceiptPreview(panel,repo.person_receipt_accounts('mama'),35000);preview.show();app.processEvents()
 assert not panel.future.isChecked()
 assert preview.table.item(2,3).text()=='50.00'
 output=Path('output/global-receipts')/f'{app.devicePixelRatio():g}';output.mkdir(parents=True,exist_ok=True)
 w.collections_scroll.ensureWidgetVisible(panel);app.processEvents();panel.grab().save(str(output/'cuenta-mama.png'))
 preview.grab().save(str(output/'vista-previa.png'))
 # Manual redistribution, sum preserved, no payment before confirmation.
 preview.table.item(0,3).setText('150.00');preview.table.item(2,3).setText('100.00')
 assert repo.count('user_payment')==0
 preview.commit();assert repo.count('user_payment')==1
 w.collection_history_toggle.setChecked(True);app.processEvents()
 assert w.collection_history.rowCount()==1
 assert 'Abono global' in w.collection_history.item(0,2).text()
 assert w.collection_history.item(0,3).text()=='$350.00 MXN'
 w.collection_history.parentWidget().grab().save(str(output/'historial.png'))
 assert repo.family_statement('mama')['remaining_cents']==25000
 write_family_pdf(repo.family_statement('mama'),output/'mama-sintetica.pdf',repository=repo)
 w.close()

def test_personal_global_tracks_virtual_accounts_once(repo):
 repo.create_order(order_id='personal',ordered_at='2026-10-12',merchant='Synthetic own expense',instrument_id='card',
  original_cents=5000,charged_cents=5000,discount_cents=0,allocations=({'user_id':'owner','amount_cents':5000},))
 account=next(a for a in repo.person_receipt_accounts('owner') if a['order_id']=='personal')
 audit=repo.count('audit_event');bank=repo.list_card_summaries()
 repo.record_global_receipt(payment_id='own-global',user_id='owner',amount_cents=1000,received_at='2026-10-12',
  applications={account['receivable_id']:1000},expected_balances={account['receivable_id']:5000})
 assert repo.count('audit_event')==audit+1
 assert repo.family_statement('owner')['remaining_cents']==4000
 assert repo.dashboard_summary()['family_received_cents']==0
 assert repo.list_card_summaries()==bank


def test_refund_repurchase_uses_adjusted_debt_without_duplicate(repo):
 from test_product_refunds import create_discount_comparison_case
 repo.add_institution('mp','MP synthetic');repo.add_instrument('wallet','mp','Wallet synthetic','WALLET_BALANCE')
 linked=create_discount_comparison_case(repo)
 accounts=repo.person_receipt_accounts('mama')
 assert not any(a.get('order_id')==linked for a in accounts)
 account=next(a for a in accounts if a['order_id']=='order')
 assert account['remaining_cents']==50507
 bank=repo.list_card_summaries();before=repo.get_order('order')
 repo.record_global_receipt(payment_id='refund-global',user_id='mama',amount_cents=50507,received_at='2026-10-12',
  applications={account['receivable_id']:50507},expected_balances={account['receivable_id']:50507})
 assert repo.list_card_summaries()==bank
 assert repo.get_order('order')['product_refunds']==before['product_refunds']
 assert next(a for a in repo.list_collection_items() if a['order_id']=='order' and a['user_id']=='mama')['remaining_cents']==0


def test_undated_msi_is_excluded_until_consent(repo):
 repo.create_order(order_id='undated',ordered_at='2026-10-12',merchant='MSI synthetic undated',instrument_id='card',
  original_cents=10000,charged_cents=10000,discount_cents=0,allocations=({'user_id':'mama','amount_cents':10000},{'user_id':'owner','amount_cents':0}),
  purchase_mode='MSI',financing_specs=(None,None))
 account=next(a for a in repo.person_receipt_accounts('mama') if a['order_id']=='undated')
 assert account['eligible_cents']==0 and account['undated_cents']==10000
 with pytest.raises(ValueError,match='elegible'):repo.record_global_receipt(payment_id='undated',user_id='mama',amount_cents=1000,received_at='2026-10-12',
  applications={account['receivable_id']:1000},expected_balances={account['receivable_id']:10000},include_future=True)
 repo.record_global_receipt(payment_id='undated',user_id='mama',amount_cents=1000,received_at='2026-10-12',
  applications={account['receivable_id']:1000},expected_balances={account['receivable_id']:10000},include_undated=True)
 assert repo.family_statement('mama')['paid_cents']==1000

def test_existing_individual_receipt_is_never_rewritten(repo):
 repo.record_receipt(payment_id='old-individual',receivable_id='order:old:mama',amount_cents=1000,received_at='2026-10-10',reference='Original reference')
 before=tuple(repo.database.connection.execute("SELECT * FROM user_payment WHERE id='old-individual'").fetchone())
 applications=[tuple(r) for r in repo.database.connection.execute("SELECT * FROM receipt_application WHERE payment_id='old-individual'")]
 record(repo,amount=5000)
 assert tuple(repo.database.connection.execute("SELECT * FROM user_payment WHERE id='old-individual'").fetchone())==before
 assert [tuple(r) for r in repo.database.connection.execute("SELECT * FROM receipt_application WHERE payment_id='old-individual'")]==applications
 assert repo.family_statement('mama')['paid_cents']==6000
