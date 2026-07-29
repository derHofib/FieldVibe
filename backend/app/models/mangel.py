import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

MANGEL_SCHWEREGRADE = ("kritisch", "hoch", "mittel", "niedrig")
MANGEL_STATUS = ("offen", "in_angebot", "in_bearbeitung", "behoben", "abgelehnt")


class Mangel(TimestampMixin, Base):
    __tablename__ = "maengel"
    __table_args__ = (
        CheckConstraint(f"schweregrad IN {MANGEL_SCHWEREGRADE}", name="ck_maengel_schweregrad_valid"),
        CheckConstraint(f"status IN {MANGEL_STATUS}", name="ck_maengel_status_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    vorgang_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=False
    )
    anlage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("anlagen.id"), nullable=True
    )
    beschreibung: Mapped[str] = mapped_column(Text, nullable=False)
    schweregrad: Mapped[str] = mapped_column(Text, nullable=False, default="mittel")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="offen")
    gemeldet_von: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    angebot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("angebote.id"), nullable=True
    )
    reparatur_vorgang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=True
    )
    behoben_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
