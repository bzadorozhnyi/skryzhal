import asyncio
import contextlib
import json
import uuid

from core.db import async_session
from core.logging import logger
from core.s3 import s3_client_context
from core.settings import settings
from core.sqs import sqs_client_context
from jobs.repositories.job import JobRepository
from jobs.repositories.queue import JobQueueRepository
from jobs.repositories.storage import JobStorageRepository
from jobs.services.render import RenderService
from templates.repositories.storage import TemplateStorageRepository
from templates.repositories.template import TemplateRepository


async def _extend_visibility_periodically(
    *, job_queue: JobQueueRepository, receipt_handle: str
) -> None:
    while True:
        await asyncio.sleep(settings.SQS.VISIBILITY_EXTENSION_INTERVAL_SECONDS)
        await job_queue.extend_visibility(receipt_handle=receipt_handle)


def _compute_backoff(*, attempt_count: int) -> int:
    delay = settings.SQS.RETRY_BACKOFF_BASE_SECONDS * (2 ** max(attempt_count - 1, 0))
    return min(delay, settings.SQS.RETRY_BACKOFF_MAX_SECONDS)


async def process_message(
    *, message: dict, job_queue: JobQueueRepository, s3_client
) -> None:
    job_id = uuid.UUID(json.loads(message["Body"])["job_id"])
    receipt_handle = message["ReceiptHandle"]

    heartbeat = asyncio.create_task(
        _extend_visibility_periodically(
            job_queue=job_queue, receipt_handle=receipt_handle
        )
    )
    try:
        async with async_session() as session:
            job_repository = JobRepository(session=session)
            render_service = RenderService(
                session=session,
                job_repository=job_repository,
                job_storage=JobStorageRepository(s3_client=s3_client),
                template_repository=TemplateRepository(session=session),
                template_storage=TemplateStorageRepository(s3_client=s3_client),
            )
            try:
                await render_service.render(job_id=job_id)
            except Exception:
                logger.exception(f"Transient failure rendering job {job_id}")
                job = await job_repository.get_by_id(job_id=job_id)
                attempt_count = job.attempt_count if job else 1
                backoff = _compute_backoff(attempt_count=attempt_count)
                await job_queue.extend_visibility(
                    receipt_handle=receipt_handle, visibility_timeout=backoff
                )
                logger.info(
                    f"Job {job_id} will be retried in {backoff}s "
                    f"(attempt {attempt_count})"
                )
                return
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat

    await job_queue.delete(receipt_handle=receipt_handle)
    logger.info(f"Rendered job {job_id}")


async def main() -> None:
    async with s3_client_context() as s3_client, sqs_client_context() as sqs_client:
        job_queue = JobQueueRepository(sqs_client=sqs_client)
        logger.info("Worker started, polling SQS...")
        while True:
            messages = await job_queue.receive()
            for message in messages:
                await process_message(
                    message=message, job_queue=job_queue, s3_client=s3_client
                )


if __name__ == "__main__":
    asyncio.run(main())
