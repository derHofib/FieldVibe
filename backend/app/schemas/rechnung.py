from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

# Muss mit RECHNUNG_POSITION_QUELLEN in app/models/rechnung.py
# uebereinstimmen (docs/konzepte/ZEITERFASSUNG.md, Abschnitt 8).
RechnungPositionQuelle = Literal["material", "zeit", "fahrzeit", "fahrtkosten", "leistung"]

# Muss mit RECHNUNG_STEUER_KATEGORIEN in app/models/rechnung.py uebereinstimmen.
# Welche davon per API anlegbar sind, regelt steuer_service (Gating).
RechnungSteuerKategorie = Literal["S", "Z", "E", "AE"]
# Muss mit den Schluesseln von steuer_service.STEUER_GRUENDE uebereinstimmen.
RechnungSteuerGrund = Literal["pv_12_3", "reverse_charge_13b", "kleinunternehmer_19", "sonstige_befreiung"]
# Belegkopf: nur die Regelsaetze und 0 (Vorbelegung E/0 fuer Altverhalten).
ERLAUBTE_BELEG_MWST_SAETZE = (Decimal("19.00"), Decimal("7.00"), Decimal("0.00"))
# Muss mit RECHNUNGSARTEN in app/models/rechnung.py uebereinstimmen.
Rechnungsart = Literal["rechnung", "abschlag", "schluss", "gutschrift"]


def _satz_zu_kategorie_pruefen(kategorie: str | None, satz: Decimal | None) -> None:
    if kategorie is not None and kategorie != "S" and satz is not None and satz != 0:
        raise ValueError(f"Bei Steuerkategorie {kategorie} muss der Steuersatz 0 sein")


class RechnungPositionCreate(BaseModel):
    beschreibung: str
    menge: Decimal = Decimal("1")
    einheit: str = "Stk"
    einzelpreis: Decimal = Decimal("0")
    # Nur gesetzt, wenn die Position aus einem Rechnungsvorschlag uebernommen
    # wurde (siehe RechnungPositionVorschlag) -- steuert, ob und welche
    # Zeiterfassung-Eintraege beim Uebernehmen gesperrt werden (Konzept
    # Abschnitt 8). NULL bei frei eingetragenen Positionen.
    quelle: RechnungPositionQuelle | None = None
    # Nur bei quelle="leistung": die LV-Position, deren SVS-gekoppelte Zeit
    # mit uebernommen (und gesperrt) wird.
    lv_position_id: UUID | None = None
    # Nur bei quelle="material": das Material, dessen offene Verwendungen am
    # Vorgang mit uebernommen (und gesperrt) werden.
    material_id: UUID | None = None
    # Ohne Angabe gilt die Vorbelegung aus dem Beleg (steuer_service); bei
    # Kleinunternehmern wird ohnehin E/0 erzwungen.
    steuer_kategorie: RechnungSteuerKategorie | None = None
    steuer_satz: Decimal | None = Field(default=None, ge=0, le=100)
    # Pflicht bei Z/E/AE (siehe steuer_service.STEUER_GRUENDE); steuer_grund_text
    # nur bei sonstige_befreiung.
    steuer_grund: RechnungSteuerGrund | None = None
    steuer_grund_text: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _steuer_konsistent(self) -> "RechnungPositionCreate":
        _satz_zu_kategorie_pruefen(self.steuer_kategorie, self.steuer_satz)
        return self


class RechnungSteuerGruppeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kategorie: RechnungSteuerKategorie
    satz: Decimal
    netto: Decimal
    steuer: Decimal
    # Hinweistext(e) aus dem Steuergrund der Positionen dieser Gruppe -- nur zur
    # Anzeige, die Berechnung gruppiert weiter nach (Kategorie, Satz).
    hinweis: str | None = None
    hinweise: list[str] = Field(default_factory=list)


class RechnungPositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position: int
    beschreibung: str
    menge: Decimal
    einheit: str
    einzelpreis: Decimal
    quelle: RechnungPositionQuelle | None
    vorgang_id: UUID | None
    lv_position_id: UUID | None
    material_id: UUID | None
    steuer_kategorie: RechnungSteuerKategorie
    steuer_satz: Decimal
    steuer_grund: RechnungSteuerGrund | None
    steuer_grund_text: str | None
    # Abzugsposition einer Schlussrechnung: die angerechnete Abschlagsrechnung.
    abschlag_rechnung_id: UUID | None = None
    # Gutschriftsposition: die Originalposition, die sie zuruecknimmt.
    bezug_position_id: UUID | None = None
    # Menge dieser Position, die bereits durch (nicht stornierte) Gutschriften
    # zurueckgenommen ist; wird vom Service gesetzt (Obergrenze fuer die
    # naechste Gutschrift = menge - bereits_gutgeschrieben).
    bereits_gutgeschrieben: Decimal = Decimal("0")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def gesamt(self) -> Decimal:
        return (self.menge * self.einzelpreis).quantize(Decimal("0.01"))


# Vorschlaege fuer POST .../positionen aus dem verknuepften Vorgang (siehe
# rechnung_service.positions_vorschlaege_fuer_vorgang) -- kein eigenes
# Objekt in der DB, wird bei jedem Aufruf frisch aus Material-Verwendungen
# und Zeiterfassung berechnet.
class RechnungPositionVorschlag(BaseModel):
    quelle: RechnungPositionQuelle
    beschreibung: str
    menge: Decimal
    einheit: str
    einzelpreis: Decimal
    lv_position_id: UUID | None = None
    material_id: UUID | None = None


class AngerechneterAbschlagRead(BaseModel):
    rechnung_id: UUID
    rechnungsnummer: str
    datum: date
    # Positiver Nettobetrag der Abschlagsrechnung (die Abzugsposition der
    # Schlussrechnung traegt ihn negativ).
    netto: Decimal


class GutschriftKurzRead(BaseModel):
    rechnung_id: UUID
    rechnungsnummer: str
    # Mit Vorzeichen wie auf dem Gutschriftsbeleg (negativ).
    brutto: Decimal


class RechnungZahlungCreate(BaseModel):
    betrag: Decimal
    datum: date | None = None
    zahlungsart: str | None = None
    notiz: str | None = None


class RechnungZahlungRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    betrag: Decimal
    datum: date
    zahlungsart: str | None
    notiz: str | None
    storniert_zahlung_id: UUID | None
    erstellt_von: UUID
    created_at: datetime


class RechnungVorgangAuswahlPosten(BaseModel):
    quelle: RechnungPositionQuelle
    lv_position_id: UUID | None = None
    material_id: UUID | None = None


class RechnungVorgangUebernahme(BaseModel):
    vorgang_id: UUID
    # Zeit ohne SVS-Kopplung hat keinen hinterlegten Satz (siehe
    # positionen_vorschlaege_fuer_vorgang) -- er wird je Uebernahme mitgegeben.
    stundensatz: Decimal = Field(default=Decimal("0"), ge=0)
    auswahl: list[RechnungVorgangAuswahlPosten]


class RechnungVorgangKopf(BaseModel):
    id: UUID
    vorgangsnummer: str
    titel: str


class RechnungPositionUpdate(BaseModel):
    # menge/einheit/quelle/vorgang_id bewusst nicht aenderbar: sie haengen an
    # den gesperrten Zeiterfassung-Eintraegen. Die Steuerfelder haengen nicht
    # daran und sind -- wie die ganze Position -- nur im Entwurf aenderbar.
    beschreibung: str | None = None
    einzelpreis: Decimal | None = Field(default=None, ge=0)
    steuer_kategorie: RechnungSteuerKategorie | None = None
    steuer_satz: Decimal | None = Field(default=None, ge=0, le=100)
    steuer_grund: RechnungSteuerGrund | None = None
    steuer_grund_text: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _steuer_konsistent(self) -> "RechnungPositionUpdate":
        _satz_zu_kategorie_pruefen(self.steuer_kategorie, self.steuer_satz)
        return self


class AbrechenbarerVorgang(BaseModel):
    vorgang_id: UUID
    vorgangsnummer: str
    titel: str
    stunden_ohne_svs: Decimal
    stunden_mit_svs: Decimal
    # Anzahl verschiedener Materialien mit offenen (nicht abgerechneten)
    # Verwendungen am Vorgang.
    material_offen: int = 0


class RechnungCreate(BaseModel):
    kunde_id: UUID
    vorgang_id: UUID | None = None
    # betrag_netto bleibt der einfache Weg fuer eine einzelne Abschlussrechnung
    # ohne eigene Positionen (unveraendertes Verhalten aus Phase 6). Werden
    # positionen mitgegeben, wird betrag_netto beim Lesen durch deren Summe
    # ersetzt -- fuer Teil-/Sammelrechnungen mit eigenen Zeilen.
    betrag_netto: Decimal = Decimal("0")
    mwst_satz: Decimal = Decimal("19.00")
    faellig_am: date | None = None
    # Zeitpunkt der Leistung/Lieferung (§14 Abs. 4 Nr. 6 UStG) -- optional,
    # da oft identisch mit dem Rechnungsdatum.
    leistungsdatum: date | None = None
    positionen: list[RechnungPositionCreate] = Field(default_factory=list)
    # Schlussrechnung entsteht nur ueber /aus-angebot bzw. /abschlaege-anrechnen,
    # Gutschrift nur ueber /gutschrift -- hier bewusst nicht waehlbar.
    rechnungsart: Literal["rechnung", "abschlag"] = "rechnung"

    @field_validator("mwst_satz")
    @classmethod
    def _mwst_satz_erlaubt(cls, v: Decimal) -> Decimal:
        if v not in ERLAUBTE_BELEG_MWST_SAETZE:
            raise ValueError("mwst_satz muss 19, 7 oder 0 sein")
        return v

    @field_validator("rechnungsart", mode="before")
    @classmethod
    def _rechnungsart_anlegbar(cls, v):
        if v == "schluss":
            raise ValueError("Eine Schlussrechnung entsteht über POST /api/rechnungen/aus-angebot oder .../abschlaege-anrechnen")
        if v == "gutschrift":
            raise ValueError("Eine Gutschrift entsteht über POST /api/rechnungen/{id}/gutschrift")
        return v


class RechnungAusAngebotCreate(BaseModel):
    angebot_id: UUID
    rechnungsart: Literal["rechnung", "abschlag", "schluss"]
    # Nur bei rechnungsart="abschlag", genau eines von beiden: Anteil bzw.
    # Betrag bezogen auf das Angebot-Netto.
    abschlag_prozent: Decimal | None = Field(default=None, gt=0, le=100)
    abschlag_netto: Decimal | None = Field(default=None, gt=0)
    faellig_am: date | None = None
    leistungsdatum: date | None = None

    @model_validator(mode="after")
    def _abschlag_angaben(self) -> "RechnungAusAngebotCreate":
        angaben = (self.abschlag_prozent is not None) + (self.abschlag_netto is not None)
        if self.rechnungsart == "abschlag":
            if angaben != 1:
                raise ValueError("Für einen Abschlag genau eines von abschlag_prozent und abschlag_netto angeben")
        elif angaben:
            raise ValueError("abschlag_prozent und abschlag_netto gelten nur bei rechnungsart abschlag")
        return self


class AbschlaegeAnrechnen(BaseModel):
    # Ohne Angabe werden alle anrechenbaren Abschlaege angerechnet.
    abschlag_rechnung_ids: list[UUID] | None = None


class GutschriftPositionAuswahl(BaseModel):
    position_id: UUID
    menge: Decimal = Field(gt=0)


class GutschriftCreate(BaseModel):
    # Genau eines von positionen/alle.
    positionen: list[GutschriftPositionAuswahl] | None = None
    alle: bool = False
    grund: str = Field(min_length=3, max_length=200)

    @field_validator("grund")
    @classmethod
    def _grund_getrimmt(cls, v: str) -> str:
        v = v.strip()
        if not 3 <= len(v) <= 200:
            raise ValueError("grund muss 3 bis 200 Zeichen lang sein")
        return v

    @model_validator(mode="after")
    def _eine_auswahl(self) -> "GutschriftCreate":
        if bool(self.positionen) == self.alle:
            raise ValueError("Genau eines von positionen und alle angeben")
        return self


class RechnungUpdate(BaseModel):
    status: str | None = None
    betrag_netto: Decimal | None = None
    faellig_am: date | None = None
    leistungsdatum: date | None = None


class RechnungRead(BaseModel):
    id: UUID
    kunde_id: UUID
    vorgang_id: UUID | None
    rechnungsnummer: str
    betrag_netto: Decimal
    mwst_satz: Decimal
    status: str
    faellig_am: date | None
    leistungsdatum: date | None
    erstellt_von: UUID
    versendet_am: datetime | None
    bezahlt_am: datetime | None
    mahnstufe: int
    letzte_mahnung_am: datetime | None
    ist_storno: bool
    storniert_rechnung_id: UUID | None
    rechnungsart: Rechnungsart = "rechnung"
    angebot_id: UUID | None = None
    # Nur bei Gutschriften: Ursprungsrechnung und Grund (steht auch auf dem Beleg).
    bezug_rechnung_id: UUID | None = None
    gutschrift_grund: str | None = None
    # Gesetzt, wenn beim Versand eine ZUGFeRD-konforme Hybrid-PDF mit
    # eingebetteter XML erzeugt und archiviert wurde -- siehe
    # rechnung_service._rechnung_dokument_bytes(). NULL bei Entwuerfen,
    # bei deaktivierter E-Rechnung oder wenn Pflichtangaben zum
    # Versand-Zeitpunkt fehlten (stiller Fallback auf normales PDF).
    xml_object_key: str | None
    # Beim Versand festgehalten: 'xrechnung' oder 'en16931' (ZUGFeRD) und die
    # Leitweg-ID, die in der E-Rechnung stand. Belegt nur, dass die interne
    # Pflichtfeldpruefung bestanden wurde, nicht den Schematron-Lauf (der braucht Java).
    e_rechnung_profil: Literal["en16931", "xrechnung"] | None = None
    leitweg_id: str | None = None
    created_at: datetime
    updated_at: datetime
    positionen: list[RechnungPositionRead]
    # Steuer je (Kategorie, Satz) -- die Quelle fuer Steuer- und Bruttobetrag
    # (steuer_service); betrag_netto ist die Summe der gerundeten Gruppen.
    steuergruppen: list[RechnungSteuerGruppeRead]
    betrag_steuer: Decimal
    zahlungen: list[RechnungZahlungRead] = Field(default_factory=list)
    # Nur bei Schlussrechnungen: die angerechneten Abschlaege.
    angerechnete_abschlaege: list[AngerechneterAbschlagRead] = Field(default_factory=list)
    # Am Original: die nicht stornierten Gutschriften zu dieser Rechnung.
    gutschriften: list[GutschriftKurzRead] = Field(default_factory=list)
    # Offener Betrag nach der zentralen Regel (rechnung_service.offener_betrag_regel):
    # Brutto - Zahlungen - |Gutschriften|, mindestens 0; an einer Gutschrift
    # bzw. einem Storno-Beleg der Ueberhang als Guthaben (negativ). Wird vom
    # Service gesetzt -- aus den Feldern dieses Modells allein nicht berechenbar.
    offener_betrag: Decimal = Decimal("0.00")
    # Alle distinct vorgang_id der Positionen, nach erster Positionsnummer --
    # Grundlage der Gruppendarstellung (Ueberschrift je Vorgang).
    vorgaenge: list[RechnungVorgangKopf] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def betrag_brutto(self) -> Decimal:
        return (self.betrag_netto + self.betrag_steuer).quantize(Decimal("0.01"))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def bezahlter_betrag(self) -> Decimal:
        return sum((z.betrag for z in self.zahlungen), Decimal("0")).quantize(Decimal("0.01"))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ist_ueberfaellig(self) -> bool:
        """Faellig, unbezahlt und das Datum ist durch -- die Kennzahl, nach der
        die Uebersicht farblich warnt und der Ueberfaellig-Filter greift.
        Ab teilweise_bezahlt weiterhin ueberfaellig, weil noch Geld aussteht."""
        if self.faellig_am is None or self.status not in ("versendet", "teilweise_bezahlt"):
            return False
        return self.faellig_am < date.today()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def tage_ueberfaellig(self) -> int:
        if not self.ist_ueberfaellig or self.faellig_am is None:
            return 0
        return (date.today() - self.faellig_am).days


class RechnungListe(BaseModel):
    """Antwort der Rechnungsuebersicht. Die Summen beziehen sich bewusst auf
    die komplette gefilterte Menge, nicht auf die ausgelieferte Seite -- eine
    Summenzeile, die nur die ersten 50 Treffer addiert, waere irrefuehrend."""

    eintraege: list[RechnungRead]
    gesamt_anzahl: int
    summe_netto: Decimal
    summe_brutto: Decimal
    summe_offen: Decimal


class ArchivObjektRead(BaseModel):
    art: Literal["pdf", "xml"]
    status: Literal["ok", "abweichung", "fehlt", "kein_hash"]
    hash_gespeichert: str | None
    hash_berechnet: str | None


class ArchivPruefungRead(BaseModel):
    rechnung_id: UUID
    rechnungsnummer: str
    objekte: list[ArchivObjektRead]
    # True nur, wenn mindestens ein Archivobjekt existiert und alle unveraendert sind.
    ok: bool
