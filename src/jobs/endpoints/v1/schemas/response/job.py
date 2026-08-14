import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel

from jobs.dto.job import JobDTO
from jobs.models.render_job import JobStatus


class JobOut(BaseModel):
    id: uuid.UUID
    template_id: uuid.UUID
    status: JobStatus
    get_url: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_dto(cls, dto: JobDTO) -> Self:
        return cls(
            id=dto.id,
            template_id=dto.template_id,
            status=dto.status,
            get_url=dto.get_url,
            error_message=dto.error_message,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )
