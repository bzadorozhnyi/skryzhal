from typing import Self

from pydantic import BaseModel

from templates.dto.upload_url import UploadUrlDTO


class UploadUrlOut(BaseModel):
    upload_url: str
    expires_in: int

    @classmethod
    def from_dto(cls, dto: UploadUrlDTO) -> Self:
        return cls(upload_url=dto.upload_url, expires_in=dto.expires_in)
