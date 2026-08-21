import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Numeric, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin


class LeistungsverzeichnisPosition(SoftDeleteMixin, TimestampMixin, Base):
    """Kunden-eigener, optionaler Katalog wiederverwendbarer Positionen
    (Pauschalen, Stundenverrechnungssaetze, ...) -- ein Kunde kann ganz ohne
    Leistungsverzeichnis (LV) arbeiten, siehe kunde_id NOT NULL aber keine
    Pflicht, ueberhaupt Eintraege anzulegen. ist_stundensatz markiert
    Eintraege, die in der Zeiterfassung als Verrechnungssatz waehlbar sind
    (siehe Zeiterfassung.lv_position_id) -- das koppelt einen SVS mit der
    Zeiterfassung, ohne die bestehende kategorie/abrechenbar-Trennung
    (billable Feldzeit vs. rein statistische Buerozeit) anzutasten."""

    __tablename__ = "leistungsverzeichnis_positionen"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    kunde_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kunden.id"), nullable=False
    )
    bezeichnung: Mapped[str] = mapped_column(Text, nullable=False)
    einheit: Mapped[str] = mapped_column(Text, nullable=False, default="Stk")
    einzelpreis: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    ist_stundensatz: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notiz: Mapped[str | None] = mapped_column(Text)


class LeistungsverzeichnisVerwendung(Base):
    """Buchung einer LV-Position an einem Vorgang -- Gegenstueck zu
    MaterialVerwendung, aber ohne Bestandsfuehrung: eine LV-Position ist ein
    Preis-/Leistungs-Eintrag, kein physischer Lagerartikel."""

    __tablename__ = "leistungsverzeichnis_verwendungen"
    __table_args__ = (
        CheckConstraint("menge > 0", name="ck_lv_verwendungen_menge_positiv"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    lv_position_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leistungsverzeichnis_positionen.id"), nullable=False
    )
    vorgang_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=False
    )
    menge: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    verwendet_von: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
