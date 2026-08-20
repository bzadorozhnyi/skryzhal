import os


def build_db_url(*, user: str, password: str, host: str, port: int, name: str) -> str:
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def resolve_db_url() -> str:
    """Builds the DB connection string directly from os.environ, with no
    dependency on core.settings.Settings (which also requires S3/SQS/
    tracing config to validate) — migrations may run standalone, before any
    app code has touched settings at all. Has no notion of files or test
    mode: whatever gets these into os.environ (docker compose, or
    tests/conftest.py loading .env.test) is a separate concern.
    """
    return build_db_url(
        user=_required_env("DB__USER"),
        password=_required_env("DB__PASS"),
        host=_required_env("DB__HOST"),
        port=int(_required_env("DB__PORT")),
        name=_required_env("DB__NAME"),
    )
