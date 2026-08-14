import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel

from templates.dto.template import TemplateDTO


class TemplateOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    version: int
    get_url: str
    created_at: datetime

    @classmethod
    def from_dto(cls, dto: TemplateDTO) -> Self:
        return cls(
            id=dto.id,
            slug=dto.slug,
            name=dto.name,
            version=dto.version,
            get_url=dto.get_url,
            created_at=dto.created_at,
        )
