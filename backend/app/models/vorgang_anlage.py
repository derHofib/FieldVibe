import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VorgangAnlage(Base):
    """Weitere Anlagen an einem Vorgang, zusaetzlich zur einzelnen
    Vorgang.anlage_id (der "Haupt-Anlage") -- v.a. wenn beim Anlegen ueber
    einen Standort mehrere Anlagen automatisch mit uebernommen werden
    (siehe app/api/routes/vorgaenge.py). Reine Zuordnungstabelle ohne
    eigene Sichtbarkeit -- kein Papierkorb-Eintrag, kein SoftDeleteMixin;
    ON DELETE CASCADE raeumt beim endgueltigen Loeschen von Vorgang oder
    Anlage automatisch auf."""

    __tablename__ = "vorgang_anlagen"

    vorgang_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id", ondelete="CASCADE"), primary_key=True
    )
    anlage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("anlagen.id", ondelete="CASCADE"), primary_key=True
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
