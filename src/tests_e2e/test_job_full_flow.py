import asyncio
import hashlib
import uuid

import pytest
from fastapi import status

from core.settings import settings
from templates.repositories.storage import TemplateStorageRepository

MINIMAL_TYPST_SOURCE = b"= Hello\nThis is an end-to-end test document.\n"
JOB_TIMEOUT_SECONDS = 30


def _checksum() -> str:
    return hashlib.sha256(uuid.uuid4().bytes).hexdigest()


async def _create_template(*, async_client, s3_client) -> dict:
    slug = f"e2e-{uuid.uuid4().hex[:8]}"
    checksum = _checksum()
    staging_key = TemplateStorageRepository.staging_key(slug=slug, checksum=checksum)
    await s3_client.put_object(
        Bucket=settings.S3_STORAGE.BUCKET, Key=staging_key, Body=MINIMAL_TYPST_SOURCE
    )

    response = await async_client.post(
        "/api/v1/templates",
        json={"slug": slug, "name": "E2E template", "checksum": checksum},
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()


async def _wait_for_status(*, async_client, job_id: str, timeout: float) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        response = await async_client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        if body["status"] in {"COMPLETED", "FAILED"}:
            return body
        await asyncio.sleep(0.5)
    raise AssertionError(f"job {job_id} did not reach a terminal status in {timeout}s")


@pytest.mark.anyio
async def test_job_completes_through_real_worker_and_relay(async_client, s3_client):
    """The full path this whole test tier exists for: a real HTTP create_job
    request, picked up by a real relay.py process (outbox -> SQS), rendered
    by a real worker.py process (SQS -> claim -> typst compile -> S3 -> DB),
    with nothing monkeypatched anywhere in between.
    """
    template = await _create_template(async_client=async_client, s3_client=s3_client)

    job_id = str(uuid.uuid4())
    create_response = await async_client.put(
        f"/api/v1/jobs/{job_id}",
        json={"template_id": template["id"], "input_data": {}},
    )
    assert create_response.status_code == status.HTTP_201_CREATED

    job = await _wait_for_status(
        async_client=async_client, job_id=job_id, timeout=JOB_TIMEOUT_SECONDS
    )
    assert job["status"] == "COMPLETED"
    assert job["get_url"] is not None
