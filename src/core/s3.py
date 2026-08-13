from typing import Annotated

import aioboto3
from botocore.config import Config
from fastapi import Depends

from core.settings import settings

session = aioboto3.Session()


async def get_s3_client():
    async with session.client(
        "s3",
        endpoint_url=settings.S3_STORAGE.ENDPOINT_URL,
        aws_access_key_id=settings.S3_STORAGE.ACCESS_KEY,
        aws_secret_access_key=settings.S3_STORAGE.SECRET_KEY,
        region_name=settings.S3_STORAGE.REGION,
        config=Config(signature_version="s3v4"),
    ) as client:
        yield client


S3ClientDep = Annotated[..., Depends(get_s3_client)]  # ty: ignore[invalid-type-form]
