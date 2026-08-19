from urllib.parse import urlparse, urlunparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _db_name(*, db_url: str) -> str:
    return urlparse(db_url).path.lstrip("/")


def _db_root_url(*, db_url: str) -> str:
    return urlunparse(urlparse(db_url)._replace(path=""))


async def is_db_exist(*, db_url: str) -> bool:
    engine = create_async_engine(db_url, echo=False, future=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        await engine.dispose()


async def drop_db(*, db_url: str) -> None:
    """Drops the database at `db_url`, connecting to its root (no-path) URL —
    you can't drop a database you're connected to.
    """
    root_url = _db_root_url(db_url=db_url)
    db_name = _db_name(db_url=db_url)

    engine = create_async_engine(root_url, isolation_level="AUTOCOMMIT", future=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity WHERE datname = :name"
                ),
                {"name": db_name},
            )
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
    finally:
        await engine.dispose()


async def create_db(*, db_url: str) -> None:
    root_url = _db_root_url(db_url=db_url)
    db_name = _db_name(db_url=db_url)

    engine = create_async_engine(root_url, isolation_level="AUTOCOMMIT", future=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    finally:
        await engine.dispose()
