import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, UniqueConstraint, false, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KundeZuweisung(Base):
    """Weist einen Mitarbeiter (User) als Betreuer einem Kunden zu -- many-to-many,
    hoechstens einer je Kunde ist Hauptbetreuer, die uebrigen Vertretung.
    Steuert, welche Kunden/Anlagen/Vorgaenge ein auf zugewiesene Kunden
    beschraenkter Nutzer sehen darf (siehe app/services/zuweisung_service.py)."""

    __tablename__ = "kunde_zuweisungen"
    __table_args__ = (
        UniqueConstraint("kunde_id", "user_id", name="uq_kunde_zuweisungen_kunde_user"),
        Index(
            "uq_kunde_zuweisungen_haupt",
            "kunde_id",
            unique=True,
            postgresql_where=text("hauptbetreuer"),
        ),
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
    hauptbetreuer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
