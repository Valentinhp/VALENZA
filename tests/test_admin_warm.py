"""Administration presentation must preserve forecasts and explicit selection."""
from PySide6.QtWidgets import QDialog, QPushButton, QMessageBox
from valenza.gui.app import MainWindow, create_application
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository


def test_encrypted_admin_selection_and_empty_forecasts(tmp_path, monkeypatch):
    app = create_application([])
    db = LocalDatabase.open(tmp_path / 'admin.db', 'synthetic-admin-test')
    db.migrate()
    repo = FinanceRepository(db)
    repo.add_person('owner', 'Propietario sintético', is_owner=True)
    repo.add_person('family', 'Familiar sintético')
    repo.add_institution('bank', 'Banco sintético')
    repo.add_instrument('card', 'bank', 'Tarjeta sintética', 'CREDIT_CARD')
    window = MainWindow(database=db)
    window.show(); window.navigation.setCurrentRow(5); app.processEvents()
    assert window.subscription_empty.isVisible()
    assert all(not button.isEnabled() for button in window.subscription_actions)
    repo.save_subscription(subscription_id='sub', name='Servicio sintético', amount_cents=10000,
        instrument_id='card', next_due='2026-10-20', allocations=[
            dict(user_id='owner', amount_cents=4000),
            dict(user_id='family', amount_cents=6000, surcharge_cents=500)])
    window._refresh_subscriptions(); window.subscription_table.selectRow(0)
    assert '$65.00' in window.subscription_summary.text()
    assert all(button.isEnabled() for button in window.subscription_actions)
    repo.set_subscription_status('sub', 'PAUSED'); window._refresh_subscriptions()
    assert window.subscription_actions[1].text() == 'Reactivar'
    assert not window.subscription_actions[3].isEnabled()
    assert '$0.00' in window.subscription_summary.text()
    window.owner_picker.setCurrentIndex(window.owner_picker.findData('family'))
    assert window._selected_owner_id() == 'family'
    assert repo.get_person('owner')['is_owner']
    window._run_integrity()
    assert window.maintenance_result.toPlainText()
    window.navigation.setCurrentRow(6); app.processEvents()
    assert window.maintenance_result.isVisible()
    def invalid_save(dialog):
        dialog.show(); app.processEvents()
        next(b for b in dialog.findChildren(QPushButton) if b.text() in ('Crear suscripción', 'Guardar suscripción')).click()
        assert dialog.isVisible()
        dialog.reject()
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(QDialog, 'exec', invalid_save)
    window._edit_subscription()
    assert len(repo.list_subscriptions()) == 1
    assert repo.list_orders() == [] and repo.list_collection_items() == []
    for row in range(window.people_table.rowCount()):
        if window.people_table.item(row, 0).text() == 'owner':
            window.people_table.selectRow(row)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.No)
    window.person_owner.setChecked(False)
    window._update_person()
    assert repo.get_person('owner')['is_owner'] == 1
    window._deactivate_person()
    assert repo.get_person('owner')['active'] == 1
    repo.deactivate_person('family')
    before = repo.list_subscriptions()[0]['allocations']
    window._edit_subscription('sub')
    assert repo.list_subscriptions()[0]['allocations'] == before
    window.close(); app.processEvents(); db.close()
