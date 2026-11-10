"""Ordnungszahlen und Zwischensummen der Angebotsgliederung.

Bewusst ohne DB-/Modell-Importe (Duck-Typing), damit auch der PDF-Dienst es
nutzen kann. Berechnet statt gespeichert: Umordnen/Loeschen verschiebt sonst
Nummern still."""
from decimal import Decimal

from app.services.steuer_service import runde_cent


def ist_titel(p) -> bool:
    return getattr(p, "zeilentyp", "position") == "titel"


def zeilensumme(p) -> Decimal:
    return Decimal("0") if ist_titel(p) else runde_cent(p.menge * p.einzelpreis)


def ordnungszahlen(positionen: list) -> dict:
    """id -> Ordnungszahl. Ebene-1-Titel "1", Ebene-2-Titel "1.1", Positionen
    "<Titel>.<n>"; Positionen vor dem ersten Titel zaehlen schlicht durch."""
    ergebnis: dict = {}
    titel_nr = [0, 0]
    aktueller_titel: str | None = None
    pos_zaehler = 0
    for p in sorted(positionen, key=lambda x: x.position):
        if ist_titel(p):
            if p.ebene == 1:
                titel_nr = [titel_nr[0] + 1, 0]
                oz = str(titel_nr[0])
            else:
                if titel_nr[0] == 0:
                    titel_nr[0] = 1
                titel_nr[1] += 1
                oz = f"{titel_nr[0]}.{titel_nr[1]}"
            ergebnis[p.id] = oz
            aktueller_titel = oz
            pos_zaehler = 0
        else:
            pos_zaehler += 1
            ergebnis[p.id] = f"{aktueller_titel}.{pos_zaehler}" if aktueller_titel else str(pos_zaehler)
    return ergebnis


def zwischensummen(positionen: list) -> dict:
    """titel-id -> Summe der gerundeten Zeilensummen bis zum naechsten Titel
    gleicher oder hoeherer Ebene (ein Ebene-1-Titel schliesst seine Ebene-2-
    Abschnitte mit ein)."""
    sortiert = sorted(positionen, key=lambda x: x.position)
    ergebnis: dict = {}
    for i, t in enumerate(sortiert):
        if not ist_titel(t):
            continue
        summe = Decimal("0")
        for p in sortiert[i + 1 :]:
            if ist_titel(p) and p.ebene <= t.ebene:
                break
            summe += zeilensumme(p)
        ergebnis[t.id] = summe
    return ergebnis
