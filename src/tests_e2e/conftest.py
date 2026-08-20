import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SRC_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI_PATH = SRC_DIR / "alembic.ini"

# Must run before any project-internal import below — core.settings and
# core.db_url both read straight off os.environ, so whatever they see has
# to already be correct by the time they're first imported. Deliberately a
# different file from the fast tests/ suite's .env.test: this suite spawns
# real worker.py/relay.py subprocesses, which must never share a DB/bucket/
# queue with either prod or the fast suite.
from tests.helpers.env import load_dotenv_into_environ  # noqa: E402

load_dotenv_into_environ(".env.test.e2e", "../.env.test.e2e")

from core.db import get_session  # noqa: E402
from core.db_url import resolve_db_url  # noqa: E402
from jobs.repositories.queue import JobQueueRepository  # noqa: E402
from main import app  # noqa: E402
from tests.helpers.db import create_db, drop_db, is_db_exist  # noqa: E402

# worker.py/relay.py each start a Prometheus HTTP server on this port —
# fine as containers (separate network namespaces), not fine as two plain
# subprocesses on one host, so each gets its own here. 9101/9102 are taken
# by docker-compose's own worker/relay port mappings, hence 9201/9202.
WORKER_METRICS_PORT = 9201
RELAY_METRICS_PORT = 9202
PROCESS_READY_TIMEOUT_SECONDS = 15


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

    engine = create_async_engine(db_url, future=True)

    yield engine

    await engine.dispose()
    await drop_db(db_url=db_url)


@pytest.fixture(scope="session")
def session_factory(async_engine):
    return async_sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest.fixture
async def db_session(session_factory):
    """Real commits, no rollback isolation — worker.py/relay.py run as
    separate processes with their own connections and need to see this
    test's writes for real. Each test is responsible for scoping its own
    assertions to the job/template ids it created, since state here
    accumulates across the whole session rather than resetting per test.
    """
    async with session_factory() as session:
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


def _spawn(*, script: str, metrics_port: int, heartbeat_file: str):
    process = subprocess.Popen(
        [sys.executable, script],
        cwd=SRC_DIR,
        env={**os.environ, "METRICS_PORT": str(metrics_port)},
    )
    deadline = time.monotonic() + PROCESS_READY_TIMEOUT_SECONDS
    heartbeat_path = Path(heartbeat_file)
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{script} exited early with code {process.returncode}")
        if heartbeat_path.exists():
            return process
        time.sleep(0.2)
    process.terminate()
    raise RuntimeError(f"{script} never wrote its heartbeat file — did it start?")


def _stop(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


@pytest.fixture(scope="session", autouse=True)
def worker_process(async_engine):
    process = _spawn(
        script="worker.py",
        metrics_port=WORKER_METRICS_PORT,
        heartbeat_file="/tmp/worker_heartbeat",
    )
    yield process
    _stop(process)


@pytest.fixture(scope="session", autouse=True)
def relay_process(async_engine):
    process = _spawn(
        script="relay.py",
        metrics_port=RELAY_METRICS_PORT,
        heartbeat_file="/tmp/relay_heartbeat",
    )
    yield process
    _stop(process)
