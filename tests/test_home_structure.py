from datetime import date

import pytest
from PySide6.QtWidgets import QLabel
from PySide6.QtGui import QFont, QFontDatabase

from valenza.gui.app import MainWindow, create_application
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository


@pytest.mark.parametrize('size', [(1366, 768), (900, 700), (640, 600), (1536, 1024)])
def test_home_structure_preserves_amounts_actions_and_database(size, tmp_path, monkeypatch):
    app = create_application([])
    font_id = QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    if font_id >= 0:
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    database = LocalDatabase.open(tmp_path / 'synthetic-home.db', 'synthetic-home-test')
    assert database.encrypted
    database.migrate()
    repo = FinanceRepository(database)
    repo.add_person('owner', 'Yo', is_owner=True)
    repo.add_person('family', 'Familiar sintético')
    repo.add_institution('bank', 'Banco sintético')
    repo.add_instrument('card', 'bank', 'Tarjeta sintética', 'CREDIT_CARD')
    today = date.today()
    future = f'{today.year + (today.month == 12):04d}-{1 if today.month == 12 else today.month + 1:02d}-15'
    repo.create_order(order_id='msi', ordered_at=today.isoformat(), merchant='Compra sintética',
                      instrument_id='card', original_cents=60000, charged_cents=60000, discount_cents=0,
                      allocations=({'user_id': 'owner', 'amount_cents': 30000},
                                   {'user_id': 'family', 'amount_cents': 30000}),
                      purchase_mode='MSI', financing_specs=(today.isoformat(), future))
    for index in range(7):
        repo.record_extra(extra_id=f'extra{index}', user_id='owner', received_at=today.isoformat(),
                          amount_cents=100, description=f'Extra sintético {index}')
    before = repo.dashboard_summary()
    people_before = repo.people_debt_summary()
    changes = database.connection.total_changes
    window = MainWindow(database=database, test_mode=True)
    window.resize(*size)
    window.show()
    app.processEvents()
    assert not window.findChild(QLabel, 'valenzaSidebarLogo').pixmap().isNull()
    assert not window.dashboard_brand.pixmap().isNull()
    assert not window.windowIcon().isNull()
    amount = lambda widget: widget.findChild(QLabel, 'summaryAmount').text()
    assert amount(window.dashboard_debt) == '$300.00 MXN'
    assert amount(window.dashboard_personal) == amount(window.dashboard_receivables) == '$300.00 MXN'
    assert amount(window.dashboard_msi) == '$300.00 MXN'
    assert window.dashboard_donut_chart.values == [('Mi parte', before['personal_pending_cents']), ('Familiares', before['receivables_cents'])]
    assert window.dashboard_bar_chart.values[0] == (today.strftime('%Y-%m'), before['scheduled_month_cents'])
    assert sum(value for _, value in window.dashboard_donut_chart.values) == 60000
    assert window.dashboard_cards.item(0, 5).text() == '$600.00 MXN'
    assert window.dashboard_cards.height() < 90
    assert window.dashboard_people.height() < 115
    assert sum(not window.dashboard_movements.item(i).isHidden() for i in range(window.dashboard_movements.count())) == 5
    window.dashboard_movements_toggle.click()
    assert all(not window.dashboard_movements.item(i).isHidden() for i in range(window.dashboard_movements.count()))
    window.dashboard_summary_toggle.click()
    assert window.dashboard_expected.isVisible()
    window.dashboard_result_toggle.click()
    assert window.dashboard_result_details.isVisible() and window.dashboard_result_details.toPlainText()
    window.dashboard_person_toggle.click()
    assert window.dashboard_person_details.isVisible() and window.dashboard_person_details.sections
    exported = []
    monkeypatch.setattr(window, '_export_family_pdf', exported.append)
    window.dashboard_person_pdf.click()
    assert exported == [window._table_id(window.dashboard_people, 5)]
    window.dashboard_bank_toggle.click()
    assert not window.dashboard_cards.isColumnHidden(2)
    window.dashboard_calendar_toggle.click()
    assert window.dashboard_upcoming.isVisible()
    window.dashboard_summary_toggle.click()
    window.dashboard_result_toggle.setChecked(False)
    window.dashboard_person_toggle.click()
    window.dashboard_calendar_toggle.click()
    window.dashboard_bank_toggle.click()
    window.dashboard_movements_toggle.click()
    app.processEvents()
    window.grab().save(str(tmp_path / 'inicio.png'))
    assert repo.dashboard_summary() == before
    assert repo.people_debt_summary() == people_before
    assert database.connection.total_changes == changes
    window.close()
