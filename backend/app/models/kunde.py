import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

KUNDE_TYPEN = ("privat", "gewerbe", "oeffentlich", "hausverwaltung")


class Kunde(TimestampMixin, Base):
    __tablename__ = "kunden"
    __table_args__ = (
        UniqueConstraint("mandant_id", "kundennummer", name="uq_kunden_mandant_kundennummer"),
        CheckConstraint(f"typ IS NULL OR typ IN {KUNDE_TYPEN}", name="ck_kunden_typ_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    kundennummer: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    typ: Mapped[str | None] = mapped_column(Text)
    ansprechpartner: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    adresse: Mapped[dict | None] = mapped_column(JSONB)
    notiz: Mapped[str | None] = mapped_column(Text)
