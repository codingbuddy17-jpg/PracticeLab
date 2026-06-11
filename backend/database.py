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
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                conn.rollback()
