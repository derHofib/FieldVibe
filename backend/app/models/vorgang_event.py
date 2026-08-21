import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

EVENT_TYPEN = (
    "kommentar",
    "status_change",
    "foto",
    "dokument",
    "mangel",
    "angebot",
    "material",
    "zeit_start",
    "zeit_stop",
    "termin",
    "rechnung_status",
    "system",
    "unterschrift",
    "eingangsrechnung_status",
    "formular",
    "leistung",
)


class VorgangEvent(Base):
    __tablename__ = "vorgang_events"
    __table_args__ = (
        CheckConstraint(f"event_type IN {EVENT_TYPEN}", name="ck_vorgang_events_event_type_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    vorgang_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    kundensichtbar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    body: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    ref_entity_type: Mapped[str | None] = mapped_column(Text)
    ref_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    client_uuid: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
