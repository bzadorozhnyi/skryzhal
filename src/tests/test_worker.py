import json
from datetime import UTC, datetime, timedelta

import pytest

import jobs.services.render as render_module
import worker
from core.settings import settings
from jobs.models.render_job import JobStatus
from jobs.repositories.job import JobRepository
from jobs.repositories.queue import JobQueueRepository


@pytest.fixture(autouse=True)
def patch_worker_session(monkeypatch, db_connection, session_factory):
    # worker.py imports async_session from core.db as a module-level
    # singleton bound to the production DB — point it at the SAME connection
    # db_session/factories use, not just the same DB: a session on a
    # different connection wouldn't see this test's uncommitted rows at all.
    monkeypatch.setattr(
        worker, "async_session", lambda: session_factory(bind=db_connection)
    )


@pytest.fixture
def fake_compile_typst(monkeypatch):
    async def _compile(*, template: bytes, input_data: dict) -> bytes:
        return b"%PDF-fake"

    monkeypatch.setattr(render_module, "compile_typst", _compile)
    return _compile


async def _publish_and_receive(*, job_queue: JobQueueRepository, job_id) -> dict:
    await job_queue.publish_batch(job_ids_by_key={"1": job_id})
    for _ in range(10):
        messages = await job_queue.receive(wait_time_seconds=2, max_messages=5)
        matching = [
            m for m in messages if json.loads(m["Body"])["job_id"] == str(job_id)
        ]
        if matching:
            return matching[0]
    raise AssertionError(f"message for job {job_id} was not received back from SQS")


@pytest.mark.anyio
async def test_process_message_completes_job(
    db_session,
    template_factory,
    render_job_factory,
    job_queue,
    s3_client,
    fake_compile_typst,
):
    template = await template_factory()
    await s3_client.put_object(
        Bucket=settings.S3_STORAGE.BUCKET,
        Key=template.s3_key,
        Body=b"fake typst source",
    )
    job = await render_job_factory(template=template)

    message = await _publish_and_receive(job_queue=job_queue, job_id=job.id)
    await worker.process_message(
        message=message, job_queue=job_queue, s3_client=s3_client
    )

    updated = await JobRepository(session=db_session).get_by_id(
        job_id=job.id, populate_existing=True
    )
    assert updated is not None
    assert updated.status == JobStatus.COMPLETED
    assert updated.result_s3_key is not None


@pytest.mark.anyio
async def test_process_message_reclaims_abandoned_lease(
    db_session,
    template_factory,
    render_job_factory,
    job_queue,
    s3_client,
    fake_compile_typst,
):
    """The exact scenario we verified by hand earlier: a job stuck at
    PROCESSING with an expired lease (the worker that claimed it is
    presumed dead) gets reclaimed and completed by whoever picks the
    redelivered message up next.
    """
    template = await template_factory()
    await s3_client.put_object(
        Bucket=settings.S3_STORAGE.BUCKET,
        Key=template.s3_key,
        Body=b"fake typst source",
    )
    job = await render_job_factory(
        template=template,
        status=JobStatus.PROCESSING,
        locked_until=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=5),
    )

    message = await _publish_and_receive(job_queue=job_queue, job_id=job.id)
    await worker.process_message(
        message=message, job_queue=job_queue, s3_client=s3_client
    )

    updated = await JobRepository(session=db_session).get_by_id(
        job_id=job.id, populate_existing=True
    )
    assert updated is not None
    assert updated.status == JobStatus.COMPLETED


@pytest.mark.anyio
async def test_process_message_skips_already_completed_job(
    db_session, template_factory, render_job_factory, job_queue, s3_client
):
    template = await template_factory()
    job = await render_job_factory(template=template, status=JobStatus.COMPLETED)

    message = await _publish_and_receive(job_queue=job_queue, job_id=job.id)
    await worker.process_message(
        message=message, job_queue=job_queue, s3_client=s3_client
    )

    # Nothing to assert on job state (untouched) — the real assertion is
    # that this didn't raise trying to re-render a finished job, and the
    # SQS message got consumed (no leftover redelivery).
    remaining = await job_queue.receive(wait_time_seconds=1, max_messages=5)
    assert not any(json.loads(m["Body"])["job_id"] == str(job.id) for m in remaining)
