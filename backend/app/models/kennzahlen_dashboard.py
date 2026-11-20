import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class KennzahlenDashboard(TimestampMixin, Base):
    """Ein vom Nutzer zusammengestelltes Kennzahlen-Dashboard (Layout = Zeitraum
    + Widget-Liste als JSONB, Schema in app/schemas/kennzahlen.py). Persoenlich;
    mit fuer_alle sehen es alle Nutzer des Mandanten, aendern darf es weiter nur
    die Ersteller-Person."""

    __tablename__ = "kennzahlen_dashboards"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_kennzahlen_dashboards_user_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    layout: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    fuer_alle: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Schluessel der Systemvorlage, aus der kopiert wurde (nur Herkunft, keine Verknuepfung).
    vorlage: Mapped[str | None] = mapped_column(Text)
    sortierung: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
