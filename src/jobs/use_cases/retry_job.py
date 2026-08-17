import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import SessionDep
from core.exceptions import InternalServerException, NotFoundException
from core.logging import logger
from jobs.dto.job import JobDTO
from jobs.models.render_job import JobStatus
from jobs.repositories.job import JobRepository, JobRepositoryDep
from jobs.services.job_transitions import transition
from outbox.models.outbox_event import OutboxEvent, OutboxEventType
from outbox.repositories.outbox import OutboxRepository, OutboxRepositoryDep


class RetryJobUseCase:
    def __init__(
        self,
        *,
        session: AsyncSession,
        job_repository: JobRepository,
        outbox_repository: OutboxRepository,
    ):
        self.session = session
        self.job_repository = job_repository
        self.outbox_repository = outbox_repository

    async def execute(self, *, job_id: uuid.UUID) -> JobDTO:
        job = await self.job_repository.get_by_id(job_id=job_id)
        if job is None:
            raise NotFoundException(f"Job {job_id} not found")

        transition(job=job, status=JobStatus.PENDING)
        await self.outbox_repository.create(
            event=OutboxEvent(
                event_type=OutboxEventType.JOB_RETRIED,
                payload={"job_id": str(job.id)},
            )
        )
        await self.session.commit()
        job = await self.job_repository.get_by_id(job_id=job_id, populate_existing=True)
        if job is None:
            raise InternalServerException(f"Job {job_id} disappeared after commit")

        logger.bind(job_id=str(job.id)).info("Job retried")
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
    outbox_repository: OutboxRepositoryDep,
) -> RetryJobUseCase:
    return RetryJobUseCase(
        session=session,
        job_repository=job_repository,
        outbox_repository=outbox_repository,
    )


RetryJobUseCaseDep = Annotated[RetryJobUseCase, Depends(get_retry_job_use_case)]
