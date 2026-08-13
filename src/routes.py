from fastapi import APIRouter

from templates.endpoints.v1.routes import template_v1_router

router = APIRouter(prefix="/api")
router.include_router(template_v1_router)
