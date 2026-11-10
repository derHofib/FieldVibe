import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ZEITPLAN_ANTRAG_ARTEN = ("verschieben", "dauer_aendern", "problem")
ZEITPLAN_ANTRAG_STATUS = ("offen", "angenommen", "abgelehnt", "zurueckgezogen")


class ZeitplanAenderungsantrag(Base):
    """Vorschlag eines Technikers (ohne projekte.bearbeiten), einen Schritt/
    Meilenstein des Zeitplans zu verschieben, zu verlaengern/kuerzen oder ein
    Problem zu melden. Aendert den Plan nie selbst -- erst die Annahme durch das
    Office wendet die Aenderung ueber zeitplan_service.element_aendern an."""

    __tablename__ = "zeitplan_aenderungsantraege"
    __table_args__ = (
        CheckConstraint(f"art IN {ZEITPLAN_ANTRAG_ARTEN}", name="ck_zeitplan_aenderungsantraege_art_valid"),
        CheckConstraint(f"status IN {ZEITPLAN_ANTRAG_STATUS}", name="ck_zeitplan_aenderungsantraege_status_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    projekt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projekte.id", ondelete="CASCADE"), nullable=False
    )
    element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projekt_aufgaben.id", ondelete="CASCADE"), nullable=False
    )
    art: Mapped[str] = mapped_column(Text, nullable=False)
    gewuenschter_start_am: Mapped[date | None] = mapped_column(Date, nullable=True)
    gewuenschtes_ende_am: Mapped[date | None] = mapped_column(Date, nullable=True)
    begruendung: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="offen", server_default="offen")
    antwort: Mapped[str | None] = mapped_column(Text, nullable=True)
    erstellt_von: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    bearbeitet_von: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    bearbeitet_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
