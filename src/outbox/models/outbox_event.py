import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Enum, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db import BaseModel


class OutboxEventType(StrEnum):
    JOB_CREATED = "JOB_CREATED"
    JOB_RETRIED = "JOB_RETRIED"


class OutboxEvent(BaseModel):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index(
            "ix_outbox_events_unpublished",
            "created_at",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_type: Mapped[OutboxEventType] = mapped_column(
        Enum(OutboxEventType, name="outbox_event_type")
    )
    payload: Mapped[dict] = mapped_column(JSONB)
    published_at: Mapped[datetime | None] = mapped_column(default=None)
    dispatch_id: Mapped[str | None] = mapped_column(String(255), default=None)
