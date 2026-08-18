import uuid
from typing import Annotated

from fastapi import Depends

from core.s3 import S3ClientDep
from core.settings import settings
from core.tracing import tracer


class JobStorageRepository:
    def __init__(self, *, s3_client):
        self.s3_client = s3_client

    @staticmethod
    def key(*, job_id: uuid.UUID) -> str:
        return f"render-jobs/{job_id}.pdf"

    async def upload_result(self, *, job_id: uuid.UUID, content: bytes) -> str:
        key = self.key(job_id=job_id)
        with tracer.start_as_current_span("s3.upload", attributes={"s3.key": key}):
            await self.s3_client.put_object(
                Bucket=settings.S3_STORAGE.BUCKET,
                Key=key,
                Body=content,
                ContentType="application/pdf",
            )
        return key

    async def generate_get_url(
        self, *, key: str, expires_in: int = settings.S3_STORAGE.GET_URL_EXPIRES_IN
    ) -> str:
        return await self.s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_STORAGE.BUCKET, "Key": key},
            ExpiresIn=expires_in,
        )


def get_job_storage_repository(s3_client: S3ClientDep) -> JobStorageRepository:
    return JobStorageRepository(s3_client=s3_client)


JobStorageRepositoryDep = Annotated[
    JobStorageRepository, Depends(get_job_storage_repository)
]
