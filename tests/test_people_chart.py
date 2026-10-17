"""Per-person Home presentation with unchanged encrypted synthetic finances."""
from pathlib import Path

import pytest
from PySide6.QtCore import QDate, QPoint, QPointF, QEvent, Qt
from PySide6.QtGui import QMouseEvent, QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from unittest.mock import patch

from test_product_refunds import repository
from test_home_initial_restore import tables
from valenza.gui.app import MainWindow, create_application
from valenza.gui.people_month_chart import PeopleMonthChart


@pytest.fixture(autouse=True)
def readable_offscreen_font():
    # Offscreen Qt does not discover Windows fonts consistently. Load the same
    # font as the Home layout tests so geometry does not depend on test order.
    app = create_application([])
    font_id = QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    if font_id >= 0:
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))


@pytest.mark.parametrize('width', [300, 460, 820])
def test_each_person_and_owner_highlight_without_changing_amounts(repository, width):
    repository.add_person('ana', 'Ana sintética con nombre muy largo')
    repository.create_order(order_id='chart', ordered_at='2026-10-15', merchant='Compra sintética',
        instrument_id='card', original_cents=600000, discount_cents=0, charged_cents=600000,
        allocations=({'user_id': 'owner', 'amount_cents': 100000},
                     {'user_id': 'mama', 'amount_cents': 300000},
                     {'user_id': 'ana', 'amount_cents': 200000}))
    repository.record_receipt(payment_id='partial', receivable_id='order:chart:mama',
        received_at='2026-10-15', amount_cents=50000)
    before = tables(repository)
    changes = repository.database.connection.total_changes
    app = create_application([])
    window = MainWindow(database=repository.database, test_mode=True)
    window.dashboard_period_picker.setDate(QDate(2026, 10, 1))
    chart = window.dashboard_donut_chart
    # Detach the preview so the dashboard layout cannot override the test width.
    chart.setParent(None)
    chart.resize(width, chart.height())
    chart.show()
    app.processEvents()
    chart.resize(width, chart.sizeHint().height())
    app.processEvents()
    try:
        assert chart.values[0] == ('Mi parte · Yo', 100000)
        assert dict(chart.values) == {'Mi parte · Yo': 100000, 'MAMÁ': 250000,
                                     'Ana sintética con nombre muy largo': 200000}
        assert chart.current == 'Mi parte · Yo'
        assert chart.period == '2026-10'
        assert chart.subtitle.isVisible()
        assert 'Abonos familiares ya descontados' in chart.subtitle.text()
        assert 'No es el pago a Nu' in chart.subtitle.text()
        with patch('valenza.gui.people_month_chart.QMessageBox.information') as help_dialog:
            chart.subtitle.linkActivated.emit('explanation')
            help_dialog.assert_called_once_with(chart, '¿Qué estoy viendo?', chart.explanation_text())
        assert 'anteriores ni futuras' in chart.explanation_text()
        assert 'Compromisos del mes' in chart.explanation_text()
        assert sum(value for _, value in chart.values) == 550000
        # Keep the original body budget, plus the new visible explanation.
        assert chart.height() <= (500 if width < 480 else 300) + chart.subtitle.height() + chart.root.spacing()
        assert chart.list_scroll.verticalScrollBar().maximum() == 0
        assert 'Ana sintética con nombre muy largo' in chart.accessibleDescription()
        for row in chart.rows.values():
            assert row.width() <= chart.list_scroll.viewport().width()
            assert row.rect().contains(row.amount.geometry())
            assert row.amount.height() >= row.amount.fontMetrics().height()
            assert row.meter.height() == 4
        output = Path('artifacts/people-chart')
        output.mkdir(parents=True, exist_ok=True)
        assert chart.grab().save(str(output / f'people-{width}.png'))
        assert tables(repository) == before
        assert repository.database.connection.total_changes == changes
    finally:
        chart.close()
        window.close()
        app.processEvents()


def test_interactive_ring_rows_keyboard_month_controls_and_account_details(repository):
    repository.create_order(order_id='interactive', ordered_at='2026-10-15', merchant='Comercio sintético',
        instrument_id='card', original_cents=60000, discount_cents=0, charged_cents=60000,
        allocations=({'user_id': 'owner', 'amount_cents': 10000}, {'user_id': 'mama', 'amount_cents': 50000}))
    before = tables(repository)
    changes = repository.database.connection.total_changes
    app = create_application([])
    window = MainWindow(database=repository.database, test_mode=True)
    window.resize(1100, 850); window.show()
    window.dashboard_period_picker.setDate(QDate(2026, 10, 1))
    chart = window.dashboard_donut_chart
    try:
        window.dashboard_scroll.ensureWidgetVisible(chart.ring)
        app.processEvents()
        expected = list(chart.values)
        owner = 'Mi parte · Yo'
        chart.rows[owner].setFocus()
        QTest.keyClick(chart.rows[owner], Qt.Key.Key_Down)
        assert chart.selected_label == 'MAMÁ'
        assert chart.rows['MAMÁ'].isChecked() and chart.rows['MAMÁ'].hasFocus()
        assert window._table_id(window.dashboard_people, 5) == 'mama'
        QTest.keyClick(chart.rows['MAMÁ'], Qt.Key.Key_Up)
        assert chart.selected_label == owner
        window.dashboard_scroll.ensureWidgetVisible(chart.ring)
        app.processEvents()
        def hover(x, y):
            position = QPoint(x, y)
            QApplication.sendEvent(chart.ring, QMouseEvent(QEvent.Type.MouseMove,
                QPointF(position), QPointF(chart.ring.mapToGlobal(position)),
                Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
        hover(20, 109)
        assert chart.hover_label == 'MAMÁ'
        assert chart.rows['MAMÁ'].property('preview')
        QTest.mouseClick(chart.ring, Qt.MouseButton.LeftButton, pos=QPoint(20, 109))
        assert chart.selected_label == 'MAMÁ'
        hover(109, 109)
        assert not chart.hover_label
        assert chart.selected_label == 'MAMÁ'
        QTest.mouseClick(chart.rows[owner], Qt.MouseButton.LeftButton)
        assert chart.selected_label == owner
        chart.rows['MAMÁ'].setFocus()
        QTest.keyClick(chart.rows['MAMÁ'], Qt.Key.Key_Space)
        assert chart.selected_label == 'MAMÁ'
        assert chart.values == expected
        # The separate people table must also update the selected monthly amount,
        # even if a different portion was previously being previewed.
        owner_row = next(r for r in range(window.dashboard_people.rowCount())
                         if window.dashboard_people.item(r, 5).text() == 'owner')
        window.dashboard_people.selectRow(owner_row)
        hover(80, 15)
        row = next(r for r in range(window.dashboard_people.rowCount())
                   if window.dashboard_people.item(r, 5).text() == 'mama')
        window.dashboard_people.selectRow(row)
        assert chart.selected_label == 'MAMÁ' and not chart.hover_label
        assert dict(chart.values)[chart.selected_label] == 50000
        assert chart.rows['MAMÁ'].isChecked()
        chart.detail_button.click()
        assert window._table_id(window.dashboard_people, 5) == 'mama'
        assert window.dashboard_person_toggle.isChecked()
        chart.next.click()
        assert window.dashboard_period_picker.date() == QDate(2026, 11, 1)
        assert chart.period == '2026-11' and not chart.body.isHidden()
        assert chart.values == expected  # Unpaid normal purchases carry forward.
        app.processEvents()
        output = Path('artifacts/people-chart')
        output.mkdir(parents=True, exist_ok=True)
        chart.grab().save(str(output / 'empty-month.png'))
        chart.previous.click()
        assert chart.values == expected and chart.period == '2026-10'
        app.processEvents()
        window.dashboard_scroll.ensureWidgetVisible(chart)
        window.grab().save(str(output / 'integrated.png'))
        chart.grab().save(str(output / 'integrated-chart.png'))
        window.dashboard_period_picker.setDate(QDate(2026, 12, 1))
        chart.next.click()
        assert chart.period == '2027-01'
        assert tables(repository) == before
        assert repository.database.connection.total_changes == changes
    finally:
        window.close(); app.processEvents()


def test_selected_month_carries_unpaid_normal_orders_but_excludes_future_msi(repository):
    def order(key, amount, allocations, purchased, dates=()):
        repository.create_order(order_id=key, ordered_at=purchased, merchant='Compra sintética ' + key,
            instrument_id='card', original_cents=amount, discount_cents=0, charged_cents=amount,
            allocations=tuple({'user_id': person, 'amount_cents': value} for person, value in allocations),
            purchase_mode='MSI' if dates else 'CASH', financing_specs=dates or None)

    order('past', 90000, [('owner', 90000)], '2026-09-15')
    order('normal', 150000, [('owner', 50000), ('mama', 100000)], '2026-10-15')
    order('january', 60000, [('owner', 60000)], '2027-01-05')
    order('msi', 480000, [('owner', 160000), ('mama', 320000)], '2026-09-20',
          ('2026-10-15', '2026-11-15', '2026-12-15', '2027-01-15'))
    for key, source, amount in [('normal-paid', 'normal', 30000), ('msi-paid', 'msi', 20000)]:
        repository.record_receipt(payment_id=key, receivable_id=f'order:{source}:mama',
            received_at='2026-10-15', amount_cents=amount)
    before = tables(repository)
    changes = repository.database.connection.total_changes
    app = create_application([])
    window = MainWindow(database=repository.database, test_mode=True)
    try:
        for year, month, expected in [
            (2026, 9, {'Mi parte · Yo': 90000, 'MAMÁ': 0}),
            (2026, 10, {'Mi parte · Yo': 180000, 'MAMÁ': 130000}),
            (2026, 11, {'Mi parte · Yo': 180000, 'MAMÁ': 150000}),
            (2026, 12, {'Mi parte · Yo': 180000, 'MAMÁ': 150000}),
            (2027, 1, {'Mi parte · Yo': 240000, 'MAMÁ': 150000}),
            (2027, 2, {'Mi parte · Yo': 200000, 'MAMÁ': 70000}),
        ]:
            window.dashboard_period_picker.setDate(QDate(year, month, 1))
            assert dict(window.dashboard_donut_chart.values) == expected
            assert window.dashboard_donut_chart.period == f'{year:04d}-{month:02d}'
            assert window.dashboard_donut_chart.month.text() in window.dashboard_donut_chart.explanation_text()
            assert window.dashboard_donut_chart.current == 'Mi parte · Yo'
        assert tables(repository) == before
        assert repository.database.connection.total_changes == changes
    finally:
        window.close()
        app.processEvents()


@pytest.mark.parametrize('width', [300, 820])
def test_many_people_names_and_large_amounts_fit_in_the_card(width):
    app = create_application([])
    chart = PeopleMonthChart()
    values = [('Mi parte · Yo', 987654321)] + [
        (f'Persona sintética con nombre y apellidos largos {index}', 123456789 + index)
        for index in range(7)]
    chart.set_data(values, 'Mi parte · Yo', period='2026-10')
    chart.resize(width, chart.sizeHint().height()); chart.show(); app.processEvents()
    chart.resize(width, chart.sizeHint().height()); app.processEvents()
    try:
        assert chart.width() == width
        assert chart.list_scroll.height() <= 240
        assert chart.list_scroll.verticalScrollBar().maximum() > 0
        for row in chart.rows.values():
            assert row.width() <= chart.list_scroll.viewport().width()
            assert row.rect().contains(row.amount.geometry())
            assert row.rect().contains(row.name.geometry())
            assert row.amount.width() >= row.amount.fontMetrics().horizontalAdvance(row.amount.text())
        chart.set_data([(label, 0) for label, _ in values], 'Mi parte · Yo', period='2026-11')
        chart.resize(width, chart.sizeHint().height()); app.processEvents()
        assert chart.body.isHidden() and chart.empty.isVisible()
        assert chart.rect().contains(chart.empty.geometry())
        assert chart.header_widget.geometry().bottom() < chart.empty.geometry().top()
    finally:
        chart.close(); app.processEvents()


def test_chart_matches_current_preparation_with_old_orders_msi_and_partial_receipts(repository):
    from datetime import date
    from valenza.gui.home_people_month import people_month_breakdown
    from valenza.gui.payment_preparation import preparation_items
    repo = repository
    repo.create_order(order_id='old-unpaid', ordered_at='2026-08-01', merchant='Compra anterior pendiente',
                      instrument_id='card', original_cents=40000, discount_cents=0, charged_cents=40000,
                      allocations=({'user_id': 'owner', 'amount_cents': 10000},
                                   {'user_id': 'mama', 'amount_cents': 30000}))
    repo.create_order(order_id='monthly', ordered_at='2026-08-02', merchant='MSI de tres meses',
                      instrument_id='card', original_cents=90000, discount_cents=0, charged_cents=90000,
                      allocations=({'user_id': 'owner', 'amount_cents': 30000},
                                   {'user_id': 'mama', 'amount_cents': 60000}),
                      purchase_mode='MSI', financing_specs=('2026-10-15', '2026-11-15', '2026-12-15'))
    for key, order, paid in [('old-paid', 'old-unpaid', 3000), ('msi-paid', 'monthly', 5000)]:
        repo.record_receipt(payment_id=key, receivable_id=f'order:{order}:mama',
                            amount_cents=paid, received_at='2026-10-01')
    before = tables(repo)
    changes = repo.database.connection.total_changes
    result = people_month_breakdown(repo, date(2026,10,1))
    assert result['amounts'] == {'owner': 20000, 'mama': 42000}
    preparation = {}
    for item in preparation_items(repo, 'card', as_of=date(2026,10,1)):
        preparation[item['user_id']] = preparation.get(item['user_id'], 0) + max(0, item['remaining_cents'])
    assert result['amounts'] == preparation
    for person, amount in result['amounts'].items():
        assert sum(s['amount_cents'] for s in result['sources'][person]) == amount
    app = create_application([])
    window = MainWindow(database=repo.database, test_mode=True)
    window.dashboard_period_picker.setDate(QDate(2026,10,1))
    chart = window.dashboard_donut_chart
    assert dict(chart.values) == {'Mi parte · Yo': 20000, 'MAMÁ': 42000}
    assert 'Compra anterior pendiente' in chart.rows['MAMÁ'].toolTip()
    assert 'MSI del mes' in chart.rows['MAMÁ'].toolTip()
    assert tables(repo) == before and repo.database.connection.total_changes == changes
    window.close()


def test_chart_does_not_treat_unknown_msi_dates_as_full_purchase(repository):
    from datetime import date
    from valenza.gui.home_people_month import people_month_breakdown
    repo = repository
    repo.create_order(order_id='no-dates', ordered_at='2026-09-01', merchant='MSI sin calendario',
                      instrument_id='card', original_cents=60000, discount_cents=0, charged_cents=60000,
                      allocations=({'user_id': 'owner', 'amount_cents': 0},
                                   {'user_id': 'mama', 'amount_cents': 60000}),
                      purchase_mode='MSI', financing_specs=(None, None, None))
    result = people_month_breakdown(repo, date(2026,10,1))
    assert not any(result['amounts'].values())
    assert result['warnings']
