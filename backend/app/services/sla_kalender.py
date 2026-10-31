"""Geschaeftszeit-Rechnung fuer SLA-Fristen (docs/konzepte/SLA.md, Abschnitt 5).

Reine Funktionen ohne DB. Gerechnet wird in der lokalen Zeit des Mandanten, damit
Fenster wie "07:00-17:00" auch ueber den Sommerzeitwechsel stimmen; Ein- und
Ausgabe sind zeitzonenbehaftet (UTC speichern, hier nur rechnen).
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.arbeitszeit_service import feiertage_fuer

Fenster = tuple[time, time]

# Schutz vor Endlosschleife bei leerem Kalender (kein Fenster an keinem Wochentag).
_MAX_TAGE = 3660


class KalenderLeerFehler(ValueError):
    """Kalender ohne jedes Geschaeftszeit-Fenster: es laeuft nie eine Frist ab."""


@dataclass(frozen=True)
class SlaKalender:
    # Wochentag (0 = Montag) -> Fenster; fehlender Tag = kein Geschaeftsbetrieb.
    fenster: dict[int, tuple[Fenster, ...]] = field(default_factory=dict)
    rund_um_die_uhr: bool = False
    feiertage_ausnehmen: bool = True
    bundesland: str | None = None
    zeitzone: str = "Europe/Berlin"


def _feiertage(kal: SlaKalender, jahr: int, cache: dict[int, set[date]]) -> set[date]:
    if jahr not in cache:
        cache[jahr] = {t for t, _ in feiertage_fuer(kal.bundesland, jahr)}
    return cache[jahr]


def _fenster_ab(kal: SlaKalender, ab: datetime):
    """Fenster in Zeitreihenfolge, deren Ende nach `ab` liegt (ab-aware)."""
    zone = ZoneInfo(kal.zeitzone)
    tag = ab.astimezone(zone).date()
    cache: dict[int, set[date]] = {}
    for _ in range(_MAX_TAGE):
        frei = kal.feiertage_ausnehmen and tag in _feiertage(kal, tag.year, cache)
        if not frei:
            for von, bis in kal.fenster.get(tag.weekday(), ()):
                # In UTC wandeln: Differenzen gleicher tzinfo rechnen sonst in Wanduhrzeit
                # und verschlucken die Stunde des Zeitumstellungstags.
                s = datetime.combine(tag, von, tzinfo=zone).astimezone(timezone.utc)
                e = datetime.combine(tag, bis, tzinfo=zone).astimezone(timezone.utc)
                if e > ab:
                    yield s, e
        tag += timedelta(days=1)
    raise KalenderLeerFehler("Kalender enthaelt kein Geschaeftszeit-Fenster")


def add_geschaeftsminuten(start: datetime, minuten: int, kal: SlaKalender) -> datetime:
    """Zeitpunkt, an dem `minuten` Geschaeftszeit ab `start` verbraucht sind.
    Beginnt `start` ausserhalb eines Fensters, laeuft die Uhr erst im naechsten."""
    if minuten < 0:
        raise ValueError("minuten darf nicht negativ sein")
    start = start.astimezone(timezone.utc)
    if kal.rund_um_die_uhr:
        return start + timedelta(minutes=minuten)
    rest = timedelta(minutes=minuten)
    for s, e in _fenster_ab(kal, start):
        s = max(s, start)
        verfuegbar = e - s
        if rest <= verfuegbar:
            return s + rest
        rest -= verfuegbar
    raise AssertionError("unerreichbar")  # pragma: no cover


def geschaeftsminuten_zwischen(a: datetime, b: datetime, kal: SlaKalender) -> int:
    """Verbrauchte Geschaeftsminuten zwischen a und b (abgerundet, 0 wenn b <= a)."""
    a, b = a.astimezone(timezone.utc), b.astimezone(timezone.utc)
    if b <= a:
        return 0
    if kal.rund_um_die_uhr:
        return int((b - a).total_seconds() // 60)
    gesamt = timedelta()
    for s, e in _fenster_ab(kal, a):
        if s >= b:
            break
        gesamt += min(e, b) - max(s, a)
    return int(gesamt.total_seconds() // 60)


def fortschritt_prozent(start: datetime, faellig: datetime, jetzt: datetime, kal: SlaKalender) -> int:
    """Anteil der Frist, der bei `jetzt` verbraucht ist (fuer Eskalationsstufen)."""
    gesamt = geschaeftsminuten_zwischen(start, faellig, kal)
    if gesamt <= 0:
        return 100 if jetzt >= faellig else 0
    return int(geschaeftsminuten_zwischen(start, jetzt, kal) * 100 // gesamt)
