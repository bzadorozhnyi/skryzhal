from typing import Annotated

from fastapi import Depends

from core.settings import settings
from templates.endpoints.v1.schemas.request.upload_url import UploadUrlIn
from templates.endpoints.v1.schemas.response.upload_url import UploadUrlOut
from templates.repositories.storage import (
    TemplateStorageRepository,
    TemplateStorageRepositoryDep,
)


class CreateUploadUrlUseCase:
    def __init__(self, *, storage: TemplateStorageRepository):
        self.storage = storage

    async def execute(self, *, data: UploadUrlIn) -> UploadUrlOut:
        upload_url = await self.storage.generate_upload_url(
            slug=data.slug, checksum=data.checksum
        )
        return UploadUrlOut(
            upload_url=upload_url, expires_in=settings.S3_STORAGE.UPLOAD_URL_EXPIRES_IN
        )


def get_create_upload_url_use_case(
    storage: TemplateStorageRepositoryDep,
) -> CreateUploadUrlUseCase:
    return CreateUploadUrlUseCase(storage=storage)


CreateUploadUrlUseCaseDep = Annotated[
    CreateUploadUrlUseCase, Depends(get_create_upload_url_use_case)
]
