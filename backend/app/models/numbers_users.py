import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NumberUser(Base):
    __tablename__ = "numbers_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    number: Mapped[str] = mapped_column(String, nullable=False)
    id_user: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False
    )
    date_assigned: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    # "free" → vigencia 10 días  |  "vip" → vigencia 3 días
    type: Mapped[str] = mapped_column(String(10), nullable=False, default="free")
