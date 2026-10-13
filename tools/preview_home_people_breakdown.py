"""Render only synthetic encrypted Home accordion scenarios."""
from pathlib import Path
import os
import sys
import tempfile
from PySide6.QtCore import QPoint
from PySide6.QtGui import QFontDatabase
from valenza.gui.app import MainWindow, create_application
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from test_home_people_breakdown import seed_breakdown


def main():
    output = Path('artifacts/home-people-breakdown') / os.environ.get('QT_SCALE_FACTOR', '1')
    output.mkdir(parents=True, exist_ok=True)
    app = create_application([])
    for name in ('segoeui.ttf','segoeuib.ttf','georgia.ttf','georgiab.ttf'):
        QFontDatabase.addApplicationFont(str(Path('C:/Windows/Fonts') / name))
    with tempfile.TemporaryDirectory(dir=output) as tmp:
        db = LocalDatabase.open(Path(tmp) / 'synthetic.db', 'synthetic-accordion-preview'); db.migrate()
        assert db.encrypted
        repo = FinanceRepository(db)
        for identity, name in [('owner','Alex'), ('mama','Joaquín')]:
            repo.add_person(identity,name,is_owner=identity=='owner')
        for identity,name in [('bank','Banco ficticio'),('mp','Mercado Pago ficticio')]:
            repo.add_institution(identity,name)
        for identity, bank, label, kind in [('card','bank','Tarjeta ficticia','CREDIT_CARD'),
            ('wallet','mp','Billetera ficticia','WALLET_BALANCE'),('other','mp','Otro destino','OTHER')]:
            repo.add_instrument(identity,bank,label,kind)
        seed_breakdown(repo)
        before = repo.dashboard_summary(), repo.people_debt_summary(), db.connection.total_changes
        window = MainWindow(database=db,test_mode=True); window.show()
        panel = window.dashboard_person_details
        for width,height in [(1080,760),(680,480)]:
            window.resize(width,height)
            window.dashboard_person_toggle.setChecked(False)
            window.dashboard_person_toggle.click(); app.processEvents(); app.processEvents()
            for section in panel.sections.values(): section.toggle.setChecked(False)
            window.dashboard_scroll.verticalScrollBar().setValue(
                window.dashboard_person_section.mapTo(window.dashboard_scroll.widget(), QPoint()).y())
            app.processEvents()
            window.grab().save(str(output / f'people-list-{width}.png'))
            panel.sections['mama'].toggle.click(); app.processEvents(); app.processEvents()
            panel.grab().save(str(output / f'orders-pending-{width}.png'))
            window.grab().save(str(output / f'home-expanded-{width}.png'))
            panel.sections['mama'].paid_toggle.click(); app.processEvents(); app.processEvents()
            panel.grab().save(str(output / f'orders-with-paid-{width}.png'))
            panel.sections['mama'].toggle.click()
            for identity in ('empty','settled'):
                section = panel.sections[identity]
                section.toggle.click(); app.processEvents(); app.processEvents()
                panel.grab().save(str(output / f'{identity}-{width}.png'))
                section.toggle.click()
        assert before == (repo.dashboard_summary(),repo.people_debt_summary(),db.connection.total_changes)
        window.database = None; window.close(); app.processEvents(); db.close()
    print(output)


if __name__ == '__main__':
    main()
