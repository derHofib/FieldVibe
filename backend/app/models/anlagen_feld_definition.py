import uuid

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

ANLAGEN_FELD_TYPEN = ("text", "zahl", "datum")


class AnlagenFeldDefinition(TimestampMixin, Base):
    """Ein vom Mandant-Admin definiertes Zusatzfeld fuer einen bestimmten
    Anlagentyp (freier Text wie "Fahrzeug", "Ladestation", "Elektroanlage" --
    derselbe Wert, den Anlage.anlagentyp traegt). Das Anlage-Formular zeigt
    fuer den gewaehlten Anlagentyp automatisch genau diese Felder an; die
    Werte landen in Anlage.stammdaten unter dem jeweiligen feld_name als
    Schluessel -- so muss fuer ein neues Zusatzfeld keine Migration
    geschrieben werden."""

    __tablename__ = "anlagen_feld_definitionen"
    __table_args__ = (
        UniqueConstraint(
            "mandant_id", "anlagentyp", "feld_name", name="uq_anlagen_feld_def_mandant_typ_name"
        ),
        CheckConstraint(f"feld_typ IN {ANLAGEN_FELD_TYPEN}", name="ck_anlagen_feld_def_typ_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    anlagentyp: Mapped[str] = mapped_column(Text, nullable=False)
    feld_name: Mapped[str] = mapped_column(Text, nullable=False)
    feld_typ: Mapped[str] = mapped_column(Text, nullable=False, default="text")
    reihenfolge: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
