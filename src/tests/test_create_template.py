import hashlib
import uuid

import pytest
from fastapi import status

from core.settings import settings
from templates.repositories.storage import TemplateStorageRepository


def _checksum() -> str:
    return hashlib.sha256(uuid.uuid4().bytes).hexdigest()


@pytest.mark.anyio
async def test_create_template_404_without_staged_upload(async_client):
    response = await async_client.post(
        "/api/v1/templates",
        json={"slug": "invoice", "name": "Invoice", "checksum": _checksum()},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.anyio
async def test_create_template_promotes_staged_upload(async_client, s3_client):
    slug = "invoice"
    checksum = _checksum()
    staging_key = TemplateStorageRepository.staging_key(slug=slug, checksum=checksum)
    await s3_client.put_object(
        Bucket=settings.S3_STORAGE.BUCKET, Key=staging_key, Body=b"fake typst source"
    )

    response = await async_client.post(
        "/api/v1/templates",
        json={"slug": slug, "name": "Invoice", "checksum": checksum},
    )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["slug"] == slug
    assert body["version"] == 1
    assert body["get_url"].startswith("http")

    target_key = TemplateStorageRepository.key(slug=slug, checksum=checksum)
    await s3_client.head_object(Bucket=settings.S3_STORAGE.BUCKET, Key=target_key)


@pytest.mark.anyio
async def test_create_template_repeat_promote_reuses_object_bumps_version(
    async_client, s3_client
):
    slug = "invoice"
    checksum = _checksum()
    staging_key = TemplateStorageRepository.staging_key(slug=slug, checksum=checksum)
    await s3_client.put_object(
        Bucket=settings.S3_STORAGE.BUCKET, Key=staging_key, Body=b"fake typst source"
    )

    first = await async_client.post(
        "/api/v1/templates",
        json={"slug": slug, "name": "Invoice", "checksum": checksum},
    )
    assert first.status_code == status.HTTP_201_CREATED
    assert first.json()["version"] == 1

    # Re-stage the same content and promote again: the storage layer dedups
    # (reuses the existing S3 object), but the repository still records a new
    # version row — promotion isn't the same thing as "already have this row".
    await s3_client.put_object(
        Bucket=settings.S3_STORAGE.BUCKET, Key=staging_key, Body=b"fake typst source"
    )
    second = await async_client.post(
        "/api/v1/templates",
        json={"slug": slug, "name": "Invoice", "checksum": checksum},
    )
    assert second.status_code == status.HTTP_201_CREATED
    assert second.json()["version"] == 2
