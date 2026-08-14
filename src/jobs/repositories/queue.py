import json
import uuid
from typing import Annotated

from fastapi import Depends

from core.settings import settings
from core.sqs import SQSClientDep


class JobQueueRepository:
    def __init__(self, *, sqs_client):
        self.sqs_client = sqs_client

    async def _queue_url(self, *, queue_name: str) -> str:
        response = await self.sqs_client.get_queue_url(QueueName=queue_name)
        return response["QueueUrl"]

    async def publish_batch(
        self, *, job_ids_by_key: dict[str, uuid.UUID]
    ) -> dict[str, str]:
        """Batch-publishes jobs to SQS. `job_ids_by_key` maps a caller-chosen
        correlation key (unique within the batch, at most 10 entries per the
        SQS send_message_batch limit) to the job_id to publish. Returns that
        same key mapped to the resulting SQS MessageId, for entries that
        succeeded — callers must check for missing keys to detect per-entry
        failures.
        """
        queue_url = await self._queue_url(queue_name=settings.SQS.QUEUE_NAME)
        entries = [
            {"Id": key, "MessageBody": json.dumps({"job_id": str(job_id)})}
            for key, job_id in job_ids_by_key.items()
        ]
        response = await self.sqs_client.send_message_batch(
            QueueUrl=queue_url, Entries=entries
        )
        return {
            entry["Id"]: entry["MessageId"] for entry in response.get("Successful", [])
        }

    async def receive(
        self,
        *,
        wait_time_seconds: int = settings.SQS.POLL_WAIT_TIME_SECONDS,
        max_messages: int = settings.SQS.POLL_MAX_MESSAGES,
    ) -> list:
        queue_url = await self._queue_url(queue_name=settings.SQS.QUEUE_NAME)
        response = await self.sqs_client.receive_message(
            QueueUrl=queue_url,
            WaitTimeSeconds=wait_time_seconds,
            MaxNumberOfMessages=max_messages,
        )
        return response.get("Messages", [])

    async def delete(self, *, receipt_handle: str) -> None:
        queue_url = await self._queue_url(queue_name=settings.SQS.QUEUE_NAME)
        await self.sqs_client.delete_message(
            QueueUrl=queue_url, ReceiptHandle=receipt_handle
        )

    async def extend_visibility(
        self,
        *,
        receipt_handle: str,
        visibility_timeout: int = settings.SQS.VISIBILITY_TIMEOUT_SECONDS,
    ) -> None:
        queue_url = await self._queue_url(queue_name=settings.SQS.QUEUE_NAME)
        await self.sqs_client.change_message_visibility(
            QueueUrl=queue_url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=visibility_timeout,
        )


def get_job_queue_repository(sqs_client: SQSClientDep) -> JobQueueRepository:
    return JobQueueRepository(sqs_client=sqs_client)


JobQueueRepositoryDep = Annotated[JobQueueRepository, Depends(get_job_queue_repository)]
