import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class NumeroAcierto(Base):
    __tablename__ = "numero_aciertos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    historic_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("numbers_historic.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resultado_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loteria_resultados.id", ondelete="CASCADE"), nullable=False
    )
    # exacto | tres_orden | tres_desorden
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    resultado = relationship("LoteriaResultado")

    __table_args__ = (
        UniqueConstraint("historic_id", "resultado_id", "tipo", name="uq_acierto_historic_resultado_tipo"),
    )
