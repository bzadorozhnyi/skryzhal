from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import SessionDep
from outbox.models.outbox_event import OutboxEvent


class OutboxRepository:
    def __init__(self, *, session: AsyncSession):
        self.session = session

    async def create(self, *, event: OutboxEvent) -> OutboxEvent:
        self.session.add(event)
        return event

    async def claim_batch_unpublished(self, *, limit: int) -> list[OutboxEvent]:
        """Locks and returns the oldest unpublished events, skipping rows
        already locked by another relay instance. Caller must commit exactly
        once for the whole batch (a mid-batch commit would release the lock
        on the not-yet-processed rows).
        """
        result = await self.session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    async def mark_published(self, *, event: OutboxEvent, dispatch_id: str) -> None:
        # published_at is TIMESTAMP WITHOUT TIME ZONE (matches created_at/
        # updated_at elsewhere), so store a naive UTC value, not aware.
        event.published_at = datetime.now(UTC).replace(tzinfo=None)
        event.dispatch_id = dispatch_id


def get_outbox_repository(session: SessionDep) -> OutboxRepository:
    return OutboxRepository(session=session)


OutboxRepositoryDep = Annotated[OutboxRepository, Depends(get_outbox_repository)]
