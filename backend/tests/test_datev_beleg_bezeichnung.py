from types import SimpleNamespace

import pytest

from app.services.auswertung_service import _beleg_bezeichnung


@pytest.mark.parametrize(
    ("art", "storno", "erwartet"),
    [
        ("rechnung", False, "Rechnung"),
        ("abschlag", False, "Abschlag"),
        ("schluss", False, "Schlussrechnung"),
        ("gutschrift", False, "Gutschrift"),
        ("rechnung", True, "Storno"),
    ],
)
def test_buchungstext_nennt_die_belegart(art, storno, erwartet):
    assert _beleg_bezeichnung(SimpleNamespace(rechnungsart=art, ist_storno=storno, betrag_netto=100)) == erwartet


def test_negative_schlussrechnung_ist_guthaben():
    beleg = SimpleNamespace(rechnungsart="schluss", ist_storno=False, betrag_netto=-400)
    assert _beleg_bezeichnung(beleg) == "Schlussrechnung Guthaben"
