import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

RECHNUNG_STATUS = ("entwurf", "versendet", "bezahlt", "storniert")


class Rechnung(SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "rechnungen"
    __table_args__ = (
        UniqueConstraint("mandant_id", "rechnungsnummer", name="uq_rechnungen_mandant_rechnungsnummer"),
        CheckConstraint(f"status IN {RECHNUNG_STATUS}", name="ck_rechnungen_status_valid"),
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
    vorgang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=True
    )
    rechnungsnummer: Mapped[str] = mapped_column(Text, nullable=False)
    # Zeitpunkt der Leistung/Lieferung (§14 Abs. 4 Nr. 6 UStG) -- kann vom
    # Rechnungsdatum abweichen (z.B. Rechnung erst Tage nach Auftragsende).
    leistungsdatum: Mapped[date | None] = mapped_column(Date, nullable=True)
    betrag_netto: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    mwst_satz: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("19.00"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="entwurf")
    faellig_am: Mapped[date | None] = mapped_column(Date)
    erstellt_von: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    versendet_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bezahlt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Mahnwesen (Nacharbeit): 0 = keine Mahnung, steigt mit jedem Eskalations-
    # Lauf des Workers fuer weiterhin ueberfaellige, unbezahlte Rechnungen.
    mahnstufe: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    letzte_mahnung_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RechnungPosition(Base):
    __tablename__ = "rechnung_positionen"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    rechnung_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rechnungen.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    beschreibung: Mapped[str] = mapped_column(Text, nullable=False)
    menge: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("1"))
    einheit: Mapped[str] = mapped_column(Text, nullable=False, default="Stk")
    einzelpreis: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
