import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
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

# Feste Spaltenanzahl des ALTEN Raster-Layouts (snapshot_version 2) --
# wird nur noch fuer bereits abgeschlossene VorgangFormular-Snapshots
# gebraucht, die vor der Umstellung auf freie Positionierung (siehe
# Formularfeld.x_mm/y_mm/breite_mm/hoehe_mm) erzeugt wurden. Neue Formulare
# verwenden dieses Raster nicht mehr -- NICHT fuer neuen Code verwenden.
GRID_SPALTEN = 12

# Nutzbare Breite einer A4-Seite in mm (210mm Seitenbreite minus 15mm Rand
# links/rechts, siehe _FORMULAR_RAND_LR in app/services/pdf_service.py) --
# Obergrenze fuer x_mm + breite_mm eines frei positionierten Formularfelds.
NUTZBARE_BREITE_MM = 180

# Nutzbare Hoehe je Seite in mm: 297mm A4-Hoehe minus unterer Rand
# (_FORMULAR_RAND_UNTEN = 15) minus oberer Rand, der auf Seite 1 die
# Kopfzeile mit Mandant/Formularname/Vorgang/Datum traegt (41mm) und ab
# Seite 2 nur eine schmale Kennzeile (_FORMULAR_RAND_OBEN_FOLGESEITE = 22).
# y_mm ist relativ zum oberen Rand, die Grenze ist also y_mm + hoehe_mm.
NUTZBARE_HOEHE_SEITE1_MM = 241
NUTZBARE_HOEHE_FOLGESEITE_MM = 260

# Standardbreite eines neu angelegten Felds: halbe nutzbare Breite, damit
# zwei Felder ohne vorheriges Verkleinern nebeneinander passen. Ein Feld mit
# der vollen NUTZBARE_BREITE_MM waere bei x_mm=0 festgenagelt, weil jede
# Bewegung nach rechts x_mm + breite_mm <= NUTZBARE_BREITE_MM verletzt.
STANDARD_FELDBREITE_MM = 85


def nutzbare_hoehe_mm(seite: int) -> float:
    """Nutzbare Hoehe der gegebenen (0-indizierten) Seite in mm."""
    return NUTZBARE_HOEHE_SEITE1_MM if seite == 0 else NUTZBARE_HOEHE_FOLGESEITE_MM

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
    # Anzahl der A4-Seiten dieses Formulars -- der Canvas-Editor zeigt je
    # eine Seite als eigene Zeichenflaeche, "Seite hinzufuegen" erhoeht
    # diesen Wert per PATCH. Ein Formularfeld referenziert seine Seite ueber
    # Formularfeld.seite (0-indiziert), muss also < anzahl_seiten bleiben --
    # als anwendungsseitige Pruefung in app/api/routes/formulare.py, da ein
    # DB-Check ueber zwei Tabellen hinweg nicht abbildbar ist.
    anzahl_seiten: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    # Feinheit der optionalen Einrasthilfe im Canvas-Editor in mm (wie
    # Access' "An Raster ausrichten") -- rein editorielles Hilfsmittel ohne
    # Einfluss auf den PDF-Export. NULL = Einrasthilfe ausgeschaltet, freies
    # Positionieren ohne jede Rundung.
    snap_mm: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    __table_args__ = (
        CheckConstraint("anzahl_seiten >= 1", name="ck_formulare_anzahl_seiten_valid"),
        CheckConstraint(
            "snap_mm IS NULL OR snap_mm BETWEEN 1 AND 50", name="ck_formulare_snap_mm_valid"
        ),
    )


class Formularfeld(Base):
    """Ein Baustein einer Formular-Vorlage, frei positioniert auf einer von
    formular.anzahl_seiten A4-Seiten (wie Steuerelemente im MS-Access-
    Formular-Designer: beliebige x/y-Position und Breite/Hoehe in mm, ein
    Raster ist nur eine optionale Einrasthilfe im Editor, siehe
    Formular.snap_mm -- keine erzwungene Struktur). seite ist 0-indiziert
    und muss < formular.anzahl_seiten bleiben (anwendungsseitig geprueft,
    siehe app/api/routes/formulare.py). x_mm/y_mm ist die obere linke Ecke
    relativ zum Seitenrand, breite_mm/hoehe_mm die Ausdehnung. Ueberlappende
    Felder sind erlaubt (wie in Access) -- der Editor markiert sie nur
    optisch als Hinweis, das Backend blockiert nichts. reihenfolge bleibt
    als serverseitig abgeleiteter Cache erhalten (neu berechnet aus
    (seite, y_mm, x_mm) bei jeder Positionsaenderung, siehe
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
        CheckConstraint("seite >= 0", name="ck_formularfelder_seite_valid"),
        CheckConstraint("x_mm >= 0", name="ck_formularfelder_x_mm_valid"),
        CheckConstraint("y_mm >= 0", name="ck_formularfelder_y_mm_valid"),
        CheckConstraint("breite_mm > 0", name="ck_formularfelder_breite_mm_valid"),
        CheckConstraint("hoehe_mm > 0", name="ck_formularfelder_hoehe_mm_valid"),
        CheckConstraint(
            f"x_mm + breite_mm <= {NUTZBARE_BREITE_MM}",
            name="ck_formularfelder_x_mm_passt_auf_seite",
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
    seite: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    x_mm: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    y_mm: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    breite_mm: Mapped[float] = mapped_column(Float, nullable=False, default=STANDARD_FELDBREITE_MM)
    hoehe_mm: Mapped[float] = mapped_column(Float, nullable=False, default=8)
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
