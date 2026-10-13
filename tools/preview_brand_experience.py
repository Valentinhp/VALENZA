"""Offline visual QA: synthetic encrypted records, pages and secondary controls."""
import os
from pathlib import Path
import tempfile
from PySide6.QtCore import QDate, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QDateEdit, QSpinBox, QDoubleSpinBox, QLineEdit, QTextEdit, QCheckBox, QRadioButton,
    QTabWidget, QProgressBar, QMenu, QMessageBox, QFileDialog, QDialog, QCalendarWidget, QScrollArea)
from valenza.gui.app import create_application, MainWindow
from valenza.gui.branding import brand_icon
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository

def main():
    output = Path('artifacts/brand-experience') / os.environ.get('QT_SCALE_FACTOR', '1')
    output.mkdir(parents=True, exist_ok=True)
    app = create_application([])
    # Windows' offscreen platform does not enumerate system fonts automatically.
    for font in ('segoeui.ttf', 'segoeuib.ttf', 'georgia.ttf', 'georgiab.ttf'):
        QFontDatabase.addApplicationFont(str(Path('C:/Windows/Fonts') / font))
    def capture(widget, name):
        widget.show(); app.processEvents(); app.processEvents()
        widget.grab().save(str(output / f'{name}.png'))
    with tempfile.TemporaryDirectory(dir=output) as tmp:
        db = LocalDatabase.open(Path(tmp) / 'synthetic.db', 'brand-preview-synthetic'); db.migrate()
        repo = FinanceRepository(db)
        repo.add_person('owner', 'Alex (sintético)', is_owner=True)
        repo.add_person('family', 'Marina (sintética)')
        for identity, name in [('nu', 'Nu'), ('mp', 'Mercado Pago'), ('bbva', 'BBVA')]:
            repo.add_institution(identity, name)
            repo.add_instrument(identity+'-card', identity, 'Billetera' if identity=='mp' else 'Personal • 1234',
                'WALLET_BALANCE' if identity=='mp' else 'CREDIT_CARD')
        for index, name in enumerate(['Spotify Premium','YouTube Premium','Netflix','Amazon Prime','Disney+','Apple Music','Servicio propio']):
            repo.save_subscription(subscription_id=str(index), name=name, amount_cents=19900,
                instrument_id='nu-card', next_due='2026-10-20', allocations=[
                    dict(user_id='owner',amount_cents=9900), dict(user_id='family',amount_cents=10000)])
        repo.record_subscription_charge('0', cycle_date='2026-10-20', charged_at='2026-10-13')
        window = MainWindow(database=db, test_mode=True)
        for width, height, suffix in [(1080,760,''),(680,480,'-small')]:
            window.resize(width,height)
            for index in range(window.navigation.count()):
                window.navigation.setCurrentRow(index)
                if index==5: window.subscription_table.selectRow(0)
                if index==2: window.orders_table.selectRow(0)
                if index==3: window.collection_items.selectRow(0)
                if index==4: window.cards_table.selectRow(0)
                capture(window, f'page-{index}{suffix}')
                scroll = window.pages.currentWidget()
                if not isinstance(scroll, QScrollArea):
                    scroll = next((s for s in scroll.findChildren(QScrollArea) if s.isVisible()), None)
                if scroll is not None:
                    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                    capture(window, f'page-{index}{suffix}-bottom')
        window.resize(1080,760); window.navigation.setCurrentRow(5)
        def capture_dialog():
            dialog = app.activeModalWidget()
            if dialog:
                capture(dialog, 'subscription-edit')
                combo = dialog.findChild(QComboBox)
                combo.showPopup(); app.processEvents()
                capture(combo.view().window(), 'subscription-payment-popup')
                combo.hidePopup(); dialog.reject()
        QTimer.singleShot(0,capture_dialog)
        window._edit_subscription('0')
        window.close(); app.processEvents(); db.close()
    gallery = QWidget(); gallery.setWindowTitle('Warm Finance · controles secundarios'); gallery.resize(760,840)
    layout = QVBoxLayout(gallery)
    title = QLabel('Controles y estados'); title.setObjectName('pageTitle'); layout.addWidget(title)
    combo = QComboBox()
    for name in ['Spotify','YouTube Premium','Netflix','Apple Music','Disney+','Servicio propio']:
        combo.addItem(brand_icon(name), name)
    layout.addWidget(combo)
    row = QHBoxLayout(); layout.addLayout(row)
    date = QDateEdit(QDate(2026,10,13)); date.setCalendarPopup(True); row.addWidget(date)
    row.addWidget(QSpinBox()); row.addWidget(QDoubleSpinBox())
    for text, state in [('Campo editable',''),('Campo deshabilitado','disabled'),('Revisar importe','error')]:
        field = QLineEdit(text)
        if state=='disabled': field.setEnabled(False)
        if state=='error': field.setProperty('validationState','error')
        layout.addWidget(field)
    text = QTextEdit('Texto y observaciones'); text.setMaximumHeight(70); layout.addWidget(text)
    row = QHBoxLayout(); layout.addLayout(row)
    for cls in [QCheckBox,QRadioButton]:
        for checked in [False,True]:
            control = cls('Seleccionado' if checked else 'Disponible'); control.setChecked(checked); row.addWidget(control)
    tabs = QTabWidget(); tabs.addTab(QLabel('Contenido'), 'Resumen'); tabs.addTab(QLabel('Detalle'), 'Movimientos'); layout.addWidget(tabs)
    calendar = QCalendarWidget(); calendar.setSelectedDate(QDate(2026,10,13)); layout.addWidget(calendar)
    progress = QProgressBar(); progress.setValue(65); layout.addWidget(progress)
    capture(gallery,'controls')
    combo.setFocus(); combo.showPopup(); app.processEvents(); capture(combo.view().window(),'service-popup'); combo.hidePopup()
    menu = QMenu(gallery); menu.addAction('Editar'); menu.addAction('Pausar'); menu.addSeparator()
    menu.addMenu('Más opciones').addAction('Consultar detalle'); menu.addAction('No disponible').setEnabled(False)
    menu.popup(gallery.mapToGlobal(gallery.rect().center())); app.processEvents(); capture(menu,'context-menu'); menu.close()
    message = QMessageBox(QMessageBox.Icon.Question,'Confirmación','¿Guardar los cambios de presentación?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,gallery)
    capture(message,'confirmation'); message.close()
    files = QFileDialog(gallery,'Seleccionar respaldo cifrado',str(output.resolve()),'Base cifrada (*.db)')
    files.setOption(QFileDialog.Option.DontUseNativeDialog); files.resize(760,480)
    capture(files,'file-dialog'); files.close(); gallery.close()
    print(output)

if __name__ == '__main__':
    main()
