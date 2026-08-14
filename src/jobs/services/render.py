import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import SessionDep
from core.logging import logger
from core.typst import TypstCompilationError, compile_typst
from jobs.models.render_job import JobStatus
from jobs.repositories.job import JobRepository, JobRepositoryDep
from jobs.repositories.storage import JobStorageRepository, JobStorageRepositoryDep
from templates.repositories.storage import (
    TemplateStorageRepository,
    TemplateStorageRepositoryDep,
)
from templates.repositories.template import TemplateRepository, TemplateRepositoryDep


class RenderService:
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

    async def render(self, *, job_id: uuid.UUID) -> None:
        job = await self.job_repository.claim_for_processing(job_id=job_id)
        if job is None:
            logger.info(f"Job {job_id} not found or already claimed, skipping")
            return

        template = await self.template_repository.get_by_id(template_id=job.template_id)
        if template is None:
            job.status = JobStatus.FAILED
            job.error_message = f"Template {job.template_id} not found"
            job.attempt_count += 1
            await self.session.commit()
            return

        try:
            template_bytes = await self.template_storage.download(key=template.s3_key)
            pdf_bytes = await compile_typst(
                template=template_bytes, input_data=job.input_data
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


def get_render_service(
    session: SessionDep,
    job_repository: JobRepositoryDep,
    job_storage: JobStorageRepositoryDep,
    template_repository: TemplateRepositoryDep,
    template_storage: TemplateStorageRepositoryDep,
) -> RenderService:
    return RenderService(
        session=session,
        job_repository=job_repository,
        job_storage=job_storage,
        template_repository=template_repository,
        template_storage=template_storage,
    )


RenderServiceDep = Annotated[RenderService, Depends(get_render_service)]
