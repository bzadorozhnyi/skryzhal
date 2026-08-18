import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import SessionDep
from core.exceptions import ConflictException, NotFoundException
from core.logging import logger
from core.tracing import inject_current_carrier, tag_current_span
from jobs.dto.job import CreateJobResultDTO, JobDTO
from jobs.endpoints.v1.schemas.request.job import CreateJobIn
from jobs.models.render_job import JobStatus, RenderJob
from jobs.repositories.job import JobRepository, JobRepositoryDep
from outbox.models.outbox_event import OutboxEvent, OutboxEventType
from outbox.repositories.outbox import OutboxRepository, OutboxRepositoryDep
from templates.repositories.template import TemplateRepository, TemplateRepositoryDep


class CreateJobUseCase:
    def __init__(
        self,
        *,
        session: AsyncSession,
        job_repository: JobRepository,
        outbox_repository: OutboxRepository,
        template_repository: TemplateRepository,
    ):
        self.session = session
        self.job_repository = job_repository
        self.outbox_repository = outbox_repository
        self.template_repository = template_repository

    async def execute(
        self, *, job_id: uuid.UUID, data: CreateJobIn
    ) -> CreateJobResultDTO:
        template = await self.template_repository.get_by_id(
            template_id=data.template_id
        )
        if template is None:
            raise NotFoundException(f"Template {data.template_id} not found")

        existing = await self.job_repository.get_by_id(job_id=job_id)
        if existing is not None:
            reconciled = self._reconcile_existing(
                job_id=job_id, data=data, existing=existing
            )
            return CreateJobResultDTO(job=reconciled, created=False)

        job = RenderJob(
            id=job_id,
            template_id=data.template_id,
            input_data=data.input_data,
            status=JobStatus.PENDING,
        )
        tag_current_span(**{"job.id": str(job.id)})
        await self.job_repository.create(job=job)
        await self.outbox_repository.create(
            event=OutboxEvent(
                event_type=OutboxEventType.JOB_CREATED,
                payload={
                    "job_id": str(job.id),
                    "trace_carrier": inject_current_carrier(),
                },
            )
        )
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.job_repository.get_by_id(job_id=job_id)
            if existing is None:
                raise
            reconciled = self._reconcile_existing(
                job_id=job_id, data=data, existing=existing
            )
            return CreateJobResultDTO(job=reconciled, created=False)

        logger.bind(job_id=str(job.id), template_id=str(template.id)).info(
            "Job created"
        )
        return CreateJobResultDTO(job=self._to_dto(job), created=True)

    @staticmethod
    def _reconcile_existing(
        *, job_id: uuid.UUID, data: CreateJobIn, existing: RenderJob
    ) -> JobDTO:
        if (
            existing.template_id != data.template_id
            or existing.input_data != data.input_data
        ):
            raise ConflictException(
                f"Job {job_id} already exists with different parameters"
            )
        return CreateJobUseCase._to_dto(existing)

    @staticmethod
    def _to_dto(job: RenderJob) -> JobDTO:
        return JobDTO(
            id=job.id,
            template_id=job.template_id,
            status=job.status,
            get_url=None,
            error_message=job.error_message,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


def get_create_job_use_case(
    session: SessionDep,
    job_repository: JobRepositoryDep,
    outbox_repository: OutboxRepositoryDep,
    template_repository: TemplateRepositoryDep,
) -> CreateJobUseCase:
    return CreateJobUseCase(
        session=session,
        job_repository=job_repository,
        outbox_repository=outbox_repository,
        template_repository=template_repository,
    )


CreateJobUseCaseDep = Annotated[CreateJobUseCase, Depends(get_create_job_use_case)]
