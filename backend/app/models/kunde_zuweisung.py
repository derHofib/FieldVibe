import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KundeZuweisung(Base):
    """Weist einen Techniker (User) einem Kunden zu -- many-to-many, ein
    Kunde kann mehrere Techniker haben (Vertretung/Team) und ein Techniker
    mehrere Kunden. Steuert, welche Kunden/Anlagen/Vorgaenge ein Techniker
    sehen darf (siehe app/services/zuweisung_service.py)."""

    __tablename__ = "kunde_zuweisungen"
    __table_args__ = (
        UniqueConstraint("kunde_id", "user_id", name="uq_kunde_zuweisungen_kunde_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    kunde_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kunden.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
