from pydantic import BaseModel, Field


class UploadUrlIn(BaseModel):
    slug: str
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
