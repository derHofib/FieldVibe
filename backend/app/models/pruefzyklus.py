import uuid
from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, SmallInteger, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Pruefzyklus(TimestampMixin, Base):
    __tablename__ = "pruefzyklen"
    __table_args__ = (
        CheckConstraint("intervall_monate > 0", name="ck_pruefzyklen_intervall_positiv"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    anlage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("anlagen.id"), nullable=False
    )
    bezeichnung: Mapped[str] = mapped_column(Text, nullable=False)
    intervall_monate: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    letzte_pruefung_am: Mapped[date | None] = mapped_column(Date)
    naechste_pruefung_am: Mapped[date] = mapped_column(Date, nullable=False)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    offener_vorgang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=True
    )
