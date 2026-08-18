import asyncio
import uuid
from pathlib import Path

from opentelemetry.trace import SpanKind
from prometheus_client import Gauge, start_http_server

from core.db import async_session
from core.logging import logger
from core.settings import settings
from core.sqs import sqs_client_context
from core.tracing import start_linked_span_batch
from jobs.repositories.queue import JobQueueRepository
from outbox.repositories.outbox import OutboxRepository

# Touched on every main-loop iteration; docker-compose healthcheck fails if
# this goes stale, catching a hung loop that a plain "process is alive"
# check would miss.
HEARTBEAT_FILE = Path("/tmp/relay_heartbeat")
RELAY_HEARTBEAT = Gauge(
    "relay_last_successful_poll_timestamp",
    "Unix timestamp of the last completed main-loop iteration",
)
OUTBOX_UNPUBLISHED = Gauge(
    "outbox_unpublished_count", "Number of outbox events not yet published"
)
METRICS_PORT = 9100


async def relay_once(*, job_queue: JobQueueRepository) -> int:
    async with async_session() as session:
        outbox_repository = OutboxRepository(session=session)
        events = await outbox_repository.claim_batch_unpublished(
            limit=settings.OUTBOX.BATCH_SIZE
        )
        if not events:
            return 0

        events_by_key = {str(event.id): event for event in events}
        job_ids_by_key = {
            key: uuid.UUID(event.payload["job_id"])
            for key, event in events_by_key.items()
        }

        spans, message_attributes_by_key = start_linked_span_batch(
            carriers_by_key={
                key: event.payload.get("trace_carrier", {})
                for key, event in events_by_key.items()
            },
            name="relay.publish",
            kind=SpanKind.PRODUCER,
        )
        for key, span in spans.items():
            span.set_attribute("job.id", str(job_ids_by_key[key]))
        try:
            message_ids_by_key = await job_queue.publish_batch(
                job_ids_by_key=job_ids_by_key,
                message_attributes_by_key=message_attributes_by_key,
            )
        finally:
            for span in spans.values():
                span.end()

        for key, message_id in message_ids_by_key.items():
            await outbox_repository.mark_published(
                event=events_by_key[key], dispatch_id=message_id
            )
            logger.bind(
                job_id=str(job_ids_by_key[key]),
                outbox_event_id=key,
                dispatch_id=message_id,
            ).info("Relayed outbox event")

        await session.commit()

        published_count = len(message_ids_by_key)
        failed_count = len(events) - published_count
        if failed_count:
            logger.warning(f"{failed_count} outbox event(s) failed to publish")
        logger.info(f"Relayed {published_count} outbox event(s)")
        return published_count


async def main() -> None:
    start_http_server(METRICS_PORT)
    async with sqs_client_context() as sqs_client:
        job_queue = JobQueueRepository(sqs_client=sqs_client)
        logger.info("Relay started, polling outbox...")
        while True:
            HEARTBEAT_FILE.touch()
            RELAY_HEARTBEAT.set_to_current_time()
            try:
                published = await relay_once(job_queue=job_queue)
            except Exception:
                logger.exception("Failed to relay outbox batch, will retry")
                published = 0

            # Always refreshed, regardless of whether the publish attempt
            # above succeeded — otherwise a failing downstream queue leaves
            # this gauge frozen at its last-good value, hiding exactly the
            # backlog growth an operator would want to see during an outage.
            async with async_session() as session:
                OUTBOX_UNPUBLISHED.set(
                    await OutboxRepository(session=session).count_unpublished()
                )

            if not published:
                await asyncio.sleep(settings.OUTBOX.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
