import uuid

import pytest
from fastapi import status

from jobs.models.render_job import JobStatus


@pytest.mark.anyio
async def test_get_job_404_on_missing_job(async_client):
    response = await async_client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.anyio
async def test_get_job_pending_has_no_get_url(async_client, render_job_factory):
    job = await render_job_factory()

    response = await async_client.get(f"/api/v1/jobs/{job.id}")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["get_url"] is None


@pytest.mark.anyio
async def test_get_job_completed_has_get_url(async_client, render_job_factory):
    job = await render_job_factory(
        status=JobStatus.COMPLETED, result_s3_key="results/some-job.pdf"
    )

    response = await async_client.get(f"/api/v1/jobs/{job.id}")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["get_url"] is not None
