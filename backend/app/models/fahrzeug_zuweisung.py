import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin


class FahrzeugZuweisung(SoftDeleteMixin, TimestampMixin, Base):
    """Weist einem Techniker sein aktuelles Fahrzeug zu (eine Anlage mit
    objekttyp="fahrzeug") -- pro Techniker hoechstens eine gleichzeitig,
    ein Fahrzeug kann aber mehreren Technikern zugewiesen sein (Schicht-
    betrieb/geteiltes Fahrzeug). Bestimmt den vorgeschlagenen Standard-
    Lagerort beim Material-Verbrauch (siehe frontend VorgangDetailPage)."""

    __tablename__ = "fahrzeug_zuweisungen"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    # Eindeutigkeit gilt nur unter den aktiven Zuweisungen (partial unique
    # index "uq_fahrzeug_zuweisungen_user_aktiv", siehe Migration 0032) --
    # eine weich geloeschte Zuweisung darf eine Neuanlage fuer denselben
    # Techniker nicht blockieren.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    anlage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("anlagen.id"), nullable=False
    )
