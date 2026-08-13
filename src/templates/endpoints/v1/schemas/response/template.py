import uuid
from datetime import datetime

from pydantic import BaseModel


class TemplateOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    version: int
    get_url: str
    created_at: datetime
