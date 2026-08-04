"""
Assessment Management API router — thin aggregator.
Domain logic lives in assessment_pkg/ sub-modules.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from routers.assessment_pkg import questions, generation, export, history, audit, sessions, take, analytics
from services.assessment_scoring import finalise_overdue_sessions

router = APIRouter(prefix="/assessment", tags=["assessment"])


def sweep_overdue(db: Session = Depends(get_db)):
    """
    Close and score any session whose time limit has passed.

    Attached to the trainer-facing routers rather than called inside each
    endpoint: a session going overdue is one fact, and every list, analytic and
    report must see it the same way. Wiring it per-endpoint is how it would end
    up applied in three places and forgotten in the fourth.

    It is idempotent, so the cost on a swept-clean database is one indexed
    query. The coder-facing `take` router is deliberately excluded — a coder
    hitting their own session should not trigger a sweep of everyone else's.
    """
    finalise_overdue_sessions(db)


_SWEEP = [Depends(sweep_overdue)]

router.include_router(questions.router)
router.include_router(generation.router)
router.include_router(export.router)
router.include_router(history.router, dependencies=_SWEEP)
router.include_router(audit.router)
router.include_router(sessions.router, dependencies=_SWEEP)
router.include_router(take.router)
router.include_router(analytics.router, dependencies=_SWEEP)
