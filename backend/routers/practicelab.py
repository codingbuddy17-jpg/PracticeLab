"""
PracticeLab API router — thin aggregator.
Domain logic lives in practicelab_pkg/ sub-modules.
"""
from fastapi import APIRouter
from routers.practicelab_pkg import config, batches, grading, analytics, self_practice, ed_grading

router = APIRouter(prefix="/practicelab", tags=["practicelab"])

router.include_router(config.router)
router.include_router(batches.router)
router.include_router(grading.router)
router.include_router(ed_grading.router)
router.include_router(analytics.router)
router.include_router(self_practice.router)
