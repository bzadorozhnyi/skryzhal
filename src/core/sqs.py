from contextlib import asynccontextmanager
from typing import Annotated

import aioboto3
from botocore.config import Config
from fastapi import Depends, Request

from core.settings import settings

session = aioboto3.Session()


@asynccontextmanager
async def sqs_client_context():
    async with session.client(
        "sqs",
        endpoint_url=settings.SQS.ENDPOINT_URL,
        aws_access_key_id=settings.SQS.ACCESS_KEY,
        aws_secret_access_key=settings.SQS.SECRET_KEY,
        region_name=settings.SQS.REGION,
        config=Config(
            connect_timeout=settings.SQS.CONNECT_TIMEOUT_SECONDS,
            read_timeout=settings.SQS.READ_TIMEOUT_SECONDS,
            retries={"max_attempts": settings.SQS.MAX_ATTEMPTS, "mode": "standard"},
        ),
    ) as client:
        yield client


def get_sqs_client(request: Request):
    return request.app.state.sqs_client


SQSClientDep = Annotated[..., Depends(get_sqs_client)]  # ty: ignore[invalid-type-form]
