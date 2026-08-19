import uuid
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Update, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from core.db import SessionDep
from core.settings import settings
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

    @staticmethod
    def _fenced(*, job_id: uuid.UUID, locked_until: datetime) -> Update:
        """An UPDATE...WHERE for `job_id`, conditioned on `locked_until`
        still matching — the fencing check every write past the initial
        claim needs, so a caller whose lease has since been reclaimed by
        someone else can't overwrite that new owner's work.
        """
        return update(RenderJob).where(
            RenderJob.id == job_id, RenderJob.locked_until == locked_until
        )

    async def claim_for_processing(self, *, job_id: uuid.UUID) -> RenderJob | None:
        """Atomically claims a job for processing: either it's PENDING, or
        it's PROCESSING with an expired lease (the previous claimant is
        presumed gone). Returns None if neither holds — the job doesn't
        exist, or someone else already holds a live lease on it.
        """
        result = await self.session.execute(
            update(RenderJob)
            .where(
                RenderJob.id == job_id,
                or_(
                    RenderJob.status == JobStatus.PENDING,
                    and_(
                        RenderJob.status == JobStatus.PROCESSING,
                        RenderJob.locked_until < func.now(),
                    ),
                ),
            )
            .values(
                status=JobStatus.PROCESSING,
                locked_until=func.now() + timedelta(seconds=settings.SQS.LEASE_SECONDS),
            )
            .returning(RenderJob)
        )
        return result.scalar_one_or_none()

    async def extend_lock(
        self, *, job_id: uuid.UUID, locked_until: datetime
    ) -> RenderJob | None:
        result = await self.session.execute(
            self._fenced(job_id=job_id, locked_until=locked_until)
            .values(
                locked_until=func.now() + timedelta(seconds=settings.SQS.LEASE_SECONDS)
            )
            .returning(RenderJob)
        )
        return result.scalar_one_or_none()

    async def complete_if_owner(
        self, *, job_id: uuid.UUID, locked_until: datetime, result_s3_key: str
    ) -> RenderJob | None:
        result = await self.session.execute(
            self._fenced(job_id=job_id, locked_until=locked_until)
            .values(status=JobStatus.COMPLETED, result_s3_key=result_s3_key)
            .returning(RenderJob)
        )
        return result.scalar_one_or_none()

    async def fail_if_owner(
        self,
        *,
        job_id: uuid.UUID,
        locked_until: datetime,
        error_message: str,
        attempt_count: int,
    ) -> RenderJob | None:
        result = await self.session.execute(
            self._fenced(job_id=job_id, locked_until=locked_until)
            .values(
                status=JobStatus.FAILED,
                error_message=error_message,
                attempt_count=attempt_count,
            )
            .returning(RenderJob)
        )
        return result.scalar_one_or_none()

    async def revert_to_pending_if_owner(
        self, *, job_id: uuid.UUID, locked_until: datetime, attempt_count: int
    ) -> RenderJob | None:
        result = await self.session.execute(
            self._fenced(job_id=job_id, locked_until=locked_until)
            .values(status=JobStatus.PENDING, attempt_count=attempt_count)
            .returning(RenderJob)
        )
        return result.scalar_one_or_none()


def get_job_repository(session: SessionDep) -> JobRepository:
    return JobRepository(session=session)


JobRepositoryDep = Annotated[JobRepository, Depends(get_job_repository)]
