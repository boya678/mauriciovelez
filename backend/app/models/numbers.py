from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Number(Base):
    __tablename__ = "numbers"

    number: Mapped[str] = mapped_column(String, primary_key=True)
    assigned: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
