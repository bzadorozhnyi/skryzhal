from enum import StrEnum

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class DBSettings(BaseModel):
    NAME: str
    USER: str
    PASS: str
    HOST: str
    PORT: int = 5432

    @property
    def url(self) -> str:
        return f"postgresql+asyncpg://{self.USER}:{self.PASS}@{self.HOST}:{self.PORT}/{self.NAME}"


class S3StorageSettings(BaseModel):
    ENDPOINT_URL: str
    BUCKET: str
    ACCESS_KEY: str
    SECRET_KEY: str
    REGION: str = "us-east-1"
    UPLOAD_URL_EXPIRES_IN: int = 900
    GET_URL_EXPIRES_IN: int = 3600
    CONNECT_TIMEOUT_SECONDS: int = 5
    READ_TIMEOUT_SECONDS: int = 10
    MAX_ATTEMPTS: int = 3


class SQSSettings(BaseModel):
    ENDPOINT_URL: str
    QUEUE_NAME: str
    DLQ_NAME: str
    ACCESS_KEY: str
    SECRET_KEY: str
    REGION: str = "us-east-1"
    POLL_WAIT_TIME_SECONDS: int = 20
    POLL_MAX_MESSAGES: int = 5
    VISIBILITY_TIMEOUT_SECONDS: int = 30
    # Must stay below VISIBILITY_TIMEOUT_SECONDS, with a safety buffer, so the
    # heartbeat always renews before the current timeout window expires.
    VISIBILITY_EXTENSION_INTERVAL_SECONDS: int = 20
    RETRY_BACKOFF_BASE_SECONDS: int = 30
    RETRY_BACKOFF_MAX_SECONDS: int = 300
    CONNECT_TIMEOUT_SECONDS: int = 5
    # Must stay above POLL_WAIT_TIME_SECONDS: SQS long-polling legitimately
    # holds the HTTP response open for up to that long before replying.
    READ_TIMEOUT_SECONDS: int = 25
    MAX_ATTEMPTS: int = 3
    # How long the worker waits before retrying after a failed receive() call
    # (e.g. SQS temporarily unreachable), so it doesn't busy-loop retrying.
    POLL_ERROR_BACKOFF_SECONDS: int = 5


class OutboxSettings(BaseModel):
    # Capped at 10: the hard limit of SQS's send_message_batch per call.
    BATCH_SIZE: int = 10
    POLL_INTERVAL_SECONDS: int = 2


class LogFormat(StrEnum):
    JSON = "JSON"
    PRETTY = "PRETTY"


class LoggingSettings(BaseModel):
    FORMAT: LogFormat = LogFormat.JSON


class TracingSettings(BaseModel):
    # Distinct per process (api/worker/relay) — becomes the OTel "service.name"
    # resource attribute, how spans are grouped/filtered in Tempo/Grafana.
    SERVICE_NAME: str
    OTLP_ENDPOINT: str = "http://tempo:4317"


class Settings(BaseSettings):
    DB: DBSettings
    S3_STORAGE: S3StorageSettings
    SQS: SQSSettings
    OUTBOX: OutboxSettings = OutboxSettings()
    LOGGING: LoggingSettings = LoggingSettings()
    TRACING: TracingSettings

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )


settings = Settings()
