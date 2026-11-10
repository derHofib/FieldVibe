import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

BOARD_TYPEN = ("frei", "bauplanung", "prozess")


class Board(TimestampMixin, Base):
    """Ein Miro-artiges Whiteboard fuer die Office-Oberflaeche. inhalt_json
    traegt den kompletten Canvas-Zustand (Notizen, Formen, Verbindungen,
    Positionen, Viewport) als ein JSON-Baum -- analog zu
    GespeicherterFilter.filter_json, kein normalisiertes Element-Schema, weil
    der Inhalt ohnehin frei bleibt (siehe app/api/routes/boards.py)."""

    __tablename__ = "boards"
    __table_args__ = (
        CheckConstraint(f"board_typ IN {BOARD_TYPEN}", name="ck_boards_board_typ_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    board_typ: Mapped[str] = mapped_column(Text, nullable=False, default="frei")
    inhalt_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    hintergrund_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    erstellt_von: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
