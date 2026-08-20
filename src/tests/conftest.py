import asyncio
import pkgutil
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ALEMBIC_INI_PATH = Path(__file__).resolve().parent.parent / "alembic.ini"

# Must run before any project-internal import below — core.settings and
# core.db_url both read straight off os.environ, so whatever they see has
# to already be correct by the time they're first imported.
from tests.helpers.env import load_dotenv_into_environ  # noqa: E402

load_dotenv_into_environ(".env.test", "../.env.test")

from core.db import get_session  # noqa: E402
from core.db_url import resolve_db_url  # noqa: E402
from jobs.repositories.queue import JobQueueRepository  # noqa: E402
from main import app  # noqa: E402
from tests.helpers.db import create_db, drop_db, is_db_exist  # noqa: E402


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
def alembic_config():
    return Config(str(ALEMBIC_INI_PATH))


@pytest.fixture(scope="session")
async def async_engine(alembic_config):
    db_url = resolve_db_url()
    if await is_db_exist(db_url=db_url):
        await drop_db(db_url=db_url)
    await create_db(db_url=db_url)

    await asyncio.to_thread(command.upgrade, alembic_config, "head")

    engine = create_async_engine(db_url, echo=True, future=True)

    yield engine

    await engine.dispose()
    await drop_db(db_url=db_url)


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
