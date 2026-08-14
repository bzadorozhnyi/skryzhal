import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import SessionDep
from jobs.models.render_job import JobStatus, RenderJob


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

    async def claim_for_processing(self, *, job_id: uuid.UUID) -> RenderJob | None:
        """Atomically flip PENDING -> PROCESSING; returns None if the job
        doesn't exist or was already claimed (e.g. a duplicate SQS delivery).
        """
        result = await self.session.execute(
            update(RenderJob)
            .where(RenderJob.id == job_id, RenderJob.status == JobStatus.PENDING)
            .values(status=JobStatus.PROCESSING)
            .returning(RenderJob)
        )
        return result.scalar_one_or_none()


def get_job_repository(session: SessionDep) -> JobRepository:
    return JobRepository(session=session)


JobRepositoryDep = Annotated[JobRepository, Depends(get_job_repository)]
