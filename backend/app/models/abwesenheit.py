import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Muessen mit den CHECK-Constraints aus Migration 0101 uebereinstimmen.
ABWESENHEIT_ARTEN = ("urlaub", "krankheit", "freizeitausgleich")
ABWESENHEIT_STATUS = ("offen", "genehmigt", "abgelehnt", "zurueckgezogen")


class Abwesenheitsantrag(Base):
    """Urlaub, Krankheit oder Freizeitausgleich eines Mitarbeiters. Erst bei
    Status "genehmigt" existieren die zugehoerigen Zeiteintraege
    (Zeiterfassung.abwesenheit_id); die Zahl der betroffenen Arbeitstage wird
    nie gespeichert, sondern aus Soll und Feiertagen berechnet
    (app/services/abwesenheit_service.py)."""

    __tablename__ = "abwesenheitsantraege"
    __table_args__ = (
        CheckConstraint(f"art IN {ABWESENHEIT_ARTEN}", name="ck_abwesenheitsantraege_art_valid"),
        CheckConstraint(f"status IN {ABWESENHEIT_STATUS}", name="ck_abwesenheitsantraege_status_valid"),
        CheckConstraint("bis >= von", name="ck_abwesenheitsantraege_zeitraum_valid"),
        Index("ix_abwesenheitsantraege_user_von", "mandant_id", "user_id", "von"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    art: Mapped[str] = mapped_column(Text, nullable=False)
    von: Mapped[date] = mapped_column(Date, nullable=False)
    bis: Mapped[date] = mapped_column(Date, nullable=False)
    halber_tag_von: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    halber_tag_bis: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="offen", server_default="offen")
    notiz: Mapped[str | None] = mapped_column(Text, nullable=True)
    antwort: Mapped[str | None] = mapped_column(Text, nullable=True)
    erstellt_von: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    bearbeitet_von: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    bearbeitet_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Urlaubsanspruch(Base):
    __tablename__ = "urlaubsanspruch"
    __table_args__ = (
        UniqueConstraint("mandant_id", "user_id", "jahr", name="uq_urlaubsanspruch_user_jahr"),
        CheckConstraint("tage >= 0 AND resturlaub_tage >= 0", name="ck_urlaubsanspruch_tage_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    jahr: Mapped[int] = mapped_column(Integer, nullable=False)
    tage: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False)
    resturlaub_tage: Mapped[Decimal] = mapped_column(
        Numeric(5, 1), nullable=False, default=Decimal("0"), server_default="0"
    )
    resturlaub_verfaellt_am: Mapped[date | None] = mapped_column(Date, nullable=True)
