import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

MATERIAL_BEDARF_ZWECKE = ("bestellung", "angebot")
MATERIAL_BEDARF_STATUS = ("offen", "bestellt", "in_angebot", "erhalten", "storniert")


class MaterialBedarf(TimestampMixin, Base):
    """Ein an einem Vorgang erfasster Materialbedarf, der (noch) nicht aus
    dem eigenen Bestand abgebucht wird (siehe dazu MaterialVerwendung) --
    entweder weil es beschafft werden muss (zweck="bestellung", sammelt sich
    in einer Bestellung, siehe app/models/bestellung.py) oder weil es Teil
    einer Kostenschaetzung fuer den Kunden ist (zweck="angebot", typisch bei
    Vorgaengen mit leistungstyp in ("planung", "beratung"), landet als
    Position in einem Angebot). Beide Ziele schliessen sich in der Praxis
    gegenseitig aus, daher genau ein Zweck pro Bedarf statt zwei Flags."""

    __tablename__ = "material_bedarfe"
    __table_args__ = (
        CheckConstraint("menge > 0", name="ck_material_bedarfe_menge_positiv"),
        CheckConstraint(
            f"zweck IN {MATERIAL_BEDARF_ZWECKE}", name="ck_material_bedarfe_zweck_valid"
        ),
        CheckConstraint(
            f"status IN {MATERIAL_BEDARF_STATUS}", name="ck_material_bedarfe_status_valid"
        ),
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
    vorgang_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=False
    )
    menge: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    notiz: Mapped[str | None] = mapped_column(Text)
    zweck: Mapped[str] = mapped_column(Text, nullable=False, default="bestellung")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="offen")
    # Gesetzt, sobald der Bedarf einer Bestellung bzw. einem Angebot
    # zugeordnet wurde (jeweils hoechstens eines der beiden, siehe zweck
    # oben) -- vorher NULL, waehrend der Bedarf noch offen ist.
    bestellung_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bestellungen.id"), nullable=True
    )
    angebot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("angebote.id"), nullable=True
    )
    erstellt_von: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
