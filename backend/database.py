import logging
from typing import Optional

from sqlalchemy import create_engine, inspect as sa_inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from config import settings

logger = logging.getLogger(__name__)


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
            except Exception as exc:
                logger.warning("Migration DDL failed (non-fatal): %s | sql=%s", exc, sql[:200])
                conn.rollback()

    def _add_enum_value(type_name: str, value: str) -> None:
        """
        Add a value to a native PostgreSQL ENUM type.

        SQLite stores enums as plain text, so this is a no-op there. On PG the
        statement must not share a transaction with any use of the new value, so
        it runs under AUTOCOMMIT. IF NOT EXISTS (PG 12+) makes it idempotent,
        matching the additive style of the rest of these migrations.

        Note: SAEnum persists the enum NAME (e.g. SURGERY), not its value
        ("Surgery") — pass the name.
        """
        if is_sqlite:
            return
        try:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.execute(text(
                    f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{value}'"
                ))
        except Exception as exc:
            logger.warning("Enum migration failed (non-fatal): %s | %s.%s",
                           exc, type_name, value)

    def _add_col(table: str, col: str, pg_def: str, sqlite_def: Optional[str] = None) -> None:
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
    _add_col("batches", "is_direct_assignment", "BOOLEAN NOT NULL DEFAULT FALSE")

    # ── batches — status normalisation ────────────────────────────────────────
    # PostgreSQL only: convert any lingering native-enum column to plain VARCHAR.
    # SQLite stores everything as TEXT already so this DDL is not needed there.
    if not is_sqlite:
        _run("ALTER TABLE batches ALTER COLUMN status TYPE VARCHAR(20) USING status::text")
        _run("DROP TYPE IF EXISTS batchstatus")
    # Normalise legacy status labels to Open / Closed on both dialects.
    _run("UPDATE batches SET status = 'Open'   WHERE status IN ('Active', 'Grading', 'Draft')")
    _run("UPDATE batches SET status = 'Closed' WHERE status = 'Complete'")

    # ── grading_results — DRG audit trail ────────────────────────────────────
    _add_col("grading_results", "drg_reviewed_by", "VARCHAR(100)")
    _add_col("grading_results", "drg_reviewed_at", "TIMESTAMPTZ", "TIMESTAMP")

    # ── grading_results — DPO columns ────────────────────────────────────────
    _add_col("grading_results", "dpo_dx_accuracy",   "FLOAT")
    _add_col("grading_results", "dpo_poa_accuracy",  "FLOAT")
    _add_col("grading_results", "dpo_proc_accuracy", "FLOAT")
    _add_col("grading_results", "dpo_overall_accuracy", "FLOAT")
    # Raw DPO counts for correct cumulative aggregation
    _add_col("grading_results", "dpo_dx_correct",   "INTEGER")
    _add_col("grading_results", "dpo_dx_total",     "INTEGER")
    _add_col("grading_results", "dpo_poa_correct",  "INTEGER")
    _add_col("grading_results", "dpo_poa_total",    "INTEGER")
    _add_col("grading_results", "dpo_proc_correct", "INTEGER")
    _add_col("grading_results", "dpo_proc_total",   "INTEGER")

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

    _add_col("batch_allocation_cycles", "randomisation_stats", "TEXT")

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
    _add_col("scoring_configs", "facility_level_weight", "INTEGER", "INTEGER")
    _add_col("scoring_configs", "profee_level_weight", "INTEGER", "INTEGER")

    # Seed default scoring configs (ON CONFLICT works on both PG and SQLite ≥3.24)
    _run("""INSERT INTO scoring_configs
        (specialty_type, pdx_weight, sdx_weight, pcs_weight, drg_weight,
         cpt_weight, facility_level_weight, profee_level_weight,
         pass_threshold, drg_triggers, overcoding_penalty, weighted_enabled,
         dpo_enabled, dpo_pass_threshold)
       VALUES
        ('IP', 20, 20, 20, 40, NULL, NULL, NULL, 80,
         '["pdx_mismatch","ccmcc_missing","pcs_undercoded","pcs_overcoded","spurious_sdx","spurious_pcs"]',
         1, 1, 1, 80.0),
        ('OP', 25, 25, NULL, NULL, 50, NULL, NULL, 90, '[]', 1, 1, 1, 80.0),
        ('EDSP', 20, 20, NULL, NULL, 20, 20, 20, 90, '[]', 1, 1, 1, 80.0)
       ON CONFLICT (specialty_type) DO NOTHING""")
    _run("UPDATE scoring_configs SET dpo_enabled = 1 WHERE specialty_type IN ('IP', 'OP', 'EDSP')")
    _run("""UPDATE batches SET use_dpo = FALSE
            WHERE specialty NOT IN ('IP-DRG', 'ED Facility', 'SDS', 'Surgery', 'Ancillary', 'ED Single Path')""")

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

    # ── ed_rubric_details — manual grading for Edits/Denials ─────────────────
    _run("""CREATE TABLE IF NOT EXISTS ed_rubric_details (
        id INTEGER PRIMARY KEY,
        result_id INTEGER REFERENCES grading_results(id) NOT NULL UNIQUE,
        review_pass BOOLEAN NOT NULL DEFAULT FALSE,
        research_coding_pass BOOLEAN NOT NULL DEFAULT FALSE,
        research_payer_pass BOOLEAN NOT NULL DEFAULT FALSE,
        research_nuances_pass BOOLEAN NOT NULL DEFAULT FALSE,
        resolution_pass BOOLEAN NOT NULL DEFAULT FALSE,
        rationale_tier VARCHAR(20) NOT NULL DEFAULT 'not_acceptable',
        trainer_note TEXT,
        graded_by VARCHAR(100) NOT NULL,
        graded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # ── charts — alias field ──────────────────────────────────────────────────
    _add_col("charts", "alias", "VARCHAR(100)")

    # ── coding_resources table ────────────────────────────────────────────────
    _run("""CREATE TABLE IF NOT EXISTS coding_resources (
        id INTEGER PRIMARY KEY,
        title VARCHAR(200) NOT NULL,
        description VARCHAR(500),
        url VARCHAR(1000) NOT NULL,
        created_by VARCHAR(100) NOT NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # ── assessment_questions table ────────────────────────────────────────────
    _run("""CREATE TABLE IF NOT EXISTS assessment_questions (
        id INTEGER PRIMARY KEY,
        question_id VARCHAR(20) NOT NULL UNIQUE,
        specialty VARCHAR(50) NOT NULL,
        question_text TEXT NOT NULL,
        option_a TEXT NOT NULL,
        option_b TEXT NOT NULL,
        option_c TEXT NOT NULL,
        option_d TEXT NOT NULL,
        correct_answer VARCHAR(1) NOT NULL,
        difficulty VARCHAR(10) NOT NULL,
        topic VARCHAR(100),
        question_type VARCHAR(20) NOT NULL DEFAULT 'Conceptual',
        status VARCHAR(10) NOT NULL DEFAULT 'Active',
        last_used_at TIMESTAMP,
        uploaded_by VARCHAR(100),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    _add_col("assessment_questions", "shuffle_options", "BOOLEAN NOT NULL DEFAULT TRUE", "INTEGER NOT NULL DEFAULT 1")

    # ── assessment_configs table ──────────────────────────────────────────────
    _run("""CREATE TABLE IF NOT EXISTS assessment_configs (
        id INTEGER PRIMARY KEY,
        name VARCHAR(200) NOT NULL,
        total_questions INTEGER NOT NULL,
        student_count INTEGER NOT NULL DEFAULT 1,
        specialty_mix TEXT NOT NULL DEFAULT '[]',
        difficulty_mode VARCHAR(10) NOT NULL DEFAULT 'auto',
        difficulty_mix TEXT,
        created_by VARCHAR(100) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # ── generated_assessments table ───────────────────────────────────────────
    _run("""CREATE TABLE IF NOT EXISTS generated_assessments (
        id INTEGER PRIMARY KEY,
        config_id INTEGER REFERENCES assessment_configs(id),
        assessment_name VARCHAR(200) NOT NULL,
        student_count INTEGER NOT NULL,
        generated_by VARCHAR(100) NOT NULL,
        generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    _add_col("generated_assessments", "batch_name", "VARCHAR(100)")
    _add_col("generated_assessments", "randomisation_stats", "TEXT")
    _add_col("generated_assessments", "is_standalone", "BOOLEAN DEFAULT FALSE")

    # ── generated_assessment_students table ───────────────────────────────────
    _run("""CREATE TABLE IF NOT EXISTS generated_assessment_students (
        id INTEGER PRIMARY KEY,
        assessment_id INTEGER REFERENCES generated_assessments(id) NOT NULL,
        student_label VARCHAR(50) NOT NULL,
        questions_json TEXT NOT NULL DEFAULT '[]'
    )""")

    # ── assessment_audit_log table ────────────────────────────────────────────
    _run("""CREATE TABLE IF NOT EXISTS assessment_audit_log (
        id INTEGER PRIMARY KEY,
        trainer_name VARCHAR(100) NOT NULL,
        action VARCHAR(50) NOT NULL,
        specialty VARCHAR(50),
        details TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    )""")

    # ── assessment_sessions table ─────────────────────────────────────────────
    _run("""CREATE TABLE IF NOT EXISTS assessment_sessions (
        id INTEGER PRIMARY KEY,
        session_token VARCHAR(20) NOT NULL UNIQUE,
        assessment_id INTEGER REFERENCES generated_assessments(id) NOT NULL,
        coder_name VARCHAR(100) NOT NULL,
        employee_id VARCHAR(50),
        duration_minutes INTEGER NOT NULL,
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        started_at TIMESTAMP WITH TIME ZONE,
        time_limit_ends_at TIMESTAMP WITH TIME ZONE,
        submitted_at TIMESTAMP WITH TIME ZONE,
        auto_submitted BOOLEAN NOT NULL DEFAULT FALSE,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        last_saved_at TIMESTAMP WITH TIME ZONE,
        student_slot_id INTEGER REFERENCES generated_assessment_students(id),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    )""")
    # Idempotent migration for DBs created before student_slot_id was added
    _add_col("assessment_sessions", "student_slot_id", "INTEGER REFERENCES generated_assessment_students(id)")

    # ── assessment_responses table ────────────────────────────────────────────
    _run("""CREATE TABLE IF NOT EXISTS assessment_responses (
        id INTEGER PRIMARY KEY,
        session_id INTEGER REFERENCES assessment_sessions(id) NOT NULL,
        question_index INTEGER NOT NULL,
        question_id VARCHAR(20) NOT NULL,
        selected_answer VARCHAR(1),
        is_correct BOOLEAN,
        answered_at TIMESTAMP WITH TIME ZONE,
        UNIQUE(session_id, question_index)
    )""")

    # ── assessment_results table ──────────────────────────────────────────────
    _run("""CREATE TABLE IF NOT EXISTS assessment_results (
        id INTEGER PRIMARY KEY,
        session_id INTEGER REFERENCES assessment_sessions(id) UNIQUE NOT NULL,
        total_questions INTEGER NOT NULL,
        correct_count INTEGER NOT NULL,
        score_pct FLOAT NOT NULL,
        time_taken_seconds INTEGER,
        submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    )""")

    # ── Seed assessment sample questions if table is empty ────────────────────
    from services.assessment_seed import seed_sample_questions
    from sqlalchemy import text as _text
    with engine.connect() as _conn:
        _count = _conn.execute(_text("SELECT COUNT(*) FROM assessment_questions")).fetchone()[0]
    if _count == 0:
        _seed_db = SessionLocal()
        try:
            seed_sample_questions(_seed_db)
        finally:
            _seed_db.close()

    # ── in-browser practice sessions ─────────────────────────────────────────
    _run("""CREATE TABLE IF NOT EXISTS practice_sessions (
        id SERIAL PRIMARY KEY,
        batch_id INTEGER REFERENCES batches(id),
        cycle_id INTEGER REFERENCES batch_allocation_cycles(id),
        coder_name VARCHAR(100) NOT NULL,
        specialty VARCHAR(50) NOT NULL,
        token VARCHAR(20) NOT NULL UNIQUE,
        chart_ids TEXT NOT NULL DEFAULT '[]',
        show_results_to_coder BOOLEAN NOT NULL DEFAULT FALSE,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        submitted_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    _run("""CREATE TABLE IF NOT EXISTS practice_chart_drafts (
        id SERIAL PRIMARY KEY,
        session_id INTEGER REFERENCES practice_sessions(id) NOT NULL,
        chart_id INTEGER REFERENCES charts(id) NOT NULL,
        pdx_code VARCHAR(20),
        pdx_poa VARCHAR(5),
        sdx TEXT DEFAULT '[]',
        pcs TEXT DEFAULT '[]',
        cpt TEXT DEFAULT '[]',
        ed_review TEXT,
        ed_research TEXT,
        ed_resolution TEXT,
        ed_rationale TEXT,
        flagged BOOLEAN DEFAULT FALSE,
        coder_notes TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    # additive migrations for existing tables
    _add_col("practice_chart_drafts", "ed_review", "TEXT", "TEXT")
    _add_col("practice_chart_drafts", "ed_research", "TEXT", "TEXT")
    _add_col("practice_chart_drafts", "ed_resolution", "TEXT", "TEXT")
    _add_col("practice_chart_drafts", "ed_rationale", "TEXT", "TEXT")
    _add_col("practice_chart_drafts", "em_data", "TEXT", "TEXT")

    _run("""CREATE TABLE IF NOT EXISTS practice_results (
        id SERIAL PRIMARY KEY,
        session_id INTEGER REFERENCES practice_sessions(id) NOT NULL,
        chart_id INTEGER REFERENCES charts(id) NOT NULL,
        specialty VARCHAR(50),
        total_score INTEGER,
        pass_fail VARCHAR(10),
        drg_flag BOOLEAN DEFAULT FALSE,
        feedback TEXT DEFAULT '[]',
        pdx_submitted VARCHAR(20),
        pdx_answer_key VARCHAR(20),
        pdx_correct BOOLEAN,
        sdx_submitted TEXT DEFAULT '[]',
        sdx_answer_key TEXT DEFAULT '[]',
        pcs_submitted TEXT DEFAULT '[]',
        pcs_answer_key TEXT DEFAULT '[]',
        cpt_submitted TEXT DEFAULT '[]',
        cpt_answer_key TEXT DEFAULT '[]',
        ed_review TEXT,
        ed_research TEXT,
        ed_resolution TEXT,
        ed_rationale TEXT,
        ed_scored BOOLEAN DEFAULT FALSE,
        ed_review_pass BOOLEAN,
        ed_research_coding_pass BOOLEAN,
        ed_research_payer_pass BOOLEAN,
        ed_research_nuances_pass BOOLEAN,
        ed_resolution_pass BOOLEAN,
        ed_rationale_tier VARCHAR(30),
        ed_trainer_note TEXT,
        ed_graded_by VARCHAR(100)
    )""")
    # additive migrations for existing tables
    _add_col("practice_results", "ed_review", "TEXT", "TEXT")
    _add_col("practice_results", "ed_research", "TEXT", "TEXT")
    _add_col("practice_results", "ed_resolution", "TEXT", "TEXT")
    _add_col("practice_results", "ed_rationale", "TEXT", "TEXT")
    _add_col("practice_results", "ed_scored", "BOOLEAN DEFAULT FALSE", "BOOLEAN DEFAULT FALSE")
    _add_col("practice_results", "drg_reviewed", "BOOLEAN DEFAULT FALSE", "BOOLEAN DEFAULT FALSE")
    _add_col("practice_results", "drg_override", "VARCHAR(20)", "VARCHAR(20)")
    _add_col("practice_results", "drg_reviewed_by", "VARCHAR(100)", "VARCHAR(100)")
    _add_col("practice_results", "drg_reviewed_at", "TIMESTAMP", "TIMESTAMP")
    _add_col("practice_results", "ed_review_pass", "BOOLEAN", "BOOLEAN")
    _add_col("practice_results", "ed_research_coding_pass", "BOOLEAN", "BOOLEAN")
    _add_col("practice_results", "ed_research_payer_pass", "BOOLEAN", "BOOLEAN")
    _add_col("practice_results", "ed_research_nuances_pass", "BOOLEAN", "BOOLEAN")
    _add_col("practice_results", "ed_resolution_pass", "BOOLEAN", "BOOLEAN")
    _add_col("practice_results", "ed_rationale_tier", "VARCHAR(30)", "TEXT")
    _add_col("practice_results", "ed_trainer_note", "TEXT", "TEXT")
    _add_col("practice_results", "ed_graded_by", "VARCHAR(100)", "TEXT")

    # ── Fix practice tables: attach sequences so PG auto-increments id ──────────
    # Tables were created with INTEGER PRIMARY KEY (no sequence on PG). Each step
    # is a separate _run() so failures are individually logged, not silently lost.
    if not is_sqlite:
        for tbl in ("practice_sessions", "practice_chart_drafts", "practice_results"):
            _run(f"CREATE SEQUENCE IF NOT EXISTS {tbl}_id_seq")
            _run(f"ALTER TABLE {tbl} ALTER COLUMN id SET DEFAULT nextval('{tbl}_id_seq')")
            _run(f"SELECT setval('{tbl}_id_seq', COALESCE((SELECT MAX(id) FROM {tbl}), 0) + 1, false)")

    # ── P2: backfill orphan batch_charts into synthetic legacy cycles ─────────
    _backfill_legacy_cycles()

    # ── Scrub "None" sentinel strings from answer key JSON arrays ─────────────
    _clean_none_in_answer_keys()

    # ── Mirror historical practice results into grading_results ───────────────
    _backfill_practice_grading_results()

    _add_col("em_answer_keys", "patient_type", "VARCHAR(20) NOT NULL DEFAULT 'NA'", "TEXT NOT NULL DEFAULT 'NA'")

    # ── New specialties: Surgery (profee surgical) + ED Single Path ───────────
    # Must land before anything reads/writes these values. On a fresh DB
    # create_all() already builds the type with every value; these calls cover
    # databases created before the values existed.
    _add_enum_value("specialty", "SURGERY")
    _add_enum_value("specialty", "ED_SINGLE_PATH")
    # Diagnosis-pointer errors on professional claims
    _add_enum_value("issuetype", "WRONG_POINTER")

    # ── ED Single Path: facility + professional levels coded together ─────────
    _add_col("answer_keys", "facility_level", "VARCHAR(20)", "TEXT")
    _add_col("answer_keys", "profee_level", "VARCHAR(20)", "TEXT")
    _add_col("practice_chart_drafts", "facility_level", "TEXT", "TEXT")
    _add_col("practice_chart_drafts", "profee_level", "TEXT", "TEXT")
    _add_col("practice_results", "facility_level_submitted", "TEXT", "TEXT")
    _add_col("practice_results", "facility_level_answer_key", "TEXT", "TEXT")
    _add_col("practice_results", "profee_level_submitted", "TEXT", "TEXT")
    _add_col("practice_results", "profee_level_answer_key", "TEXT", "TEXT")

    # ── E/M levelling method: MDM or Time (2021+ office/outpatient rules) ─────
    _add_col("em_answer_keys", "level_method", "VARCHAR(10) NOT NULL DEFAULT 'MDM'", "TEXT NOT NULL DEFAULT 'MDM'")
    _add_col("em_answer_keys", "total_time", "INTEGER", "INTEGER")

    # ── E/M MDM answer keys ───────────────────────────────────────────────────
    _run("""CREATE TABLE IF NOT EXISTS em_answer_keys (
        id INTEGER PRIMARY KEY,
        chart_id INTEGER REFERENCES charts(id) NOT NULL UNIQUE,
        -- COPA elements (counts per problem type)
        copa_self_limited INTEGER NOT NULL DEFAULT 0,
        copa_stable_acute INTEGER NOT NULL DEFAULT 0,
        copa_stable_chronic INTEGER NOT NULL DEFAULT 0,
        copa_acute_uncomplicated INTEGER NOT NULL DEFAULT 0,
        copa_chronic_exacerbation INTEGER NOT NULL DEFAULT 0,
        copa_undiagnosed_new INTEGER NOT NULL DEFAULT 0,
        copa_acute_systemic INTEGER NOT NULL DEFAULT 0,
        copa_acute_complicated_injury INTEGER NOT NULL DEFAULT 0,
        copa_chronic_severe INTEGER NOT NULL DEFAULT 0,
        copa_threat_to_life INTEGER NOT NULL DEFAULT 0,
        copa_level VARCHAR(20) NOT NULL,
        copa_level_overridden BOOLEAN NOT NULL DEFAULT FALSE,
        -- Data Review elements
        dr_prior_external_notes INTEGER NOT NULL DEFAULT 0,
        dr_review_test_results INTEGER NOT NULL DEFAULT 0,
        dr_order_tests INTEGER NOT NULL DEFAULT 0,
        dr_independent_historian BOOLEAN NOT NULL DEFAULT FALSE,
        dr_independent_interpretation BOOLEAN NOT NULL DEFAULT FALSE,
        dr_external_discussion BOOLEAN NOT NULL DEFAULT FALSE,
        dr_level VARCHAR(20) NOT NULL,
        dr_level_overridden BOOLEAN NOT NULL DEFAULT FALSE,
        -- Risk elements
        risk_low BOOLEAN NOT NULL DEFAULT FALSE,
        risk_prescription_drug_mgmt BOOLEAN NOT NULL DEFAULT FALSE,
        risk_minor_surgery_with_factors BOOLEAN NOT NULL DEFAULT FALSE,
        risk_elective_major_no_factors BOOLEAN NOT NULL DEFAULT FALSE,
        risk_hospitalization BOOLEAN NOT NULL DEFAULT FALSE,
        risk_sdoh BOOLEAN NOT NULL DEFAULT FALSE,
        risk_drug_intensive_monitoring BOOLEAN NOT NULL DEFAULT FALSE,
        risk_elective_major_with_factors BOOLEAN NOT NULL DEFAULT FALSE,
        risk_emergency_major_surgery BOOLEAN NOT NULL DEFAULT FALSE,
        risk_hospitalization_escalation BOOLEAN NOT NULL DEFAULT FALSE,
        risk_dnr_deescalate BOOLEAN NOT NULL DEFAULT FALSE,
        risk_parenteral_controlled BOOLEAN NOT NULL DEFAULT FALSE,
        risk_level VARCHAR(20) NOT NULL,
        risk_level_overridden BOOLEAN NOT NULL DEFAULT FALSE,
        -- Coding outputs
        em_code VARCHAR(10) NOT NULL,
        em_modifier VARCHAR(10),
        dx_codes TEXT NOT NULL DEFAULT '[]',
        procedure_cpts TEXT NOT NULL DEFAULT '[]',
        entered_by VARCHAR(100) NOT NULL,
        entered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # ── E/M grading results ───────────────────────────────────────────────────
    _run("""CREATE TABLE IF NOT EXISTS em_grading_results (
        id INTEGER PRIMARY KEY,
        result_id INTEGER REFERENCES grading_results(id) NOT NULL UNIQUE,
        -- Submitted COPA
        sub_copa_self_limited INTEGER NOT NULL DEFAULT 0,
        sub_copa_stable_acute INTEGER NOT NULL DEFAULT 0,
        sub_copa_stable_chronic INTEGER NOT NULL DEFAULT 0,
        sub_copa_acute_uncomplicated INTEGER NOT NULL DEFAULT 0,
        sub_copa_chronic_exacerbation INTEGER NOT NULL DEFAULT 0,
        sub_copa_undiagnosed_new INTEGER NOT NULL DEFAULT 0,
        sub_copa_acute_systemic INTEGER NOT NULL DEFAULT 0,
        sub_copa_acute_complicated_injury INTEGER NOT NULL DEFAULT 0,
        sub_copa_chronic_severe INTEGER NOT NULL DEFAULT 0,
        sub_copa_threat_to_life INTEGER NOT NULL DEFAULT 0,
        -- Submitted Data Review
        sub_dr_prior_external_notes INTEGER NOT NULL DEFAULT 0,
        sub_dr_review_test_results INTEGER NOT NULL DEFAULT 0,
        sub_dr_order_tests INTEGER NOT NULL DEFAULT 0,
        sub_dr_independent_historian BOOLEAN NOT NULL DEFAULT FALSE,
        sub_dr_independent_interpretation BOOLEAN NOT NULL DEFAULT FALSE,
        sub_dr_external_discussion BOOLEAN NOT NULL DEFAULT FALSE,
        -- Submitted Risk
        sub_risk_low BOOLEAN NOT NULL DEFAULT FALSE,
        sub_risk_prescription_drug_mgmt BOOLEAN NOT NULL DEFAULT FALSE,
        sub_risk_minor_surgery_with_factors BOOLEAN NOT NULL DEFAULT FALSE,
        sub_risk_elective_major_no_factors BOOLEAN NOT NULL DEFAULT FALSE,
        sub_risk_hospitalization BOOLEAN NOT NULL DEFAULT FALSE,
        sub_risk_sdoh BOOLEAN NOT NULL DEFAULT FALSE,
        sub_risk_drug_intensive_monitoring BOOLEAN NOT NULL DEFAULT FALSE,
        sub_risk_elective_major_with_factors BOOLEAN NOT NULL DEFAULT FALSE,
        sub_risk_emergency_major_surgery BOOLEAN NOT NULL DEFAULT FALSE,
        sub_risk_hospitalization_escalation BOOLEAN NOT NULL DEFAULT FALSE,
        sub_risk_dnr_deescalate BOOLEAN NOT NULL DEFAULT FALSE,
        sub_risk_parenteral_controlled BOOLEAN NOT NULL DEFAULT FALSE,
        -- Submitted coding outputs
        sub_em_code VARCHAR(10),
        sub_em_modifier VARCHAR(10),
        sub_dx_codes TEXT NOT NULL DEFAULT '[]',
        sub_procedure_cpts TEXT NOT NULL DEFAULT '[]',
        -- Derived levels
        derived_copa_level VARCHAR(20),
        derived_dr_level VARCHAR(20),
        derived_risk_level VARCHAR(20),
        -- Coding Accuracy scores
        em_level_score FLOAT,
        cpt_score FLOAT,
        dx_score FLOAT,
        coding_accuracy_total FLOAT,
        -- Reasoning Accuracy scores
        copa_element_score FLOAT,
        dr_element_score FLOAT,
        risk_element_score FLOAT,
        reasoning_accuracy_total FLOAT
    )""")

    # ── E/M scoring config ────────────────────────────────────────────────────
    _run("""CREATE TABLE IF NOT EXISTS em_scoring_configs (
        id INTEGER PRIMARY KEY,
        line1_weight FLOAT NOT NULL DEFAULT 70.0,
        line2_weight FLOAT NOT NULL DEFAULT 30.0,
        em_level_weight FLOAT NOT NULL DEFAULT 23.33,
        cpt_weight FLOAT NOT NULL DEFAULT 23.33,
        dx_weight FLOAT NOT NULL DEFAULT 23.34,
        copa_weight FLOAT NOT NULL DEFAULT 10.0,
        dr_weight FLOAT NOT NULL DEFAULT 10.0,
        risk_weight FLOAT NOT NULL DEFAULT 10.0,
        pass_threshold FLOAT NOT NULL DEFAULT 80.0,
        overcoding_penalty BOOLEAN NOT NULL DEFAULT TRUE,
        updated_by VARCHAR(100),
        updated_at TIMESTAMP
    )""")
    _run("""INSERT INTO em_scoring_configs
        (line1_weight, line2_weight, em_level_weight, cpt_weight, dx_weight,
         copa_weight, dr_weight, risk_weight, pass_threshold, overcoding_penalty)
        VALUES (70.0, 30.0, 23.33, 23.33, 23.34, 10.0, 10.0, 10.0, 80.0, TRUE)
        ON CONFLICT DO NOTHING""" if not True else
        """INSERT INTO em_scoring_configs
        (id, line1_weight, line2_weight, em_level_weight, cpt_weight, dx_weight,
         copa_weight, dr_weight, risk_weight, pass_threshold, overcoding_penalty)
        VALUES (1, 70.0, 30.0, 23.33, 23.33, 23.34, 10.0, 10.0, 10.0, 80.0, TRUE)
        ON CONFLICT (id) DO NOTHING""")


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
        except Exception as exc:
            logger.warning("_backfill_legacy_cycles skipped: %s", exc)
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


def _backfill_practice_grading_results() -> None:
    """
    Mirror historical practice_results rows into grading_results.

    In-browser practice sessions write to practice_results, but every analytics
    endpoint and both PDF reports read grading_results. Sessions submitted before
    the write-through mirror existed are invisible to reporting; this backfills
    them once. Idempotent — skips any (batch_id, coder_name, chart_id) that
    already has a grading_results row.

    Note: practice_results has no DPO columns, so backfilled rows carry no DPO
    figures. Re-grading a session repopulates them via the live mirror.
    """
    with engine.connect() as conn:
        try:
            rows = conn.execute(text("""
                SELECT ps.batch_id, ps.coder_name, pr.chart_id, pr.specialty,
                       pr.total_score, pr.pass_fail, pr.drg_flag, pr.feedback,
                       ps.submitted_at
                FROM practice_results pr
                JOIN practice_sessions ps ON ps.id = pr.session_id
                WHERE pr.total_score IS NOT NULL
                  AND ps.batch_id IS NOT NULL
                  AND ps.coder_name IS NOT NULL
            """)).fetchall()
        except Exception as exc:
            logger.warning("_backfill_practice_grading_results skipped: %s", exc)
            return

        import json as _json
        from models import Specialty
        from models.practicelab import GradingSection, IssueType

        created = 0

        for (batch_id, coder_name, chart_id, specialty, total_score,
             pass_fail, drg_flag, feedback, submitted_at) in rows:
            try:
                existing = conn.execute(text(
                    "SELECT id FROM grading_results "
                    "WHERE batch_id=:b AND coder_name=:n AND chart_id=:c"
                ), {"b": batch_id, "n": coder_name, "c": chart_id}).fetchone()
                if existing:
                    continue

                # grading_results.specialty is a SAEnum column: SQLAlchemy persists
                # the enum NAME (IP_DRG), while practice_results stores the VALUE
                # (IP-DRG). Insert the name or the ORM cannot read the row back.
                try:
                    spec_name = Specialty(specialty).name
                except (ValueError, TypeError):
                    logger.warning("backfill: unknown specialty %r (batch=%s chart=%s), skipping",
                                   specialty, batch_id, chart_id)
                    continue

                conn.execute(text("""
                    INSERT INTO grading_results
                      (batch_id, submission_id, coder_name, chart_id, specialty,
                       total_score, pass_fail, drg_flag, graded_at)
                    VALUES (:b, NULL, :n, :c, :sp, :tot, :pf, :drg,
                            COALESCE(:ts, CURRENT_TIMESTAMP))
                """), {
                    "b": batch_id, "n": coder_name, "c": chart_id, "sp": spec_name,
                    "tot": total_score, "pf": pass_fail,
                    "drg": bool(drg_flag), "ts": submitted_at,
                })
                new_id = conn.execute(text(
                    "SELECT id FROM grading_results "
                    "WHERE batch_id=:b AND coder_name=:n AND chart_id=:c"
                ), {"b": batch_id, "n": coder_name, "c": chart_id}).fetchone()[0]

                items = _json.loads(feedback) if isinstance(feedback, str) else (feedback or [])
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    # Same SAEnum name-vs-value rule as above. E/M emits free-text
                    # section/issue strings that map to neither enum — skip those.
                    try:
                        section_name = GradingSection(str(item.get("section") or "")).name
                        issue_name = IssueType(
                            str(item.get("issue") or item.get("issue_type") or "")).name
                    except (ValueError, TypeError):
                        continue
                    conn.execute(text("""
                        INSERT INTO grading_feedback
                          (result_id, section, issue_type, ak_code, coder_code)
                        VALUES (:r, :s, :i, :ak, :cc)
                    """), {
                        "r": new_id, "s": section_name, "i": issue_name,
                        "ak": item.get("ak_code") or None,
                        "cc": item.get("coder_code") or None,
                    })
                conn.commit()
                created += 1
            except Exception as exc:
                logger.warning("backfill row skipped (batch=%s coder=%s chart=%s): %s",
                               batch_id, coder_name, chart_id, exc)
                conn.rollback()

        if created:
            logger.info("_backfill_practice_grading_results: mirrored %d practice result(s)", created)


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
        except Exception as exc:
            logger.warning("_clean_none_in_answer_keys skipped: %s", exc)
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
            except Exception as exc:
                logger.warning("_clean_none_in_answer_keys row update failed: %s", exc)
                conn.rollback()
