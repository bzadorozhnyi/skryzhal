from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import SessionDep
from templates.endpoints.v1.schemas.request.template import CreateTemplateIn
from templates.endpoints.v1.schemas.response.template import TemplateOut
from templates.models.template import Template
from templates.repositories.storage import (
    TemplateStorageRepository,
    TemplateStorageRepositoryDep,
)
from templates.repositories.template import TemplateRepository, TemplateRepositoryDep


class CreateTemplateUseCase:
    def __init__(
        self,
        *,
        session: AsyncSession,
        repository: TemplateRepository,
        storage: TemplateStorageRepository,
    ):
        self.session = session
        self.repository = repository
        self.storage = storage

    async def execute(self, *, data: CreateTemplateIn) -> TemplateOut:
        s3_key = await self.storage.promote(slug=data.slug, checksum=data.checksum)

        await self.repository.lock_slug(slug=data.slug)
        max_version = await self.repository.get_max_version(slug=data.slug)

        template = Template(
            slug=data.slug,
            name=data.name,
            version=(max_version or 0) + 1,
            s3_key=s3_key,
            checksum=data.checksum,
        )
        await self.repository.create(template=template)
        await self.session.commit()

        get_url = await self.storage.generate_get_url(key=template.s3_key)
        return TemplateOut(
            id=template.id,
            slug=template.slug,
            name=template.name,
            version=template.version,
            get_url=get_url,
            created_at=template.created_at,
        )


def get_create_template_use_case(
    session: SessionDep,
    repository: TemplateRepositoryDep,
    storage: TemplateStorageRepositoryDep,
) -> CreateTemplateUseCase:
    return CreateTemplateUseCase(
        session=session, repository=repository, storage=storage
    )


CreateTemplateUseCaseDep = Annotated[
    CreateTemplateUseCase, Depends(get_create_template_use_case)
]
