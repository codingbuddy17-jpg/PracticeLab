from sqlalchemy import create_engine, inspect as sa_inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from config import settings


def _sync_url(url: str) -> str:
    url = url.replace("postgres://", "postgresql://", 1)
    url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


engine = create_engine(_sync_url(settings.DATABASE_URL), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    _run_migrations()


def _run_migrations():
    """
    Safe additive migrations — only adds missing columns, never drops data.
    Dialect-aware: works against both SQLite (local dev) and PostgreSQL (production).
    """
    is_sqlite = engine.dialect.name == "sqlite"
    insp = sa_inspect(engine)

    def _col_exists(table: str, col: str) -> bool:
        try:
            return col in [c["name"] for c in insp.get_columns(table)]
        except Exception:
            return False

    def _run(sql: str) -> None:
        with engine.connect() as conn:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                conn.rollback()

    def _add_col(table: str, col: str, pg_def: str, sqlite_def: str | None = None) -> None:
        """Add a column only if it doesn't exist — works on both dialects."""
        if _col_exists(table, col):
            return
        defn = (sqlite_def or pg_def) if is_sqlite else pg_def
        _run(f"ALTER TABLE {table} ADD COLUMN {col} {defn}")

    # ── chart_files ──────────────────────────────────────────────────────────
    _add_col("chart_files", "page_text", "TEXT")

    # ── chart_feedback (supplemental table, safe cross-dialect DDL) ──────────
    _run("""CREATE TABLE IF NOT EXISTS chart_feedback (
        id INTEGER PRIMARY KEY,
        chart_id INTEGER REFERENCES charts(id),
        chart_number VARCHAR(20) NOT NULL,
        reporter VARCHAR(100) NOT NULL,
        issues VARCHAR(500) NOT NULL,
        notes TEXT,
        status VARCHAR(20) DEFAULT 'Open',
        resolved_by VARCHAR(100),
        resolved_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # ── batch_coders ─────────────────────────────────────────────────────────
    _add_col("batch_coders", "emp_id", "VARCHAR(50)")

    # ── batches — additive columns ────────────────────────────────────────────
    _add_col("batches", "use_weighted", "BOOLEAN NOT NULL DEFAULT TRUE")
    _add_col("batches", "use_dpo",      "BOOLEAN NOT NULL DEFAULT FALSE")
    _add_col("batches", "closed_at",    "TIMESTAMPTZ",  "TIMESTAMP")
    _add_col("batches", "closed_by",    "VARCHAR(100)")
    _add_col("batches", "force_closed", "BOOLEAN NOT NULL DEFAULT FALSE")
    _add_col("batches", "force_close_reason", "TEXT")
    _add_col("batches", "notes", "JSONB DEFAULT '[]'", "TEXT DEFAULT '[]'")
    _add_col("batches", "tags",  "JSONB DEFAULT '[]'", "TEXT DEFAULT '[]'")

    # ── batches — status normalisation ────────────────────────────────────────
    # PostgreSQL only: convert any lingering native-enum column to plain VARCHAR.
    # SQLite stores everything as TEXT already so this DDL is not needed there.
    if not is_sqlite:
        _run("ALTER TABLE batches ALTER COLUMN status TYPE VARCHAR(20) USING status::text")
        _run("DROP TYPE IF EXISTS batchstatus")
    # Normalise legacy status labels to Open / Closed on both dialects.
    _run("UPDATE batches SET status = 'Open'   WHERE status IN ('Active', 'Grading', 'Draft')")
    _run("UPDATE batches SET status = 'Closed' WHERE status = 'Complete'")

    # ── grading_results — DPO columns ────────────────────────────────────────
    _add_col("grading_results", "dpo_dx_accuracy",   "FLOAT")
    _add_col("grading_results", "dpo_poa_accuracy",  "FLOAT")
    _add_col("grading_results", "dpo_proc_accuracy", "FLOAT")
    _add_col("grading_results", "dpo_overall_accuracy", "FLOAT")

    # ── batch_allocation_cycles (must exist before batch_charts FK ref) ───────
    _run("""CREATE TABLE IF NOT EXISTS batch_allocation_cycles (
        id INTEGER PRIMARY KEY,
        batch_id INTEGER REFERENCES batches(id) NOT NULL,
        cycle_number INTEGER NOT NULL,
        run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        run_by VARCHAR(100) NOT NULL,
        charts_per_coder INTEGER NOT NULL,
        notes VARCHAR(300)
    )""")

    # ── batch_charts — cycle FK (SQLite doesn't support inline FK in ALTER) ──
    _add_col("batch_charts", "cycle_id", "INTEGER REFERENCES batch_allocation_cycles(id)", "INTEGER")

    # ── scoring_configs — create first, then add columns ─────────────────────
    _run("""CREATE TABLE IF NOT EXISTS scoring_configs (
        id INTEGER PRIMARY KEY,
        specialty_type VARCHAR(10) NOT NULL UNIQUE,
        pdx_weight INTEGER NOT NULL DEFAULT 20,
        sdx_weight INTEGER NOT NULL DEFAULT 20,
        pcs_weight INTEGER,
        drg_weight INTEGER,
        cpt_weight INTEGER,
        pass_threshold INTEGER NOT NULL DEFAULT 80,
        drg_triggers TEXT DEFAULT '[]',
        overcoding_penalty INTEGER NOT NULL DEFAULT 1,
        updated_by VARCHAR(100),
        updated_at TIMESTAMP
    )""")
    _add_col("scoring_configs", "weighted_enabled",   "BOOLEAN NOT NULL DEFAULT TRUE",  "INTEGER NOT NULL DEFAULT 1")
    _add_col("scoring_configs", "dpo_enabled",        "BOOLEAN NOT NULL DEFAULT TRUE",  "INTEGER NOT NULL DEFAULT 1")
    _add_col("scoring_configs", "dpo_pass_threshold", "FLOAT NOT NULL DEFAULT 80.0", "REAL NOT NULL DEFAULT 80.0")

    # Seed default scoring configs (ON CONFLICT works on both PG and SQLite ≥3.24)
    _run("""INSERT INTO scoring_configs
        (specialty_type, pdx_weight, sdx_weight, pcs_weight, drg_weight,
         cpt_weight, pass_threshold, drg_triggers, overcoding_penalty)
       VALUES
        ('IP', 20, 20, 20, 40, NULL, 80,
         '["pdx_mismatch","ccmcc_missing","pcs_undercoded","pcs_overcoded","spurious_sdx","spurious_pcs"]',
         1),
        ('OP', 25, 25, NULL, NULL, 50, 90, '[]', 1)
       ON CONFLICT (specialty_type) DO NOTHING""")

    # ── self_practice tables ──────────────────────────────────────────────────
    _run("""CREATE TABLE IF NOT EXISTS self_practice_submissions (
        id INTEGER PRIMARY KEY,
        coder_name VARCHAR(100) NOT NULL,
        emp_id VARCHAR(50),
        source VARCHAR(20) NOT NULL DEFAULT 'coder',
        status VARCHAR(20) NOT NULL DEFAULT 'pending_review',
        trainer_feedback TEXT,
        reviewed_by VARCHAR(100),
        reviewed_at TIMESTAMP,
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    _run("""CREATE TABLE IF NOT EXISTS self_practice_results (
        id INTEGER PRIMARY KEY,
        submission_id INTEGER REFERENCES self_practice_submissions(id) NOT NULL,
        chart_id INTEGER REFERENCES charts(id),
        chart_number VARCHAR(20) NOT NULL,
        specialty VARCHAR(50),
        weighted_score INTEGER,
        pass_fail VARCHAR(10),
        dpo_dx_accuracy FLOAT,
        dpo_poa_accuracy FLOAT,
        dpo_proc_accuracy FLOAT,
        dpo_overall_accuracy FLOAT,
        error_message VARCHAR(300),
        feedback_items TEXT DEFAULT '[]'
    )""")

    # ── P2: backfill orphan batch_charts into synthetic legacy cycles ─────────
    _backfill_legacy_cycles()

    # ── Scrub "None" sentinel strings from answer key JSON arrays ─────────────
    _clean_none_in_answer_keys()


def _backfill_legacy_cycles() -> None:
    """
    Create a synthetic Cycle 0 (legacy) for any batch that has batch_charts
    rows with cycle_id = NULL (i.e. assignments made before cycle tracking
    was introduced).  This makes the batch detail consistent with the home
    card allocation_cycles count.
    """
    with engine.connect() as conn:
        try:
            rows = conn.execute(text(
                "SELECT DISTINCT batch_id FROM batch_charts WHERE cycle_id IS NULL"
            )).fetchall()
        except Exception:
            return  # table may not exist on a truly fresh install

        for (bid,) in rows:
            existing = conn.execute(text(
                "SELECT id FROM batch_allocation_cycles "
                "WHERE batch_id = :bid AND cycle_number = 0"
            ), {"bid": bid}).fetchone()

            if existing:
                cycle_id = existing[0]
            else:
                # Derive charts_per_coder from the orphan rows
                charts_per_coder_row = conn.execute(text(
                    "SELECT COUNT(*) FROM batch_charts "
                    "WHERE batch_id = :bid AND cycle_id IS NULL"
                ), {"bid": bid}).fetchone()
                cpc = max(1, (charts_per_coder_row[0] or 1))

                conn.execute(text(
                    "INSERT INTO batch_allocation_cycles "
                    "(batch_id, cycle_number, run_by, charts_per_coder, notes) "
                    "VALUES (:bid, 0, 'system', :cpc, 'Legacy — pre-cycle tracking')"
                ), {"bid": bid, "cpc": cpc})
                conn.commit()
                cycle_id = conn.execute(text(
                    "SELECT id FROM batch_allocation_cycles "
                    "WHERE batch_id = :bid AND cycle_number = 0"
                ), {"bid": bid}).fetchone()[0]

            conn.execute(text(
                "UPDATE batch_charts SET cycle_id = :cid "
                "WHERE batch_id = :bid AND cycle_id IS NULL"
            ), {"cid": cycle_id, "bid": bid})
            conn.commit()


def _clean_none_in_answer_keys() -> None:
    """
    Remove entries whose code is the string 'None' or '' from the sdx/pcs/cpt
    JSON arrays stored in answer_keys.  These were created when the Excel parser
    did str(None) → 'None' on empty template cells.
    """
    import json

    def _scrub(arr):
        if not isinstance(arr, list):
            return arr
        return [
            item for item in arr
            if item.get("code", "").strip().lower() not in ("none", "")
        ]

    with engine.connect() as conn:
        try:
            rows = conn.execute(text("SELECT id, sdx, pcs, cpt FROM answer_keys")).fetchall()
        except Exception:
            return

        for (ak_id, sdx_raw, pcs_raw, cpt_raw) in rows:
            try:
                sdx = json.loads(sdx_raw) if isinstance(sdx_raw, str) else (sdx_raw or [])
                pcs = json.loads(pcs_raw) if isinstance(pcs_raw, str) else (pcs_raw or [])
                cpt = json.loads(cpt_raw) if isinstance(cpt_raw, str) else (cpt_raw or [])

                clean_sdx = _scrub(sdx)
                clean_pcs = _scrub(pcs)
                clean_cpt = _scrub(cpt)

                if clean_sdx != sdx or clean_pcs != pcs or clean_cpt != cpt:
                    conn.execute(text(
                        "UPDATE answer_keys SET sdx=:sdx, pcs=:pcs, cpt=:cpt WHERE id=:id"
                    ), {
                        "sdx": json.dumps(clean_sdx),
                        "pcs": json.dumps(clean_pcs),
                        "cpt": json.dumps(clean_cpt),
                        "id": ak_id,
                    })
                    conn.commit()
            except Exception:
                conn.rollback()
