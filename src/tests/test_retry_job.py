import uuid

import pytest
from fastapi import status
from sqlalchemy import select

from jobs.models.render_job import JobStatus
from jobs.repositories.queue import JobQueueRepository
from outbox.models.outbox_event import OutboxEvent, OutboxEventType


@pytest.mark.anyio
async def test_retry_job_404_on_missing_job(async_client):
    response = await async_client.post(f"/api/v1/jobs/{uuid.uuid4()}/retry")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.anyio
async def test_retry_job_409_on_invalid_source_status(async_client, render_job_factory):
    job = await render_job_factory(status=JobStatus.PENDING)

    response = await async_client.post(f"/api/v1/jobs/{job.id}/retry")
    assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.anyio
async def test_retry_job_from_failed_reverts_to_pending_and_publishes_event(
    async_client, db_session, render_job_factory, job_queue: JobQueueRepository
):
    job = await render_job_factory(status=JobStatus.FAILED, error_message="boom")

    response = await async_client.post(f"/api/v1/jobs/{job.id}/retry")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "PENDING"

    result = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.event_type == OutboxEventType.JOB_RETRIED)
    )
    event = result.scalar_one()
    assert event.payload["job_id"] == str(job.id)
