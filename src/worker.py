import asyncio
import contextlib
import json
import uuid
from datetime import datetime
from pathlib import Path

from opentelemetry.trace import SpanKind
from prometheus_client import Gauge, start_http_server

from core.db import async_session
from core.logging import logger
from core.s3 import s3_client_context
from core.settings import settings
from core.sqs import sqs_client_context
from core.tracing import linked_span
from jobs.repositories.job import JobRepository
from jobs.repositories.queue import JobQueueRepository
from jobs.repositories.storage import JobStorageRepository
from jobs.services.render import RenderService
from templates.repositories.storage import TemplateStorageRepository
from templates.repositories.template import TemplateRepository

# Touched on every main-loop iteration; docker-compose healthcheck fails if
# this goes stale, catching a hung loop that a plain "process is alive"
# check would miss.
HEARTBEAT_FILE = Path("/tmp/worker_heartbeat")
WORKER_HEARTBEAT = Gauge(
    "worker_last_successful_poll_timestamp",
    "Unix timestamp of the last completed main-loop iteration",
)
METRICS_PORT = 9100


async def _extend_lease_periodically(
    *,
    job_queue: JobQueueRepository,
    receipt_handle: str,
    job_id: uuid.UUID,
    locked_until: datetime,
) -> None:
    while True:
        await asyncio.sleep(settings.SQS.VISIBILITY_EXTENSION_INTERVAL_SECONDS)
        await job_queue.extend_visibility(receipt_handle=receipt_handle)

        async with async_session() as session:
            extended = await JobRepository(session=session).extend_lock(
                job_id=job_id, locked_until=locked_until
            )
            await session.commit()

        if extended is None or extended.locked_until is None:
            logger.bind(job_id=str(job_id)).warning(
                "Lost the DB lease while still processing — "
                "another worker may have reclaimed this job"
            )
            return
        locked_until = extended.locked_until


def _compute_backoff(*, attempt_count: int) -> int:
    delay = settings.SQS.RETRY_BACKOFF_BASE_SECONDS * (2 ** max(attempt_count - 1, 0))
    return min(delay, settings.SQS.RETRY_BACKOFF_MAX_SECONDS)


def _extract_carrier(*, message: dict) -> dict[str, str]:
    attributes = message.get("MessageAttributes", {})
    return {
        name: value["StringValue"]
        for name, value in attributes.items()
        if "StringValue" in value
    }


async def process_message(
    *, message: dict, job_queue: JobQueueRepository, s3_client
) -> None:
    job_id = uuid.UUID(json.loads(message["Body"])["job_id"])
    receipt_handle = message["ReceiptHandle"]
    log = logger.bind(job_id=str(job_id))

    async with async_session() as session:
        job = await JobRepository(session=session).claim_for_processing(job_id=job_id)
        await session.commit()

    if job is None or job.locked_until is None:
        log.info("Job not found or already claimed, skipping")
        await job_queue.delete(receipt_handle=receipt_handle)
        return

    heartbeat = asyncio.create_task(
        _extend_lease_periodically(
            job_queue=job_queue,
            receipt_handle=receipt_handle,
            job_id=job_id,
            locked_until=job.locked_until,
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
                with linked_span(
                    carrier=_extract_carrier(message=message),
                    name="worker.process_message",
                    kind=SpanKind.CONSUMER,
                ) as span:
                    span.set_attribute("job.id", str(job_id))
                    await render_service.render(job=job)
            except Exception:
                log.exception("Transient failure rendering job")
                fresh = await job_repository.get_by_id(
                    job_id=job_id, populate_existing=True
                )
                attempt_count = fresh.attempt_count if fresh else 1
                backoff = _compute_backoff(attempt_count=attempt_count)
                await job_queue.extend_visibility(
                    receipt_handle=receipt_handle, visibility_timeout=backoff
                )
                log.bind(backoff_seconds=backoff, attempt_count=attempt_count).info(
                    "Job will be retried"
                )
                return
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat

    await job_queue.delete(receipt_handle=receipt_handle)
    log.info("Rendered job")


async def main() -> None:
    start_http_server(METRICS_PORT)
    async with s3_client_context() as s3_client, sqs_client_context() as sqs_client:
        job_queue = JobQueueRepository(sqs_client=sqs_client)
        logger.info("Worker started, polling SQS...")
        while True:
            HEARTBEAT_FILE.touch()
            WORKER_HEARTBEAT.set_to_current_time()
            try:
                messages = await job_queue.receive()
            except Exception:
                logger.exception("Failed to poll SQS, will retry")
                await asyncio.sleep(settings.SQS.POLL_ERROR_BACKOFF_SECONDS)
                continue

            for message in messages:
                try:
                    await process_message(
                        message=message, job_queue=job_queue, s3_client=s3_client
                    )
                except Exception:
                    logger.bind(message_id=message.get("MessageId")).exception(
                        "Unexpected failure processing message, skipping"
                    )
                HEARTBEAT_FILE.touch()
                WORKER_HEARTBEAT.set_to_current_time()


if __name__ == "__main__":
    asyncio.run(main())
