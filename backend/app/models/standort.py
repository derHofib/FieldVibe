import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin


class Standort(SoftDeleteMixin, TimestampMixin, Base):
    """Eigenstaendige Ebene zwischen Kunde und Anlage: ein Kunde kann mehrere
    Standorte haben (z.B. Filialen), eine Anlage haengt optional an einem
    Standort (siehe Anlage.standort_id) und ein Vorgang kann direkt einen
    Standort als Ausfuehrungsadresse referenzieren, auch ohne dass eine
    konkrete Anlage betroffen ist."""

    __tablename__ = "standorte"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    kunde_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kunden.id"), nullable=False
    )
    bezeichnung: Mapped[str] = mapped_column(Text, nullable=False)
    adresse: Mapped[dict] = mapped_column(JSONB, nullable=False)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    geo_lat: Mapped[float | None] = mapped_column(Float)
    geo_lng: Mapped[float | None] = mapped_column(Float)
    # Gesetzt, wenn ein Kunde diesen Standort selbst ueber das Kundenportal
    # angelegt hat (siehe app/api/routes/kundenportal.py) -- NULL, wenn ein
    # Mitarbeiter ihn angelegt hat.
    erstellt_von_kundenportal_zugang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kundenportal_zugaenge.id"), nullable=True
    )
