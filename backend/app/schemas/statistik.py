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
