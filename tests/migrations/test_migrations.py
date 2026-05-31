from yuki.migrations import CURRENT_SCHEMA, run_migrations


def test_current_schema_is_int():
    assert isinstance(CURRENT_SCHEMA, int)
    assert CURRENT_SCHEMA >= 1


def test_run_migrations_noop_at_current(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    applied = run_migrations()
    assert applied == []
