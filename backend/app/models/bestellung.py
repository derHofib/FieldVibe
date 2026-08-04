import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, SmallInteger, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

BESTELLUNG_STATUS = ("entwurf", "bestellt", "eingegangen")


class Bestellung(SoftDeleteMixin, TimestampMixin, Base):
    """Sammelt ausgewaehlte offene MaterialBedarf-Eintraege (zweck=
    "bestellung") zu einer Bestellung an einen Lieferanten -- Export als
    CSV/PDF (siehe app/api/routes/bestellungen.py). status="eingegangen"
    bucht fuer jede Position automatisch einen Wareneingang
    (MaterialBewegung + Bestandserhoehung am Zentrallager)."""

    __tablename__ = "bestellungen"
    __table_args__ = (
        UniqueConstraint("mandant_id", "bestellnummer", name="uq_bestellungen_mandant_bestellnummer"),
        CheckConstraint(f"status IN {BESTELLUNG_STATUS}", name="ck_bestellungen_status_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    lieferant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lieferanten.id"), nullable=True
    )
    bestellnummer: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="entwurf")
    notiz: Mapped[str | None] = mapped_column(Text)
    erstellt_von: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )


class BestellungPosition(Base):
    """menge/einheit/einzelpreis sind ein Schnappschuss zum Bestellzeitpunkt
    (nicht live an Material verknuepft), damit eine spaetere Preisaenderung
    am Artikel nicht rueckwirkend alte Bestellungen veraendert -- dasselbe
    Prinzip wie bei AngebotPosition/RechnungPosition."""

    __tablename__ = "bestellung_positionen"
    __table_args__ = (
        CheckConstraint("menge > 0", name="ck_bestellung_positionen_menge_positiv"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    bestellung_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bestellungen.id", ondelete="CASCADE"), nullable=False
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("material.id"), nullable=False
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    beschreibung: Mapped[str] = mapped_column(Text, nullable=False)
    menge: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    einheit: Mapped[str] = mapped_column(Text, nullable=False, default="Stk")
    einzelpreis: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
