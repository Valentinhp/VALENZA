import pytest

from test_product_refunds import repository, create_discount_comparison_case
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository


def reference_case(repo):
    create_discount_comparison_case(repo)
    repo.add_instrument('second-card', 'bank', 'Segunda tarjeta ficticia', 'CREDIT_CARD')
    repo.create_order(order_id='new', ordered_at='2026-10-11', merchant='Ficticio', instrument_id='second-card',
                      original_cents=59900, discount_cents=0, charged_cents=59900,
                      allocations=({'user_id': 'owner', 'amount_cents': 39900}, {'user_id': 'mama', 'amount_cents': 20000}))
    repo.record_receipt(payment_id='own', receivable_id='order:order:owner', amount_cents=4122, received_at='2026-10-11')


def test_reference_balance_is_dynamic_and_personal_receipts_are_not_profit(repository):
    reference_case(repository)
    summary = repository.dashboard_summary()
    assert summary['personal_pending_cents'] == 39900
    assert summary['receivables_cents'] == 70507
    assert summary['institutional_balance_cents'] == 114158
    assert summary['discount_benefit_cents'] == 6029
    assert summary['personal_pending_less_discounts_cents'] == 33871
    assert summary['personal_expected_result_cents'] == -37993
    assert summary['family_received_cents'] == 0
    assert repository.order_benefit_summary('order')['expected_result_cents'] == 1907
    repository.record_receipt(payment_id='another-own', receivable_id='order:new:owner', amount_cents=1000, received_at='2026-10-11')
    after = repository.dashboard_summary()
    assert after['personal_pending_less_discounts_cents'] == 32871
    assert after['personal_expected_result_cents'] == -37993
    assert after['family_received_cents'] == 0
    assert after['institutional_balance_cents'] == 114158
    repository.record_receipt(payment_id='family', receivable_id='order:new:mama', amount_cents=2000, received_at='2026-10-11')
    assert repository.dashboard_summary()['family_received_cents'] == 2000
    assert repository.dashboard_summary()['personal_expected_result_cents'] == -37993


def test_bank_queries_are_metadata_only_and_newest_consultation_wins(repository):
    reference_case(repository)
    connection = repository.database.connection
    tables = ('order_record','order_allocation','receivable','user_payment','receipt_application',
              'institution_payment','institution_movement','imported_product_refund','product_refund_repurchase')
    before = {table: [tuple(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY rowid')] for table in tables}
    initial = repository.dashboard_summary()
    assert all(item['reported_cents'] is None for item in initial['bank_comparisons'])
    repository.record_bank_balance('card', 55000, '2026-10-11')
    reported = next(item for item in repository.list_bank_comparisons() if item['instrument_id'] == 'card')
    assert reported['calculated_cents'] == 54258 and reported['difference_cents'] == 742
    repository.record_bank_balance('card', 70000, '2026-10-10')
    assert next(item for item in repository.list_bank_comparisons() if item['instrument_id'] == 'card')['reported_cents'] == 55000
    repository.record_bank_balance('card', 0, '2026-10-11')
    assert next(item for item in repository.list_bank_comparisons() if item['instrument_id'] == 'card')['difference_cents'] == -54258
    for table in tables:
        assert [tuple(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY rowid')] == before[table]
    after = repository.dashboard_summary()
    for key in initial:
        if key != 'bank_comparisons': assert after[key] == initial[key]


@pytest.mark.parametrize('instrument,amount,dated', [
    ('wallet', 100, '2026-10-11'), ('unknown', 100, '2026-10-11'),
    ('card', -1, '2026-10-11'), ('card', 1.5, '2026-10-11'), ('card', 100, ''),
])
def test_invalid_bank_consultation_does_not_write(repository, instrument, amount, dated):
    before = repository.database.connection.total_changes
    with pytest.raises(ValueError): repository.record_bank_balance(instrument, amount, dated)
    assert repository.database.connection.total_changes == before


def test_bank_consultation_survives_encrypted_reopen(tmp_path):
    path = tmp_path / 'synthetic-consultation.db'
    db = LocalDatabase.open(path, 'synthetic-password')
    db.migrate()
    repo = FinanceRepository(db)
    repo.add_institution('bank', 'Banco ficticio')
    repo.add_instrument('card', 'bank', 'Tarjeta ficticia', 'CREDIT_CARD')
    repo.record_bank_balance('card', 20000, '2026-10-11')
    db.close()
    reopened = LocalDatabase.open(path, 'synthetic-password')
    assert FinanceRepository(reopened).list_bank_comparisons()[0]['reported_cents'] == 20000
    reopened.close()


def test_compact_home_bank_query_and_manual_form(repository, monkeypatch, tmp_path):
    from valenza.gui.app import MainWindow, create_application
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QLabel, QScrollArea
    app = create_application([])
    font = QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    if font >= 0: app.setFont(QFont(QFontDatabase.applicationFontFamilies(font)[0], 10))
    reference_case(repository)
    errors = []
    monkeypatch.setattr(MainWindow, '_show_error', lambda _, message: errors.append(message))
    window = MainWindow(database=repository.database)
    window.resize(820, 520)
    window.show()
    app.processEvents()
    assert '$338.71 MXN' in window.dashboard_net_pending.text()
    assert '$379.93 MXN' in window.dashboard_expected.text()
    assert '$0.00 MXN' in window.dashboard_received.text()
    assert window.dashboard_debt.findChild(QLabel, 'summaryAmount').text() == '$1,141.58 MXN'
    assert window.dashboard_cards.rowCount() == 2
    assert all(window.dashboard_cards.item(row, 2).text() == 'Sin consultar' for row in range(2))
    window.grab().save(str(tmp_path / 'personal-home-small.png'))
    window._show_page(4)
    row = next(row for row in range(window.cards_table.rowCount()) if window.cards_table.item(row, 12).text() == 'card')
    window.cards_table.selectRow(row)
    window.bank_query_amount.setText('550.00')
    window.bank_query_date.setText('2026-10-11')
    window.bank_query_save.click()
    app.processEvents()
    assert not errors and '$7.42 MXN' in window.bank_query_comparison.text()
    assert window.cards_table.item(row, 13).text() == '$550.00 MXN'
    assert window.cards_table.item(row, 15).text() == '$7.42 MXN'
    assert window.cards_table.item(row, 4).text() == '$542.58 MXN'
    window.grab().save(str(tmp_path / 'bank-comparison.png'))
    window._show_page(0)
    home_row = next(row for row in range(window.dashboard_cards.rowCount()) if '$542.58' in window.dashboard_cards.item(row, 1).text())
    assert window.dashboard_cards.item(home_row, 4).text() == '$7.42 MXN'
    window.resize(1100, 680)
    app.processEvents()
    window.grab().save(str(tmp_path / 'personal-home.png'))
    window._show_page(2)
    window._open_manual_expense()
    window.manual_dialog.resize(520, 320)
    app.processEvents()
    window.manual_scroll.verticalScrollBar().setValue(window.manual_scroll.verticalScrollBar().maximum())
    app.processEvents()
    assert window.save_order_button.isVisible() and window.cancel_manual_button.isVisible()
    window.manual_dialog.grab().save(str(tmp_path / 'comfortable-expense-small.png'))
    window.manual_dialog.reject()
    window.close()
