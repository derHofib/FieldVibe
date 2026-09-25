import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Muss mit der CHECK-Constraint ck_zeiterfassung_aenderungen_aktion_valid
# (Migration 0084) uebereinstimmen.
ZEITERFASSUNG_AENDERUNG_AKTIONEN = (
    "angelegt",
    "geaendert",
    "geloescht",
    "wiederhergestellt",
    "vorgemerkt",
    "vormerkung_zurueckgezogen",
    "gebucht",
    "buchung_storniert",
    "abgerechnet",
    "abrechnung_zurueckgesetzt",
)


class ZeiterfassungAenderung(Base):
    """Unveraenderliches Protokoll je Zeiterfassungs-Eintrag (docs/konzepte/
    ZEITERFASSUNG.md Abschnitt 5.2, nach dem Vorbild von
    FormSubmissionAudit) -- ueber die API nur lesbar, nie aenderbar oder
    loeschbar. Eine Zeile je geaendertem Feld bzw. je Buchungsschritt."""

    __tablename__ = "zeiterfassung_aenderungen"
    __table_args__ = (
        CheckConstraint(
            f"aktion IN {ZEITERFASSUNG_AENDERUNG_AKTIONEN}",
            name="ck_zeiterfassung_aenderungen_aktion_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()"
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    zeiterfassung_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zeiterfassung.id", ondelete="CASCADE"), nullable=False
    )
    aktion: Mapped[str] = mapped_column(Text, nullable=False)
    feld: Mapped[str | None] = mapped_column(Text, nullable=True)
    alter_wert: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    neuer_wert: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    # Pflicht, wenn jemand einen fremden Eintrag aendert (Konzept 5.2/6.2) --
    # Pruefung dafuer sitzt in der Route, nicht hier.
    grund: Mapped[str | None] = mapped_column(Text, nullable=True)
    geaendert_von: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    geaendert_am: Mapped[datetime] = mapped_column(server_default="now()", nullable=False)
