import uuid

import pytest
from fastapi import status


@pytest.mark.anyio
async def test_create_job_404_on_missing_template(async_client):
    job_id = uuid.uuid4()
    response = await async_client.put(
        f"/api/v1/jobs/{job_id}",
        json={"template_id": str(uuid.uuid4()), "input_data": {}},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.anyio
async def test_create_job_idempotent_repeat_returns_200(async_client, template_factory):
    template = await template_factory()
    job_id = uuid.uuid4()
    body = {"template_id": str(template.id), "input_data": {"a": 1}}

    first = await async_client.put(f"/api/v1/jobs/{job_id}", json=body)
    assert first.status_code == status.HTTP_201_CREATED

    second = await async_client.put(f"/api/v1/jobs/{job_id}", json=body)
    assert second.status_code == status.HTTP_200_OK
    assert second.json()["id"] == str(job_id)


@pytest.mark.anyio
async def test_create_job_409_on_conflicting_repeat(async_client, template_factory):
    template = await template_factory()
    job_id = uuid.uuid4()

    first = await async_client.put(
        f"/api/v1/jobs/{job_id}",
        json={"template_id": str(template.id), "input_data": {"a": 1}},
    )
    assert first.status_code == status.HTTP_201_CREATED

    second = await async_client.put(
        f"/api/v1/jobs/{job_id}",
        json={"template_id": str(template.id), "input_data": {"a": 2}},
    )
    assert second.status_code == status.HTTP_409_CONFLICT
