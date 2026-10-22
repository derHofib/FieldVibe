import csv
import io
from datetime import date
from decimal import Decimal

from app.services.csv_service import csv_response


def _zeilen(resp) -> list[list[str]]:
    text = resp.body.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text, newline=""), delimiter=";"))


def test_freitext_mit_formelanfang_wird_neutralisiert():
    resp = csv_response(
        ["Name"],
        [["=HYPERLINK(\"http://boese.example\")"], ["+cmd|' /C calc'!A0"], ["-2+3"], ["@SUMME(A1)"], ["\tTab"], ["Normal"]],
        "x.csv",
    )
    werte = [z[0] for z in _zeilen(resp)[1:]]
    assert werte[0].startswith("'=")
    assert werte[1].startswith("'+")
    assert werte[2] == "'-2+3"
    assert werte[3] == "'@SUMME(A1)"
    assert werte[4].startswith("'\t")
    assert werte[5] == "Normal"


def test_zahlen_und_datumsangaben_bleiben_unveraendert():
    resp = csv_response(
        ["Netto", "Menge", "Datum", "Saldo", "Text"],
        [["-12.50", "-1,5", "01.02.2026", "-1.234,56", "+49"], [Decimal("-3.10"), -7, date(2026, 2, 1), 0, None]],
        "x.csv",
    )
    erste, zweite = _zeilen(resp)[1:]
    assert erste[:4] == ["-12.50", "-1,5", "01.02.2026", "-1.234,56"]
    assert zweite[:4] == ["-3.10", "-7", "2026-02-01", "0"]


def test_kopfzeile_wird_ebenfalls_geschuetzt():
    resp = csv_response(["=Spalte"], [["x"]], "x.csv")
    assert _zeilen(resp)[0][0] == "'=Spalte"


def test_bereits_geschuetzter_wert_wird_nicht_doppelt_praefixiert():
    from app.services.csv_service import formel_sicher

    resp = csv_response(["A"], [[formel_sicher("=1+1")]], "x.csv")
    assert _zeilen(resp)[1][0] == "'=1+1"
