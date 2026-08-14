import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import SessionDep
from core.exceptions import InternalServerException, NotFoundException
from jobs.dto.job import JobDTO
from jobs.models.render_job import JobStatus
from jobs.repositories.job import JobRepository, JobRepositoryDep
from jobs.repositories.queue import JobQueueRepository, JobQueueRepositoryDep
from jobs.services.job_transitions import transition


class RetryJobUseCase:
    def __init__(
        self,
        *,
        session: AsyncSession,
        job_repository: JobRepository,
        job_queue: JobQueueRepository,
    ):
        self.session = session
        self.job_repository = job_repository
        self.job_queue = job_queue

    async def execute(self, *, job_id: uuid.UUID) -> JobDTO:
        job = await self.job_repository.get_by_id(job_id=job_id)
        if job is None:
            raise NotFoundException(f"Job {job_id} not found")

        transition(job=job, status=JobStatus.PENDING)
        await self.session.commit()
        job = await self.job_repository.get_by_id(job_id=job_id, populate_existing=True)
        if job is None:
            raise InternalServerException(f"Job {job_id} disappeared after commit")

        await self.job_queue.publish(job_id=job.id)

        return JobDTO(
            id=job.id,
            template_id=job.template_id,
            status=job.status,
            get_url=None,
            error_message=job.error_message,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


def get_retry_job_use_case(
    session: SessionDep,
    job_repository: JobRepositoryDep,
    job_queue: JobQueueRepositoryDep,
) -> RetryJobUseCase:
    return RetryJobUseCase(
        session=session, job_repository=job_repository, job_queue=job_queue
    )


RetryJobUseCaseDep = Annotated[RetryJobUseCase, Depends(get_retry_job_use_case)]
