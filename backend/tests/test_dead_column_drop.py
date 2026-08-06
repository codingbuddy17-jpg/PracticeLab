"""
The one destructive migration, and the guard rails around it.

Everything else in _run_migrations is additive by design: it runs on every
startup against the live database, so a step that removes data is a step that
can destroy it on a bad deploy. batch_coders.excel_generated_at is the
exception — it recorded whether a coder's offline Excel workbook had been
generated, that workflow is gone, and no code ever wrote the column, so every
row holds NULL and there is nothing to lose.
"""
from sqlalchemy import create_engine, inspect, text


def _columns(engine, table):
    return [c["name"] for c in inspect(engine).get_columns(table)]


def _fresh_db(tmp_path, monkeypatch):
    """A database built by the app's own migrations, isolated from the suite's."""
    import database

    url = f"sqlite:///{tmp_path}/drop.db"
    engine = create_engine(url)
    monkeypatch.setattr(database, "engine", engine)
    return engine


def test_the_dead_column_is_gone_after_migrations(tmp_path, monkeypatch):
    import database

    engine = _fresh_db(tmp_path, monkeypatch)
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE batch_coders (id INTEGER PRIMARY KEY, "
                          "coder_name TEXT, excel_generated_at TIMESTAMP)"))
        conn.commit()
    assert "excel_generated_at" in _columns(engine, "batch_coders")

    database._run_migrations()
    assert "excel_generated_at" not in _columns(engine, "batch_coders")


def test_the_rest_of_the_table_survives(tmp_path, monkeypatch):
    """A DROP COLUMN rebuilds the table on SQLite. The rows must come back."""
    import database

    engine = _fresh_db(tmp_path, monkeypatch)
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE batch_coders (id INTEGER PRIMARY KEY, "
                          "coder_name TEXT, excel_generated_at TIMESTAMP)"))
        conn.execute(text("INSERT INTO batch_coders (id, coder_name) VALUES (1, 'Alice')"))
        conn.commit()

    database._run_migrations()

    with engine.connect() as conn:
        assert conn.execute(text("SELECT coder_name FROM batch_coders")).scalar() == "Alice"


def test_running_migrations_twice_is_harmless(tmp_path, monkeypatch):
    """
    These run on every startup. A drop that errors on the second boot would
    turn a one-off cleanup into a permanent warning in the logs.
    """
    import database

    engine = _fresh_db(tmp_path, monkeypatch)
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE batch_coders (id INTEGER PRIMARY KEY, "
                          "coder_name TEXT, excel_generated_at TIMESTAMP)"))
        conn.commit()

    database._run_migrations()
    database._run_migrations()
    assert "excel_generated_at" not in _columns(engine, "batch_coders")


def test_a_database_that_never_had_the_column_is_untouched(tmp_path, monkeypatch):
    import database

    engine = _fresh_db(tmp_path, monkeypatch)
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE batch_coders (id INTEGER PRIMARY KEY, coder_name TEXT)"))
        conn.commit()

    database._run_migrations()
    cols = _columns(engine, "batch_coders")
    assert "excel_generated_at" not in cols
    # The additive steps still run: emp_id is one of them, and its absence
    # here would mean the drop had short-circuited the rest of the migration.
    assert {"id", "coder_name", "emp_id"} <= set(cols)
