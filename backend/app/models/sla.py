import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, SmallInteger, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

SLA_KALENDER = ("rund_um_die_uhr", "geschaeftszeiten")
SLA_FRIST_ARTEN = ("reaktion", "loesung")
SLA_STUFEN_AKTIONEN = ("benachrichtigen", "mail")
SLA_EMPFAENGER = ("zugewiesener", "dispo", "vorgesetzter", "admin")


class SlaRichtlinie(TimestampMixin, Base):
    __tablename__ = "sla_richtlinien"
    __table_args__ = (
        CheckConstraint(f"kalender IN {SLA_KALENDER}", name="ck_sla_richtlinien_kalender_valid"),
        UniqueConstraint("mandant_id", "name", name="uq_sla_richtlinien_mandant_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    beschreibung: Mapped[str | None] = mapped_column(Text)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Hoechstens eine je Mandant (partieller Unique-Index in Migration 0116).
    ist_standard: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    kalender: Mapped[str] = mapped_column(Text, nullable=False, default="rund_um_die_uhr")
    # {"0": [["07:00", "17:00"]], ...}; Wochentag 0 = Montag.
    geschaeftszeiten: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    feiertage_ausnehmen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # {"5": {"reaktion_min": 30, "loesung_min": 240}, ...}, Prioritaet 1-5.
    ziele: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # {"stoerung": 5}: Leistungstyp -> Prioritaet, gilt nur fuer Vorgaenge dieser Richtlinie.
    prioritaet_regeln: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class SlaEskalationsstufe(TimestampMixin, Base):
    __tablename__ = "sla_eskalationsstufen"
    __table_args__ = (
        CheckConstraint(f"frist_art IN {SLA_FRIST_ARTEN}", name="ck_sla_stufen_frist_art_valid"),
        CheckConstraint(f"aktion IN {SLA_STUFEN_AKTIONEN}", name="ck_sla_stufen_aktion_valid"),
        CheckConstraint(f"empfaenger IN {SLA_EMPFAENGER}", name="ck_sla_stufen_empfaenger_valid"),
        CheckConstraint("schwelle_prozent BETWEEN 1 AND 500", name="ck_sla_stufen_schwelle_bereich"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    richtlinie_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sla_richtlinien.id", ondelete="CASCADE"), nullable=False, index=True
    )
    frist_art: Mapped[str] = mapped_column(Text, nullable=False)
    schwelle_prozent: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    aktion: Mapped[str] = mapped_column(Text, nullable=False)
    empfaenger: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
