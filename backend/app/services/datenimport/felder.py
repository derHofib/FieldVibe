"""Felddefinitionen je Importtyp: Zielfelder, Kopfzeilen-Synonyme (DE), Dublettenarten,
Vorlagen und der automatische Zuordnungsvorschlag."""
from dataclasses import dataclass, field

from app.services.datenimport.werte import schluessel

DUBLETTEN_AKTIONEN = ("ueberspringen", "aktualisieren", "anlegen")


@dataclass(frozen=True)
class FeldDef:
    key: str
    label: str
    synonyme: tuple[str, ...] = ()
    pflicht: bool = False
    gruppe: str | None = None
    hinweis: str | None = None


@dataclass(frozen=True)
class DublettenArt:
    key: str
    label: str
    # Aktionen, die fuer diese Art gewaehlt werden duerfen (eine gleiche Kundennummer
    # laesst sich z. B. nie "trotzdem anlegen": sie ist eindeutig).
    aktionen: tuple[str, ...] = DUBLETTEN_AKTIONEN
    standard: str = "ueberspringen"


@dataclass(frozen=True)
class EntitaetDef:
    key: str
    label: str
    beschreibung: str
    felder: tuple[FeldDef, ...]
    dubletten_arten: tuple[DublettenArt, ...]
    vorlage_kopf: tuple[str, ...]
    vorlage_zeilen: tuple[tuple[str, ...], ...]
    # Mindestanforderung an die Zuordnung: jede Gruppe verlangt, dass mindestens eines
    # der Felder zugeordnet ist (ODER-verknuepft innerhalb der Gruppe).
    pflicht_gruppen: tuple[tuple[str, ...], ...] = field(default=())
    pflicht_hinweis: str = ""
    modul: str = "kundenverwaltung"

    def feld(self, key: str) -> FeldDef:
        return next(f for f in self.felder if f.key == key)


_ADRESSE = "Adresse"

KUNDEN = EntitaetDef(
    key="kunden",
    label="Kunden",
    beschreibung="Kundenstamm mit Adresse, optional Ansprechpartner, USt-IdNr. und Debitorenkonto.",
    felder=(
        FeldDef("kundennummer", "Kundennummer", (
            "kundennummer", "kundennr", "kdnr", "kd-nr", "kunden-nr", "kundennummer alt", "kd nummer",
            "customer number", "customer id", "adressnummer", "=nummer", "=nr",
        ), hinweis="Leer = wird automatisch vergeben"),
        FeldDef("name", "Name / Firma", (
            "firma", "name", "kundenname", "firmenname", "firma/name", "name 1", "name1", "unternehmen",
            "company", "=kunde", "=bezeichnung",
        ), pflicht=True),
        FeldDef("vorname", "Vorname", ("vorname", "first name", "firstname"), gruppe="Person"),
        FeldDef("nachname", "Nachname", ("nachname", "familienname", "last name", "lastname"), gruppe="Person",
                hinweis="Ohne Firma wird „Vorname Nachname“ als Name verwendet"),
        FeldDef("typ", "Kundentyp", ("kundentyp", "=typ", "kundenart", "=art", "kundengruppe", "=kategorie"),
                hinweis="privat, gewerbe, oeffentlich, hausverwaltung"),
        FeldDef("strasse", "Straße", (
            "strasse", "straße", "anschrift", "adresse", "strasse hausnummer", "straße und hausnummer",
            "strasse und hausnummer", "street", "=str",
        ), gruppe=_ADRESSE),
        FeldDef("hausnummer", "Hausnummer", ("hausnummer", "hausnr", "haus-nr", "hnr"), gruppe=_ADRESSE),
        FeldDef("plz", "PLZ", ("plz", "postleitzahl", "zip", "zipcode", "postcode"), gruppe=_ADRESSE),
        FeldDef("ort", "Ort", ("ort", "stadt", "wohnort", "city", "ortsname"), gruppe=_ADRESSE),
        FeldDef("ansprechpartner", "Ansprechpartner", (
            "ansprechpartner", "ansprechperson", "kontaktperson", "=kontakt", "=ap",
        ), gruppe="Ansprechpartner"),
        FeldDef("ansprechpartner_position", "Position des Ansprechpartners", (
            "position", "funktion", "ansprechpartner position",
        ), gruppe="Ansprechpartner"),
        FeldDef("email", "E-Mail", (
            "email", "e-mail", "=mail", "e mail", "emailadresse", "e-mail adresse", "mailadresse",
            "ansprechpartner email", "ansprechpartner e-mail",
        ), gruppe="Ansprechpartner", hinweis="Wird beim Ansprechpartner hinterlegt"),
        FeldDef("telefon", "Telefon", (
            "telefon", "=tel", "telefonnummer", "phone", "rufnummer", "festnetz", "tel.", "telefon 1",
        ), gruppe="Ansprechpartner"),
        FeldDef("mobil", "Mobil", ("mobil", "mobiltelefon", "handy", "mobilnummer", "mobile"),
                gruppe="Ansprechpartner", hinweis="Wird nur genutzt, wenn Telefon leer ist"),
        FeldDef("ust_idnr", "USt-IdNr.", (
            "ustidnr", "ust-idnr", "ust id", "ust-id", "ustid", "umsatzsteuer-id", "umsatzsteuer id",
            "umsatzsteueridentifikationsnummer", "vat id", "vat", "ust.-idnr.", "ust idnr",
        )),
        FeldDef("leitweg_id", "Leitweg-ID", ("leitwegid", "leitweg-id", "leitweg id", "leitweg")),
        FeldDef("debitorenkonto", "Debitorenkonto", (
            "debitorenkonto", "debitor", "debitorennummer", "personenkonto", "debitorenkontonummer",
            "debitoren-nr", "debitorennr",
        )),
        FeldDef("notiz", "Notiz", (
            "notiz", "bemerkung", "bemerkungen", "anmerkung", "kommentar", "hinweis", "notizen", "memo",
        )),
    ),
    dubletten_arten=(
        DublettenArt("kundennummer", "Gleiche Kundennummer", ("ueberspringen", "aktualisieren")),
        DublettenArt("ust_idnr", "Gleiche USt-IdNr."),
        DublettenArt("name_plz", "Gleicher Name und gleiche PLZ"),
        DublettenArt("email", "Gleiche E-Mail-Adresse"),
    ),
    vorlage_kopf=(
        "Kundennummer", "Firma", "Kundentyp", "Straße", "PLZ", "Ort", "Ansprechpartner", "E-Mail", "Telefon",
        "USt-IdNr.", "Notiz",
    ),
    vorlage_zeilen=(
        ("K-10001", "Mustermann Elektrotechnik GmbH", "gewerbe", "Hauptstraße 12", "01067", "Dresden",
         "Erika Mustermann", "info@mustermann-elektro.example", "0351 1234567", "DE123456789", "Wartungsvertrag 2024"),
        ("", "Max Beispiel", "privat", "Gartenweg 3", "80331", "München", "", "max.beispiel@example.org",
         "0171 2345678", "", ""),
    ),
    pflicht_gruppen=(("name", "nachname"),),
    pflicht_hinweis="Name/Firma (oder Nachname) muss zugeordnet sein.",
)

ANLAGEN = EntitaetDef(
    key="anlagen",
    label="Standorte & Anlagen",
    beschreibung=(
        "Anlagen beim Kunden, optional mit Standort und Prüfdaten (letzte Prüfung, Prüfintervall). "
        "Der Kunde wird über Kundennummer oder Kundenname zugeordnet."
    ),
    modul="kundenverwaltung",
    felder=(
        FeldDef("kundennummer", "Kundennummer", (
            "kundennummer", "kundennr", "kdnr", "kd-nr", "kunden-nr", "kd nummer", "customer number",
            "kunde nr", "kunden nr",
        ), gruppe="Kunde"),
        FeldDef("kundenname", "Kundenname", (
            "kundenname", "=kunde", "firma", "auftraggeber", "kunde name", "firmenname", "=name",
        ), gruppe="Kunde"),
        FeldDef("standort_bezeichnung", "Standort", (
            "standort", "standortbezeichnung", "standortname", "objekt", "objektname", "liegenschaft",
            "filiale", "gebaeude", "gebäude",
        ), gruppe="Standort", hinweis="Wird beim Kunden angelegt, falls noch nicht vorhanden"),
        FeldDef("bezeichnung", "Anlage / Bezeichnung", (
            "bezeichnung", "anlage", "anlagenbezeichnung", "anlagenname", "geraet", "gerät",
            "geraetebezeichnung", "gerätebezeichnung", "objektbezeichnung", "betriebsmittel",
        ), gruppe="Anlage"),
        FeldDef("anlagentyp", "Anlagentyp", ("anlagentyp", "=typ", "=art", "anlagenart", "geraeteart", "=kategorie"),
                gruppe="Anlage"),
        FeldDef("hersteller", "Hersteller", ("hersteller", "fabrikat", "marke", "manufacturer"), gruppe="Anlage"),
        FeldDef("modell", "Modell", ("modell", "typenbezeichnung", "model", "geraetetyp", "gerätetyp"),
                gruppe="Anlage"),
        FeldDef("seriennummer", "Seriennummer", (
            "seriennummer", "serien-nr", "seriennr", "serial", "serial number", "=snr", "=sn", "fabriknummer",
            "fabrik-nr", "serien nr",
        ), gruppe="Anlage"),
        FeldDef("baujahr", "Baujahr", ("baujahr", "=bj", "herstellungsjahr"), gruppe="Anlage",
                hinweis="Wird in der Notiz vermerkt (kein eigenes Feld im Anlagenmodell)"),
        FeldDef("anschaffungsdatum", "Anschaffungs- / Inbetriebnahmedatum", (
            "anschaffungsdatum", "inbetriebnahme", "inbetriebnahmedatum", "kaufdatum", "installationsdatum",
            "ib datum",
        ), gruppe="Anlage"),
        FeldDef("strasse", "Straße", ("strasse", "straße", "anschrift", "=adresse", "street", "standort strasse"),
                gruppe=_ADRESSE),
        FeldDef("hausnummer", "Hausnummer", ("hausnummer", "hausnr", "haus-nr", "hnr"), gruppe=_ADRESSE),
        FeldDef("plz", "PLZ", ("plz", "postleitzahl", "zip", "zipcode"), gruppe=_ADRESSE),
        FeldDef("ort", "Ort", ("ort", "stadt", "city", "ortsname"), gruppe=_ADRESSE),
        FeldDef("notiz", "Notiz", ("notiz", "bemerkung", "bemerkungen", "anmerkung", "kommentar", "notizen"),
                gruppe="Anlage"),
        FeldDef("letzte_pruefung", "Letzte Prüfung", (
            "letzte pruefung", "letzte prüfung", "zuletzt geprueft", "zuletzt geprüft", "pruefdatum", "prüfdatum",
            "letzte wartung", "geprueft am", "geprüft am", "datum letzte pruefung", "letzte prüfung am",
        ), gruppe="Prüfdaten"),
        FeldDef("pruefintervall_monate", "Prüfintervall (Monate)", (
            "pruefintervall", "prüfintervall", "=intervall", "intervall monate", "pruefzyklus", "prüfzyklus",
            "wartungsintervall", "pruefintervall monate", "prüfintervall monate", "turnus", "prüfintervall (monate)",
        ), gruppe="Prüfdaten"),
        FeldDef("naechste_pruefung", "Nächste Prüfung", (
            "naechste pruefung", "nächste prüfung", "faellig am", "fällig am", "faelligkeit", "fälligkeit",
            "naechste wartung", "nächste wartung", "naechste faelligkeit", "nächste fälligkeit", "pruefung faellig",
        ), gruppe="Prüfdaten", hinweis="Leer = letzte Prüfung + Intervall"),
        FeldDef("pruefung_bezeichnung", "Bezeichnung der Prüfung", (
            "pruefungsart", "prüfungsart", "prüfart", "pruefart", "=pruefung", "=prüfung",
        ), gruppe="Prüfdaten", hinweis="Standard: „Regelprüfung“"),
    ),
    dubletten_arten=(
        DublettenArt("seriennummer_kunde", "Gleiche Seriennummer beim selben Kunden"),
        DublettenArt("bezeichnung_standort", "Gleiche Bezeichnung am selben Standort"),
        DublettenArt("standort", "Standort existiert bereits (reine Standortzeile)"),
    ),
    vorlage_kopf=(
        "Kundennummer", "Standort", "Anlagenbezeichnung", "Anlagentyp", "Hersteller", "Seriennummer", "Baujahr",
        "Straße", "PLZ", "Ort", "Letzte Prüfung", "Prüfintervall (Monate)",
    ),
    vorlage_zeilen=(
        ("K-10001", "Werk 1", "Hauptverteilung EG", "Elektroanlage", "Siemens", "SN-4711", "2015",
         "Hauptstraße 12", "01067", "Dresden", "15.03.2025", "12"),
        ("K-10001", "Werk 1", "Notbeleuchtung Treppenhaus", "Notbeleuchtung", "Hella", "NB-0815", "2018",
         "Hauptstraße 12", "01067", "Dresden", "02.06.2025", "6"),
    ),
    pflicht_gruppen=(("kundennummer", "kundenname"), ("bezeichnung", "standort_bezeichnung")),
    pflicht_hinweis=(
        "Der Kunde (Kundennummer oder Kundenname) und die Anlagenbezeichnung oder der Standort müssen "
        "zugeordnet sein."
    ),
)

MATERIAL = EntitaetDef(
    key="material",
    label="Material / Artikel",
    beschreibung="Artikelstamm mit Artikelnummer, Einheit und Einzelpreis (netto); optional Mindest- und Anfangsbestand.",
    modul="material",
    felder=(
        FeldDef("artikelnummer", "Artikelnummer", (
            "artikelnummer", "art-nr", "artnr", "art nr", "artikel-nr", "artikelnr", "artikel nr", "sku",
            "materialnummer", "teilenummer", "=nummer", "=nr",
        )),
        FeldDef("bezeichnung", "Bezeichnung", (
            "bezeichnung", "artikelbezeichnung", "artikel", "artikelname", "=name", "material", "kurztext",
            "beschreibung", "=text",
        ), pflicht=True),
        FeldDef("einheit", "Einheit", ("einheit", "=me", "mengeneinheit", "unit", "=ve"), hinweis="Leer = Stk"),
        FeldDef("einzelpreis", "Einzelpreis (netto)", (
            "einzelpreis", "=preis", "=vk", "vk-preis", "vk preis", "verkaufspreis", "preis netto", "netto preis",
            "einzelpreis netto", "vk netto", "listenpreis", "preis (netto)",
        ), hinweis="Einkaufspreise kennt das Materialmodell nicht"),
        FeldDef("mindestbestand", "Mindestbestand", ("mindestbestand", "min bestand", "meldebestand", "mindestmenge")),
        FeldDef("bestand", "Anfangsbestand", ("bestand", "=menge", "lagerbestand", "istbestand", "bestand aktuell"),
                hinweis="Wird als Wareneingang im Zentrallager gebucht"),
    ),
    dubletten_arten=(
        DublettenArt("artikelnummer", "Gleiche Artikelnummer"),
        DublettenArt("bezeichnung", "Gleiche Bezeichnung (nur Zeilen ohne Artikelnummer)"),
    ),
    vorlage_kopf=("Artikelnummer", "Bezeichnung", "Einheit", "Einzelpreis", "Mindestbestand", "Bestand"),
    vorlage_zeilen=(
        ("A-1001", "NYM-J 3x1,5 mm² Mantelleitung", "m", "1,25", "100", "250"),
        ("A-2040", "Leitungsschutzschalter B16 1-polig", "Stk", "7,90", "20", "35"),
    ),
    pflicht_gruppen=(("bezeichnung",),),
    pflicht_hinweis="Die Bezeichnung muss zugeordnet sein.",
)

ENTITAETEN: dict[str, EntitaetDef] = {e.key: e for e in (KUNDEN, ANLAGEN, MATERIAL)}


def entitaet(key: str) -> EntitaetDef | None:
    return ENTITAETEN.get(key)


@dataclass(frozen=True)
class Vorschlag:
    feld: str
    spalte: int | None
    sicherheit: str | None  # "sicher" (Synonym exakt) | "vermutet" (Teiltreffer)


def schlage_zuordnung_vor(definition: EntitaetDef, kopf: list[str]) -> list[Vorschlag]:
    """Ordnet Spalten per Kopfzeilen-Synonymen zu. Exakte Treffer gehen vor Teiltreffern,
    jede Spalte und jedes Feld wird hoechstens einmal vergeben."""
    spalten = [schluessel(name) for name in kopf]
    kandidaten: list[tuple[int, int, int, str]] = []  # (-wertung, feld_idx, spalte, sicherheit)
    for feld_idx, feld in enumerate(definition.felder):
        synonyme = [(schluessel(s.lstrip("=")), s.startswith("=")) for s in feld.synonyme]
        synonyme += [(schluessel(feld.label), False), (schluessel(feld.key), False)]
        for spalte, name in enumerate(spalten):
            if not name:
                continue
            wertung = _wertung(name, synonyme)
            if wertung:
                kandidaten.append((-wertung, feld_idx, spalte, "sicher" if wertung >= 100 else "vermutet"))
    kandidaten.sort()
    feld_zu_spalte: dict[int, tuple[int, str]] = {}
    belegte_spalten: set[int] = set()
    for _, feld_idx, spalte, sicherheit in kandidaten:
        if feld_idx in feld_zu_spalte or spalte in belegte_spalten:
            continue
        feld_zu_spalte[feld_idx] = (spalte, sicherheit)
        belegte_spalten.add(spalte)
    return [
        Vorschlag(f.key, *(feld_zu_spalte[i] if i in feld_zu_spalte else (None, None)))
        for i, f in enumerate(definition.felder)
    ]


def _wertung(spaltenname: str, synonyme: list[tuple[str, bool]]) -> int:
    if any(spaltenname == s for s, _ in synonyme):
        return 100
    beste = 0
    for synonym, nur_exakt in synonyme:
        # Teiltreffer nur bei ausreichend langen, spezifischen Begriffen: "nr" oder "kontakt"
        # duerfen nicht auf jede Spalte passen, die sie enthaelt.
        if nur_exakt or len(synonym) < 6 or len(spaltenname) < 6:
            continue
        if synonym in spaltenname or spaltenname in synonym:
            beste = max(beste, 50 + min(len(synonym), 40))
    return min(beste, 99)
