import time
from datetime import datetime
from typing import Annotated

from fastapi import Depends
from prometheus_client import Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import SessionDep
from core.logging import logger
from core.typst import TypstCompilationError, compile_typst
from jobs.models.render_job import JobStatus, RenderJob
from jobs.repositories.job import JobRepository, JobRepositoryDep
from jobs.repositories.storage import JobStorageRepository, JobStorageRepositoryDep
from jobs.services.job_transitions import transition
from templates.repositories.storage import (
    TemplateStorageRepository,
    TemplateStorageRepositoryDep,
)
from templates.repositories.template import TemplateRepository, TemplateRepositoryDep

# Only terminal outcomes (COMPLETED/FAILED) are recorded — a transient
# failure that reverts a job to PENDING for retry isn't "done" yet, so it
# shouldn't count toward completion rate or duration.
JOBS_COMPLETED = Counter(
    "jobs_completed_total", "Render jobs that reached a terminal status", ["status"]
)
RENDER_DURATION = Histogram(
    "render_duration_seconds", "Time from claiming a job to a terminal status"
)


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

    async def render(self, *, job: RenderJob) -> None:
        """Renders an already-claimed job. Every write below is fenced on
        job.locked_until — if that lease has since been reclaimed by another
        worker, the write is a no-op and this result is discarded rather
        than overwriting whatever the new owner is doing.
        """
        if job.locked_until is None:
            raise ValueError(f"Job {job.id} has no lease — was it claimed first?")
        locked_until = job.locked_until

        start = time.perf_counter()
        try:
            template = await self.template_repository.get_by_id(
                template_id=job.template_id
            )
            if template is None:
                await self._finalize(
                    job=job,
                    locked_until=locked_until,
                    status=JobStatus.FAILED,
                    start=start,
                    error_message=f"Template {job.template_id} not found",
                    attempt_count=job.attempt_count + 1,
                )
                return

            template_bytes = await self.template_storage.download(key=template.s3_key)
            pdf_bytes = await compile_typst(
                template=template_bytes, input_data=job.input_data
            )
            result_s3_key = await self.job_storage.upload_result(
                job_id=job.id, content=pdf_bytes
            )
            await self._finalize(
                job=job,
                locked_until=locked_until,
                status=JobStatus.COMPLETED,
                start=start,
                result_s3_key=result_s3_key,
            )
        except TypstCompilationError as exc:
            await self._finalize(
                job=job,
                locked_until=locked_until,
                status=JobStatus.FAILED,
                start=start,
                error_message=exc.stderr,
                attempt_count=job.attempt_count + 1,
            )
        except Exception:
            # Unexpected/transient failure (S3 outage, DB hiccup, etc.) — revert
            # to PENDING so SQS redelivery + claim_for_processing can retry it,
            # instead of leaving the job stuck at PROCESSING forever.
            await self._finalize(
                job=job,
                locked_until=locked_until,
                status=JobStatus.PENDING,
                start=None,
                attempt_count=job.attempt_count + 1,
            )
            raise

    async def _finalize(
        self,
        *,
        job: RenderJob,
        locked_until: datetime,
        status: JobStatus,
        start: float | None,
        **fields,
    ) -> None:
        transition(job=job, status=status)  # validates the transition is legal

        match status:
            case JobStatus.COMPLETED:
                updated = await self.job_repository.complete_if_owner(
                    job_id=job.id, locked_until=locked_until, **fields
                )
            case JobStatus.FAILED:
                updated = await self.job_repository.fail_if_owner(
                    job_id=job.id, locked_until=locked_until, **fields
                )
            case JobStatus.PENDING:
                updated = await self.job_repository.revert_to_pending_if_owner(
                    job_id=job.id, locked_until=locked_until, **fields
                )
            case _:
                raise ValueError(f"No fenced writer for status {status}")

        await self.session.commit()

        if updated is None:
            logger.bind(job_id=str(job.id)).warning(
                "Lease was reclaimed by another worker before this result "
                "could be saved — discarding"
            )
        elif start is not None:
            self._record_outcome(status=status, start=start)

    @staticmethod
    def _record_outcome(*, status: JobStatus, start: float) -> None:
        JOBS_COMPLETED.labels(status=status).inc()
        RENDER_DURATION.observe(time.perf_counter() - start)


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
