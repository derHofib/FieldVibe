import uuid
from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, SmallInteger, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.vorgang import ABRECHNUNGSARTEN_VORGANG, LEISTUNGSTYPEN


class Dauerauftrag(TimestampMixin, Base):
    """Wiederkehrender Auftrag: erzeugt in festen Abstaenden (in Tagen,
    gerechnet ab Abschluss des jeweils letzten erzeugten Vorgangs, nicht ab
    einem festen Kalenderdatum) automatisch einen neuen Vorgang fuer denselben
    Kunden/dieselbe Anlage -- siehe app/services/scheduler_service.py fuer
    die Erzeugung und app/api/routes/vorgaenge.py fuer den Abschluss-Hook,
    der naechste_faelligkeit_am fortschreibt."""

    __tablename__ = "dauerauftraege"
    __table_args__ = (
        CheckConstraint("intervall_tage > 0", name="ck_dauerauftraege_intervall_positiv"),
        CheckConstraint(
            f"abrechnungsart IN {ABRECHNUNGSARTEN_VORGANG}",
            name="ck_dauerauftraege_abrechnungsart_valid",
        ),
        CheckConstraint(
            f"leistungstyp IN {LEISTUNGSTYPEN}", name="ck_dauerauftraege_leistungstyp_valid"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    kunde_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kunden.id"), nullable=False
    )
    anlage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("anlagen.id"), nullable=True
    )
    titel: Mapped[str] = mapped_column(Text, nullable=False)
    beschreibung: Mapped[str | None] = mapped_column(Text)
    abrechnungsart: Mapped[str] = mapped_column(Text, nullable=False)
    leistungstyp: Mapped[str] = mapped_column(Text, nullable=False)
    intervall_tage: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    naechste_faelligkeit_am: Mapped[date] = mapped_column(Date, nullable=False)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    offener_vorgang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=True
    )
