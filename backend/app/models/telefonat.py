import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

# Muessen mit den CHECK-Constraints aus Migration 0121 uebereinstimmen.
TELEFONAT_RICHTUNGEN = ("ausgehend", "eingehend")
TELEFONAT_ERGEBNISSE = ("erreicht", "nicht_erreicht", "mailbox")
TELEFONAT_ERSTELLT_VIA = ("app", "claude")


class Telefonat(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "telefonate"
    __table_args__ = (
        CheckConstraint(f"richtung IN {TELEFONAT_RICHTUNGEN}", name="ck_telefonate_richtung_valid"),
        CheckConstraint(f"ergebnis IN {TELEFONAT_ERGEBNISSE}", name="ck_telefonate_ergebnis_valid"),
        CheckConstraint(f"erstellt_via IN {TELEFONAT_ERSTELLT_VIA}", name="ck_telefonate_erstellt_via_valid"),
        CheckConstraint(
            "kunde_id IS NOT NULL OR vorgang_id IS NOT NULL", name="ck_telefonate_kunde_oder_vorgang"
        ),
        CheckConstraint(
            "dauer_sekunden IS NULL OR dauer_sekunden >= 0", name="ck_telefonate_dauer_nicht_negativ"
        ),
        Index("ix_telefonate_mandant_kunde_beginn", "mandant_id", "kunde_id", "beginn"),
        Index("ix_telefonate_mandant_vorgang", "mandant_id", "vorgang_id"),
        Index(
            "ix_telefonate_offene_rueckrufe",
            "rueckruf_am",
            postgresql_where=text("rueckruf_erledigt_am IS NULL AND geloescht_am IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False, index=True
    )
    kunde_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kunden.id", ondelete="CASCADE"), nullable=True
    )
    vorgang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id", ondelete="CASCADE"), nullable=True
    )
    # Id aus der JSONB-Liste kunden.ansprechpartner, kein FK; Name/Nummer sind eine Kopie, damit der
    # Eintrag auch nach Aenderung oder Loeschen des Ansprechpartners stimmt.
    ansprechpartner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    partner_name: Mapped[str] = mapped_column(Text, nullable=False)
    partner_nummer: Mapped[str | None] = mapped_column(Text)
    richtung: Mapped[str] = mapped_column(Text, nullable=False)
    ergebnis: Mapped[str] = mapped_column(Text, nullable=False)
    erstellt_via: Mapped[str] = mapped_column(Text, nullable=False, default="app")
    beginn: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dauer_sekunden: Mapped[int | None] = mapped_column(Integer)
    notiz: Mapped[str | None] = mapped_column(Text)
    rueckruf_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rueckruf_erledigt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Einmal-Kennzeichen des Scheduler-Laufs (siehe scheduler_service._rueckrufe_fuer_mandant).
    rueckruf_benachrichtigt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    zeiterfassung_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zeiterfassung.id", ondelete="SET NULL"), nullable=True
    )
    erfasst_von: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    client_uuid: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True)
