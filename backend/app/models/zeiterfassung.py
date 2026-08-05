import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Zeiterfassung(TimestampMixin, Base):
    __tablename__ = "zeiterfassung"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    vorgang_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=False
    )
    techniker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ende_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    taetigkeit: Mapped[str | None] = mapped_column(Text)
    abrechenbar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    freigegeben: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
