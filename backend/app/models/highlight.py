import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Highlight(Base):
    __tablename__ = "highlights"
    __table_args__ = (
        UniqueConstraint("vorgang_event_id", name="uq_highlights_vorgang_event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    vorgang_event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("vorgang_events.id", ondelete="CASCADE"), nullable=False
    )
    titel: Mapped[str | None] = mapped_column(Text)
    erstellt_von: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
