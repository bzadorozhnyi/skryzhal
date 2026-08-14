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

    async def publish(self, *, job_id: uuid.UUID) -> None:
        queue_url = await self._queue_url(queue_name=settings.SQS.QUEUE_NAME)
        await self.sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps({"job_id": str(job_id)}),
        )

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
