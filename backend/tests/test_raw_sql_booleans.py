"""
No raw-SQL fixture may write 1 or 0 into a boolean column.

SQLite accepts it and PostgreSQL does not, so this class is invisible until the
nightly run — where it accounted for eight of twelve failures, and then for the
last six on the retry, because fixing the column named in the error left a
second literal three lines below it. An error only ever reports the first one.

So this enumerates rather than greps: every boolean column in the REAL schema,
checked against every raw INSERT in the suite. It must be the real schema —
`Base.metadata` is missing the six em_* and practice_* tables that exist only
in raw DDL, and the column that survived the first fix, practice_chart_drafts
.flagged, is in one of them. Asking the ORM would have reported all clear.
"""
import re

import sqlalchemy as sa
from pathlib import Path

TESTS = Path(__file__).resolve().parent


def _boolean_columns(engine):
    insp = sa.inspect(engine)
    out = {}
    for table in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns(table)
                if isinstance(c["type"], sa.Boolean)}
        if cols:
            out[table] = cols
    return out


def _raw_inserts(src):
    """(table, [column], [value]) for each `INSERT INTO t (...) VALUES (...)`."""
    for m in re.finditer(r"INSERT INTO\s+(\w+)\s*\(([^)]*)\)\s*VALUES\s*\(", src, re.S):
        names = [c.strip() for c in m.group(2).replace("\n", " ").split(",")]
        depth, vals = 1, ""
        for ch in src[m.end():]:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            vals += ch
        parts = [v.strip() for v in vals.replace("\n", " ").split(",")]
        if len(names) == len(parts):
            yield m.group(1), names, parts


def test_no_test_writes_an_integer_into_a_boolean_column(db):
    booleans = _boolean_columns(db.get_bind())
    # Guard the guard: if the schema introspection ever comes back empty, this
    # test would pass by finding nothing to check.
    assert len(booleans) > 20, "expected the real schema, got %d tables with booleans" % len(booleans)
    assert "practice_chart_drafts" in booleans, \
        "raw-DDL tables are missing — this is inspecting the ORM, not the schema"

    offenders = []
    for path in sorted(TESTS.glob("*.py")):
        for table, names, values in _raw_inserts(path.read_text()):
            for name, value in zip(names, values):
                if name in booleans.get(table, ()) and re.fullmatch(r"[01]", value):
                    offenders.append("%s: %s.%s = %s" % (path.name, table, name, value))

    assert not offenders, (
        "raw SQL writing an integer into a boolean column — PostgreSQL rejects "
        "these, SQLite does not:\n  " + "\n  ".join(offenders))
