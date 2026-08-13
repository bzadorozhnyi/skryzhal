import uuid

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.db import BaseModel


class Template(BaseModel):
    __tablename__ = "templates"
    __table_args__ = (UniqueConstraint("slug", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[int]
    s3_key: Mapped[str] = mapped_column(String(512))
    checksum: Mapped[str] = mapped_column(String(64))
