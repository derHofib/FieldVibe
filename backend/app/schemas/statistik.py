from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class TechnikerOffeneVorgaenge(BaseModel):
    techniker_id: UUID
    techniker_name: str
    anzahl_offen: int


class VorgangKennzahlen(BaseModel):
    offene_vorgaenge_gesamt: int
    offene_vorgaenge_je_techniker: list[TechnikerOffeneVorgaenge]
    # None, wenn im betrachteten Zeitraum kein Vorgang abgeschlossen wurde --
    # ein Durchschnitt ueber 0 Werte waere sonst irrefuehrend 0.0 statt "keine
    # Daten".
    durchschnittliche_durchlaufzeit_tage: float | None
    abgeschlossene_vorgaenge_zeitraum: int


AggregatBereich = Literal["vorgaenge", "rechnungen"]
AggregatKennzahl = Literal[
    "anzahl_erstellt",
    "anzahl_abgeschlossen",
    "durchlaufzeit_tage",
    "arbeitszeit_stunden",
    "umsatz_netto",
    "umsatz_brutto",
    "anzahl",
]
AggregatGruppierung = Literal[
    "monat", "woche", "techniker", "kunde", "status", "leistungstyp", "prioritaet", "projekt"
]


class AggregatZeile(BaseModel):
    schluessel: str
    label: str
    wert: float


class AggregatAntwort(BaseModel):
    bereich: AggregatBereich
    kennzahl: AggregatKennzahl
    gruppierung: AggregatGruppierung
    von: date
    bis: date
    # Welches Datum den Zeitraum bestimmt -- je Kennzahl ein anderes, sonst
    # ist "Umsatz im Oktober" nicht eindeutig lesbar.
    datumsbezug: str
    zeilen: list[AggregatZeile]
    # Eigene Abfrage ohne Gruppierung, kein Zeilensumme: bei durchlaufzeit_tage
    # waere die Summe der Gruppenmittel sinnlos, und bei abgeschnittenen Zeilen
    # waere sie zu klein.
    gesamt: float
    # True, wenn es mehr als MAX_ZEILEN Gruppen gab und nur die ersten
    # (nach Sortierung) geliefert werden.
    abgeschnitten: bool = False
