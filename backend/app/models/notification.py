import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

NOTIFICATION_TYPEN = ("mention", "frist", "zuweisung", "angebot")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    typ: Mapped[str] = mapped_column(Text, nullable=False)
    titel: Mapped[str] = mapped_column(Text, nullable=False)
    ref_entity_type: Mapped[str | None] = mapped_column(Text)
    ref_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    gelesen_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
