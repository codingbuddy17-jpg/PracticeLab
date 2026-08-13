"""
Auditor API router — thin aggregator.

Domain logic lives in auditor_pkg/ sub-modules, and none of it shares storage
with PracticeLab. The two modules share charts, answer keys and the allocation
algorithm; everything else is separate, so audit work can never leak into
coder analytics through a query someone forgot to filter.
"""
from fastapi import APIRouter

from routers.auditor_pkg import batches, config, keys, sessions

router = APIRouter(prefix="/auditor", tags=["auditor"])

router.include_router(config.router)
router.include_router(keys.router)
router.include_router(batches.router)
router.include_router(sessions.router)
