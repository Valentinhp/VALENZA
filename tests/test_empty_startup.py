from valenza.gui.app import MainWindow, create_application
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository


def test_official_empty_encrypted_startup_and_new_catalog(tmp_path):
    app = create_application([])
    path = tmp_path / 'synthetic-empty.db'
    database = LocalDatabase.open(path, 'synthetic-test-only')
    database.migrate()
    names = [r[0] for r in database.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    assert all(database.connection.execute('SELECT COUNT(*) FROM "' + name + '"').fetchone()[0] == 0 for name in names)
    window = MainWindow(database=database)
    window.show()
    app.processEvents()
    assert all(database.connection.execute('SELECT COUNT(*) FROM "' + name + '"').fetchone()[0] == 0 for name in names)
    repo = FinanceRepository(database)
    summary = repo.dashboard_summary()
    for field in ('personal_pending_cents','receivables_cents','institutional_balance_cents',
                  'credit_cents','discount_benefit_cents','personal_expected_result_cents','family_received_cents'):
        assert summary[field] == 0
    assert database.integrity_report()['ok']
    # Creation is exercised ONLY in this synthetic temporary database.
    owner = repo.create_person('Propietario sintético', is_owner=True)
    repo.add_institution('bank', 'Banco sintético')
    repo.add_instrument('card', 'bank', 'Tarjeta sintética', 'CREDIT_CARD')
    assert repo.list_people()[0]['id'] == owner
    assert repo.list_instruments()[0]['id'] == 'card'
    assert repo.list_orders() == []
    assert repo.dashboard_summary()['institutional_balance_cents'] == 0
    window.close()
    app.processEvents()
    database.close()
    reopened = LocalDatabase.open(path, 'synthetic-test-only')
    assert reopened.integrity_report()['ok']
    reopened.close()
