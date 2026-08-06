import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

EINGANGSRECHNUNG_STATUS = ("offen", "bezahlt", "storniert")
EINGANGSRECHNUNG_KATEGORIEN = (
    "wareneinkauf",
    "betriebskosten",
    "miete",
    "personal",
    "fahrzeug",
    "versicherung",
    "sonstiges",
)


class Eingangsrechnung(SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "eingangsrechnungen"
    __table_args__ = (
        CheckConstraint(f"status IN {EINGANGSRECHNUNG_STATUS}", name="ck_eingangsrechnungen_status_valid"),
        CheckConstraint(
            f"kategorie IS NULL OR kategorie IN {EINGANGSRECHNUNG_KATEGORIEN}",
            name="ck_eingangsrechnungen_kategorie_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    lieferant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lieferanten.id"), nullable=True
    )
    # Schnappschuss des Lieferantennamens zum Erfassungszeitpunkt -- erlaubt
    # Anzeige ohne Join und ist Pflicht auch dann, wenn der Aussteller (noch)
    # kein eigener Lieferanten-Stammdatensatz ist (z.B. einmalige Betriebs-
    # kosten-Rechnung), also lieferant_id NULL bleibt.
    lieferant_name: Mapped[str] = mapped_column(Text, nullable=False)
    vorgang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=True
    )
    # Vom Aussteller vergebene Nummer -- reine Freitexteingabe, anders als bei
    # Rechnung.rechnungsnummer keine eigene Vergabe durch numbering_service.
    rechnungsnummer_lieferant: Mapped[str] = mapped_column(Text, nullable=False)
    rechnungsdatum: Mapped[date] = mapped_column(Date, nullable=False)
    # Datum der eigenen Erfassung -- kann vom Rechnungsdatum abweichen und ist
    # fuer die GoBD-Nachvollziehbarkeit relevant (wann wurde der Beleg erfasst).
    eingegangen_am: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    faellig_am: Mapped[date | None] = mapped_column(Date)
    betrag_netto: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    mwst_satz: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("19.00"))
    # Skonto (Kreditorenbuchhaltung): Prozentsatz + Frist in Tagen ab
    # rechnungsdatum, innerhalb der der Abzug gilt. Beide optional -- viele
    # Eingangsbelege (Miete, Versicherung, ...) kennen kein Skonto.
    skonto_prozent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    skonto_tage: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    kategorie: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="offen")
    bezahlt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Unveraenderliches Abbild des hochgeladenen Belegs (S3/MinIO-Objekt-
    # schluessel) -- der eigentliche Nachweis, den GoBD unveraendert
    # aufbewahrt verlangt; die Metadaten um ihn herum bleiben normal
    # korrigierbar, solange status == "offen".
    beleg_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    notiz: Mapped[str | None] = mapped_column(Text)
    erstellt_von: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )


class EingangsrechnungPosition(Base):
    __tablename__ = "eingangsrechnung_positionen"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    eingangsrechnung_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("eingangsrechnungen.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    beschreibung: Mapped[str] = mapped_column(Text, nullable=False)
    menge: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("1"))
    einheit: Mapped[str] = mapped_column(Text, nullable=False, default="Stk")
    einzelpreis: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))


class EingangsrechnungZahlung(Base):
    """Buchungsprotokoll fuer Teilzahlungen -- rein additiv (kein Update/
    Delete), analog zu MaterialBewegung: eine Zahlung ist ein Ereignis mit
    eigenem Zeitstempel, keine nachtraeglich editierbare Belegzeile wie
    EingangsrechnungPosition."""

    __tablename__ = "eingangsrechnung_zahlungen"
    __table_args__ = (
        CheckConstraint("betrag > 0", name="ck_eingangsrechnung_zahlungen_betrag_positiv"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    eingangsrechnung_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("eingangsrechnungen.id", ondelete="CASCADE"), nullable=False
    )
    betrag: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    datum: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    erstellt_von: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
