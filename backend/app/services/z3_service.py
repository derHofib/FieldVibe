"""Z3-Export: Datentraegeruberlassung nach den GoBD (Rz. 164 ff.), Beschreibungsstandard
"GDPdU" (index.xml + Tabellen als Textdateien) fuer die Auswertung mit IDEA.

Abgrenzung: Z3 ist die Datentraegeruberlassung auf Anforderung der Finanzverwaltung. Es
ist NICHT Z1 (unmittelbarer Lesezugriff) und NICHT Z2 (mittelbarer Zugriff, Auswertung
durch den Steuerpflichtigen). Die index.xml ist anhand der oeffentlich bekannten
Struktur des Beschreibungsstandards (gdpdu-01-09-2004.dtd) aus dem Gedaechtnis
aufgebaut und wurde NICHT gegen IDEA oder die DTD validiert; die DTD wird nicht
mitgeliefert (der DOCTYPE verweist auf den Standardnamen, IDEA bringt sie mit).

Format der Tabellen: CP1252 (ANSI, Standard von IDEA), Semikolon, Texterkennung ", Satzende
CRLF, Dezimalkomma ohne Tausendertrennung, Datum TT.MM.JJJJ, erste Zeile = Spaltennamen
(in der index.xml per Range/From=2 uebersprungen). Nicht in CP1252 darstellbare Zeichen
werden durch ? ersetzt und im README gezaehlt."""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from lxml import etree
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.zeit import in_lokal, tagesbeginn_utc, tagesende_utc
from app.models.eingangsrechnung import Eingangsrechnung, EingangsrechnungPosition, EingangsrechnungZahlung
from app.models.kunde import Kunde
from app.models.lieferant import Lieferant
from app.models.mandant import Mandant
from app.models.rechnung import Rechnung, RechnungPosition, RechnungZahlung
from app.services import rechnung_service, steuer_service
from app.services.export_zip import ZipSchreiber

DTD_NAME = "gdpdu-01-09-2004.dtd"
ENCODING = "cp1252"
_CENT = Decimal("0.01")


@dataclass(frozen=True)
class Spalte:
    name: str
    typ: str  # "text" | "zahl" | "betrag" | "datum"
    beschreibung: str
    schluessel: bool = False
    verweis: str | None = None  # Tabellenname der Fremdschluessel-Referenz


@dataclass
class Tabelle:
    datei: str
    name: str
    beschreibung: str
    spalten: list[Spalte]
    zeilen: list[list[Any]] = field(default_factory=list)


def fmt_datum(wert: date | datetime | None) -> str:
    if wert is None:
        return ""
    if isinstance(wert, datetime):
        wert = in_lokal(wert).date()
    return wert.strftime("%d.%m.%Y")


def fmt_betrag(wert: Decimal | None) -> str:
    if wert is None:
        return ""
    return f"{Decimal(wert).quantize(_CENT):f}".replace(".", ",")


def fmt_zahl(wert: Any) -> str:
    if wert is None:
        return ""
    if isinstance(wert, Decimal):
        return format(wert.normalize(), "f").replace(".", ",")
    return str(wert)


def _zelle(spalte: Spalte, wert: Any) -> str:
    if wert is None:
        return ""
    if spalte.typ == "datum":
        return fmt_datum(wert)
    if spalte.typ == "betrag":
        return fmt_betrag(wert)
    if spalte.typ == "zahl":
        return fmt_zahl(wert)
    return str(wert).replace("\r", " ").replace("\n", " ")


def csv_bytes(tabelle: Tabelle) -> tuple[bytes, int]:
    """CP1252-Bytes der Tabelle und Anzahl ersetzter (nicht darstellbarer) Zeichen."""
    puffer = io.StringIO()
    writer = csv.writer(puffer, delimiter=";", quotechar='"', quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow([s.name for s in tabelle.spalten])
    for zeile in tabelle.zeilen:
        writer.writerow([_zelle(s, w) for s, w in zip(tabelle.spalten, zeile)])
    text = puffer.getvalue()
    roh = text.encode(ENCODING, errors="replace")
    ersetzt = roh.count(b"?") - text.count("?")
    return roh, max(ersetzt, 0)


def index_xml(
    tabellen: list[Tabelle], *, betrieb: str, ort: str, von: date, bis: date, erzeugt: datetime
) -> bytes:
    """index.xml nach dem Beschreibungsstandard (Struktur nicht gegen IDEA validiert)."""
    wurzel = etree.Element("DataSet")
    etree.SubElement(wurzel, "Version").text = "1.0"
    lieferant = etree.SubElement(wurzel, "DataSupplier")
    etree.SubElement(lieferant, "Name").text = betrieb
    etree.SubElement(lieferant, "Location").text = ort or "-"
    etree.SubElement(lieferant, "Comment").text = (
        f"Datenträgerüberlassung (Z3) {fmt_datum(von)} bis {fmt_datum(bis)}, erzeugt mit FieldVibe am "
        f"{erzeugt:%d.%m.%Y %H:%M} UTC. Tabellen: CP1252, Semikolon, Dezimalkomma."
    )
    medium = etree.SubElement(wurzel, "Media")
    etree.SubElement(medium, "Name").text = "Datenträger 1"
    for t in tabellen:
        tab = etree.SubElement(medium, "Table")
        etree.SubElement(tab, "URL").text = t.datei
        etree.SubElement(tab, "Name").text = t.name
        etree.SubElement(tab, "Description").text = t.beschreibung
        etree.SubElement(tab, "DecimalSymbol").text = ","
        # Erste Zeile enthaelt die Spaltennamen.
        rng = etree.SubElement(tab, "Range")
        etree.SubElement(rng, "From").text = "2"
        var = etree.SubElement(tab, "VariableLength")
        etree.SubElement(var, "ColumnDelimiter").text = ";"
        etree.SubElement(var, "RecordDelimiter").text = "\r\n"
        etree.SubElement(var, "TextEncapsulator").text = '"'
        for s in t.spalten:
            spalten_el = etree.SubElement(var, "VariablePrimaryKey" if s.schluessel else "VariableColumn")
            etree.SubElement(spalten_el, "Name").text = s.name
            etree.SubElement(spalten_el, "Description").text = s.beschreibung
            if s.typ == "text":
                etree.SubElement(spalten_el, "AlphaNumeric")
            elif s.typ == "datum":
                datum = etree.SubElement(spalten_el, "Date")
                etree.SubElement(datum, "Format").text = "DD.MM.YYYY"
            elif s.typ == "betrag":
                num = etree.SubElement(spalten_el, "Numeric")
                etree.SubElement(num, "Accuracy").text = "2"
            else:
                etree.SubElement(spalten_el, "Numeric")
        for s in t.spalten:
            if s.verweis:
                fk = etree.SubElement(var, "ForeignKey")
                etree.SubElement(fk, "Name").text = s.name
                etree.SubElement(fk, "References").text = s.verweis
    return etree.tostring(
        wurzel,
        xml_declaration=True,
        encoding="UTF-8",
        doctype=f'<!DOCTYPE DataSet SYSTEM "{DTD_NAME}">',
        pretty_print=True,
    )


README = """\
FieldVibe -- Z3-Datenträgerüberlassung (GoBD)
=============================================

Betrieb:   {betrieb}
Zeitraum:  {von} bis {bis}
Erzeugt:   {zeit} UTC

Inhalt
------
  index.xml      Beschreibung der Tabellen im Beschreibungsstandard (GDPdU/Z3) für IDEA.
  *.csv          Tabellen: Kodierung Windows-1252 (CP1252), Trennzeichen Semikolon,
                 Texterkennung ", Satzende CRLF, Dezimalkomma ohne Tausendertrennung,
                 Datum TT.MM.JJJJ. Die erste Zeile enthält die Spaltennamen.
  manifest.json  SHA-256 je Datei.

Tabellen
--------
{tabellen}

Abgrenzung und Hinweise
-----------------------
* Dies ist eine Datenträgerüberlassung (Z3), kein unmittelbarer (Z1) oder mittelbarer (Z2)
  Datenzugriff.
* Die index.xml folgt dem öffentlich beschriebenen Aufbau des Beschreibungsstandards, wurde
  aber nicht mit IDEA geprüft. Vor Übergabe an die Finanzverwaltung bitte mit dem
  Steuerberater einmal in IDEA einlesen.
* Die DTD ({dtd}) liegt nicht bei; IDEA bringt sie mit.
* Nicht darstellbare Zeichen wurden durch ? ersetzt: {ersetzt} Zeichen.
* Entwürfe sind nicht enthalten. Rechnungen sind nach Ausstellungsdatum (Versand) selektiert,
  Zahlungen nach Zahlungsdatum, Eingangsrechnungen nach Rechnungsdatum.
"""


def _betrag(wert: Decimal | None) -> Decimal:
    return Decimal(wert or 0).quantize(_CENT)


async def _tabellen_bauen(
    session: AsyncSession, mandant_id: UUID, mandant: Mandant, von: date, bis: date
) -> list[Tabelle]:
    anfang, ende = tagesbeginn_utc(von), tagesende_utc(bis)

    rechnungen = list(
        (
            await session.execute(
                select(Rechnung)
                .where(
                    Rechnung.mandant_id == mandant_id,
                    Rechnung.status != "entwurf",
                    Rechnung.versendet_am >= anfang,
                    Rechnung.versendet_am < ende,
                )
                .order_by(Rechnung.versendet_am, Rechnung.rechnungsnummer)
            )
        ).scalars()
    )
    nummern = {r.id: r.rechnungsnummer for r in rechnungen}
    # Bezugsrechnungen ausserhalb des Zeitraums: nur fuer die Nummernanzeige.
    bezug_ids = {r.bezug_rechnung_id or r.storniert_rechnung_id for r in rechnungen} - {None} - set(nummern)
    if bezug_ids:
        for rid, nr in (
            await session.execute(select(Rechnung.id, Rechnung.rechnungsnummer).where(Rechnung.id.in_(bezug_ids)))
        ).all():
            nummern[rid] = nr

    positionen: dict[UUID, list[RechnungPosition]] = defaultdict(list)
    if rechnungen:
        for p in (
            await session.execute(
                select(RechnungPosition)
                .where(RechnungPosition.rechnung_id.in_([r.id for r in rechnungen]))
                .order_by(RechnungPosition.rechnung_id, RechnungPosition.position)
            )
        ).scalars():
            positionen[p.rechnung_id].append(p)

    kunden = {
        k.id: k for k in (await session.execute(select(Kunde).where(Kunde.mandant_id == mandant_id))).scalars()
    }

    t_rechnungen = Tabelle(
        "rechnungen.csv",
        "Rechnungen",
        "Ausgangsrechnungen, Gutschriften und Stornobelege (ab Versand, ohne Entwürfe)",
        [
            Spalte("Rechnungsnummer", "text", "Fortlaufende Rechnungsnummer", schluessel=True),
            Spalte("Rechnungsart", "text", "rechnung, abschlag, schluss, gutschrift"),
            Spalte("Rechnungsdatum", "datum", "Ausstellungsdatum (Versand)"),
            Spalte("Leistungsdatum", "datum", "Zeitpunkt der Leistung (§ 14 Abs. 4 Nr. 6 UStG)"),
            Spalte("Faelligkeitsdatum", "datum", "Fälligkeit"),
            Spalte("Kundennummer", "text", "Kundennummer des Rechnungsempfängers", verweis="Kunden"),
            Spalte("Kundenname", "text", "Name des Rechnungsempfängers"),
            Spalte("Status", "text", "versendet, teilweise_bezahlt, bezahlt, storniert"),
            Spalte("Storno", "text", "J bei Stornobeleg, sonst N"),
            Spalte("Bezug_Rechnungsnummer", "text", "Ursprungsrechnung bei Gutschrift/Storno"),
            Spalte("Netto", "betrag", "Nettobetrag in EUR"),
            Spalte("Steuerbetrag", "betrag", "Umsatzsteuer in EUR"),
            Spalte("Brutto", "betrag", "Bruttobetrag in EUR"),
        ],
    )
    t_positionen = Tabelle(
        "rechnungspositionen.csv",
        "Rechnungspositionen",
        "Positionen der Rechnungen",
        [
            Spalte("Rechnungsnummer", "text", "Zugehörige Rechnung", verweis="Rechnungen"),
            Spalte("Position", "zahl", "Positionsnummer"),
            Spalte("Beschreibung", "text", "Leistungsbeschreibung"),
            Spalte("Menge", "betrag", "Menge"),
            Spalte("Einheit", "text", "Mengeneinheit"),
            Spalte("Einzelpreis", "betrag", "Einzelpreis netto in EUR"),
            Spalte("Steuerkategorie", "text", "S, Z, E oder AE (EN 16931)"),
            Spalte("Steuersatz", "betrag", "Steuersatz in Prozent"),
            Spalte("Nettobetrag", "betrag", "Menge x Einzelpreis in EUR"),
        ],
    )
    for r in rechnungen:
        pos = positionen.get(r.id, [])
        netto = rechnung_service.netto_betrag(r, pos)
        brutto = rechnung_service.brutto_betrag(r, pos)
        kunde = kunden.get(r.kunde_id)
        bezug = r.bezug_rechnung_id or r.storniert_rechnung_id
        t_rechnungen.zeilen.append(
            [
                r.rechnungsnummer,
                r.rechnungsart,
                r.versendet_am,
                r.leistungsdatum,
                r.faellig_am,
                kunde.kundennummer if kunde else "",
                kunde.name if kunde else "",
                r.status,
                "J" if r.ist_storno else "N",
                nummern.get(bezug, "") if bezug else "",
                netto,
                brutto - netto,
                brutto,
            ]
        )
        for p in pos:
            t_positionen.zeilen.append(
                [
                    r.rechnungsnummer,
                    p.position,
                    p.beschreibung,
                    p.menge,
                    p.einheit,
                    p.einzelpreis,
                    p.steuer_kategorie,
                    p.steuer_satz,
                    steuer_service.runde_cent(p.menge * p.einzelpreis),
                ]
            )

    t_zahlungen = Tabelle(
        "zahlungen.csv",
        "Zahlungen",
        "Zahlungseingänge zu Ausgangsrechnungen (nach Zahlungsdatum im Zeitraum)",
        [
            Spalte("Rechnungsnummer", "text", "Rechnung, auf die gezahlt wurde", verweis="Rechnungen"),
            Spalte("Zahlungsdatum", "datum", "Datum der Zahlung"),
            Spalte("Betrag", "betrag", "Betrag in EUR; negativ bei Gegenbuchung (Storno einer Zahlung)"),
            Spalte("Zahlungsart", "text", "ueberweisung, bar, karte, lastschrift, sonstiges"),
            Spalte("Storno_Zahlung", "text", "J bei Gegenbuchung, sonst N"),
        ],
    )
    zahlungen = (
        await session.execute(
            select(RechnungZahlung, Rechnung.rechnungsnummer)
            .join(Rechnung, Rechnung.id == RechnungZahlung.rechnung_id)
            .where(RechnungZahlung.mandant_id == mandant_id, RechnungZahlung.datum >= von, RechnungZahlung.datum <= bis)
            .order_by(RechnungZahlung.datum, Rechnung.rechnungsnummer, RechnungZahlung.created_at)
        )
    ).all()
    for z, nummer in zahlungen:
        t_zahlungen.zeilen.append(
            [nummer, z.datum, z.betrag, z.zahlungsart or "", "J" if z.storniert_zahlung_id else "N"]
        )

    t_kunden = Tabelle(
        "kunden.csv",
        "Kunden",
        "Debitorenstammdaten (alle Kunden des Betriebs)",
        [
            Spalte("Kundennummer", "text", "Kundennummer", schluessel=True),
            Spalte("Name", "text", "Name/Firma"),
            Spalte("Strasse", "text", "Straße und Hausnummer"),
            Spalte("PLZ", "text", "Postleitzahl"),
            Spalte("Ort", "text", "Ort"),
            Spalte("USt_IdNr", "text", "Umsatzsteuer-Identifikationsnummer"),
            Spalte("Debitorenkonto", "text", "DATEV-Personenkonto"),
        ],
    )
    for k in sorted(kunden.values(), key=lambda k: k.kundennummer):
        adresse = k.adresse or {}
        t_kunden.zeilen.append(
            [k.kundennummer, k.name, adresse.get("strasse", ""), adresse.get("plz", ""), adresse.get("ort", ""), k.ust_idnr or "", k.debitorenkonto or ""]
        )

    lieferanten = {
        l.id: l for l in (await session.execute(select(Lieferant).where(Lieferant.mandant_id == mandant_id))).scalars()
    }
    eingang = list(
        (
            await session.execute(
                select(Eingangsrechnung)
                .where(
                    Eingangsrechnung.mandant_id == mandant_id,
                    Eingangsrechnung.status != "entwurf",
                    Eingangsrechnung.rechnungsdatum >= von,
                    Eingangsrechnung.rechnungsdatum <= bis,
                )
                .order_by(Eingangsrechnung.rechnungsdatum, Eingangsrechnung.rechnungsnummer_lieferant)
            )
        ).scalars()
    )
    t_eingang = Tabelle(
        "eingangsrechnungen.csv",
        "Eingangsrechnungen",
        "Erhaltene Rechnungen (nach Rechnungsdatum im Zeitraum, ohne Entwürfe)",
        [
            Spalte("Belegnummer", "text", "Rechnungsnummer des Lieferanten", schluessel=True),
            Spalte("Lieferant", "text", "Name des Lieferanten"),
            Spalte("Kreditorenkonto", "text", "DATEV-Personenkonto des Lieferanten"),
            Spalte("Rechnungsdatum", "datum", "Datum der Rechnung"),
            Spalte("Eingangsdatum", "datum", "Datum der Erfassung/des Eingangs"),
            Spalte("Faelligkeitsdatum", "datum", "Fälligkeit"),
            Spalte("Kategorie", "text", "Kategorie"),
            Spalte("Status", "text", "offen, bezahlt, storniert"),
            Spalte("Netto", "betrag", "Nettobetrag in EUR"),
            Spalte("Steuerbetrag", "betrag", "Vorsteuer in EUR"),
            Spalte("Brutto", "betrag", "Bruttobetrag in EUR"),
            Spalte("Bezahlt", "betrag", "Summe der Zahlungen in EUR"),
        ],
    )
    if eingang:
        ids = [e.id for e in eingang]
        pos_e: dict[UUID, list[EingangsrechnungPosition]] = defaultdict(list)
        for p in (
            await session.execute(select(EingangsrechnungPosition).where(EingangsrechnungPosition.eingangsrechnung_id.in_(ids)))
        ).scalars():
            pos_e[p.eingangsrechnung_id].append(p)
        zahl_e: dict[UUID, Decimal] = defaultdict(Decimal)
        for z in (
            await session.execute(select(EingangsrechnungZahlung).where(EingangsrechnungZahlung.eingangsrechnung_id.in_(ids)))
        ).scalars():
            zahl_e[z.eingangsrechnung_id] += z.betrag
        from app.services.eingangsrechnung_service import brutto_betrag as brutto_e
        from app.services.eingangsrechnung_service import netto_betrag as netto_e

        for e in eingang:
            netto = _betrag(netto_e(e, pos_e.get(e.id, [])))
            brutto = _betrag(brutto_e(e, pos_e.get(e.id, [])))
            lief = lieferanten.get(e.lieferant_id) if e.lieferant_id else None
            t_eingang.zeilen.append(
                [
                    e.rechnungsnummer_lieferant,
                    e.lieferant_name,
                    lief.kreditorenkonto if lief and lief.kreditorenkonto else "",
                    e.rechnungsdatum,
                    e.eingegangen_am,
                    e.faellig_am,
                    e.kategorie or "",
                    e.status,
                    netto,
                    brutto - netto,
                    brutto,
                    _betrag(zahl_e.get(e.id)),
                ]
            )

    t_konten = Tabelle(
        "konten.csv",
        "Konten",
        "Kontenbezüge für den DATEV-Export: Erlöskonten (Steuerkategorie/Satz), Debitoren, Kreditoren",
        [
            Spalte("Kontoart", "text", "Erloes, Debitor oder Kreditor"),
            Spalte("Konto", "text", "Kontonummer"),
            Spalte("Bezeichnung", "text", "Bezeichnung (Name bzw. Steuerschlüssel)"),
            Spalte("Bezug", "text", "Kundennummer bzw. Lieferant bzw. Steuerkategorie:Satz"),
        ],
    )
    buchhaltung = (mandant.firmendaten or {}).get("buchhaltung") or {}
    for schluessel, konto in sorted((buchhaltung.get("erloeskonten") or {}).items()):
        t_konten.zeilen.append(["Erloes", konto, f"Erlöse {schluessel}", schluessel])
    for k in sorted(kunden.values(), key=lambda k: k.kundennummer):
        if k.debitorenkonto:
            t_konten.zeilen.append(["Debitor", k.debitorenkonto, k.name, k.kundennummer])
    for l in sorted(lieferanten.values(), key=lambda l: l.name):
        if l.kreditorenkonto:
            t_konten.zeilen.append(["Kreditor", l.kreditorenkonto, l.name, l.name])

    return [t_rechnungen, t_positionen, t_zahlungen, t_kunden, t_eingang, t_konten]


async def erzeuge(session: AsyncSession, zip_: ZipSchreiber, mandant_id: UUID, von: date, bis: date) -> dict[str, Any]:
    mandant = await session.get(Mandant, mandant_id)
    jetzt = datetime.now(timezone.utc)
    tabellen = await _tabellen_bauen(session, mandant_id, mandant, von, bis)

    ersetzt_gesamt = 0
    for t in tabellen:
        daten, ersetzt = csv_bytes(t)
        ersetzt_gesamt += ersetzt
        zip_.bytes_hinzufuegen(t.datei, daten)

    adresse = (mandant.firmendaten or {}).get("adresse") or {}
    ort = " ".join(x for x in (adresse.get("plz"), adresse.get("ort")) if x)
    zip_.bytes_hinzufuegen(
        "index.xml", index_xml(tabellen, betrieb=mandant.name, ort=ort, von=von, bis=bis, erzeugt=jetzt)
    )
    zip_.bytes_hinzufuegen(
        "README.txt",
        README.format(
            betrieb=mandant.name,
            von=fmt_datum(von),
            bis=fmt_datum(bis),
            zeit=jetzt.strftime("%d.%m.%Y %H:%M"),
            tabellen="\n".join(f"  {t.datei:<28} {len(t.zeilen):>6} Zeilen  {t.beschreibung}" for t in tabellen),
            dtd=DTD_NAME,
            ersetzt=ersetzt_gesamt,
        ).encode("utf-8"),
    )
    return {
        "export_version": 1,
        "art": "z3",
        "erstellt_am": jetzt.isoformat(),
        "mandant": {"id": str(mandant_id), "name": mandant.name},
        "zeitraum": {"von": von.isoformat(), "bis": bis.isoformat()},
        "zeilen_je_tabelle": {t.name: len(t.zeilen) for t in tabellen},
        "kodierung_tabellen": ENCODING,
        "validierung": "index.xml nicht gegen IDEA/DTD validiert",
    }
