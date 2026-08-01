"""
Shared test fixtures.

- Uses an in-memory SQLite database — no PostgreSQL needed.
- Runs the same migrate() function that production uses on startup,
  so schema is always in sync with the app.
- Each test function gets a fresh, isolated database via function-scoped
  fixtures, so tests never bleed state into each other.
"""
import os
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Put backend/ on the path so imports work the same as production
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Set required env vars before any app import
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MASTER_ADMIN_PASSPHRASE", "test-passphrase")
os.environ.setdefault("STORAGE_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("STORAGE_ACCESS_KEY", "test")
os.environ.setdefault("STORAGE_SECRET_KEY", "test")
os.environ.setdefault("STORAGE_BUCKET_NAME", "test-bucket")
os.environ.setdefault("STORAGE_PUBLIC_URL", "http://localhost/files")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")

from database import Base, _run_migrations as migrate
from models import (
    AssessmentQuestion, AssessmentConfig,
    GeneratedAssessment, GeneratedAssessmentStudent, AssessmentSession,
    Batch, BatchCoder, BatchChart, BatchAllocationCycle,
    Chart, Specialty, Difficulty, ChartStatus,
    AnswerKey,
)


# ── Per-test isolated DB ──────────────────────────────────────────────────────

@pytest.fixture()
def engine():
    # StaticPool is required: every new connection to sqlite ":memory:" gets its
    # OWN empty database, so create_all() on one connection is invisible to the
    # session opened on the next one ("no such table: batches"). StaticPool keeps
    # a single shared connection for the fixture's lifetime.
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    # Run additive migrations so new columns are present
    from unittest.mock import patch
    with patch("database.engine", eng):
        try:
            migrate()
        except Exception:
            pass  # SQLite doesn't support all ALTER TABLE forms; Base.metadata covers the rest
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ── FastAPI test client ───────────────────────────────────────────────────────

@pytest.fixture()
def client(engine):
    from main import app
    from database import get_db
    Session = sessionmaker(bind=engine)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Seed helpers ──────────────────────────────────────────────────────────────

def make_question(db, specialty="IPDRG", difficulty="Medium", topic="Coding",
                  q_id=None, text=None):
    from datetime import datetime, timezone
    q = AssessmentQuestion(
        question_id=q_id or f"Q-{specialty[:2]}-{difficulty[:1]}-{id(object())}",
        specialty=specialty,
        difficulty=difficulty,
        topic=topic,
        question_text=text or f"Sample question ({difficulty})",
        option_a="Option A",
        option_b="Option B",
        option_c="Option C",
        option_d="Option D",
        correct_answer="A",
        status="active",
        uploaded_by="test",
    )
    db.add(q)
    db.flush()
    return q


def seed_question_pool(db, specialty="IPDRG", easy=4, medium=4, hard=4):
    """Seed a balanced question pool and return all questions."""
    qs = []
    for i in range(easy):
        qs.append(make_question(db, specialty=specialty, difficulty="Easy",
                                q_id=f"{specialty}-E{i}", text=f"Easy Q{i}"))
    for i in range(medium):
        qs.append(make_question(db, specialty=specialty, difficulty="Medium",
                                q_id=f"{specialty}-M{i}", text=f"Medium Q{i}"))
    for i in range(hard):
        qs.append(make_question(db, specialty=specialty, difficulty="Hard",
                                q_id=f"{specialty}-H{i}", text=f"Hard Q{i}"))
    db.commit()
    return qs


def make_chart(db, specialty="IP-DRG", difficulty="Intermediate", category="CC",
               chart_number=None):
    import uuid
    c = Chart(
        chart_number=chart_number or f"IP{uuid.uuid4().hex[:4].upper()}",
        specialty=Specialty(specialty),
        difficulty=Difficulty(difficulty),
        category=category,
        status=ChartStatus.ACTIVE,
        uploaded_by="test",
    )
    db.add(c)
    db.flush()
    return c


def seed_charts(db, specialty="IP-DRG", count=10, difficulty="Intermediate"):
    charts = [make_chart(db, specialty=specialty, difficulty=difficulty,
                         chart_number=f"IP{i:03d}") for i in range(1, count + 1)]
    db.commit()
    return charts


def make_batch(db, specialty="IP-DRG", coders=None, charts_per_coder=3):
    coders = coders or ["Alice", "Bob", "Charlie"]
    batch = Batch(
        name=f"Test Batch {id(object())}",
        specialty=Specialty(specialty),
        charts_per_coder=charts_per_coder,
        created_by="trainer",
        use_weighted=True,
    )
    db.add(batch)
    db.flush()
    for name in coders:
        db.add(BatchCoder(batch_id=batch.id, name=name, emp_id=f"EMP-{name[:3]}"))
    db.commit()
    return batch
