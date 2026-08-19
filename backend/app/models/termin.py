import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

TERMIN_STATUS = ("geplant", "bestaetigt", "abgeschlossen", "abgesagt")


class Termin(SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "termine"
    __table_args__ = (
        CheckConstraint("ende_at > start_at", name="ck_termine_ende_after_start"),
        CheckConstraint(f"status IN {TERMIN_STATUS}", name="ck_termine_status_valid"),
        Index("idx_termine_techniker", "techniker_id", "start_at"),
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
    techniker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    erstellt_von: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    titel: Mapped[str] = mapped_column(Text, nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ende_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="geplant")
    notiz: Mapped[str | None] = mapped_column(Text)
    # Zusatzangaben fuers Gantt-Dispo: Fahrzeit zur Anlage und Pause direkt
    # nach dem Termin, jeweils als fester Block in der Zeitachse sichtbar,
    # damit ein Disponent realistisch plant statt Termine Rand an Rand zu
    # setzen. Beides optional, NULL = kein Zuschlag (bisheriges Verhalten).
    fahrzeit_minuten: Mapped[int | None] = mapped_column(Integer)
    pause_minuten: Mapped[int | None] = mapped_column(Integer)
