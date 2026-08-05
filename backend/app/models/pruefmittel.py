import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, SmallInteger, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

PRUEFMITTEL_STATUS = ("aktiv", "defekt", "ausser_betrieb")


class Pruefmittel(SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "pruefmittel"
    __table_args__ = (
        CheckConstraint(
            "kalibrierintervall_monate > 0", name="ck_pruefmittel_intervall_positiv"
        ),
        CheckConstraint(f"status IN {PRUEFMITTEL_STATUS}", name="ck_pruefmittel_status_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    bezeichnung: Mapped[str] = mapped_column(Text, nullable=False)
    seriennummer: Mapped[str | None] = mapped_column(Text)
    zugewiesen_an: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    kalibrierintervall_monate: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    letzte_kalibrierung_am: Mapped[date | None] = mapped_column(Date)
    naechste_kalibrierung_am: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="aktiv")
