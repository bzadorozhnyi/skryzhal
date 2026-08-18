import asyncio
import uuid

from core.db import async_session
from core.logging import logger
from core.settings import settings
from core.sqs import sqs_client_context
from jobs.repositories.queue import JobQueueRepository
from outbox.repositories.outbox import OutboxRepository


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
        message_ids_by_key = await job_queue.publish_batch(
            job_ids_by_key=job_ids_by_key
        )

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
    async with sqs_client_context() as sqs_client:
        job_queue = JobQueueRepository(sqs_client=sqs_client)
        logger.info("Relay started, polling outbox...")
        while True:
            try:
                published = await relay_once(job_queue=job_queue)
            except Exception:
                logger.exception("Failed to relay outbox batch, will retry")
                published = 0
            if not published:
                await asyncio.sleep(settings.OUTBOX.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
