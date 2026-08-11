import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

RECHNUNG_STATUS = ("entwurf", "versendet", "teilweise_bezahlt", "bezahlt", "storniert")
RECHNUNG_ZAHLUNGSARTEN = ("ueberweisung", "bar", "karte", "lastschrift", "sonstiges")


class Rechnung(SoftDeleteMixin, TimestampMixin, Base):
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
    # Zeitpunkt der Leistung/Lieferung (§14 Abs. 4 Nr. 6 UStG) -- kann vom
    # Rechnungsdatum abweichen (z.B. Rechnung erst Tage nach Auftragsende).
    leistungsdatum: Mapped[date | None] = mapped_column(Date, nullable=True)
    betrag_netto: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    mwst_satz: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("19.00"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="entwurf")
    faellig_am: Mapped[date | None] = mapped_column(Date)
    erstellt_von: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    versendet_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bezahlt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Mahnwesen (Nacharbeit): 0 = keine Mahnung, steigt mit jedem Eskalations-
    # Lauf des Workers fuer weiterhin ueberfaellige, unbezahlte Rechnungen.
    mahnstufe: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    letzte_mahnung_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # True auf dem Storno-Beleg selbst (negative Positionen, storniert eine
    # andere Rechnung) -- nie auf der urspruenglichen Rechnung gesetzt.
    ist_storno: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Nur auf dem Storno-Beleg gesetzt: welche Rechnung er stornoriert. GoBD
    # verbietet, eine einmal versendete Rechnung zu aendern oder zu loeschen
    # -- die Korrektur braucht einen eigenen, referenzierten Gegenbeleg statt
    # eines simplen Status-Flips (siehe rechnung_service.erstelle_stornorechnung).
    storniert_rechnung_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rechnungen.id"), nullable=True
    )
    # Unveraenderliches Abbild des tatsaechlich versendeten PDFs (S3/MinIO-
    # Objektschluessel) -- ab dem Versand-Zeitpunkt archiviert statt bei
    # jedem Abruf neu erzeugt, damit spaetere Aenderungen an Firmendaten/Logo
    # das bereits verschickte Dokument nicht nachtraeglich veraendern.
    pdf_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Analog zu pdf_object_key: die zum Versand-Zeitpunkt eingebettete
    # ZUGFeRD-XML wird zusaetzlich einzeln archiviert, damit sie auch ohne
    # das PDF abrufbar ist (siehe GET /rechnungen/{id}/xml). NULL, wenn
    # E-Rechnung fuer den Mandanten nicht aktiv war oder die
    # EN16931-Vollstaendigkeitspruefung zum Versand-Zeitpunkt fehlschlug --
    # in beiden Faellen wurde stillschweigend nur ein normales PDF erzeugt.
    xml_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)


class RechnungPosition(Base):
    __tablename__ = "rechnung_positionen"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    rechnung_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rechnungen.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    beschreibung: Mapped[str] = mapped_column(Text, nullable=False)
    menge: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("1"))
    einheit: Mapped[str] = mapped_column(Text, nullable=False, default="Stk")
    einzelpreis: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)


class RechnungZahlung(Base):
    """Buchungsprotokoll fuer Zahlungseingaenge -- rein additiv (kein Update/
    Delete auf einer Zeile), analog zu EingangsrechnungZahlung/MaterialBewegung:
    eine Zahlung ist ein Ereignis mit eigenem Zeitstempel, keine nachtraeglich
    editierbare Belegzeile. Zahlungen sind Bewegungsdaten, kein Belegtinhalt --
    sie duerfen daher auch nach dem GoBD-Versandzeitpunkt der Rechnung
    hinzukommen, ohne das archivierte PDF zu beruehren (siehe
    rechnung_service.archiviere_pdf/pdf_bytes_fuer, die nur betrag_netto/
    mwst_satz/Positionen lesen).

    Abweichend von EingangsrechnungZahlung (dort betrag > 0): hier
    betrag <> 0, weil eine Fehlbuchung als negative Gegenbuchung mit
    storniert_zahlung_id korrigiert wird statt geloescht/geaendert zu werden --
    Ruecklastschriften und Fehlerfassungen sind auf der Debitorenseite real."""

    __tablename__ = "rechnung_zahlungen"
    __table_args__ = (
        CheckConstraint("betrag <> 0", name="ck_rechnung_zahlungen_betrag_nicht_null"),
        CheckConstraint(
            f"zahlungsart IS NULL OR zahlungsart IN {RECHNUNG_ZAHLUNGSARTEN}",
            name="ck_rechnung_zahlungen_zahlungsart_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    rechnung_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rechnungen.id", ondelete="CASCADE"), nullable=False
    )
    betrag: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # Frei waehlbar (nicht zwingend "heute") -- das ist der Kernpunkt: ein
    # Kontoauszug von letzter Woche muss rueckdatiert buchbar sein.
    datum: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    zahlungsart: Mapped[str | None] = mapped_column(Text, nullable=True)
    notiz: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Nur auf der Gegenbuchung gesetzt: welche Zahlung sie korrigiert.
    storniert_zahlung_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rechnung_zahlungen.id"), nullable=True
    )
    erstellt_von: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
