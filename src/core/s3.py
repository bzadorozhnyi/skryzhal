from contextlib import asynccontextmanager
from typing import Annotated

import aioboto3
from botocore.config import Config
from fastapi import Depends, Request

from core.settings import settings

session = aioboto3.Session()


@asynccontextmanager
async def s3_client_context():
    async with session.client(
        "s3",
        endpoint_url=settings.S3_STORAGE.ENDPOINT_URL,
        aws_access_key_id=settings.S3_STORAGE.ACCESS_KEY,
        aws_secret_access_key=settings.S3_STORAGE.SECRET_KEY,
        region_name=settings.S3_STORAGE.REGION,
        config=Config(
            signature_version="s3v4",
            connect_timeout=settings.S3_STORAGE.CONNECT_TIMEOUT_SECONDS,
            read_timeout=settings.S3_STORAGE.READ_TIMEOUT_SECONDS,
            retries={
                "max_attempts": settings.S3_STORAGE.MAX_ATTEMPTS,
                "mode": "standard",
            },
        ),
    ) as client:
        yield client


def get_s3_client(request: Request):
    return request.app.state.s3_client


S3ClientDep = Annotated[..., Depends(get_s3_client)]  # ty: ignore[invalid-type-form]
