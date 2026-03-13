import uuid
from datetime import date

from sqlalchemy import Date, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NumberHistoric(Base):
    __tablename__ = "numbers_historic"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    number: Mapped[str] = mapped_column(String, nullable=False)
    id_user: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
