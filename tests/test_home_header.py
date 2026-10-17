"""Header geometry and read-only navigation, with synthetic encrypted data."""
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton
from PySide6.QtTest import QTest
from test_home_polish import synthetic, seed
from valenza.gui.app import MainWindow


def settle(app):
    for _ in range(8):
        app.processEvents()


def test_header_normal_wide_small_and_maximized_without_duplicate_controls(synthetic,tmp_path):
    app,repo=synthetic;seed(repo)
    db=repo.database
    before=repo.dashboard_summary();changes=db.connection.total_changes
    window=MainWindow(database=db,test_mode=True)
    window.show();settle(app)
    identities=(id(window.dashboard_period_picker),id(window.prepare_payment_button))
    results=[]
    for width,height in ((900,700),(1536,900),(1920,1080),(1100,760),(820,650),(680,480),(1366,768),(900,700)):
        window.resize(width,height);settle(app)
        actions=window.dashboard_header_actions
        buttons=actions.findChildren(QPushButton)
        positions=[(b.x(),b.y(),b.width(),b.height()) for b in buttons]
        viewport=window.dashboard_scroll.viewport().width()
        assert len(buttons)==4 and len(set(b.text() for b in buttons))==4
        assert (id(window.dashboard_period_picker),id(window.prepare_payment_button))==identities
        assert window.dashboard_scroll.widget().width()<=viewport
        assert window.dashboard_scroll.horizontalScrollBar().maximum()==0
        assert all(b.geometry().right()<actions.width() and b.geometry().bottom()<actions.height() for b in buttons)
        if width>=900:
            assert len({b.y() for b in buttons})==1, positions
            assert window.dashboard_header_grid.getItemPosition(window.dashboard_header_grid.indexOf(actions))[0]==0
            assert actions.height()<60
            assert actions.x()-(window.dashboard_heading.x()+window.dashboard_heading.width())<=16
        else:
            assert len({b.y() for b in buttons})<=2
        assert not window.dashboard_brand.isVisible()
        window.dashboard_period_picker.setFocus()
        original_focus = app.focusWidget()
        QTest.keyClick(window.dashboard_period_picker, Qt.Key.Key_Tab)
        assert app.focusWidget() is not None
        QTest.keyClick(app.focusWidget(), Qt.Key.Key_Backtab)
        assert app.focusWidget() is original_focus
        window.grab().save(str(tmp_path/f'header-{width}.png'))
        if width in (900, 1920, 680):
            window.dashboard_scroll.ensureWidgetVisible(window.dashboard_donut_chart)
            settle(app)
            window.grab().save(str(tmp_path/f'donut-{width}.png'))
            window.dashboard_scroll.verticalScrollBar().setValue(0)
            settle(app)
        results.append(dict(size=[width,height],viewport=viewport,buttons=positions,action_height=actions.height()))
    window.showMaximized();settle(app)
    assert window.isMaximized()
    window.grab().save(str(tmp_path/'header-maximized.png'))
    assert window.dashboard_scroll.horizontalScrollBar().maximum()==0
    window.showNormal();window.resize(900,700);settle(app)
    assert len({b.y() for b in window.dashboard_header_actions.findChildren(QPushButton)})==1
    assert repo.dashboard_summary()==before and db.connection.total_changes==changes
    (tmp_path/'header-geometry.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    window.close()
