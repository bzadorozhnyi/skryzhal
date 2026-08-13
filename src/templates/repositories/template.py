from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import SessionDep
from templates.models.template import Template


class TemplateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def lock_slug(self, slug: str) -> None:
        await self.session.execute(
            select(func.pg_advisory_xact_lock(func.hashtext(slug)))
        )

    async def get_max_version(self, slug: str) -> int | None:
        result = await self.session.execute(
            select(func.max(Template.version)).where(Template.slug == slug)
        )
        return result.scalar_one_or_none()

    async def create(self, template: Template) -> Template:
        self.session.add(template)
        return template


def get_template_repository(session: SessionDep) -> TemplateRepository:
    return TemplateRepository(session)


TemplateRepositoryDep = Annotated[TemplateRepository, Depends(get_template_repository)]
