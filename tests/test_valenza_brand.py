from valenza.gui.app import default_database_path


def test_new_installation_uses_valenza_paths(tmp_path):
    assert default_database_path(home=tmp_path) == tmp_path / 'AppData/Local/Valenza/valenza.db'
    assert default_database_path(home=tmp_path, test_mode=True) == tmp_path / 'AppData/Local/Valenza/valenza-test.db'


def test_existing_legacy_database_stays_in_place(tmp_path):
    legacy = tmp_path / 'AppData/Local/SGCCC/sgccc.db'
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b'synthetic-path-test')
    assert default_database_path(home=tmp_path) == legacy
    assert default_database_path(home=tmp_path, test_mode=True).name == 'valenza-test.db'
    assert legacy.read_bytes() == b'synthetic-path-test'
    preferred = tmp_path / 'AppData/Local/Valenza/valenza.db'
    preferred.parent.mkdir(parents=True)
    preferred.write_bytes(b'synthetic-new-path')
    assert default_database_path(home=tmp_path) == preferred
