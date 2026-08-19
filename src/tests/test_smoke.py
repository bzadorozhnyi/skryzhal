"""Verifies the test infra itself: test DB lifecycle, transaction rollback
isolation, and that factories don't over-generate when overridden. Not
feature coverage — replace/delete once real tests exist.
"""

import pytest
from fastapi import status
from sqlalchemy import func, select

from jobs.models.render_job import RenderJob
from templates.models.template import Template


@pytest.mark.anyio
async def test_db_is_empty_at_test_start(db_session):
    """Confirms rollback-per-test isolation is real, not accidental."""
    count = await db_session.scalar(select(func.count()).select_from(Template))
    assert count == 0


@pytest.mark.anyio
async def test_template_factory_creates_a_row(db_session, template_factory):
    template = await template_factory()

    count = await db_session.scalar(select(func.count()).select_from(Template))
    assert count == 1
    assert template.slug.startswith("template-")


@pytest.mark.anyio
async def test_render_job_factory_default_creates_one_template(
    db_session, render_job_factory
):
    await render_job_factory()

    template_count = await db_session.scalar(select(func.count()).select_from(Template))
    job_count = await db_session.scalar(select(func.count()).select_from(RenderJob))
    assert template_count == 1
    assert job_count == 1


@pytest.mark.anyio
async def test_render_job_factory_reuses_explicit_template_override(
    db_session, template_factory, render_job_factory
):
    template = await template_factory()

    await render_job_factory(template=template)
    await render_job_factory(template=template)

    template_count = await db_session.scalar(select(func.count()).select_from(Template))
    job_count = await db_session.scalar(select(func.count()).select_from(RenderJob))
    assert template_count == 1  # not 3 — the override was actually honored
    assert job_count == 2


@pytest.mark.anyio
async def test_render_job_factory_create_batch(render_job_factory):
    jobs = await render_job_factory.create_batch(3)
    assert len(jobs) == 3


@pytest.mark.anyio
async def test_create_job_via_api(async_client, template_factory):
    template = await template_factory()

    job_id = "11111111-1111-1111-1111-111111111111"
    response = await async_client.put(
        f"/api/v1/jobs/{job_id}",
        json={"template_id": str(template.id), "input_data": {}},
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["status"] == "PENDING"
