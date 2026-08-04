import uuid
from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

ANLAGEN_OBJEKTTYPEN = ("kundenanlage", "fahrzeug", "lager", "baustelle")


class Anlage(SoftDeleteMixin, TimestampMixin, Base):
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
    # Optional: eine Anlage kann, muss aber nicht einem Standort zugeordnet
    # sein (siehe app/models/standort.py) -- Bestandsanlagen ohne Standort
    # bleiben gueltig.
    standort_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("standorte.id"), nullable=True
    )
    objekttyp: Mapped[str] = mapped_column(Text, nullable=False, default="kundenanlage")
    bezeichnung: Mapped[str] = mapped_column(Text, nullable=False)
    adresse: Mapped[dict] = mapped_column(JSONB, nullable=False)
    anlagentyp: Mapped[str | None] = mapped_column(Text)
    qr_code: Mapped[str | None] = mapped_column(Text, unique=True)
    # Universelle Beschreibungsfelder, unabhaengig vom konkreten Anlagentyp
    # (Fahrzeug, Ladestation, Geraet, ...) -- fuer alles Typ-Spezifische
    # siehe stammdaten unten, befuellt anhand von AnlagenFeldDefinition.
    hersteller: Mapped[str | None] = mapped_column(Text)
    modell: Mapped[str | None] = mapped_column(Text)
    seriennummer: Mapped[str | None] = mapped_column(Text)
    anschaffungsdatum: Mapped[date | None] = mapped_column(Date)
    notiz: Mapped[str | None] = mapped_column(Text)
    # Werte der mandantenkonfigurierbaren Zusatzfelder je Anlagentyp (siehe
    # app/models/anlagen_feld_definition.py), als {feld_name: wert}. Bewusst
    # ohne eigenes Schema/Migration pro neuem Feld -- die Definitionen selbst
    # geben Namen/Typ vor, hier liegen nur die Werte.
    stammdaten: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    geo_lat: Mapped[float | None] = mapped_column(Float)
    geo_lng: Mapped[float | None] = mapped_column(Float)
    # Inaktive Anlagen stehen beim Anlegen eines neuen Vorgangs nicht mehr
    # zur Auswahl (siehe _validate_references in vorgaenge.py), bleiben aber
    # an bestehenden Vorgaengen/Vertraegen weiter gueltig verknuepft.
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    erstellt_von_kundenportal_zugang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kundenportal_zugaenge.id"), nullable=True
    )
