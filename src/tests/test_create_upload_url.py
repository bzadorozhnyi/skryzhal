import hashlib
import uuid

import pytest
from fastapi import status


@pytest.mark.anyio
async def test_create_upload_url_returns_presigned_url(async_client):
    checksum = hashlib.sha256(uuid.uuid4().bytes).hexdigest()

    response = await async_client.post(
        "/api/v1/templates/upload-url",
        json={"slug": "invoice", "checksum": checksum},
    )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["upload_url"].startswith("http")
    assert body["expires_in"] > 0


@pytest.mark.anyio
async def test_create_upload_url_400_on_invalid_checksum(async_client):
    response = await async_client.post(
        "/api/v1/templates/upload-url",
        json={"slug": "invoice", "checksum": "not-a-checksum"},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
