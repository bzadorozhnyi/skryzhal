from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from core.db import SessionDep

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/ready")
async def ready(session: SessionDep) -> JSONResponse:
    checks = {"db": "ok"}
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        checks["db"] = "unreachable"

    status_code = 200 if all(v == "ok" for v in checks.values()) else 503
    return JSONResponse(status_code=status_code, content={"checks": checks})
