"""Einzige Wahrheit fuer die Steuer von Ausgangsrechnungen.

Netto/Steuer/Brutto werden nirgends persistiert, sondern ueberall aus den
Positionen berechnet -- in Python (steuer_gruppen) und, wo gefiltert/sortiert/
summiert wird, als SQL (netto_sql/steuer_sql/brutto_sql). Beide Wege bilden
dieselbe Regel ab, damit Liste, Detail, Summenzeile und Filter nie
auseinanderlaufen:

- Positionen werden nach (Steuerkategorie, Satz) gruppiert.
- Netto je Gruppe = Summe(menge * einzelpreis), auf Cent gerundet.
- Steuer je Gruppe = Gruppen-Netto * Satz / 100, auf Cent gerundet -- nie je
  Position (EN-16931-Konvention, sonst summieren sich Rundungsfehler).
- Gerundet wird kaufmaennisch (ROUND_HALF_UP, Postgres round() auf numeric
  rundet ebenso). Das Python-quantize() mit seinem Standard HALF_EVEN haette
  an exakten Halb-Cent-Faellen von der SQL-Seite abgewichen.
- Ohne Positionen (einfache Abschlussrechnung aus Phase 6) bildet
  betrag_netto mit mwst_satz des Belegs die einzige Gruppe.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.sql.elements import ColumnElement

from app.models.rechnung import RECHNUNG_STEUER_KATEGORIEN, Rechnung, RechnungPosition

_CENT = Decimal("0.01")
_HUNDERT = Decimal("100")

# Reihenfolge der Gruppen in Anzeige und Auswertung.
_KATEGORIE_REIHENFOLGE = {kategorie: i for i, kategorie in enumerate(RECHNUNG_STEUER_KATEGORIEN)}

# Gating: welche Kategorien/Saetze per API angelegt werden duerfen. Z, E und
# AE brauchen vorher Mapping in UStVA/DATEV und Darstellung in PDF/E-Rechnung
# (Schritt 3); Kleinunternehmer (E/0) sind davon ausgenommen und werden
# serverseitig erzwungen.
FREIGEGEBENE_STEUER_KATEGORIEN = ("S",)
ERLAUBTE_REGELSAETZE = (Decimal("19.00"), Decimal("7.00"))


class SteuerFehler(ValueError):
    """Unzulaessige Steuerangabe an einer Position -- die Routen machen daraus
    ein 422 mit der (deutschen) Meldung."""


def runde_cent(wert: Decimal) -> Decimal:
    return Decimal(wert).quantize(_CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class SteuerGruppe:
    kategorie: str
    satz: Decimal
    netto: Decimal
    steuer: Decimal

    @property
    def brutto(self) -> Decimal:
        return self.netto + self.steuer


def _satz(wert: Decimal) -> Decimal:
    return Decimal(wert).quantize(_CENT)


def kategorie_fuer_beleg_satz(satz: Decimal) -> str:
    """Kategorie einer Position, die nur den Satz des Belegs erbt. Satz 0 ist
    Kleinunternehmer-Bestand und wird wie bisher als Befreiung (E) gefuehrt."""
    return "E" if satz == 0 else "S"


def steuer_gruppen(rechnung: Rechnung, positionen: Iterable[RechnungPosition]) -> list[SteuerGruppe]:
    positionen = list(positionen)
    if not positionen:
        satz = _satz(rechnung.mwst_satz)
        netto = runde_cent(rechnung.betrag_netto)
        return [SteuerGruppe(kategorie_fuer_beleg_satz(satz), satz, netto, runde_cent(netto * satz / _HUNDERT))]

    summen: dict[tuple[str, Decimal], Decimal] = {}
    for p in positionen:
        # Nicht gespeicherte Positionen (z. B. im Speicher gebaute Vorschau-
        # Positionen) haben noch keine Steuerfelder und erben vom Beleg.
        satz = _satz(rechnung.mwst_satz if p.steuer_satz is None else p.steuer_satz)
        schluessel = (p.steuer_kategorie or kategorie_fuer_beleg_satz(satz), satz)
        summen[schluessel] = summen.get(schluessel, Decimal("0")) + p.menge * p.einzelpreis
    gruppen = [
        SteuerGruppe(kategorie, satz, runde_cent(roh), runde_cent(runde_cent(roh) * satz / _HUNDERT))
        for (kategorie, satz), roh in summen.items()
    ]
    gruppen.sort(key=lambda g: (_KATEGORIE_REIHENFOLGE[g.kategorie], -g.satz))
    return gruppen


def netto_summe(gruppen: Iterable[SteuerGruppe]) -> Decimal:
    return sum((g.netto for g in gruppen), Decimal("0")).quantize(_CENT)


def steuer_summe(gruppen: Iterable[SteuerGruppe]) -> Decimal:
    return sum((g.steuer for g in gruppen), Decimal("0")).quantize(_CENT)


def brutto_summe(gruppen: Iterable[SteuerGruppe]) -> Decimal:
    return sum((g.brutto for g in gruppen), Decimal("0")).quantize(_CENT)


def ist_kleinunternehmer(mandant) -> bool:
    return bool((mandant.firmendaten or {}).get("ist_kleinunternehmer"))


def beleg_vorbelegung(beleg_mwst_satz: Decimal, *, kleinunternehmer: bool) -> tuple[str, Decimal]:
    """Steuerfelder einer Position ohne eigene Angabe: Kleinunternehmer immer
    E/0, sonst der Satz des Belegs (siehe kategorie_fuer_beleg_satz)."""
    satz = Decimal("0.00") if kleinunternehmer else _satz(beleg_mwst_satz)
    return kategorie_fuer_beleg_satz(satz), satz


def _pruefe_freigabe(kategorie: str, satz: Decimal) -> None:
    if kategorie not in RECHNUNG_STEUER_KATEGORIEN:
        raise SteuerFehler(f"Steuerkategorie {kategorie} ist unbekannt")
    if kategorie not in FREIGEGEBENE_STEUER_KATEGORIEN:
        raise SteuerFehler(f"Steuerkategorie {kategorie} ist noch nicht freigeschaltet")
    if kategorie != "S":
        if satz != 0:
            raise SteuerFehler(f"Bei Steuerkategorie {kategorie} muss der Steuersatz 0 sein")
        return
    if _satz(satz) not in ERLAUBTE_REGELSAETZE:
        erlaubt = " und ".join(f"{s:f}".rstrip("0").rstrip(".") + " %" for s in ERLAUBTE_REGELSAETZE)
        raise SteuerFehler(
            f"Steuersatz {satz:f} % ist bei Steuerkategorie S nicht erlaubt (erlaubt: {erlaubt})"
        )


def loese_steuer_auf(
    *,
    kategorie: str | None,
    satz: Decimal | None,
    beleg_mwst_satz: Decimal,
    kleinunternehmer: bool,
) -> tuple[str, Decimal]:
    """Steuerfelder einer neu angelegten Position aus API-Angaben. Fehlt beides,
    gilt die Vorbelegung aus dem Beleg; ein daraus entstehender Satz
    ausserhalb der Regelsaetze wird wie eine explizite Angabe abgelehnt. Die
    geerbte Befreiung E/0 (Beleg mit Satz 0) ist Altverhalten und bleibt
    zulaessig."""
    if kleinunternehmer:
        return "E", Decimal("0.00")
    if kategorie is None and satz is None:
        kategorie_v, satz_v = beleg_vorbelegung(beleg_mwst_satz, kleinunternehmer=False)
        if kategorie_v != "E":
            _pruefe_freigabe(kategorie_v, satz_v)
        return kategorie_v, satz_v
    kategorie = kategorie or "S"
    if satz is None:
        satz = _satz(beleg_mwst_satz) if kategorie == "S" else Decimal("0.00")
    _pruefe_freigabe(kategorie, satz)
    return kategorie, _satz(satz)


def aendere_steuer(
    *,
    aktuell_kategorie: str,
    aktuell_satz: Decimal,
    kategorie: str | None,
    satz: Decimal | None,
    kleinunternehmer: bool,
) -> tuple[str, Decimal]:
    """Steuerfelder einer bestehenden Position nach PATCH. Nicht angegebene
    Felder bleiben; wechselt nur die Kategorie auf eine ohne Satz, wird der
    Satz 0."""
    if kleinunternehmer:
        return "E", Decimal("0.00")
    neue_kategorie = kategorie or aktuell_kategorie
    if satz is not None:
        neuer_satz = satz
    elif neue_kategorie != "S":
        neuer_satz = Decimal("0.00")
    else:
        neuer_satz = aktuell_satz
    _pruefe_freigabe(neue_kategorie, neuer_satz)
    return neue_kategorie, _satz(neuer_satz)


# --- SQL-Gegenstuecke -------------------------------------------------------


def _gruppen_summe(je_gruppe) -> ColumnElement:
    """Summe von je_gruppe(netto, satz) ueber die Steuergruppen eines Belegs.
    Die innere Aggregation je (Kategorie, Satz) rundet das Gruppen-Netto
    (menge*einzelpreis vergroessert in Postgres die Skala auf 4); die aeussere
    Summe addiert die gerundeten Gruppenwerte -- exakt wie steuer_gruppen()."""
    gruppen = (
        select(
            func.round(func.sum(RechnungPosition.menge * RechnungPosition.einzelpreis), 2).label("netto"),
            RechnungPosition.steuer_satz.label("satz"),
        )
        .where(RechnungPosition.rechnung_id == Rechnung.id)
        .group_by(RechnungPosition.steuer_kategorie, RechnungPosition.steuer_satz)
        .correlate(Rechnung)
        .subquery()
    )
    return select(func.sum(je_gruppe(gruppen.c.netto, gruppen.c.satz))).scalar_subquery()


def _steuer_von(netto, satz) -> ColumnElement:
    return func.round(netto * satz / _HUNDERT, 2)


def netto_sql() -> ColumnElement:
    """Fallback ohne Positionen: betrag_netto des Belegs (coalesce, weil die
    Gruppensumme nur ohne Positionen NULL ist)."""
    return func.coalesce(_gruppen_summe(lambda netto, satz: netto), func.round(Rechnung.betrag_netto, 2))


def steuer_sql() -> ColumnElement:
    return func.coalesce(
        _gruppen_summe(_steuer_von),
        _steuer_von(func.round(Rechnung.betrag_netto, 2), Rechnung.mwst_satz),
    )


def brutto_sql() -> ColumnElement:
    return func.coalesce(
        _gruppen_summe(lambda netto, satz: netto + _steuer_von(netto, satz)),
        func.round(Rechnung.betrag_netto, 2) + _steuer_von(func.round(Rechnung.betrag_netto, 2), Rechnung.mwst_satz),
    )
