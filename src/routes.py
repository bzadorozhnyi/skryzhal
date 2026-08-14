from fastapi import APIRouter

from jobs.endpoints.v1.routes import job_v1_router
from templates.endpoints.v1.routes import template_v1_router

router = APIRouter(prefix="/api")
router.include_router(template_v1_router)
router.include_router(job_v1_router)
