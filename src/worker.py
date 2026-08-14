import asyncio
import json
import uuid

from core.db import async_session
from core.logging import logger
from core.s3 import s3_client_context
from core.sqs import sqs_client_context
from jobs.repositories.job import JobRepository
from jobs.repositories.queue import JobQueueRepository
from jobs.repositories.storage import JobStorageRepository
from jobs.services.render import RenderService
from templates.repositories.storage import TemplateStorageRepository
from templates.repositories.template import TemplateRepository


async def process_message(
    *, message: dict, job_queue: JobQueueRepository, s3_client
) -> None:
    job_id = uuid.UUID(json.loads(message["Body"])["job_id"])

    async with async_session() as session:
        render_service = RenderService(
            session=session,
            job_repository=JobRepository(session=session),
            job_storage=JobStorageRepository(s3_client=s3_client),
            template_repository=TemplateRepository(session=session),
            template_storage=TemplateStorageRepository(s3_client=s3_client),
        )
        try:
            await render_service.render(job_id=job_id)
        except Exception:
            logger.exception(f"Failed to render job {job_id}")
            return

    await job_queue.delete(receipt_handle=message["ReceiptHandle"])
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
