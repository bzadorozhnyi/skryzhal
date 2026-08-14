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


class SQSSettings(BaseModel):
    ENDPOINT_URL: str
    QUEUE_NAME: str
    DLQ_NAME: str
    ACCESS_KEY: str
    SECRET_KEY: str
    REGION: str = "us-east-1"


class Settings(BaseSettings):
    DB: DBSettings
    S3_STORAGE: S3StorageSettings
    SQS: SQSSettings

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )


settings = Settings()
