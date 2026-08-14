from contextlib import asynccontextmanager
from typing import Annotated

import aioboto3
from fastapi import Depends

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
    ) as client:
        yield client


async def get_sqs_client():
    async with sqs_client_context() as client:
        yield client


SQSClientDep = Annotated[..., Depends(get_sqs_client)]  # ty: ignore[invalid-type-form]
