import uuid
from datetime import datetime

from pydantic import BaseModel

from jobs.models.render_job import JobStatus


class JobOut(BaseModel):
    id: uuid.UUID
    template_id: uuid.UUID
    status: JobStatus
    get_url: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
