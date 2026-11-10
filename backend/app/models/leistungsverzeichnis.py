import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

LV_KALKULATIONSMODI = ("festpreis", "berechnet")


class Leistungsverzeichnis(SoftDeleteMixin, TimestampMixin, Base):
    """Container-Entitaet: buendelt Positionen (LeistungsverzeichnisPosition)
    und traegt selbst die Kunden-Zuweisung (siehe LeistungsverzeichnisKunde;
    keine Zuweisung = gilt fuer alle Kunden). Positionen kennen ihren Kunden
    nur noch indirekt ueber ihr LV -- so kann ein ganzes Leistungsverzeichnis
    per "Duplizieren" fuer einen anderen Kunden wiederverwendet werden, ohne
    jede einzelne Position neu zuzuweisen."""

    __tablename__ = "leistungsverzeichnisse"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    beschreibung: Mapped[str | None] = mapped_column(Text)


class LeistungsverzeichnisKunde(Base):
    """Many-to-many (gleiches Muster wie die fruehere positionsbezogene
    Zuordnung): ein Leistungsverzeichnis kann keinem, einem oder mehreren
    Kunden zugewiesen sein -- kein Eintrag heisst "gilt fuer alle Kunden"."""

    __tablename__ = "leistungsverzeichnis_kunden"
    __table_args__ = (
        UniqueConstraint(
            "leistungsverzeichnis_id", "kunde_id", name="uq_leistungsverzeichnis_kunden_lv_kunde"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    leistungsverzeichnis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leistungsverzeichnisse.id", ondelete="CASCADE"), nullable=False
    )
    kunde_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kunden.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class LeistungsverzeichnisPosition(SoftDeleteMixin, TimestampMixin, Base):
    """Positionen gehoeren zwingend zu einem Leistungsverzeichnis
    (leistungsverzeichnis_id) -- die Kunden-Zuweisung sitzt seit der
    LV-Container-Umstellung ausschliesslich dort, nicht mehr an der
    einzelnen Position (siehe Leistungsverzeichnis). ist_stundensatz
    markiert Eintraege, die in der Zeiterfassung als Verrechnungssatz
    waehlbar sind (siehe Zeiterfassung.lv_position_id) -- das koppelt einen
    SVS mit der Zeiterfassung, ohne die bestehende kategorie/abrechenbar-
    Trennung (billable Feldzeit vs. rein statistische Buerozeit) anzutasten.

    eltern_position_id macht eine Zeile zum Unterpunkt eines Hauptpunkts --
    bewusst nur eine Ebene tief. Ein Hauptpunkt (hat aktive Kinder) bekommt
    seinen Preis rein rechnerisch als Summe seiner Unterpunkte; eigene
    Kalkulationsfelder werden dann ignoriert (siehe app/api/routes/
    leistungsverzeichnis.py:_neu_berechnen).

    kalkulationsmodus "festpreis" (Default, bisheriges Verhalten): einzelpreis
    ist frei editierbar. "berechnet": einzelpreis/lohn_gesamt/material_gesamt
    werden serverseitig ermittelt -- Lohn zunaechst aus lohn_minuten x
    lohn_stundensatz, darauf lohn_gemeinkosten_prozent (Anteil Buero/Fahrzeug/
    Verwaltung etc.); Material aus material_posten x
    material_aufschlag_prozent wie bisher; auf die Zwischensumme aus beidem
    kommt zuletzt gewinn_wagnis_prozent (zweite, eigene Marge-Schicht) --
    siehe _berechne_eigenen_preis. Beide neuen Prozentsaetze werden bei
    Positions-Anlage aus Mandant.standard_lohn_gemeinkosten_prozent /
    Mandant.standard_gewinn_wagnis_prozent vorbefuellt, aber danach NICHT
    mehr automatisch nachgezogen, falls sich der Mandant-Default spaeter
    aendert -- sonst wuerden sich bereits kalkulierte/angebotene Preise
    rueckwirkend und unbemerkt veraendern."""

    __tablename__ = "leistungsverzeichnis_positionen"
    __table_args__ = (
        CheckConstraint(
            f"kalkulationsmodus IN {LV_KALKULATIONSMODI}",
            name="ck_leistungsverzeichnis_positionen_kalkulationsmodus_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    leistungsverzeichnis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leistungsverzeichnisse.id", ondelete="CASCADE"), nullable=False
    )
    eltern_position_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leistungsverzeichnis_positionen.id", ondelete="CASCADE"), nullable=True
    )
    bezeichnung: Mapped[str] = mapped_column(Text, nullable=False)
    einheit: Mapped[str] = mapped_column(Text, nullable=False, default="Stk")
    # Frei editierbar im Modus "festpreis" -- im Modus "berechnet" oder mit
    # Kindern serverseitig gepflegt, siehe Klassen-Docstring.
    einzelpreis: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    ist_stundensatz: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notiz: Mapped[str | None] = mapped_column(Text)

    kalkulationsmodus: Mapped[str] = mapped_column(Text, nullable=False, default="festpreis")
    lohn_minuten: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lohn_stundensatz: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    # Gemeinkosten-Zuschlag auf den Lohnanteil (Buero/Fahrzeug/Verwaltung
    # etc.) -- gleiches Prinzip wie material_aufschlag_prozent, nur fuer die
    # Lohnseite statt der Materialseite.
    lohn_gemeinkosten_prozent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    # Liste von {bezeichnung, menge, einzelpreis, material_id} -- gleiches
    # Prinzip wie ProjektAufgabe.checkliste, komplett ersetzt statt einzeln
    # bearbeitet.
    material_posten: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    material_aufschlag_prozent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    # Zweite, eigene Marge-Schicht auf die Zwischensumme aus Lohn (inkl.
    # Gemeinkosten) und Material (inkl. Aufschlag) -- siehe Klassen-Docstring.
    gewinn_wagnis_prozent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    lohn_gesamt: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    material_gesamt: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))


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
