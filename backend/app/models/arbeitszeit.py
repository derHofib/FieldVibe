import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Reihenfolge = date.weekday() (Montag = 0); der Service greift darueber auf
# die Spalten stunden_mo..stunden_so zu.
ARBEITSZEIT_WOCHENTAG_SPALTEN = (
    "stunden_mo",
    "stunden_di",
    "stunden_mi",
    "stunden_do",
    "stunden_fr",
    "stunden_sa",
    "stunden_so",
)


class ArbeitszeitSoll(Base):
    """Soll-Arbeitszeit je Mitarbeiter und Wochentag. Eine Zeile gilt ab
    gueltig_ab bis zur naechsten Zeile desselben Mitarbeiters -- Aenderungen
    wirken so nie rueckwirkend (siehe docs/konzepte/ZEITERFASSUNG.md)."""

    __tablename__ = "arbeitszeit_soll"
    __table_args__ = (
        UniqueConstraint("mandant_id", "user_id", "gueltig_ab", name="uq_arbeitszeit_soll_user_gueltig_ab"),
        *(
            CheckConstraint(f"{spalte} >= 0 AND {spalte} <= 24", name=f"ck_arbeitszeit_soll_{spalte}_valid")
            for spalte in ARBEITSZEIT_WOCHENTAG_SPALTEN
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    gueltig_ab: Mapped[date] = mapped_column(Date, nullable=False)
    stunden_mo: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=Decimal("0"))
    stunden_di: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=Decimal("0"))
    stunden_mi: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=Decimal("0"))
    stunden_do: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=Decimal("0"))
    stunden_fr: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=Decimal("0"))
    stunden_sa: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=Decimal("0"))
    stunden_so: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Feiertag(Base):
    """Feiertag eines Mandanten. Per Service aus Bundesland+Jahr erzeugt, danach
    wie jede andere Zeile bearbeitbar (manuell ergaenzen/loeschen)."""

    __tablename__ = "feiertage"
    __table_args__ = (UniqueConstraint("mandant_id", "datum", name="uq_feiertage_mandant_datum"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    datum: Mapped[date] = mapped_column(Date, nullable=False)
    bezeichnung: Mapped[str] = mapped_column(Text, nullable=False)
