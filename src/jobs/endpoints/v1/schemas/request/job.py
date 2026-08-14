import uuid

from pydantic import BaseModel


class CreateJobIn(BaseModel):
    template_id: uuid.UUID
    input_data: dict
