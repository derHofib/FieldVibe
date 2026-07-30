import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DauerauftragZiel(TimestampMixin, Base):
    """Ein einzelnes Ziel innerhalb eines Dauerauftrag-Buendels: entweder eine
    bestimmte Anlage des Kunden (anlage_id gesetzt) oder der Kunde direkt
    ohne Anlagenbezug (anlage_id NULL, hoechstens ein solches Ziel je
    Dauerauftrag). Jedes Ziel hat seinen eigenen Faelligkeits-/Offen-Zyklus,
    der unabhaengig von den anderen Zielen desselben Dauerauftrags weiterlaeuft."""

    __tablename__ = "dauerauftrag_ziele"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    dauerauftrag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dauerauftraege.id", ondelete="CASCADE"), nullable=False
    )
    anlage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("anlagen.id"), nullable=True
    )
    naechste_faelligkeit_am: Mapped[date] = mapped_column(Date, nullable=False)
    offener_vorgang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=True
    )
