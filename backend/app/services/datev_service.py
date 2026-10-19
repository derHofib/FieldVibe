"""DATEV-Buchungsstapel: Stammdaten je Mandant, Personenkonten, Format.

ACHTUNG, NICHT GEGEN DIE SPEZIFIKATION GEPRUEFT: Header-Aufbau (31 Felder,
Formatversion 13 / Versionsnr. 700), Spaltenkoepfe, Feldlaengen und
Quoting-Regeln sind aus dem Gedaechtnis rekonstruiert (kein Netzzugriff auf die
DATEV-Developer-Doku). Annahmen im Einzelnen: docs/konzepte/DATEV.md. Vor dem
ersten produktiven Einsatz muss ein Testimport beim Steuerberater erfolgen.
"""
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Sequence
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kunde import Kunde
from app.models.lieferant import Lieferant
from app.models.mandant import Mandant

FORMATVERSION = 13
VERSIONSNUMMER = 700
HERKUNFT = "FV"
EXPORTIERT_VON = "FieldVibe"

MAX_BELEGFELD1 = 36
MAX_BUCHUNGSTEXT = 60
MAX_BEZEICHNUNG = 30

# Spaltenkoepfe 1-14 (feste Position laut DATEV). Weitere Spalten (Postensperre,
# Beleginfos, ...) werden bewusst nicht ausgegeben; DATEV erlaubt es, die
# hinteren Felder wegzulassen.
SPALTENKOEPFE = (
    "Umsatz (ohne Soll/Haben-Kz)",
    "Soll/Haben-Kennzeichen",
    "WKZ Umsatz",
    "Kurs",
    "Basis-Umsatz",
    "WKZ Basis-Umsatz",
    "Konto",
    "Gegenkonto (ohne BU-Schlüssel)",
    "BU-Schlüssel",
    "Belegdatum",
    "Belegfeld 1",
    "Belegfeld 2",
    "Skonto",
    "Buchungstext",
)

# Defaults je Kontenrahmen. SKR03 entspricht dem bisherigen Verhalten; die
# SKR04-Werte sind aus dem Gedaechtnis und muessen vom Steuerberater bestaetigt
# werden. Alles 4-stellig, wird auf die Sachkontenlaenge aufgefuellt.
ERLOESKONTO_NACH_SATZ = {
    "SKR03": {"19.00": "8400", "7.00": "8300"},
    "SKR04": {"19.00": "4400", "7.00": "4300"},
}
KLEINUNTERNEHMER_ERLOESKONTO = {"SKR03": "8400", "SKR04": "4400"}
AUFWANDSKONTO_NACH_KATEGORIE = {
    "SKR03": {
        "wareneinkauf": "3200",
        "betriebskosten": "4900",
        "miete": "4210",
        "personal": "4120",
        "fahrzeug": "4530",
        "versicherung": "4360",
        "sonstiges": "4900",
    },
    "SKR04": {
        "wareneinkauf": "5200",
        "betriebskosten": "6300",
        "miete": "6310",
        "personal": "6020",
        "fahrzeug": "6530",
        "versicherung": "6400",
        "sonstiges": "6300",
    },
}


class DatevKonfigurationFehler(Exception):
    """Der Export ist mit der Mandantenkonfiguration nicht moeglich; die Route
    macht daraus ein 422 mit der Meldung."""


class DatevStammdatenFehlen(DatevKonfigurationFehler):
    # Der Text-Anker "DATEV-Stammdaten unvollständig" wird vom Frontend
    # erkannt (utils/datev.ts), um den Link zu den Einstellungen zu zeigen.
    def __init__(self, fehlend: Sequence[str]):
        self.fehlend = tuple(fehlend)
        super().__init__(
            f"DATEV-Stammdaten unvollständig: {' und '.join(fehlend)} nicht hinterlegt – "
            "bitte unter Einstellungen ➝ Buchhaltung (DATEV) eintragen"
        )


@dataclass(frozen=True)
class DatevStammdaten:
    berater_nr: int
    mandant_nr: int
    wirtschaftsjahr_beginn_monat: int
    kontenrahmen: str
    sachkontenlaenge: int


def _buchhaltung(mandant: Mandant) -> dict:
    rohwert = (mandant.firmendaten or {}).get("buchhaltung")
    return rohwert if isinstance(rohwert, dict) else {}


def _als_int(wert: object) -> int | None:
    try:
        return int(wert) if wert not in (None, "") and not isinstance(wert, bool) else None
    except (TypeError, ValueError):
        return None


def sachkontenlaenge_von(mandant: Mandant) -> int:
    return _als_int(_buchhaltung(mandant).get("sachkontenlaenge")) or 4


def stammdaten_lesen(mandant: Mandant) -> DatevStammdaten:
    """Berater- und Mandantennummer haben bewusst keinen Default: ein geratener
    Wert wuerde den Stapel beim falschen Mandanten im Kanzlei-System landen
    lassen."""
    buchhaltung = _buchhaltung(mandant)
    berater = _als_int(buchhaltung.get("berater_nr"))
    mandant_nr = _als_int(buchhaltung.get("mandant_nr"))
    fehlend = [name for name, wert in (("Beraternummer", berater), ("Mandantennummer", mandant_nr)) if not wert]
    if fehlend:
        raise DatevStammdatenFehlen(fehlend)
    kontenrahmen = buchhaltung.get("kontenrahmen")
    return DatevStammdaten(
        berater_nr=berater,
        mandant_nr=mandant_nr,
        wirtschaftsjahr_beginn_monat=_als_int(buchhaltung.get("wirtschaftsjahr_beginn_monat")) or 1,
        kontenrahmen=kontenrahmen if kontenrahmen in ERLOESKONTO_NACH_SATZ else "SKR03",
        sachkontenlaenge=sachkontenlaenge_von(mandant),
    )


def sachkonto(konto: str, stammdaten: DatevStammdaten, *, bezeichnung: str) -> str:
    """Sachkonten haben genau Sachkontenlaenge Stellen (laengere Nummern waeren
    fuer DATEV Personenkonten). 4-stellige Defaults werden rechts mit Nullen
    aufgefuellt, konfigurierte Konten muessen passen -- ein stilles Kuerzen oder
    Auffuellen wuerde falsch buchen."""
    if len(konto) != stammdaten.sachkontenlaenge:
        raise DatevKonfigurationFehler(
            f"{bezeichnung}: Konto {konto} hat {len(konto)} Stellen, die Sachkontenlänge ist "
            f"{stammdaten.sachkontenlaenge} – bitte unter Einstellungen ➝ Buchhaltung (DATEV) angleichen"
        )
    return konto


def standardkonto(konto4: str, stammdaten: DatevStammdaten) -> str:
    return konto4.ljust(stammdaten.sachkontenlaenge, "0")


# --- Personenkonten -----------------------------------------------------------


def personenkonto_bereich(art: str, sachkontenlaenge: int) -> tuple[int, int]:
    """Debitoren 10000-69999, Kreditoren 70000-99999 (bei Sachkontenlaenge 4;
    sonst entsprechend mit mehr Stellen: Personenkonten sind immer
    Sachkontenlaenge + 1 Stellen lang)."""
    basis = 10**sachkontenlaenge
    if art == "debitor":
        return basis, 7 * basis - 1
    return 7 * basis, 10 * basis - 1


def kreditoren_sammelkonto(sachkontenlaenge: int) -> str:
    """Erste Kreditorennummer: Sammelkonto fuer Eingangsrechnungen ohne
    Lieferantenstamm (Freitext-Lieferant). Wird nie an einen Lieferanten
    vergeben."""
    return str(personenkonto_bereich("kreditor", sachkontenlaenge)[0])


def personenkonto_pruefen(konto: str, art: str, sachkontenlaenge: int) -> None:
    """Fuer manuell gesetzte Konten (Kunden-/Lieferantenformular)."""
    name = "Debitorenkonto" if art == "debitor" else "Kreditorenkonto"
    start, ende = personenkonto_bereich(art, sachkontenlaenge)
    if len(konto) != sachkontenlaenge + 1 or not konto.isdigit() or not start <= int(konto) <= ende:
        raise ValueError(
            f"{name} muss {sachkontenlaenge + 1} Ziffern im Bereich {start} bis {ende} haben "
            f"(Sachkontenlänge {sachkontenlaenge})"
        )
    if art == "kreditor" and konto == kreditoren_sammelkonto(sachkontenlaenge):
        raise ValueError(f"Kreditorenkonto {konto} ist als Sammelkonto für Eingangsrechnungen ohne Lieferant reserviert")


async def personenkonto_fuer_mandant_pruefen(session: AsyncSession, mandant_id: UUID, konto: str, art: str) -> None:
    mandant = await session.get(Mandant, mandant_id)
    personenkonto_pruefen(konto, art, sachkontenlaenge_von(mandant))


_MAX_VERSUCHE = 5


async def _konten_vergeben(
    session: AsyncSession,
    mandant_id: UUID,
    objekte: Sequence,
    *,
    modell,
    spalte: str,
    art: str,
    sachkontenlaenge: int,
    wunschkonto: Callable[[object], str | None] = lambda _o: None,
) -> None:
    """Vergibt jedem Objekt ohne Konto das naechste freie im Bereich (oder sein
    Wunschkonto, falls frei). Ein Advisory-Lock je Mandant und Art serialisiert
    parallele Exporte bis zum Commit; der Teil-Unique-Index faengt zusaetzlich
    manuelle Eintraege ab, die den Lock nicht nehmen (dann neuer Versuch)."""
    offen = [o for o in objekte if getattr(o, spalte) is None]
    if not offen:
        return
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:schluessel, 0))"),
        {"schluessel": f"datev-{art}:{mandant_id}"},
    )
    start, ende = personenkonto_bereich(art, sachkontenlaenge)
    spaltenattr = getattr(modell, spalte)
    for _ in range(_MAX_VERSUCHE):
        # Ein paralleler Export kann zwischenzeitlich vergeben haben.
        for objekt in offen:
            await session.refresh(objekt)
        offen = [o for o in offen if getattr(o, spalte) is None]
        if not offen:
            return
        belegt = set(
            (await session.execute(select(spaltenattr).where(modell.mandant_id == mandant_id, spaltenattr.isnot(None))))
            .scalars()
            .all()
        )
        if art == "kreditor":
            belegt.add(kreditoren_sammelkonto(sachkontenlaenge))
        zeiger = start
        zuteilung = []
        for objekt in sorted(offen, key=lambda o: (o.created_at, str(o.id))):
            wunsch = wunschkonto(objekt)
            if wunsch and len(wunsch) == sachkontenlaenge + 1 and start <= int(wunsch) <= ende and wunsch not in belegt:
                konto = wunsch
            else:
                while str(zeiger) in belegt:
                    zeiger += 1
                if zeiger > ende:
                    raise DatevKonfigurationFehler(
                        f"Im Bereich {start} bis {ende} ist kein {'Debitoren' if art == 'debitor' else 'Kreditoren'}konto "
                        "mehr frei"
                    )
                konto = str(zeiger)
            belegt.add(konto)
            zuteilung.append((objekt, konto))
        try:
            async with session.begin_nested():
                for objekt, konto in zuteilung:
                    setattr(objekt, spalte, konto)
                await session.flush()
            return
        except IntegrityError:
            continue
    raise DatevKonfigurationFehler("Personenkonten konnten nicht vergeben werden – bitte den Export wiederholen")


def _numerische_kundennummer(kunde: Kunde) -> str | None:
    nummer = kunde.kundennummer.strip()
    return nummer if nummer.isascii() and nummer.isdigit() else None


async def debitorenkonten_vergeben(
    session: AsyncSession, mandant_id: UUID, kunden: Sequence[Kunde], sachkontenlaenge: int
) -> None:
    """Regel: numerische Kundennummer, wenn sie genau Sachkontenlaenge + 1 Stellen
    hat, im Debitorenbereich liegt und frei ist; sonst die kleinste freie Nummer
    ab dem Bereichsanfang (10000)."""
    await _konten_vergeben(
        session,
        mandant_id,
        kunden,
        modell=Kunde,
        spalte="debitorenkonto",
        art="debitor",
        sachkontenlaenge=sachkontenlaenge,
        wunschkonto=_numerische_kundennummer,
    )


async def kreditorenkonten_vergeben(
    session: AsyncSession, mandant_id: UUID, lieferanten: Sequence[Lieferant], sachkontenlaenge: int
) -> None:
    await _konten_vergeben(
        session,
        mandant_id,
        lieferanten,
        modell=Lieferant,
        spalte="kreditorenkonto",
        art="kreditor",
        sachkontenlaenge=sachkontenlaenge,
    )


# --- Format ---------------------------------------------------------------------


def betrag(wert) -> str:
    """Komma statt Punkt, keine Tausenderpunkte, immer positiv -- die Richtung
    steht allein im Soll/Haben-Kennzeichen."""
    return f"{abs(wert):.2f}".replace(".", ",")


def _cp1252_zeichen(zeichen: str) -> str:
    try:
        zeichen.encode("cp1252")
        return zeichen
    except UnicodeEncodeError:
        pass
    # Akzentbuchstaben ausserhalb von CP1252 (z. B. "ő") auf den Grundbuchstaben
    # zurueckfuehren, alles andere wird "?" -- der Export darf nie abbrechen.
    zerlegt = "".join(z for z in unicodedata.normalize("NFKD", zeichen) if not unicodedata.combining(z))
    try:
        zerlegt.encode("cp1252")
        return zerlegt or "?"
    except UnicodeEncodeError:
        return "?"


def bereinigen(wert: str, max_laenge: int | None = None) -> str:
    """Steuer- und Zeilenumbruchzeichen entfernen, auf CP1252-darstellbare
    Zeichen bringen und auf die Feldlaenge kuerzen (nach der Ersetzung, damit
    die Laenge in Zeichen der Zieldatei stimmt)."""
    sauber = "".join(" " if unicodedata.category(z) == "Cc" else _cp1252_zeichen(z) for z in wert).strip()
    return sauber[:max_laenge] if max_laenge else sauber


def _text(wert: str) -> str:
    return '"' + wert.replace('"', '""') + '"'


def wirtschaftsjahr_beginn(von: date, beginn_monat: int) -> date:
    jahr = von.year if von.month >= beginn_monat else von.year - 1
    return date(jahr, beginn_monat, 1)


def header_zeile(stammdaten: DatevStammdaten, von: date, bis: date, erzeugt: datetime) -> str:
    """31 Header-Felder (Formatversion 13). Reihenfolge aus dem Gedaechtnis:
    1 Kennzeichen, 2 Versionsnr., 3 Datenkategorie, 4 Formatname, 5 Formatversion,
    6 erzeugt am, 7 importiert, 8 Herkunft, 9 exportiert von, 10 importiert von,
    11 Berater, 12 Mandant, 13 WJ-Beginn, 14 Sachkontenlaenge, 15/16 Datum
    von/bis, 17 Bezeichnung, 18 Diktatkuerzel, 19 Buchungstyp (1 = Fibu),
    20 Rechnungslegungszweck, 21 Festschreibung, 22 WKZ, 23 reserviert,
    24 Derivatskennzeichen, 25/26 reserviert, 27 SKR, 28 Branchenloesungs-ID,
    29/30 reserviert, 31 Anwendungsinformation."""
    felder = [
        _text("EXTF"),
        str(VERSIONSNUMMER),
        "21",
        _text("Buchungsstapel"),
        str(FORMATVERSION),
        erzeugt.strftime("%Y%m%d%H%M%S%f")[:-3],
        "",
        _text(HERKUNFT),
        _text(EXPORTIERT_VON),
        "",
        str(stammdaten.berater_nr),
        str(stammdaten.mandant_nr),
        wirtschaftsjahr_beginn(von, stammdaten.wirtschaftsjahr_beginn_monat).strftime("%Y%m%d"),
        str(stammdaten.sachkontenlaenge),
        von.strftime("%Y%m%d"),
        bis.strftime("%Y%m%d"),
        _text(bereinigen(f"FieldVibe {von:%Y%m%d}-{bis:%Y%m%d}", MAX_BEZEICHNUNG)),
        _text(""),
        "1",
        "0",
        "0",
        _text("EUR"),
        "",
        _text(""),
        "",
        "",
        _text(stammdaten.kontenrahmen[3:]),
        "",
        "",
        _text(""),
        _text(""),
    ]
    return ";".join(felder)


@dataclass(frozen=True)
class Buchung:
    betrag: str
    soll_haben: str
    konto: str
    gegenkonto: str
    bu_schluessel: str
    belegdatum: date
    belegfeld1: str
    buchungstext: str


def buchungszeile(b: Buchung) -> str:
    felder = [
        b.betrag,
        _text(b.soll_haben),
        _text("EUR"),
        "",
        "",
        "",
        b.konto,
        b.gegenkonto,
        _text(b.bu_schluessel) if b.bu_schluessel else "",
        b.belegdatum.strftime("%d%m"),
        _text(bereinigen(b.belegfeld1, MAX_BELEGFELD1)),
        "",
        "",
        _text(bereinigen(b.buchungstext, MAX_BUCHUNGSTEXT)),
    ]
    return ";".join(felder)


def csv_bytes(stammdaten: DatevStammdaten, von: date, bis: date, erzeugt: datetime, buchungen: Sequence[Buchung]) -> bytes:
    zeilen = [
        header_zeile(stammdaten, von, bis, erzeugt),
        ";".join(_text(k) for k in SPALTENKOEPFE),
        *(buchungszeile(b) for b in buchungen),
    ]
    # Alle Zeichen sind durch bereinigen() bereits CP1252-tauglich; errors="replace"
    # ist nur das Netz gegen Felder, die nicht darueber laufen (Konten sind Ziffern).
    return ("\r\n".join(zeilen) + "\r\n").encode("cp1252", errors="replace")
