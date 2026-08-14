import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import SessionDep
from jobs.models.render_job import RenderJob


class JobRepository:
    def __init__(self, *, session: AsyncSession):
        self.session = session

    async def get_by_id(
        self, *, job_id: uuid.UUID, populate_existing: bool = False
    ) -> RenderJob | None:
        return await self.session.get(
            RenderJob, job_id, populate_existing=populate_existing
        )

    async def create(self, *, job: RenderJob) -> RenderJob:
        self.session.add(job)
        return job


def get_job_repository(session: SessionDep) -> JobRepository:
    return JobRepository(session=session)


JobRepositoryDep = Annotated[JobRepository, Depends(get_job_repository)]
