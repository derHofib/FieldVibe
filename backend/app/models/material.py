import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

MATERIAL_BEWEGUNG_TYPEN = ("eingang", "umlagerung", "verwendung", "korrektur")


class Material(TimestampMixin, Base):
    """Der tatsaechliche Bestand liegt nicht mehr hier, sondern verteilt auf
    Lagerorte (siehe MaterialBestand) -- Material selbst beschreibt nur noch
    den Artikel (Bezeichnung, Einheit, Mindestbestand, Preis)."""

    __tablename__ = "material"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    bezeichnung: Mapped[str] = mapped_column(Text, nullable=False)
    einheit: Mapped[str] = mapped_column(Text, nullable=False, default="Stk")
    mindestbestand: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    einzelpreis: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))


class MaterialBestand(TimestampMixin, Base):
    """Bestand eines Materials an einem bestimmten Lagerort. Lagerort ist
    keine eigene Tabelle, sondern eine Anlage mit objekttyp in
    ("fahrzeug", "lager", "baustelle") -- siehe app/models/anlage.py."""

    __tablename__ = "material_bestand"
    __table_args__ = (
        CheckConstraint("menge >= 0", name="ck_material_bestand_menge_nicht_negativ"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("material.id", ondelete="CASCADE"), nullable=False
    )
    lager_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("anlagen.id"), nullable=False
    )
    menge: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))


class MaterialBewegung(Base):
    """Buchungsprotokoll fuer jede Bestandsaenderung -- Wareneingang,
    Umlagerung zwischen zwei Lagerorten, Verwendung in einem Vorgang oder
    manuelle Korrektur. Rein additiv (kein Update/Delete), damit sich der
    Bestand eines Lagerorts jederzeit nachvollziehen laesst."""

    __tablename__ = "material_bewegungen"
    __table_args__ = (
        CheckConstraint("menge > 0", name="ck_material_bewegungen_menge_positiv"),
        CheckConstraint(
            f"typ IN {MATERIAL_BEWEGUNG_TYPEN}", name="ck_material_bewegungen_typ_valid"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("material.id", ondelete="CASCADE"), nullable=False
    )
    typ: Mapped[str] = mapped_column(Text, nullable=False)
    von_lager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("anlagen.id"), nullable=True
    )
    nach_lager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("anlagen.id"), nullable=True
    )
    menge: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    vorgang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=True
    )
    erstellt_von: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


class MaterialVerwendung(Base):
    __tablename__ = "material_verwendungen"
    __table_args__ = (
        CheckConstraint("menge > 0", name="ck_material_verwendungen_menge_positiv"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("material.id"), nullable=False
    )
    lager_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("anlagen.id"), nullable=False
    )
    vorgang_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=False
    )
    menge: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    verwendet_von: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
