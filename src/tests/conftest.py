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
from jobs.repositories.queue import JobQueueRepository
from main import app
from tests.helpers.db import create_db, drop_db, is_db_exist

ALEMBIC_INI_PATH = Path(__file__).resolve().parent.parent / "alembic.ini"
os.environ["TESTING"] = "1"

# The "test-*" bucket/queue/DLQ these point at are provisioned by
# localstack-init-testing/ (mirrors localstack-init/, mounted alongside it —
# see docker-compose.yml), so this suite never competes for SQS messages
# with a live docker-compose worker/relay consuming the real queue.
# Application code (worker.py, job_queue.py, template storage) reads these
# fields straight off the settings singleton with no test-awareness of its
# own, so mutating them once here — before anything constructs a client or
# reads a queue/bucket name — is what makes the redirection invisible to it.
settings.S3_STORAGE.BUCKET = f"test-{settings.S3_STORAGE.BUCKET}"
settings.SQS.QUEUE_NAME = f"test-{settings.SQS.QUEUE_NAME}"
settings.SQS.DLQ_NAME = f"test-{settings.SQS.DLQ_NAME}"


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
async def db_connection(async_engine):
    """One test = one connection-level transaction, rolled back at the end.
    Exposed separately from db_session so anything else that needs a
    session in the SAME test (e.g. worker/relay's module-level async_session,
    monkeypatched) can bind to this same connection — a session bound to a
    different connection wouldn't see this transaction's uncommitted rows at
    all, regardless of what status they're in.
    """
    async with async_engine.connect() as conn:
        transaction = await conn.begin()
        yield conn
        await transaction.rollback()


@pytest.fixture
async def db_session(db_connection, session_factory):
    """A session bound to an already-began external transaction treats its
    own commit() as a flush, not a real commit — so app code (and factories)
    can commit freely without breaking isolation between tests.
    """
    async with session_factory(bind=db_connection) as session:
        yield session
        await session.close()


@pytest.fixture(scope="session")
async def app_lifespan():
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
def s3_client(app_lifespan):
    return app_lifespan.state.s3_client


@pytest.fixture
def sqs_client(app_lifespan):
    return app_lifespan.state.sqs_client


@pytest.fixture
def job_queue(sqs_client):
    return JobQueueRepository(sqs_client=sqs_client)


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
