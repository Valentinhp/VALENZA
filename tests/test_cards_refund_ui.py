"""Presentation only: real Qt widgets backed by isolated encrypted fixtures."""
from datetime import datetime
from PySide6.QtWidgets import QLabel, QWidget, QPushButton, QStyleOptionComboBox, QStyle
from PySide6.QtCore import Qt
from test_home_polish import synthetic, seed
from test_bank_reconciliation import financial_snapshot
from valenza.gui.app import MainWindow


def settle(app):
    for _ in range(16):
        app.processEvents()


def assert_combo_text_fits(combo):
    option = QStyleOptionComboBox()
    combo.initStyleOption(option)
    field = combo.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option,
                                        QStyle.SubControl.SC_ComboBoxEditField, combo)
    assert field.width() >= combo.fontMetrics().horizontalAdvance(combo.currentText())


def assert_siblings_fit(parent):
    widgets = [w for w in parent.findChildren(QWidget) if w.parentWidget() is parent
               and w.isVisible() and not w.geometry().isEmpty()]
    for i, widget in enumerate(widgets):
        assert parent.rect().contains(widget.geometry()), (widget.objectName(), widget.geometry(), parent.size())
        for other in widgets[i+1:]:
            assert not widget.geometry().intersects(other.geometry()), (type(widget).__name__, type(other).__name__, widget.geometry(), other.geometry())
        if isinstance(widget, QLabel) and widget.wordWrap():
            assert widget.height() >= widget.heightForWidth(widget.width())


def test_cards_expanding_sections_never_overlap_and_collapse(synthetic, tmp_path):
    app, repo = synthetic; seed(repo)
    repo.record_bank_balance('card1', 25000, datetime.now().astimezone().isoformat(timespec='seconds'))
    before = financial_snapshot(repo)
    changes = repo.database.connection.total_changes
    window = MainWindow(database=repo.database, test_mode=True)
    window.show(); window._show_page(4)
    row = next(r for r in range(window.cards_table.rowCount()) if window.cards_table.item(r,12).text()=='card1')
    window.cards_table.selectRow(row)
    toggle, content = window.card_panels['bank']; toggle.setChecked(True)
    for width in (680, 900, 1920, 900):
        window.resize(width, 850); settle(app)
        for kind in ('TOTAL', 'NO_INTEREST', 'OTHER'):
            window.bank_query_type.setCurrentIndex(window.bank_query_type.findData(kind)); settle(app)
            if kind == 'NO_INTEREST':
                assert_combo_text_fits(window.bank_query_type)
            assert_siblings_fit(content)
            assert_siblings_fit(window.bank_form_widget)
            for text in ('Opciones avanzadas', 'Tarjetas de una misma línea', 'Ver desglose bancario', 'Ver historial de consultas'):
                button = next(b for b in content.findChildren(QPushButton) if b.text()==text)
                button.setChecked(True); settle(app)
                if text=='Ver historial de consultas':
                    window.bank_history.selectRow(0); settle(app)
                assert_siblings_fit(content)
                for child in content.findChildren(QWidget):
                    if child.isVisible() and child.layout() is not None:
                        assert_siblings_fit(child)
                if kind=='NO_INTEREST' and width==900:
                    slug = {'Opciones avanzadas':'opciones', 'Tarjetas de una misma línea':'linea',
                            'Ver desglose bancario':'desglose', 'Ver historial de consultas':'historial'}[text]
                    content.grab().save(str(tmp_path/f'cards-expanded-{slug}.png'))
                button.setChecked(False); settle(app)
                assert_siblings_fit(content)
        window.bank_query_type.setCurrentIndex(window.bank_query_type.findData('NO_INTEREST')); settle(app)
        window.cards_scroll.ensureWidgetVisible(window.bank_query_save); settle(app)
        assert window.cards_scroll.horizontalScrollBar().maximum()==0
        window.grab().save(str(tmp_path/f'cards-{width}.png'))
        content.grab().save(str(tmp_path/f'cards-panel-{width}.png'))
        (tmp_path/f'cards-labels-{width}.txt').write_text(str([
            (label.text()[:30],label.geometry().getRect(),label.minimumHeight(),label.maximumHeight(),label.heightForWidth(label.width()))
            for label in content.findChildren(QLabel) if label.parentWidget() is content and label.isVisible()]),encoding='utf-8')
        expanded = content.parentWidget().height()
        toggle.setChecked(False); settle(app)
        assert content.parentWidget().height() < expanded
        toggle.setChecked(True); settle(app)
    window.showMaximized(); settle(app)
    assert_siblings_fit(content)
    window.cards_scroll.ensureWidgetVisible(window.bank_query_save); settle(app)
    window.grab().save(str(tmp_path/'cards-maximized.png'))
    assert financial_snapshot(repo)==before
    assert repo.database.connection.total_changes==changes
    window.close()


def test_cards_all_sections_and_validation_keep_finances_unchanged(synthetic):
    app, repo = synthetic
    seed(repo)
    repo.record_bank_balance('card1', 25000, datetime.now().astimezone().isoformat(timespec='seconds'))
    before = financial_snapshot(repo)
    changes = repo.database.connection.total_changes
    window = MainWindow(database=repo.database, test_mode=True)
    window.show(); window._show_page(4)
    row = next(r for r in range(window.cards_table.rowCount()) if window.cards_table.item(r,12).text() == 'card1')
    window.cards_table.selectRow(row)
    for toggle, _ in window.card_panels.values():
        toggle.setChecked(True)
    bank = window.card_panels['bank'][1]
    for button in bank.findChildren(QPushButton):
        if button.isCheckable():
            button.setChecked(True)
    for width in (640, 900, 1536, 1920, 680):
        window.resize(width, 768); settle(app)
        for kind in ('NO_INTEREST', 'TOTAL', 'OTHER', 'MINIMUM'):
            window.bank_query_type.setCurrentIndex(window.bank_query_type.findData(kind))
            window.bank_query_amount.setText('123.45'); settle(app)
            for _, panel in window.card_panels.values():
                assert_siblings_fit(panel)
                for child in panel.findChildren(QWidget):
                    if child.isVisible() and child.layout() is not None:
                        assert_siblings_fit(child)
            assert window.cards_scroll.horizontalScrollBar().maximum() == 0
        window.bank_history.selectRow(0); settle(app)
        account = window.bank_history.item(0, 5)
        assert account.text() == 'Tarjeta principal'
        assert account.data(Qt.ItemDataRole.UserRole) == 'card1'
        assert 'card1' in account.toolTip()
        window.cards_scroll.ensureWidgetVisible(window.bank_scope_save); settle(app)
        point = window.bank_scope_save.mapTo(window.cards_scroll.viewport(), window.bank_scope_save.rect().center())
        assert window.cards_scroll.viewport().rect().contains(point)
    errors = []
    window._show_error = errors.append
    window.bank_query_type.setCurrentIndex(window.bank_query_type.findData('NO_INTEREST'))
    window.bank_closing_date.clear(); window.bank_due_date.clear()
    window.bank_query_save.click(); settle(app)
    assert errors and 'fecha' in errors[-1].lower()
    assert financial_snapshot(repo) == before
    assert repo.database.connection.total_changes == changes
    window.close()
