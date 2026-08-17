import uuid

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BelegZaehler(Base):
    """Atomarer Nummernkreis je Mandant + Belegart (z.B. "rechnung"),
    ersetzt einen COUNT(*)-basierten Ansatz: zwei parallele Anfragen
    koennten sonst dieselbe naechste_nummer lesen und beide denselben
    Belegnamen vergeben wollen. naechste_nummer wird ausschliesslich per
    atomarem INSERT ... ON CONFLICT DO UPDATE ... RETURNING erhoeht (siehe
    app/services/numbering_service.py), nie per SELECT+UPDATE -- das macht
    die Vergabe unter Nebenlaeufigkeit race-frei, ohne eine explizite Zeilen-
    Sperre zu brauchen."""

    __tablename__ = "beleg_zaehler"

    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), primary_key=True
    )
    belegart: Mapped[str] = mapped_column(Text, primary_key=True)
    naechste_nummer: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
