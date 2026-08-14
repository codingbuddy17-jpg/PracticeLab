"""
Regenerate docs/figures/schema.json from the real schema.

schema.json was hand-produced for the first version of the handover documents
and then drifted: it still described 32 tables after the Auditor module took the
count to 41. This script removes the hand step.

It builds the schema the way the application does — create_all() plus the raw
migration DDL — against a throwaway SQLite file, then introspects it. That
matters: six tables (the E/M and practice-session ones) exist only in the raw
DDL and are invisible to Base.metadata, so introspecting the models alone would
silently omit them.

    cd docs && python _schema_json_build.py

Types are reported as SQLite renders them. They are close enough for a
reference document, but PostgreSQL is the source of truth for a live system —
the runbook says so, and this script is not trying to replace `\\d`.
"""
import json
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
BACKEND = HERE.parent / "backend"

# The app refuses to import without these; values are irrelevant, nothing is
# contacted.
os.environ.setdefault("STORAGE_ENDPOINT_URL", "x")
os.environ.setdefault("STORAGE_ACCESS_KEY", "x")
os.environ.setdefault("STORAGE_SECRET_KEY", "x")
os.environ.setdefault("STORAGE_BUCKET_NAME", "x")
os.environ.setdefault("STORAGE_PUBLIC_URL", "x")
os.environ.setdefault("MASTER_ADMIN_PASSPHRASE", "x")

tmp = pathlib.Path(tempfile.mkdtemp()) / "schema.db"
os.environ["DATABASE_URL"] = f"sqlite:///{tmp}"
sys.path.insert(0, str(BACKEND))

import main  # noqa: F401,E402  — imports every router, and so every model
from database import engine, init_db  # noqa: E402
from sqlalchemy import inspect  # noqa: E402

init_db()
insp = inspect(engine)

out: dict[str, dict] = {}
for table in sorted(insp.get_table_names()):
    if table == "sqlite_sequence":
        continue
    pks = set(insp.get_pk_constraint(table).get("constrained_columns") or [])
    out[table] = {
        "cols": [{
            "name": c["name"],
            "type": str(c["type"]),
            "notnull": not c["nullable"],
            "default": c.get("default"),
            "pk": c["name"] in pks,
        } for c in insp.get_columns(table)],
        "fks": [{
            "col": (fk["constrained_columns"] or [None])[0],
            "ref_table": fk["referred_table"],
            "ref_col": (fk["referred_columns"] or [None])[0],
        } for fk in insp.get_foreign_keys(table)],
        "uniq": [list(u["column_names"]) for u in insp.get_unique_constraints(table)],
    }

dest = HERE / "figures" / "schema.json"
dest.write_text(json.dumps(out, indent=1) + "\n")
cols = sum(len(t["cols"]) for t in out.values())
print(f"wrote {dest.relative_to(HERE.parent)} — {len(out)} tables, {cols} columns")
