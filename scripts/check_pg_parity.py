"""
Build the schema on a real PostgreSQL and check what SQLite cannot.

The suite runs on SQLite, which is more permissive than production in ways
that have each cost a real outage:

  * `id INTEGER PRIMARY KEY` auto-assigns in SQLite. In PostgreSQL it is a
    plain integer with no default, and every insert omitting id fails. This
    took down the entire E/M module — no answer key, grading result or scoring
    config could be written — while 2,510 tests passed.
  * VARCHAR lengths are not enforced by SQLite. `String(60)` accepted a
    98-character value locally and was rejected outright by PostgreSQL.

Both are properties of the built schema, so neither needs the test suite to
find them: build the schema and look. That takes seconds.

    PARITY_DATABASE_URL=postgresql://... python scripts/check_pg_parity.py

Exits non-zero on a finding, so it can gate a deploy.
"""
import os
import pathlib
import sys
import uuid

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))

URL = os.environ.get("PARITY_DATABASE_URL", "").strip()
if not URL:
    print("PARITY_DATABASE_URL is not set — nothing to check against.")
    print("This check is a no-op without a real PostgreSQL; it is not a pass.")
    sys.exit(0)

for key in ("STORAGE_ENDPOINT_URL", "STORAGE_ACCESS_KEY", "STORAGE_SECRET_KEY",
            "STORAGE_BUCKET_NAME", "STORAGE_PUBLIC_URL", "MASTER_ADMIN_PASSPHRASE"):
    os.environ.setdefault(key, "x")
os.environ["DATABASE_URL"] = URL

from sqlalchemy import create_engine, text  # noqa: E402

SCHEMA = "parity_%s" % uuid.uuid4().hex[:10]

# Columns that hold text somebody WRITES. A length on one of these is a future
# rejection: notes and titles outgrow any number picked in advance.
PROSE_HINTS = ("notes", "reason", "rationale", "feedback", "comment",
               "summary", "title", "description")

# ...unless the name says it is a bounded vocabulary. "rationale_tier" contains
# "rationale" and holds one of four words; flagging it teaches people to ignore
# this check, which is worse than not having it.
BOUNDED_SUFFIXES = ("_tier", "_type", "_status", "_level", "_label", "_id",
                    "_code", "_by")

# CMS publishes short_description at a fixed width; the bound is theirs, not a
# guess of ours.
ALLOWED = {("code_descriptions", "short_description")}


def main() -> int:
    admin = create_engine(URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text('CREATE SCHEMA "%s"' % SCHEMA))
    eng = create_engine(URL, connect_args={"options": "-csearch_path=%s" % SCHEMA})
    findings = []       # fail the build
    warnings = []       # say it, do not block on it
    try:
        import database
        database.engine = eng
        from database import Base, _run_migrations
        import models  # noqa: F401 — registers every model

        Base.metadata.create_all(eng)
        # Not wrapped in try/except: on PostgreSQL a failing migration is a
        # defect. Swallowing them is how a broken table reached production.
        _run_migrations()

        with eng.connect() as c:
            tables = [r[0] for r in c.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :s AND table_type = 'BASE TABLE'"
                " ORDER BY table_name"), {"s": SCHEMA})]

            # ── 1. every id auto-assigns ──────────────────────────────────
            no_default = [r[0] for r in c.execute(text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = :s AND column_name = 'id' "
                "  AND column_default IS NULL"), {"s": SCHEMA})]
            for t in no_default:
                findings.append(
                    "%s.id has no default — every insert omitting id will fail. "
                    "Use the _PK helper in database.py." % t)

            # ── 2. prose in a bounded VARCHAR ─────────────────────────────
            for tbl, col, n in c.execute(text(
                    "SELECT table_name, column_name, character_maximum_length "
                    "FROM information_schema.columns "
                    "WHERE table_schema = :s AND data_type = 'character varying' "
                    "  AND character_maximum_length IS NOT NULL"), {"s": SCHEMA}):
                name = col.lower()
                if (tbl, col) in ALLOWED:
                    continue
                if name.endswith(BOUNDED_SUFFIXES):
                    continue
                if any(h in name for h in PROSE_HINTS) and n < 500:
                    warnings.append(
                        "%s.%s is VARCHAR(%s) and holds written text — SQLite "
                        "will not enforce the length and PostgreSQL will. "
                        "Text is metadata-only to switch to." % (tbl, col, n))

        print("schema built on PostgreSQL: %d tables" % len(tables))
    finally:
        eng.dispose()
        with admin.connect() as c:
            c.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % SCHEMA))
        admin.dispose()

    if warnings:
        # Warnings, not failures, and deliberately so. These are pre-existing
        # and none has broken anything yet; failing on them would make this
        # check red from the day it is switched on, and a check that is always
        # red is a check nobody reads.
        print("\nWARNINGS (%d) — worth fixing, not worth blocking a deploy:"
              % len(warnings))
        for w in warnings:
            print("  !", w)

    if findings:
        print("\nPARITY FAILURES (%d):" % len(findings))
        for f in findings:
            print("  ✗", f)
        return 1
    print("\nPASS — every id auto-assigns on PostgreSQL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
