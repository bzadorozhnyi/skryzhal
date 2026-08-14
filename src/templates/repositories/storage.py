import base64
from typing import Annotated

from botocore.exceptions import ClientError
from fastapi import Depends

from core.exceptions import NotFoundException
from core.s3 import S3ClientDep
from core.settings import settings


class TemplateStorageRepository:
    def __init__(self, *, s3_client):
        self.s3_client = s3_client

    @staticmethod
    def staging_key(*, slug: str, checksum: str) -> str:
        return f"staging/{slug}/{checksum}.typ"

    @staticmethod
    def key(*, slug: str, checksum: str) -> str:
        return f"templates/{slug}/{checksum}.typ"

    async def generate_upload_url(
        self,
        *,
        slug: str,
        checksum: str,
        expires_in: int = settings.S3_STORAGE.UPLOAD_URL_EXPIRES_IN,
    ) -> str:
        checksum_b64 = base64.b64encode(bytes.fromhex(checksum)).decode()
        return await self.s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.S3_STORAGE.BUCKET,
                "Key": self.staging_key(slug=slug, checksum=checksum),
                "ContentType": "application/x-typst",
                "ChecksumSHA256": checksum_b64,
            },
            ExpiresIn=expires_in,
        )

    async def promote(self, *, slug: str, checksum: str) -> str:
        bucket = settings.S3_STORAGE.BUCKET
        target_key = self.key(slug=slug, checksum=checksum)

        try:
            await self.s3_client.head_object(Bucket=bucket, Key=target_key)
        except ClientError:
            pass
        else:
            # Same slug+checksum was already promoted by an earlier version —
            # dedup, reuse the existing object instead of requiring a re-upload.
            return target_key

        source_key = self.staging_key(slug=slug, checksum=checksum)
        try:
            await self.s3_client.copy_object(
                Bucket=bucket,
                CopySource={"Bucket": bucket, "Key": source_key},
                Key=target_key,
            )
        except ClientError as exc:
            raise NotFoundException(
                f"No staged upload found for slug={slug!r}, checksum={checksum!r}"
            ) from exc

        await self.s3_client.delete_object(Bucket=bucket, Key=source_key)
        return target_key

    async def generate_get_url(
        self, *, key: str, expires_in: int = settings.S3_STORAGE.GET_URL_EXPIRES_IN
    ) -> str:
        return await self.s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_STORAGE.BUCKET, "Key": key},
            ExpiresIn=expires_in,
        )

    async def download(self, *, key: str) -> bytes:
        response = await self.s3_client.get_object(
            Bucket=settings.S3_STORAGE.BUCKET, Key=key
        )
        return await response["Body"].read()


def get_template_storage_repository(
    s3_client: S3ClientDep,
) -> TemplateStorageRepository:
    return TemplateStorageRepository(s3_client=s3_client)


TemplateStorageRepositoryDep = Annotated[
    TemplateStorageRepository, Depends(get_template_storage_repository)
]
