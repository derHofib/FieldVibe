import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

RECHNUNG_STATUS = ("entwurf", "versendet", "bezahlt", "storniert")


class Rechnung(TimestampMixin, Base):
    __tablename__ = "rechnungen"
    __table_args__ = (
        UniqueConstraint("mandant_id", "rechnungsnummer", name="uq_rechnungen_mandant_rechnungsnummer"),
        CheckConstraint(f"status IN {RECHNUNG_STATUS}", name="ck_rechnungen_status_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    kunde_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kunden.id"), nullable=False
    )
    vorgang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=True
    )
    rechnungsnummer: Mapped[str] = mapped_column(Text, nullable=False)
    betrag_netto: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    mwst_satz: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("19.00"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="entwurf")
    faellig_am: Mapped[date | None] = mapped_column(Date)
    erstellt_von: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    versendet_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bezahlt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
