import json

import pytest
from sqlalchemy import select

import relay
from jobs.repositories.queue import JobQueueRepository
from outbox.models.outbox_event import OutboxEvent, OutboxEventType


@pytest.fixture(autouse=True)
def patch_relay_session(monkeypatch, db_connection, session_factory):
    # Same reasoning as worker's patch_relay_session: bind to the same
    # connection db_session/factories use, or relay can't see this test's
    # uncommitted rows at all.
    monkeypatch.setattr(
        relay, "async_session", lambda: session_factory(bind=db_connection)
    )


async def _get_event(*, db_session, event_id) -> OutboxEvent:
    result = await db_session.execute(
        select(OutboxEvent)
        .where(OutboxEvent.id == event_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


@pytest.mark.anyio
async def test_relay_once_with_no_backlog(db_session, job_queue: JobQueueRepository):
    published_count = await relay.relay_once(job_queue=job_queue)
    assert published_count == 0


@pytest.mark.anyio
async def test_relay_once_publishes_pending_event(
    db_session, render_job_factory, job_queue: JobQueueRepository
):
    job = await render_job_factory()
    event = OutboxEvent(
        event_type=OutboxEventType.JOB_CREATED, payload={"job_id": str(job.id)}
    )
    db_session.add(event)
    await db_session.flush()

    published_count = await relay.relay_once(job_queue=job_queue)
    assert published_count == 1

    updated_event = await _get_event(db_session=db_session, event_id=event.id)
    assert updated_event.published_at is not None
    assert updated_event.dispatch_id is not None

    messages = await job_queue.receive(wait_time_seconds=5, max_messages=5)
    assert any(json.loads(m["Body"])["job_id"] == str(job.id) for m in messages)
