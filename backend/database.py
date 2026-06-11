from sqlalchemy import create_engine, text
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
    """Safe additive migrations — only adds missing columns, never drops."""
    migrations = [
        "ALTER TABLE chart_files ADD COLUMN IF NOT EXISTS page_text TEXT",
        """CREATE TABLE IF NOT EXISTS chart_feedback (
            id SERIAL PRIMARY KEY,
            chart_id INTEGER REFERENCES charts(id),
            chart_number VARCHAR(20) NOT NULL,
            reporter VARCHAR(100) NOT NULL,
            issues VARCHAR(500) NOT NULL,
            notes TEXT,
            status VARCHAR(20) DEFAULT 'Open',
            resolved_by VARCHAR(100),
            resolved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )""",
        # PracticeLab tables
        """CREATE TABLE IF NOT EXISTS answer_keys (
            id SERIAL PRIMARY KEY,
            chart_id INTEGER REFERENCES charts(id) UNIQUE NOT NULL,
            specialty VARCHAR(50) NOT NULL,
            pdx_code VARCHAR(20),
            pdx_poa VARCHAR(5),
            sdx JSONB DEFAULT '[]',
            pcs JSONB DEFAULT '[]',
            cpt JSONB DEFAULT '[]',
            entered_by VARCHAR(100) NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ
        )""",
        """CREATE TABLE IF NOT EXISTS batches (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            specialty VARCHAR(50) NOT NULL,
            categories JSONB DEFAULT '[]',
            difficulties JSONB DEFAULT '[]',
            charts_per_coder INTEGER NOT NULL,
            created_by VARCHAR(100) NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            status VARCHAR(20) DEFAULT 'Draft'
        )""",
        """CREATE TABLE IF NOT EXISTS batch_coders (
            id SERIAL PRIMARY KEY,
            batch_id INTEGER REFERENCES batches(id) NOT NULL,
            coder_name VARCHAR(100) NOT NULL,
            excel_generated_at TIMESTAMPTZ
        )""",
        """CREATE TABLE IF NOT EXISTS batch_charts (
            id SERIAL PRIMARY KEY,
            batch_id INTEGER REFERENCES batches(id) NOT NULL,
            coder_name VARCHAR(100) NOT NULL,
            chart_id INTEGER REFERENCES charts(id) NOT NULL,
            submission_status VARCHAR(20) DEFAULT 'Pending'
        )""",
        """CREATE TABLE IF NOT EXISTS submissions (
            id SERIAL PRIMARY KEY,
            batch_id INTEGER REFERENCES batches(id) NOT NULL,
            coder_name VARCHAR(100) NOT NULL,
            chart_id INTEGER REFERENCES charts(id) NOT NULL,
            specialty VARCHAR(50) NOT NULL,
            pdx_code VARCHAR(20),
            pdx_poa VARCHAR(5),
            sdx JSONB DEFAULT '[]',
            pcs JSONB DEFAULT '[]',
            cpt JSONB DEFAULT '[]',
            submitted_at TIMESTAMPTZ DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS grading_results (
            id SERIAL PRIMARY KEY,
            batch_id INTEGER REFERENCES batches(id) NOT NULL,
            submission_id INTEGER REFERENCES submissions(id),
            coder_name VARCHAR(100) NOT NULL,
            chart_id INTEGER REFERENCES charts(id) NOT NULL,
            specialty VARCHAR(50) NOT NULL,
            pdx_score INTEGER DEFAULT 0,
            sdx_score INTEGER DEFAULT 0,
            pcs_score INTEGER,
            cpt_score INTEGER,
            drg_score INTEGER,
            drg_flag BOOLEAN DEFAULT FALSE,
            drg_reviewed BOOLEAN DEFAULT FALSE,
            drg_override VARCHAR(5),
            total_score INTEGER,
            pass_fail VARCHAR(10),
            graded_at TIMESTAMPTZ DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS grading_feedback (
            id SERIAL PRIMARY KEY,
            result_id INTEGER REFERENCES grading_results(id) NOT NULL,
            section VARCHAR(10) NOT NULL,
            issue_type VARCHAR(30) NOT NULL,
            ak_code VARCHAR(50),
            coder_code VARCHAR(50),
            detail VARCHAR(200)
        )""",
        "ALTER TABLE batch_coders ADD COLUMN IF NOT EXISTS emp_id VARCHAR(50)",
        """CREATE TABLE IF NOT EXISTS scoring_configs (
            id SERIAL PRIMARY KEY,
            specialty_type VARCHAR(10) NOT NULL UNIQUE,
            pdx_weight INTEGER NOT NULL DEFAULT 20,
            sdx_weight INTEGER NOT NULL DEFAULT 20,
            pcs_weight INTEGER,
            drg_weight INTEGER,
            cpt_weight INTEGER,
            pass_threshold INTEGER NOT NULL DEFAULT 80,
            drg_triggers JSONB DEFAULT '[]',
            overcoding_penalty BOOLEAN NOT NULL DEFAULT TRUE,
            updated_by VARCHAR(100),
            updated_at TIMESTAMPTZ
        )""",
        # Seed default configs if not present
        """INSERT INTO scoring_configs
            (specialty_type, pdx_weight, sdx_weight, pcs_weight, drg_weight,
             cpt_weight, pass_threshold, drg_triggers, overcoding_penalty)
           VALUES
            ('IP', 20, 20, 20, 40, NULL, 80,
             '["pdx_mismatch","ccmcc_missing","pcs_undercoded","pcs_overcoded","spurious_sdx","spurious_pcs"]',
             TRUE),
            ('OP', 25, 25, NULL, NULL, 50, 90, '[]', TRUE)
           ON CONFLICT (specialty_type) DO NOTHING""",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                conn.rollback()
