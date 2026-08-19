import asyncio
import os
import pkgutil
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.db import get_session
from core.settings import settings
from main import app
from tests.helpers.db import create_db, drop_db, is_db_exist

ALEMBIC_INI_PATH = Path(__file__).resolve().parent.parent / "alembic.ini"
os.environ["TESTING"] = "1"


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
def alembic_config():
    return Config(str(ALEMBIC_INI_PATH))


@pytest.fixture(scope="session")
async def async_engine(alembic_config):
    if await is_db_exist(db_url=settings.DB.test_url):
        await drop_db(db_url=settings.DB.test_url)
    await create_db(db_url=settings.DB.test_url)

    await asyncio.to_thread(command.upgrade, alembic_config, "head")

    engine = create_async_engine(settings.DB.test_url, echo=True, future=True)

    yield engine

    await engine.dispose()
    await drop_db(db_url=settings.DB.test_url)


@pytest.fixture(scope="session")
def session_factory(async_engine):
    return async_sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest.fixture
async def db_session(async_engine, session_factory):
    """One test = one connection-level transaction, rolled back at the end.
    A session bound to an already-began external transaction treats its own
    commit() as a flush, not a real commit — so app code (and factories)
    can commit freely without breaking isolation between tests.
    """
    async with async_engine.connect() as conn:
        transaction = await conn.begin()
        async with session_factory(bind=conn) as session:
            yield session
            await session.close()
        await transaction.rollback()


@pytest.fixture(scope="session")
async def app_lifespan():
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def async_client(app_lifespan, db_session):
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client

    app.dependency_overrides.clear()


# Auto-load every fixture-factory in tests/factories/ without manual imports.
pytest_plugins = [
    f"tests.factories.{modname}"
    for _, modname, _ in pkgutil.iter_modules(
        [str(Path(__file__).resolve().parent / "factories")]
    )
]
