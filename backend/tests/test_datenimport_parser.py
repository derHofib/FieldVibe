from datetime import date
from decimal import Decimal

import pytest

from app.services.datenimport import werte
from app.services.datenimport.felder import ANLAGEN, KUNDEN, MATERIAL, schlage_zuordnung_vor
from app.services.datenimport.parser import ImportDateiFehler, Limits, lese_tabelle

LIMITS = Limits(max_bytes=1_000_000, max_zeilen=100, max_spalten=20, max_zellenlaenge=200, max_unkomprimiert=10_000_000, zeitlimit_sekunden=10)


@pytest.mark.parametrize(
    "text,erwartet",
    [("1.234,56", "1234.56"), ("1234,56", "1234.56"), ("1,234.56", "1234.56"), ("12.5", "12.5"), ("1.234", "1234"),
     ("1'234.50", "1234.50"), ("12,5 €", "12.5"), ("-3,5", "-3.5"), ("0,99", "0.99")],
)
def test_dezimal(text, erwartet):
    assert werte.parse_dezimal(text) == Decimal(erwartet)


@pytest.mark.parametrize("text", ["abc", "1,2,3x", "1.2.3"])
def test_dezimal_ungueltig(text):
    with pytest.raises(ValueError):
        werte.parse_dezimal(text)


@pytest.mark.parametrize(
    "text,erwartet",
    [("15.03.2025", date(2025, 3, 15)), ("2025-03-15", date(2025, 3, 15)), ("1.3.25", date(2025, 3, 1)),
     ("15/03/1999", date(1999, 3, 15)), ("45000", date(2023, 3, 15)), ("20250315", date(2025, 3, 15))],
)
def test_datum(text, erwartet):
    assert werte.parse_datum(text) == erwartet


def test_datum_ungueltig():
    for t in ("31.02.2025", "gestern", "13.13.2020"):
        with pytest.raises(ValueError):
            werte.parse_datum(t)


def test_schluessel_und_ust():
    assert werte.schluessel("Müller & Söhne GmbH") == werte.schluessel("mueller soehne gmbh")
    assert werte.ust_idnr_normalisieren("de 123.456.789") == ("DE123456789", True)
    assert werte.ust_idnr_normalisieren("DE12")[1] is False


def test_csv_leer_und_nur_kopf():
    with pytest.raises(ImportDateiFehler):
        lese_tabelle(b"", "a.csv", LIMITS)
    with pytest.raises(ImportDateiFehler):
        lese_tabelle(b"a;b\n", "a.csv", LIMITS)


def test_csv_sep_zeile_und_ragged():
    t = lese_tabelle(b"sep=,\nA,B\n1\n2,3,4\n\n", "a.csv", LIMITS)
    assert t.trennzeichen == "," and t.kopf == ["A", "B", "Spalte 3"]
    assert t.zeilen == [["1", "", ""], ["2", "3", "4"]]


def test_doppelte_kopfzeilen_und_zellenlimit():
    t = lese_tabelle(b"A;A\n1;2\n", "a.csv", LIMITS)
    assert t.kopf == ["A", "A (2)"]
    with pytest.raises(ImportDateiFehler):
        lese_tabelle(b"A\n" + b"x" * 500, "a.csv", LIMITS)


def test_xlsx_zipbombe_und_makros():
    import io
    import zipfile

    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/workbook.xml", "<x/>")
        z.writestr("xl/sheet.xml", b"0" * 5_000_000)
    klein = Limits(**{**LIMITS.__dict__, "max_unkomprimiert": 1_000_000})
    with pytest.raises(ImportDateiFehler, match="entpackt"):
        lese_tabelle(puffer.getvalue(), "b.xlsx", klein)
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("xl/workbook.xml", "<x/>")
        z.writestr("xl/vbaProject.bin", b"x")
    with pytest.raises(ImportDateiFehler, match="Makros"):
        lese_tabelle(puffer.getvalue(), "b.xlsx", LIMITS)
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("xl/workbook.xml", '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x/>')
    with pytest.raises(ImportDateiFehler, match="XML"):
        lese_tabelle(puffer.getvalue(), "b.xlsx", LIMITS)


def test_zuordnungsvorschlag():
    kopf = ["Kd-Nr", "Firma", "Straße", "PLZ", "Ort", "E-Mail", "Telefon", "USt-IdNr", "Bemerkung", "Egal"]
    v = {x.feld: x for x in schlage_zuordnung_vor(KUNDEN, kopf)}
    assert [v[f].spalte for f in ("kundennummer", "name", "strasse", "plz", "ort", "email", "telefon", "ust_idnr", "notiz")] == list(range(9))
    assert v["leitweg_id"].spalte is None
    spalten = [x.spalte for x in schlage_zuordnung_vor(KUNDEN, kopf) if x.spalte is not None]
    assert len(spalten) == len(set(spalten))
    m = {x.feld: x.spalte for x in schlage_zuordnung_vor(MATERIAL, ["Art.-Nr.", "Artikel", "Einkaufspreis", "VK", "Menge"])}
    assert m["artikelnummer"] == 0 and m["bezeichnung"] == 1 and m["einzelpreis"] == 3 and m["bestand"] == 4
    a = {x.feld: x.spalte for x in schlage_zuordnung_vor(ANLAGEN, ["Kunde", "Anlage", "Serien-Nr", "Letzte Prüfung", "Intervall"])}
    assert a["kundenname"] == 0 and a["bezeichnung"] == 1 and a["seriennummer"] == 2 and a["pruefintervall_monate"] == 4
