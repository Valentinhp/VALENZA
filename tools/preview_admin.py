"""Render administration screens using exclusively a temporary encrypted fixture."""
from pathlib import Path
import tempfile

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QScrollArea
from PySide6.QtGui import QFont, QFontDatabase
from valenza.gui.app import MainWindow, create_application
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository


def main():
    import os
    scale = os.environ.get('QT_SCALE_FACTOR', '1')
    output = Path('artifacts/admin-preview') / scale
    output.mkdir(parents=True, exist_ok=True)
    app = create_application([])
    font_id = QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    if font_id >= 0:
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    with tempfile.TemporaryDirectory(dir=output) as temporary:
        database = LocalDatabase.open(Path(temporary) / 'synthetic.db', 'synthetic-preview-only')
        database.migrate()
        assert database.encrypted
        repo = FinanceRepository(database)
        repo.add_person('owner', 'Alex (sintético)', is_owner=True)
        repo.add_person('family', 'Marina (sintética)')
        repo.add_person('inactive', 'Persona inactiva sintética')
        repo.deactivate_person('inactive')
        repo.add_institution('bank', 'Banco sintético')
        repo.add_instrument('card', 'bank', 'Tarjeta sintética', 'CREDIT_CARD')
        window = MainWindow(database=database, test_mode=True)
        window.show(); window.navigation.setCurrentRow(5); app.processEvents()
        window.grab().save(str(output / 'subscriptions-empty.png'))
        for identity, name, status in [('active', 'Música familiar', 'ACTIVE'), ('paused', 'Almacenamiento', 'PAUSED'), ('cancelled', 'Video mensual', 'CANCELLED')]:
            repo.save_subscription(subscription_id=identity, name=name, amount_cents=19900,
                instrument_id='card', next_due='2026-10-20', allocations=[
                    dict(user_id='owner', amount_cents=9900),
                    dict(user_id='family', amount_cents=10000, surcharge_cents=500)])
            if status != 'ACTIVE': repo.set_subscription_status(identity, status)
        window._refresh_subscriptions()
        for width, height, suffix in [(1080, 760, ''), (680, 480, '-small')]:
            window.resize(width, height)
            for index, name in [(5, 'subscriptions'), (1, 'users'), (6, 'settings')]:
                window.navigation.setCurrentRow(index)
                if index == 5: window.subscription_table.selectRow(0)
                if index == 1: window.people_table.selectRow(0)
                app.processEvents()
                app.processEvents()
                app.processEvents()
                window.grab().save(str(output / (name + suffix + '.png')))
                if suffix:
                    scroll = window.pages.currentWidget()
                    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                    app.processEvents(); app.processEvents()
                    window.grab().save(str(output / (name + suffix + '-details.png')))
        window.resize(1080, 760)
        window.navigation.setCurrentRow(5)
        window.subscription_table.selectRow(0)
        for name, action in [('new', lambda: window._edit_subscription()),
                             ('edit', lambda: window._edit_subscription('active')),
                             ('charge', window._subscription_charge_dialog)]:
            if name == 'charge':
                for row in range(window.subscription_table.rowCount()):
                    if window.subscription_table.item(row, 5).text() == 'active':
                        window.subscription_table.selectRow(row)
            def capture(name=name):
                dialog = next(d for d in window.findChildren(QDialog) if d.isVisible())
                app.processEvents()
                dialog.grab().save(str(output / ('subscription-' + name + '.png')))
                scroll = dialog.findChild(QScrollArea)
                scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                app.processEvents()
                dialog.grab().save(str(output / ('subscription-' + name + '-details.png')))
                dialog.reject()
            QTimer.singleShot(0, capture)
            action()
        assert not repo.list_orders()
        window.close()
        app.processEvents()
        database.close()
    print(f'Encrypted synthetic previews: {output}')


if __name__ == '__main__':
    main()
