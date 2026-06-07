from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Contact(Base):
    __tablename__ = "contactos"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
