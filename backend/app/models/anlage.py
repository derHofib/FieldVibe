import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

ANLAGEN_OBJEKTTYPEN = ("kundenanlage", "fahrzeug", "lager", "baustelle")


class Anlage(TimestampMixin, Base):
    """objekttyp="kundenanlage" (Default): eine Anlage beim Kunden, kunde_id
    ist Pflicht. objekttyp in ("fahrzeug", "lager", "baustelle"): ein
    internes Objekt des Mandanten selbst, kunde_id bleibt leer -- diese
    Anlagen sind gleichzeitig gueltige Lagerorte (siehe
    app/models/material_bestand.py: MaterialBestand.lager_id verweist direkt
    auf anlagen.id, es gibt keine eigene Lager-Tabelle)."""

    __tablename__ = "anlagen"
    __table_args__ = (
        CheckConstraint(
            f"objekttyp IN {ANLAGEN_OBJEKTTYPEN}", name="ck_anlagen_objekttyp_valid"
        ),
        CheckConstraint(
            "(objekttyp = 'kundenanlage' AND kunde_id IS NOT NULL) "
            "OR (objekttyp != 'kundenanlage' AND kunde_id IS NULL)",
            name="ck_anlagen_kunde_id_passend_zu_objekttyp",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    kunde_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kunden.id"), nullable=True
    )
    objekttyp: Mapped[str] = mapped_column(Text, nullable=False, default="kundenanlage")
    bezeichnung: Mapped[str] = mapped_column(Text, nullable=False)
    adresse: Mapped[dict] = mapped_column(JSONB, nullable=False)
    anlagentyp: Mapped[str | None] = mapped_column(Text)
    qr_code: Mapped[str | None] = mapped_column(Text, unique=True)
    stammdaten: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    geo_lat: Mapped[float | None] = mapped_column(Float)
    geo_lng: Mapped[float | None] = mapped_column(Float)
