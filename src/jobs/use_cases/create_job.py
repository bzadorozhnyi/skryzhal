import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import SessionDep
from core.exceptions import ConflictException, NotFoundException
from jobs.dto.job import CreateJobResultDTO, JobDTO
from jobs.endpoints.v1.schemas.request.job import CreateJobIn
from jobs.models.render_job import JobStatus, RenderJob
from jobs.repositories.job import JobRepository, JobRepositoryDep
from jobs.repositories.queue import JobQueueRepository, JobQueueRepositoryDep
from templates.repositories.template import TemplateRepository, TemplateRepositoryDep


class CreateJobUseCase:
    def __init__(
        self,
        *,
        session: AsyncSession,
        job_repository: JobRepository,
        job_queue: JobQueueRepository,
        template_repository: TemplateRepository,
    ):
        self.session = session
        self.job_repository = job_repository
        self.job_queue = job_queue
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
        await self.job_repository.create(job=job)
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

        await self.job_queue.publish(job_id=job.id)
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
    job_queue: JobQueueRepositoryDep,
    template_repository: TemplateRepositoryDep,
) -> CreateJobUseCase:
    return CreateJobUseCase(
        session=session,
        job_repository=job_repository,
        job_queue=job_queue,
        template_repository=template_repository,
    )


CreateJobUseCaseDep = Annotated[CreateJobUseCase, Depends(get_create_job_use_case)]
