from pydantic import BaseModel


class UploadUrlDTO(BaseModel):
    upload_url: str
    expires_in: int
