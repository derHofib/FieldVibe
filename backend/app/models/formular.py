import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

FORMULARFELD_TYPEN = (
    "text",
    "textarea",
    "zahl",
    "datum",
    "dropdown",
    "mehrfachauswahl",
    "ja_nein",
    "bewertung",
    "foto",
    "unterschrift",
    "gps",
    "qr_scan",
    "abschnitt",
)
# Feldtypen ohne echten Antwortwert -- reine Gliederung, wird beim
# Pflichtfeld-Check und beim PDF-Export wie eine Zwischenueberschrift
# behandelt statt wie eine Frage.
FORMULARFELD_TYPEN_OHNE_ANTWORT = ("abschnitt",)

# Feste Spaltenanzahl des Raster-Layouts im Formular-Editor/PDF-Export --
# projektweit fix (nicht pro Formular konfigurierbar), nur die Zeilenhoehe
# ist einstellbar (siehe Formular.zeilenhoehe_mm).
GRID_SPALTEN = 12

# Vokabular fuer Formularfeld.datenquelle -- optionale Bindung eines Felds an
# einen Wert des Vorgangs/Kunde/Anlage/Standort, der beim Start einer
# Ausfuellung automatisch als Antwort vorbelegt wird (siehe
# formular_service.auto_fill_werte). Nur fuer feld_typ in
# FORMULARFELD_TYPEN_MIT_DATENQUELLE zulaessig -- dropdown ist bewusst
# ausgeschlossen, da ein aufgeloester Wert nicht zwingend in den definierten
# Auswahlwerten (optionen.werte) enthalten ist.
FORMULARFELD_DATENQUELLEN = (
    "vorgang.vorgangsnummer",
    "vorgang.titel",
    "vorgang.beschreibung",
    "vorgang.leistungstyp",
    "vorgang.faelligkeit_am",
    "vorgang.adresse",
    "vorgang.zugewiesener_name",
    "kunde.kundennummer",
    "kunde.name",
    "kunde.adresse",
    "kunde.ansprechpartner",
    "anlage.bezeichnung",
    "anlage.adresse",
    "anlage.hersteller",
    "anlage.modell",
    "anlage.seriennummer",
    "anlage.anlagentyp",
    "standort.bezeichnung",
    "standort.adresse",
)
FORMULARFELD_TYPEN_MIT_DATENQUELLE = ("text", "textarea", "zahl", "datum")


class Formular(TimestampMixin, Base):
    """Vom mandant_admin im Baukasten erstellte Formular-Vorlage (z.B.
    "Wartungsprotokoll Heizung", "Abnahme-Checkliste"). Wird ueber
    FormularAuftragstypZuordnung an Leistungstypen gebunden und am Vorgang
    beliebig oft ausgefuellt (siehe VorgangFormular). Vorlagen werden nie
    hart geloescht (nur aktiv=false gesetzt), da bereits ausgefuellte
    VorgangFormular-Eintraege per FK auf sie zeigen."""

    __tablename__ = "formulare"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    beschreibung: Mapped[str | None] = mapped_column(Text)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    erstellt_von: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # Hoehe einer Rasterzeile im Canvas-Editor/PDF-Export in mm -- die
    # Spaltenanzahl ist projektweit fix (GRID_SPALTEN), nur die Zeilenhoehe
    # ist pro Formular einstellbar (UI bietet Presets fein/mittel/grob an,
    # gespeichert wird immer der Rohwert in mm).
    zeilenhoehe_mm: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=8)

    __table_args__ = (
        CheckConstraint(
            "zeilenhoehe_mm BETWEEN 4 AND 20", name="ck_formulare_zeilenhoehe_valid"
        ),
    )


class Formularfeld(Base):
    """Ein Baustein einer Formular-Vorlage, positioniert auf einem Raster
    mit fester Spaltenanzahl (GRID_SPALTEN) und variabler Zeilenhoehe (siehe
    Formular.zeilenhoehe_mm). raster_zeile/raster_spalte ist die obere linke
    Ecke, raster_breite/raster_hoehe der Colspan/Rowspan. reihenfolge bleibt
    als serverseitig abgeleiteter Cache erhalten (neu berechnet aus
    (raster_zeile, raster_spalte) bei jeder Positionsaenderung, siehe
    app/api/routes/formulare.py:update_formularfeld_positionen) --
    bestehende Consumer der Spalte (z.B. Snapshots) bleiben dadurch
    unangetastet. optionen transportiert je feld_typ unterschiedliche
    Zusatzangaben: bei dropdown/mehrfachauswahl die Auswahlwerte
    ({"werte": [...]}), bei bewertung die Skala ({"min": 1, "max": 5}).
    datenquelle bindet ein Feld optional an einen Vorgangs-/Kunden-/Anlagen-/
    Standort-Wert, der beim Start einer Ausfuellung automatisch als Antwort
    vorbelegt wird (siehe formular_service.auto_fill_werte) -- bleibt dabei
    weiterhin vom Techniker ueberschreibbar."""

    __tablename__ = "formularfelder"
    __table_args__ = (
        CheckConstraint(
            f"feld_typ IN {FORMULARFELD_TYPEN}", name="ck_formularfelder_feld_typ_valid"
        ),
        CheckConstraint(
            f"datenquelle IS NULL OR datenquelle IN {FORMULARFELD_DATENQUELLEN}",
            name="ck_formularfelder_datenquelle_valid",
        ),
        CheckConstraint(
            "raster_spalte BETWEEN 0 AND 11", name="ck_formularfelder_raster_spalte_valid"
        ),
        CheckConstraint(
            "raster_breite BETWEEN 1 AND 12", name="ck_formularfelder_raster_breite_valid"
        ),
        CheckConstraint("raster_hoehe >= 1", name="ck_formularfelder_raster_hoehe_valid"),
        CheckConstraint(
            "raster_spalte + raster_breite <= 12", name="ck_formularfelder_raster_passt_in_zeile"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    formular_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("formulare.id", ondelete="CASCADE"), nullable=False
    )
    feld_typ: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    hilfetext: Mapped[str | None] = mapped_column(Text)
    pflichtfeld: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reihenfolge: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    optionen: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    raster_zeile: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    raster_spalte: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    raster_breite: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=12)
    raster_hoehe: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    datenquelle: Mapped[str | None] = mapped_column(Text, nullable=True)


class FormularAuftragstypZuordnung(Base):
    """Ordnet ein Formular einem Leistungstyp zu (siehe LEISTUNGSTYPEN in
    app/models/vorgang.py) -- ein Formular kann fuer mehrere Leistungstypen
    gelten, ein Leistungstyp kann mehrere Formulare haben (z.B. Checkliste
    UND Abnahmeprotokoll bei "installation")."""

    __tablename__ = "formular_auftragstyp_zuordnungen"
    __table_args__ = (
        UniqueConstraint(
            "formular_id", "leistungstyp", name="uq_formular_auftragstyp_zuordnung"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    formular_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("formulare.id", ondelete="CASCADE"), nullable=False
    )
    leistungstyp: Mapped[str] = mapped_column(Text, nullable=False)
    # Blockiert das Abschliessen/Schliessen des Vorgangs, solange dieses
    # Formular an ihm noch nicht mindestens einmal abgeschlossen wurde --
    # ausgewertet in app/services/vorgang_service.py analog zum bestehenden
    # Pruefzyklus-Pflicht-Check.
    pflicht_vor_abschluss: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class VorgangFormular(TimestampMixin, Base):
    """Eine konkrete Ausfuellung eines Formulars an einem Vorgang. Ein
    Formular darf am selben Vorgang mehrfach ausgefuellt werden (z.B. ein
    Wartungsprotokoll pro Besuch). formular_snapshot friert die
    Felddefinitionen zum Startzeitpunkt ein, damit spaetere Aenderungen an
    der Formular-Vorlage bereits abgeschlossene Ausfuellungen nicht
    nachtraeglich veraendern -- dieselbe Snapshot-Idee wie bei
    Pruefzyklus.letzter_wert, nur fuer eine ganze Feldliste statt eines
    einzelnen Werts."""

    __tablename__ = "vorgang_formulare"
    __table_args__ = (
        CheckConstraint(
            "status IN ('offen', 'abgeschlossen')", name="ck_vorgang_formulare_status_valid"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    vorgang_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id", ondelete="CASCADE"), nullable=False
    )
    formular_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("formulare.id"), nullable=False
    )
    formular_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    antworten: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="offen")
    ausgefuellt_von: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    kundensichtbar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    abgeschlossen_am: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
