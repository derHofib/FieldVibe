import uuid
from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

ABRECHNUNGSARTEN_VERTRAG = ("pauschale", "aufwand", "festpreis", "wartungsvertrag")


class Vertrag(TimestampMixin, Base):
    __tablename__ = "vertraege"
    __table_args__ = (
        CheckConstraint(
            f"abrechnungsart IN {ABRECHNUNGSARTEN_VERTRAG}",
            name="ck_vertraege_abrechnungsart_valid",
        ),
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
    anlage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("anlagen.id"), nullable=True
    )
    bezeichnung: Mapped[str] = mapped_column(Text, nullable=False)
    abrechnungsart: Mapped[str] = mapped_column(Text, nullable=False)
    konditionen: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    laufzeit_von: Mapped[date | None] = mapped_column(Date)
    laufzeit_bis: Mapped[date | None] = mapped_column(Date)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
