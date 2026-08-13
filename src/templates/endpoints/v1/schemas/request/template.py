from pydantic import BaseModel, Field


class CreateTemplateIn(BaseModel):
    slug: str
    name: str
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
