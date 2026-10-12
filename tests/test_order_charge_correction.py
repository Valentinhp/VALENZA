import json
import pytest
from pathlib import Path
from PySide6.QtWidgets import QInputDialog,QMessageBox
from PySide6.QtGui import QFontDatabase
from valenza.gui.app import MainWindow,create_application
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository

@pytest.fixture
def repo(tmp_path):
 db=LocalDatabase.open(tmp_path/'synthetic.db','synthetic-only');db.migrate();r=FinanceRepository(db)
 r.add_person('owner','Owner synthetic',is_owner=True);r.add_person('family','Family synthetic')
 r.add_institution('bank','Bank synthetic');r.add_instrument('card','bank','Card synthetic','CREDIT_CARD')
 r.create_order(order_id='order',ordered_at='2026-10-12',merchant='Synthetic store',instrument_id='card',
   original_cents=10000,discount_cents=1000,charged_cents=9000,
   allocations=({'user_id':'owner','amount_cents':3000},{'user_id':'family','amount_cents':7000}))
 yield r
 db.close()

def test_correct_charge_preserves_responsibility_and_evidence(repo):
 before=repo.get_order('order');statement=repo.family_statement('family')
 repo.correct_order_charge('order',8500,expected_charged_cents=9000,reason='Bank entry correction')
 after=repo.get_order('order')
 for key in before:
  if key!='charged_cents': assert after[key]==before[key],key
 assert after['charged_cents']==8500
 assert repo.list_card_summaries()[0]['remaining_cents']==8500
 assert repo.family_statement('family')['remaining_cents']==statement['remaining_cents']
 assert repo.family_statement('family')['rows'][0]['financial_detail']['charged_cents']==8500
 assert repo.dashboard_summary()['discount_benefit_cents']==1000
 assert repo.dashboard_summary()['institutional_balance_cents']==8500
 audit=repo.database.connection.execute("SELECT old_value,new_value FROM audit_event WHERE action='ORDER_BANK_CHARGE_CORRECTED'").fetchone()
 assert json.loads(audit[0])['charged_cents']==9000
 assert json.loads(audit[1])['charged_cents']==8500
 assert json.loads(audit[1])['difference_cents']==-500
 assert repo.count('institution_payment')==repo.count('user_payment')==0

@pytest.mark.parametrize('value',[0,-1,8500.0,True,2**63])
def test_invalid_and_stale_are_atomic(repo,value):
 changes=repo.database.connection.total_changes
 with pytest.raises(ValueError):repo.correct_order_charge('order',value,expected_charged_cents=9000,reason='Synthetic')
 with pytest.raises(ValueError,match='camb'):repo.correct_order_charge('order',8500,expected_charged_cents=9001,reason='Synthetic')
 assert repo.database.connection.total_changes==changes

def test_paid_card_reduction_blocked_increase_preserves_payments(repo):
 repo.record_institution_payment(payment_id='payment',instrument_id='card',paid_at='2026-10-12',amount_cents=1000)
 before=repo.list_institution_payments('card')
 with pytest.raises(ValueError,match='pagos bancarios'):repo.correct_order_charge('order',8500,expected_charged_cents=9000,reason='Synthetic')
 repo.correct_order_charge('order',9500,expected_charged_cents=9000,reason='Synthetic')
 assert repo.list_institution_payments('card')==before
 assert repo.list_card_summaries()[0]['remaining_cents']==8500

def test_msi_blocked_without_rewriting_plan(repo):
 repo.create_order(order_id='msi',ordered_at='2026-10-12',merchant='Synthetic MSI',instrument_id='card',
  original_cents=10000,discount_cents=0,charged_cents=10000,allocations=({'user_id':'owner','amount_cents':10000},),
  purchase_mode='MSI',financing_specs=('2026-11-12','2026-12-12'))
 before=repo.list_installments('card')
 with pytest.raises(ValueError,match='MSI'):repo.correct_order_charge('msi',9000,expected_charged_cents=10000,reason='Synthetic')
 assert repo.list_installments('card')==before

def test_editor_correction_and_cancel(repo,monkeypatch):
 app=create_application([])
 QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
 monkeypatch.setattr(MainWindow,'_show_information',lambda *a:None)
 monkeypatch.setattr(MainWindow,'_show_error',lambda self,t:pytest.fail(t))
 w=MainWindow(database=repo.database);w._show_page(2);w.orders_table.selectRow(0);w._edit_manual_expense()
 app.processEvents()
 assert w.correct_charge_button.isVisible()
 assert w.order_charged.text()=='90.00'
 w.manual_scroll.ensureWidgetVisible(w.correct_charge_button)
 app.processEvents()
 output=Path('output/charge-correction');output.mkdir(parents=True,exist_ok=True)
 w.manual_dialog.grab().save(str(output/f'editor-{app.devicePixelRatio():g}.png'))
 responses=iter([('85.00',True),('Bank correction synthetic',True)])
 monkeypatch.setattr(QInputDialog,'getText',lambda *a:next(responses))
 monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.StandardButton.Yes)
 w.correct_charge_button.click()
 assert repo.get_order('order')['charged_cents']==8500
 assert w.order_charged.text()=='85.00'
 assert w.order_discount.text()=='$10.00 MXN'
 responses=iter([('80.00',True),('Cancelled synthetic correction',True)])
 monkeypatch.setattr(QInputDialog,'getText',lambda *a:next(responses))
 monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.StandardButton.No)
 w.correct_charge_button.click()
 assert repo.get_order('order')['charged_cents']==8500
 monkeypatch.setattr(QInputDialog,'getText',lambda *a:('',False))
 w.correct_charge_button.click()
 assert repo.get_order('order')['charged_cents']==8500
 w.manual_dialog.reject();w.close()

def test_refund_and_repurchase_blocked(tmp_path):
 from test_product_refunds import purchase_args,repurchase_proposal
 db=LocalDatabase.open(tmp_path/'refund.db','synthetic');db.migrate();r=FinanceRepository(db)
 r.add_person('owner','Owner',is_owner=True);r.add_person('mama','Mother')
 r.add_institution('bank','Bank');r.add_institution('mp','MP')
 r.add_instrument('card','bank','Card','CREDIT_CARD');r.add_instrument('wallet','mp','Wallet','WALLET_BALANCE')
 r.create_order(**purchase_args(destination='wallet'))
 before=r.dashboard_summary()
 with pytest.raises(ValueError,match='devoluc'):r.correct_order_charge('order',53000,expected_charged_cents=54258,reason='Synthetic')
 assert r.dashboard_summary()==before
 linked=r.register_refund_repurchase(r.list_product_refunds('order')[0]['id'],repurchase_proposal())
 before=r.dashboard_summary()
 with pytest.raises(ValueError):r.correct_order_charge('order',53000,expected_charged_cents=54258,reason='Synthetic')
 with pytest.raises(ValueError,match='Wallet'):r.correct_order_charge(linked,12000,expected_charged_cents=12999,reason='Synthetic')
 assert r.dashboard_summary()==before
 db.close()

def test_audit_failure_rolls_back(repo,monkeypatch):
 def fail(*args,**kwargs):raise RuntimeError('Synthetic audit failure')
 monkeypatch.setattr(repo,'_insert_person_audit',fail)
 before=repo.get_order('order')
 with pytest.raises(RuntimeError):repo.correct_order_charge('order',8500,expected_charged_cents=9000,reason='Synthetic')
 assert repo.get_order('order')==before

def test_editor_does_not_save_draft_when_correcting(repo,monkeypatch):
 app=create_application([])
 monkeypatch.setattr(MainWindow,'_show_information',lambda *a:None)
 w=MainWindow(database=repo.database);w._show_page(2);w.orders_table.selectRow(0);w._edit_manual_expense()
 original=repo.editable_order_concepts(repo.get_order('order'))
 w.manual_concepts.item(0,0).setText('Uncommitted synthetic description')
 responses=iter([('85.00',True),('Synthetic evidence correction',True)])
 monkeypatch.setattr(QInputDialog,'getText',lambda *a:next(responses))
 monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.StandardButton.Yes)
 w.correct_charge_button.click()
 assert repo.editable_order_concepts(repo.get_order('order'))==original
 assert w.manual_concepts.item(0,0).text()=='Uncommitted synthetic description'
 w.manual_dialog.reject();w.close()

def test_direct_charge_field_saves_with_confirmation(repo,monkeypatch):
 app=create_application([])
 monkeypatch.setattr(MainWindow,'_show_information',lambda *a:None)
 monkeypatch.setattr(MainWindow,'_show_error',lambda self,t:pytest.fail(t))
 w=MainWindow(database=repo.database);w._show_page(2);w.orders_table.selectRow(0);w._edit_manual_expense()
 assert w.order_charged.isEnabled() and not w.order_charged.isReadOnly()
 w.order_charged.setText('85.00')
 monkeypatch.setattr(QInputDialog,'getText',lambda *a:('Synthetic direct correction',True))
 monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.StandardButton.No)
 w._save_order()
 assert repo.get_order('order')['charged_cents']==9000
 assert w.manual_dialog.isVisible()
 monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.StandardButton.Yes)
 w._save_order()
 assert repo.get_order('order')['charged_cents']==8500
 assert repo.get_order('order')['discount_cents']==1000
 assert repo.family_statement('family')['remaining_cents']==7000
 assert not w.manual_dialog.isVisible()
 w.close()
