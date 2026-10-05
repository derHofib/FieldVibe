"""Soll-Arbeitszeit, Feiertage und Ueberstundensaldo
(docs/konzepte/ZEITERFASSUNG.md, Abschnitt "Soll-Zeit, Feiertage,
Ueberstundensaldo"). Berechnung bewusst als reine Funktionen ohne DB-Zugriff;
die Route laedt die Zeilen und reicht sie hier durch."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable, Protocol

from app.core.zeit import in_lokal
from app.models.arbeitszeit import ARBEITSZEIT_WOCHENTAG_SPALTEN
from app.schemas.zeiterfassung import ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT

SALDO_MAX_TAGE = 366
_ZWEI_STELLEN = Decimal("0.01")
_NULL = Decimal("0.00")

# Bundeslaender None = bundesweit.
# Regional begrenzte Feiertage (z. B. Mariae Himmelfahrt in Teilen Bayerns,
# Fronleichnam in Teilen Sachsens/Thueringens, Augsburger Friedensfest)
# bleiben absichtlich draussen -- das Bundesland allein reicht dafuer nicht;
# der Mandant ergaenzt sie manuell.
_FESTE_FEIERTAGE: tuple[tuple[int, int, str, frozenset[str] | None, int], ...] = (
    # (Monat, Tag, Bezeichnung, Bundeslaender, ab Jahr)
    (1, 1, "Neujahr", None, 0),
    (1, 6, "Heilige Drei Könige", frozenset({"BW", "BY", "ST"}), 0),
    (3, 8, "Internationaler Frauentag", frozenset({"BE"}), 2019),
    (3, 8, "Internationaler Frauentag", frozenset({"MV"}), 2023),
    (5, 1, "Tag der Arbeit", None, 0),
    (8, 15, "Mariä Himmelfahrt", frozenset({"SL"}), 0),
    (9, 20, "Weltkindertag", frozenset({"TH"}), 2019),
    (10, 3, "Tag der Deutschen Einheit", None, 0),
    (10, 31, "Reformationstag", frozenset({"BB", "MV", "SN", "ST", "TH"}), 0),
    (10, 31, "Reformationstag", frozenset({"HB", "HH", "NI", "SH"}), 2018),
    (11, 1, "Allerheiligen", frozenset({"BW", "BY", "NW", "RP", "SL"}), 0),
    (12, 25, "1. Weihnachtstag", None, 0),
    (12, 26, "2. Weihnachtstag", None, 0),
)
_FRONLEICHNAM_LAENDER = frozenset({"BW", "BY", "HE", "NW", "RP", "SL"})


def ostersonntag(jahr: int) -> date:
    """Gaussche Osterformel in der Variante nach Meeus/Jones/Butcher
    (gregorianischer Kalender)."""
    a = jahr % 19
    b, c = divmod(jahr, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    monat, tag = divmod(h + l - 7 * m + 114, 31)
    return date(jahr, monat, tag + 1)


def _buss_und_bettag(jahr: int) -> date:
    # Mittwoch vor dem 23. November (der 23. selbst zaehlt nicht).
    tag = date(jahr, 11, 22)
    return tag - timedelta(days=(tag.weekday() - 2) % 7)


def feiertage_fuer(bundesland: str | None, jahr: int) -> list[tuple[date, str]]:
    """Gesetzliche Feiertage des Bundeslands im Jahr, nach Datum sortiert.
    Ohne Bundesland (None) nur die bundesweiten."""
    ostern = ostersonntag(jahr)
    ergebnis: dict[date, str] = {
        ostern - timedelta(days=2): "Karfreitag",
        ostern + timedelta(days=1): "Ostermontag",
        ostern + timedelta(days=39): "Christi Himmelfahrt",
        ostern + timedelta(days=50): "Pfingstmontag",
    }
    if bundesland in _FRONLEICHNAM_LAENDER:
        ergebnis[ostern + timedelta(days=60)] = "Fronleichnam"
    if bundesland == "SN":
        ergebnis[_buss_und_bettag(jahr)] = "Buß- und Bettag"
    for monat, tag, bezeichnung, laender, ab_jahr in _FESTE_FEIERTAGE:
        if jahr < ab_jahr:
            continue
        if laender is None or bundesland in laender:
            ergebnis[date(jahr, monat, tag)] = bezeichnung
    return sorted(ergebnis.items())


class SollZeileLike(Protocol):
    gueltig_ab: date
    stunden_mo: Decimal
    stunden_di: Decimal
    stunden_mi: Decimal
    stunden_do: Decimal
    stunden_fr: Decimal
    stunden_sa: Decimal
    stunden_so: Decimal


def soll_fuer_tag(tag: date, soll_zeilen: Iterable[SollZeileLike], feiertage: Iterable[date] | set[date]) -> Decimal:
    """Soll-Stunden eines Kalendertags: die juengste Zeile mit gueltig_ab <=
    tag, deren Wert fuer den Wochentag; 0 ohne Zeile und an Feiertagen."""
    if tag in feiertage:
        return _NULL
    gueltige = [z for z in soll_zeilen if z.gueltig_ab <= tag]
    if not gueltige:
        return _NULL
    zeile = max(gueltige, key=lambda z: z.gueltig_ab)
    return Decimal(getattr(zeile, ARBEITSZEIT_WOCHENTAG_SPALTEN[tag.weekday()])).quantize(_ZWEI_STELLEN)


_ABWESENHEIT_RANG = {"freizeitausgleich": 1, "urlaub": 2, "krankheit": 3}


@dataclass(frozen=True)
class ZeitEintrag:
    start_at: datetime
    ende_at: datetime | None
    kategorie: str


@dataclass(frozen=True)
class SaldoTag:
    datum: date
    soll: Decimal
    ist: Decimal
    saldo: Decimal
    feiertag: bool
    abwesenheit: str | None


@dataclass(frozen=True)
class SaldoErgebnis:
    soll_stunden: Decimal
    ist_stunden: Decimal
    saldo_stunden: Decimal
    tage: list[SaldoTag]


def berechne_saldo(
    von: date,
    bis: date,
    soll_zeilen: list[SollZeileLike],
    feiertage: set[date],
    eintraege: Iterable[ZeitEintrag],
    jetzt: datetime,
) -> SaldoErgebnis:
    """Ist minus Soll je Kalendertag (inkl. von und bis), aufsummiert.

    Ein Eintrag zaehlt komplett am lokalen Tag seines Starts -- wie die
    bestehende Zeiterfassung (Statistik/Liste filtern nach start_at), auch
    ueber Mitternacht hinweg. Laufende Eintraege zaehlen bis jetzt.
    Urlaub/Krankheit machen den Tag zum erfuellten Soll (saldo 0, ist = soll);
    Freizeitausgleich nicht: sein Eintrag zaehlt nicht als Arbeitszeit und
    zieht seine Stunden vom Saldo ab. Ein ganzer Ausgleichstag ohne Arbeit hat
    ist 0 / saldo -soll; bei einem halben Tag gilt der uebrige Teil als erfuellt
    (ist = soll minus Ausgleichsstunden, saldo -Ausgleichsstunden), echte
    Mehrarbeit darueber zaehlt. Pausen zaehlen wie in der Statistik nicht als
    Arbeitszeit."""
    sekunden: dict[date, float] = {}
    abwesenheit: dict[date, str] = {}
    ausgleich_sekunden: dict[date, float] = {}
    for e in eintraege:
        tag = in_lokal(e.start_at).date()
        if e.kategorie == "freizeitausgleich" and e.ende_at is not None:
            dauer = max((e.ende_at - e.start_at).total_seconds(), 0.0)
            ausgleich_sekunden[tag] = ausgleich_sekunden.get(tag, 0.0) + dauer
        if e.kategorie in _ABWESENHEIT_RANG:
            # Bei mehreren am selben Tag gewinnt der hoechste Rang
            # (krankheit vor urlaub vor freizeitausgleich).
            bisher = abwesenheit.get(tag)
            if bisher is None or _ABWESENHEIT_RANG[e.kategorie] > _ABWESENHEIT_RANG[bisher]:
                abwesenheit[tag] = e.kategorie
        if e.kategorie in ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT:
            continue
        ende = e.ende_at or jetzt
        sekunden[tag] = sekunden.get(tag, 0.0) + max((ende - e.start_at).total_seconds(), 0.0)

    tage: list[SaldoTag] = []
    summe_soll = summe_ist = _NULL
    tag = von
    while tag <= bis:
        ist_feiertag = tag in feiertage
        soll = soll_fuer_tag(tag, soll_zeilen, feiertage)
        grund = abwesenheit.get(tag)
        if grund in ("urlaub", "krankheit"):
            ist = soll
        else:
            ist = (Decimal(sekunden.get(tag, 0.0)) / Decimal(3600)).quantize(_ZWEI_STELLEN)
            if grund == "freizeitausgleich":
                ausgleich = min(
                    (Decimal(ausgleich_sekunden.get(tag, 0.0)) / Decimal(3600)).quantize(_ZWEI_STELLEN), soll
                )
                ist = max(ist, soll - ausgleich)
        tage.append(SaldoTag(tag, soll, ist, ist - soll, ist_feiertag, grund))
        summe_soll += soll
        summe_ist += ist
        tag += timedelta(days=1)
    return SaldoErgebnis(summe_soll, summe_ist, summe_ist - summe_soll, tage)
