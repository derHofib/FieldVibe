import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ANGEBOT_ANNAHME_AKTIONEN = ("annahme", "ablehnung", "widerruf")


class AngebotAnnahme(Base):
    """Nachweis, wer wann welche Fassung eines Angebots im Portal angenommen,
    abgelehnt oder widerrufen hat. Append-only: ein Trigger verbietet UPDATE
    und DELETE (siehe Migration 0111), weil der Eintrag im Streitfall als
    Beweis dient. Die Zugangs-Angaben sind bewusst als Momentaufnahme kopiert
    -- E-Mail/Name des Zugangs koennen sich spaeter aendern."""

    __tablename__ = "angebot_annahmen"
    __table_args__ = (
        CheckConstraint(f"aktion IN {ANGEBOT_ANNAHME_AKTIONEN}", name="aktion_valid"),
        CheckConstraint("char_length(fassung_sha256) = 64", name="fassung_sha256_laenge"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    angebot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("angebote.id"), nullable=False
    )
    aktion: Mapped[str] = mapped_column(Text, nullable=False)
    kunden_portal_zugang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        # Eigener Name: der generierte waere laenger als Postgres' 63 Zeichen.
        ForeignKey("kundenportal_zugaenge.id", name="fk_angebot_annahmen_zugang_kundenportal_zugaenge"),
        nullable=True,
    )
    zugang_email: Mapped[str] = mapped_column(Text, nullable=False)
    zugang_name: Mapped[str] = mapped_column(Text, nullable=False)
    ip: Mapped[str] = mapped_column(Text, nullable=False)
    user_agent: Mapped[str] = mapped_column(Text, nullable=False, default="")
    fassung_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    b2c_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    belehrung_version: Mapped[str | None] = mapped_column(Text)
    # Wortlaut der angezeigten Belehrung: die Version allein beweist nichts,
    # wenn der Betrieb den Text spaeter aendert, ohne sie hochzuzaehlen.
    belehrung_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
