from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import SessionDep
from core.exceptions import InternalServerException, NotFoundException
from core.logging import logger
from core.typst import TypstCompilationError, compile_typst
from jobs.endpoints.v1.schemas.request.job import CreateJobIn
from jobs.endpoints.v1.schemas.response.job import JobOut
from jobs.models.render_job import JobStatus, RenderJob
from jobs.repositories.job import JobRepository, JobRepositoryDep
from jobs.repositories.storage import JobStorageRepository, JobStorageRepositoryDep
from templates.repositories.storage import (
    TemplateStorageRepository,
    TemplateStorageRepositoryDep,
)
from templates.repositories.template import TemplateRepository, TemplateRepositoryDep


class CreateJobUseCase:
    def __init__(
        self,
        *,
        session: AsyncSession,
        job_repository: JobRepository,
        job_storage: JobStorageRepository,
        template_repository: TemplateRepository,
        template_storage: TemplateStorageRepository,
    ):
        self.session = session
        self.job_repository = job_repository
        self.job_storage = job_storage
        self.template_repository = template_repository
        self.template_storage = template_storage

    async def execute(self, *, data: CreateJobIn) -> JobOut:
        template = await self.template_repository.get_by_id(
            template_id=data.template_id
        )
        if template is None:
            raise NotFoundException(f"Template {data.template_id} not found")

        job = RenderJob(
            template_id=data.template_id,
            input_data=data.input_data,
            status=JobStatus.PENDING,
        )
        await self.job_repository.create(job=job)
        await self.session.commit()

        # TODO(Stage 2): this synchronous render belongs in a queue-consuming
        # worker; this use case should just enqueue the PENDING job instead.
        try:
            template_bytes = await self.template_storage.download(key=template.s3_key)
            pdf_bytes = await compile_typst(
                template=template_bytes, input_data=data.input_data
            )
            job.result_s3_key = await self.job_storage.upload_result(
                job_id=job.id, content=pdf_bytes
            )
            job.status = JobStatus.COMPLETED
        except TypstCompilationError as exc:
            job.status = JobStatus.FAILED
            job.error_message = exc.stderr
            job.attempt_count += 1

        await self.session.commit()
        job_id = job.id
        job = await self.job_repository.get_by_id(job_id=job_id, populate_existing=True)
        if job is None:
            logger.error(f"Job {job_id} disappeared after commit")
            raise InternalServerException(f"Job {job_id} disappeared after commit")

        get_url = None
        if job.status == JobStatus.COMPLETED and job.result_s3_key:
            get_url = await self.job_storage.generate_get_url(key=job.result_s3_key)

        return JobOut(
            id=job.id,
            template_id=job.template_id,
            status=job.status,
            get_url=get_url,
            error_message=job.error_message,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


def get_create_job_use_case(
    session: SessionDep,
    job_repository: JobRepositoryDep,
    job_storage: JobStorageRepositoryDep,
    template_repository: TemplateRepositoryDep,
    template_storage: TemplateStorageRepositoryDep,
) -> CreateJobUseCase:
    return CreateJobUseCase(
        session=session,
        job_repository=job_repository,
        job_storage=job_storage,
        template_repository=template_repository,
        template_storage=template_storage,
    )


CreateJobUseCaseDep = Annotated[CreateJobUseCase, Depends(get_create_job_use_case)]
