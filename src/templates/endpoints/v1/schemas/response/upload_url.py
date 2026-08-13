from pydantic import BaseModel


class UploadUrlOut(BaseModel):
    upload_url: str
    expires_in: int
