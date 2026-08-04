import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, SmallInteger, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

PRUEFZYKLUS_EINHEITEN = ("tag", "monat", "stunde")


class Pruefzyklus(TimestampMixin, Base):
    """intervall_wert/intervall_einheit ersetzen ein frueheres, fest auf
    Monate begrenztes intervall_monate -- damit lassen sich auch kurze
    Pruefintervalle (z.B. "alle 48 Stunden") abbilden. Deshalb sind
    letzte_pruefung_am/naechste_pruefung_am volle Zeitstempel statt reiner
    Datumswerte (siehe app.services.date_utils.add_intervall)."""

    __tablename__ = "pruefzyklen"
    __table_args__ = (
        CheckConstraint("intervall_wert > 0", name="ck_pruefzyklen_intervall_positiv"),
        CheckConstraint(
            f"intervall_einheit IN {PRUEFZYKLUS_EINHEITEN}", name="ck_pruefzyklen_einheit_valid"
        ),
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
    intervall_wert: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    intervall_einheit: Mapped[str] = mapped_column(Text, nullable=False, default="monat")
    letzte_pruefung_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    naechste_pruefung_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    offener_vorgang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=True
    )
