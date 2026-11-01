"""Gemeinsame Helfer der DATEV-Export-Tests: Stammdaten (ohne Berater-/Mandantennummer
laeuft der Export nicht) und die Spaltenpositionen des Buchungsstapels."""
import csv
import io

STAMMDATEN = {"berater_nr": 29098, "mandant_nr": 55003}

# Spaltenindizes der Buchungszeilen (Position 1-14 laut DATEV, nullbasiert).
UMSATZ, SH, WKZ, KURS, BASIS, WKZ_BASIS, KONTO, GEGENKONTO, BU, BELEGDATUM, BELEG1, BELEG2, SKONTO, TEXT = range(14)


def buchhaltung(**zusatz) -> dict:
    """firmendaten fuer PATCH /api/mandant/einstellungen. Das Backend ersetzt
    `buchhaltung` als Ganzes, deshalb gehoeren Stammdaten und Erloeskonten in
    denselben Aufruf."""
    return {"buchhaltung": {**STAMMDATEN, **zusatz}}


async def stammdaten_setzen(client, h, **zusatz) -> None:
    antwort = await client.patch("/api/mandant/einstellungen", headers=h, json={"firmendaten": buchhaltung(**zusatz)})
    assert antwort.status_code == 200, antwort.text


def parse(antwort_text: str) -> tuple[list[str], list[str], list[list[str]]]:
    """(Header, Spaltenkoepfe, Buchungszeilen) eines Exports."""
    zeilen = list(csv.reader(io.StringIO(antwort_text), delimiter=";"))
    return zeilen[0], zeilen[1], zeilen[2:]
