"""
Assessment Management API router — thin aggregator.
Domain logic lives in assessment_pkg/ sub-modules.
"""
from fastapi import APIRouter
from routers.assessment_pkg import questions, generation, export, history, audit, sessions, take, analytics

router = APIRouter(prefix="/assessment", tags=["assessment"])

router.include_router(questions.router)
router.include_router(generation.router)
router.include_router(export.router)
router.include_router(history.router)
router.include_router(audit.router)
router.include_router(sessions.router)
router.include_router(take.router)
router.include_router(analytics.router)
