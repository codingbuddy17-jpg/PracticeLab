"""
Every raw-DDL table must auto-assign its own id.

This is the SQLite-hides-a-PostgreSQL-fault trap, and it cost the whole E/M
module in production.

`id INTEGER PRIMARY KEY` is, in SQLite, the exact phrase that makes a column
the auto-assigning rowid alias. In PostgreSQL it is a plain integer with no
default, so every insert that omits id raises NotNullViolation. `database.py`
already has `_PK` for precisely this reason — the practice_* tables were fixed
after the same fault — but the three em_* tables were written with the literal
and nobody carried the fix across.

Why no test caught it: these tables have **no ORM model**, so `create_all()`
never corrects them the way it does for tables it owns, and the suite runs on
SQLite where the literal works perfectly. 2,510 tests passed while no E/M
answer key, grading result or scoring config could be written to production.

This reads the DDL as text rather than executing it, because executing it on
SQLite is exactly the thing that proves nothing.
"""
import pathlib
import re

DATABASE_PY = (pathlib.Path(__file__).resolve().parents[1] / "database.py").read_text()

# Tables created by raw DDL AND absent from the ORM: nothing else builds them,
# so the DDL is the only chance to get the primary key right.
RAW_CREATE = re.compile(
    r"CREATE TABLE IF NOT EXISTS (\w+) \(\s*\n\s*id ([^,\n]+),", re.M)


def _orm_tables() -> set:
    from database import Base
    import models  # noqa: F401  — registers every model on the metadata
    return set(Base.metadata.tables)


class TestRawTablesAutoAssignTheirIds:
    def test_no_raw_table_declares_a_bare_integer_primary_key(self):
        orm = _orm_tables()
        offenders = []
        for table, pk in RAW_CREATE.findall(DATABASE_PY):
            if table in orm:
                # create_all() owns these and gives them a real SERIAL; the
                # raw statement is a no-op behind IF NOT EXISTS.
                continue
            if "{_PK}" not in pk:
                offenders.append("%s -> id %s" % (table, pk.strip()))
        assert offenders == [], (
            "raw-DDL tables with a hand-written primary key. On PostgreSQL "
            "these get no default and every insert fails, while SQLite hides "
            "it. Use {_PK}: " + "; ".join(offenders))

    def test_the_helper_still_means_what_this_test_assumes(self):
        """
        If `_PK` ever stopped emitting SERIAL on PostgreSQL, the test above
        would keep passing while every table it guards broke.
        """
        assert 'SERIAL PRIMARY KEY' in DATABASE_PY
        assert 'INTEGER PRIMARY KEY AUTOINCREMENT" if is_sqlite' in DATABASE_PY

    def test_the_em_tables_are_covered_by_this(self):
        """The three that actually broke, named so the regression is explicit."""
        orm = _orm_tables()
        found = {t: pk for t, pk in RAW_CREATE.findall(DATABASE_PY)
                 if t.startswith("em_")}
        assert set(found) == {"em_answer_keys", "em_grading_results",
                              "em_scoring_configs"}
        assert not (set(found) & orm), "em_* tables are not ORM-backed"
        for table, pk in found.items():
            assert "{_PK}" in pk, table
