"""Z3-Export (GDPdU-Beschreibungsstandard): Struktur von index.xml, Tabellen, Zeitraum, Rechte."""
import asyncio
import csv
import re
import io
import json
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
import pytest
from lxml import etree
from sqlalchemy import select, update

from app.db.session import system_session
from app.models.rechnung import Rechnung, RechnungPosition, RechnungZahlung
from app.services import export_job_service, z3_service
from tests.conftest import auth_headers, login


async def _fertig() -> None:
    tasks = export_job_service.hintergrund_tasks()
    if tasks:
        await asyncio.gather(*tasks)


async def _z3_laden(client, h, von: str, bis: str) -> zipfile.ZipFile:
    resp = await client.post("/api/exporte/z3", headers=h, json={"von": von, "bis": bis})
    assert resp.status_code == 202, resp.text
    await _fertig()
    export_id = resp.json()["id"]
    job = (await client.get(f"/api/exporte/{export_id}", headers=h)).json()
    assert job["status"] == "fertig", job
    dl = (await client.get(f"/api/exporte/{export_id}/download-url", headers=h)).json()
    async with httpx.AsyncClient() as http:
        return zipfile.ZipFile(io.BytesIO((await http.get(dl["url"])).content))


def _tabelle(archiv: zipfile.ZipFile, datei: str) -> list[list[str]]:
    text = archiv.read(datei).decode("cp1252")
    return list(csv.reader(io.StringIO(text), delimiter=";", quotechar='"'))


@pytest.mark.asyncio
async def test_z3_struktur_index_xml_und_tabellen(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant("Müller Elektrotechnik")
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Söhne & Töchter € GmbH", kundennummer="K-100")
    fremd = await make_mandant("Fremdbetrieb")
    fremd_kunde = await make_kunde(mandant=fremd, name="GEHEIM-FREMD", kundennummer="K-999")
    h = auth_headers(await login(client, admin.email, "pw-123456"))
    hf = auth_headers(await login(client, (await make_user(mandant=fremd, role="mandant_admin", password="pw-123456")).email, "pw-123456"))

    r = (
        await client.post(
            "/api/rechnungen", headers=h,
            json={"kunde_id": str(kunde.id), "positionen": [{"beschreibung": "Montage Schalter ä", "menge": "2", "einheit": "Std", "einzelpreis": "50.00"}]},
        )
    ).json()
    assert (await client.patch(f"/api/rechnungen/{r['id']}", headers=h, json={"status": "versendet"})).status_code == 200
    await client.post(f"/api/rechnungen/{r['id']}/zahlungen", headers=h, json={"betrag": "50.00", "zahlungsart": "bar"})
    # Entwurf (nicht enthalten) und fremder Betrieb.
    await client.post("/api/rechnungen", headers=h, json={"kunde_id": str(kunde.id), "betrag_netto": "5"})
    rf = (await client.post("/api/rechnungen", headers=hf, json={"kunde_id": str(fremd_kunde.id), "betrag_netto": "7"})).json()
    await client.patch(f"/api/rechnungen/{rf['id']}", headers=hf, json={"status": "versendet"})
    # Gutschrift (Teil) und Storno einer zweiten Rechnung.
    r2 = (await client.post("/api/rechnungen", headers=h, json={"kunde_id": str(kunde.id), "betrag_netto": "40"})).json()
    await client.patch(f"/api/rechnungen/{r2['id']}", headers=h, json={"status": "versendet"})
    await client.post(f"/api/rechnungen/{r2['id']}/storno", headers=h)

    heute = date.today()
    archiv = await _z3_laden(client, h, f"{heute.year}-01-01", f"{heute.year}-12-31")
    namen = set(archiv.namelist())
    assert {"index.xml", "README.txt", "manifest.json", "rechnungen.csv", "rechnungspositionen.csv", "zahlungen.csv",
            "kunden.csv", "eingangsrechnungen.csv", "konten.csv"} <= namen
    assert not any(n.endswith(".dtd") for n in namen)  # DTD wird bewusst nicht mitgeliefert

    # index.xml: Wohlgeformt, DOCTYPE verweist auf die Standard-DTD, Tabellen/Spalten passen zu den CSV.
    baum = etree.fromstring(archiv.read("index.xml"), etree.XMLParser(load_dtd=False, no_network=True)).getroottree()
    assert baum.docinfo.system_url == "gdpdu-01-09-2004.dtd" and baum.docinfo.root_name == "DataSet"
    assert baum.docinfo.encoding.lower() == "utf-8"
    wurzel = baum.getroot()
    assert wurzel.findtext("Version") == "1.0"
    assert wurzel.findtext("DataSupplier/Name") == "Müller Elektrotechnik"
    tabellen = wurzel.findall("Media/Table")
    assert [t.findtext("URL") for t in tabellen] == [
        "rechnungen.csv", "rechnungspositionen.csv", "zahlungen.csv", "kunden.csv", "eingangsrechnungen.csv", "konten.csv"
    ]
    for t in tabellen:
        assert t.findtext("DecimalSymbol") == ","
        assert t.findtext("Range/From") == "2"
        var = t.find("VariableLength")
        assert var.findtext("ColumnDelimiter") == ";" and var.findtext("TextEncapsulator") == '"'
        spalten = [e.findtext("Name") for e in var if e.tag in ("VariablePrimaryKey", "VariableColumn")]
        assert spalten == _tabelle(archiv, t.findtext("URL"))[0], t.findtext("URL")
    rechnungen_el = tabellen[0].find("VariableLength")
    typen = {e.findtext("Name"): [c.tag for c in e if c.tag not in ("Name", "Description")][0] for e in rechnungen_el if e.tag in ("VariablePrimaryKey", "VariableColumn")}
    assert typen["Rechnungsnummer"] == "AlphaNumeric" and typen["Rechnungsdatum"] == "Date" and typen["Brutto"] == "Numeric"
    assert rechnungen_el.find("VariableColumn[Name='Rechnungsdatum']/Date/Format").text == "DD.MM.YYYY"
    assert rechnungen_el.find("VariableColumn[Name='Brutto']/Numeric/Accuracy").text == "2"
    assert rechnungen_el.find("ForeignKey/References").text == "Kunden"

    # Tabellen: CP1252 (Umlaute, Euro bleiben erhalten), Dezimalkomma, Datum TT.MM.JJJJ.
    zeilen = _tabelle(archiv, "rechnungen.csv")
    kopf, daten = zeilen[0], zeilen[1:]
    spalte = {n: i for i, n in enumerate(kopf)}
    nummern = [z[spalte["Rechnungsnummer"]] for z in daten]
    assert r["rechnungsnummer"] in nummern
    ersterechnung = next(z for z in daten if z[spalte["Rechnungsnummer"]] == r["rechnungsnummer"])
    assert ersterechnung[spalte["Netto"]] == "100,00" and ersterechnung[spalte["Brutto"]] == "119,00"
    assert ersterechnung[spalte["Steuerbetrag"]] == "19,00"
    assert ersterechnung[spalte["Kundenname"]] == "Söhne & Töchter € GmbH"
    assert ersterechnung[spalte["Rechnungsdatum"]] == heute.strftime("%d.%m.%Y")
    # Entwurf fehlt; Original + Storno der zweiten Rechnung sind da (Storno mit Bezug).
    assert len(daten) == 3
    storno = next(z for z in daten if z[spalte["Storno"]] == "J")
    original2 = next(z for z in daten if z[spalte["Status"]] == "storniert")
    assert storno[spalte["Bezug_Rechnungsnummer"]] == original2[spalte["Rechnungsnummer"]]
    assert storno[spalte["Brutto"]] == "-47,60"

    positionen = _tabelle(archiv, "rechnungspositionen.csv")
    assert positionen[1][:6] == [r["rechnungsnummer"], "1", "Montage Schalter ä", "2,00", "Std", "50,00"]
    zahlungen = _tabelle(archiv, "zahlungen.csv")
    assert zahlungen[1] == [r["rechnungsnummer"], heute.strftime("%d.%m.%Y"), "50,00", "bar", "N"]

    kunden = _tabelle(archiv, "kunden.csv")
    assert [z[0] for z in kunden[1:]] == ["K-100"]
    alles = b"".join(archiv.read(n) for n in namen)
    assert b"GEHEIM-FREMD" not in alles and b"K-999" not in alles

    manifest = json.loads(archiv.read("manifest.json"))
    assert manifest["art"] == "z3" and manifest["kodierung_tabellen"] == "cp1252"
    assert "nicht gegen IDEA" in manifest["validierung"]
    readme = archiv.read("README.txt").decode("utf-8")
    assert "Z3" in readme and "kein unmittelbarer (Z1) oder mittelbarer (Z2)" in readme


@pytest.mark.asyncio
async def test_z3_zeitraum_und_nicht_darstellbare_zeichen(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant("Zeitraum GmbH")
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Emoji \U0001F600 Kunde")
    h = auth_headers(await login(client, admin.email, "pw-123456"))
    async with system_session() as session:
        for nr, tag in (("R-ALT", date(2023, 12, 31)), ("R-IN-1", date(2024, 1, 1)), ("R-IN-2", date(2024, 12, 31)), ("R-NEU", date(2025, 1, 1))):
            session.add(
                Rechnung(
                    mandant_id=mandant.id, kunde_id=kunde.id, rechnungsnummer=nr, betrag_netto=Decimal("10"),
                    mwst_satz=Decimal("19"), status="versendet", erstellt_von=admin.id,
                    versendet_am=datetime(tag.year, tag.month, tag.day, 12, 0, tzinfo=timezone.utc),
                )
            )
    archiv = await _z3_laden(client, h, "2024-01-01", "2024-12-31")
    nummern = [z[0] for z in _tabelle(archiv, "rechnungen.csv")[1:]]
    assert nummern == ["R-IN-1", "R-IN-2"]
    # Emoji ist in CP1252 nicht darstellbar: ersetzt und im README gezaehlt.
    assert _tabelle(archiv, "kunden.csv")[1][1] == "Emoji ? Kunde"
    assert re.search(r"durch \? ersetzt: [1-9]\d* Zeichen", archiv.read("README.txt").decode("utf-8"))


@pytest.mark.asyncio
async def test_z3_validierung_und_rechte(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant("Rechte GmbH")
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    h = auth_headers(await login(client, admin.email, "pw-123456"))
    assert (await client.post("/api/exporte/z3", headers=h, json={"von": "2026-02-01", "bis": "2026-01-01"})).status_code == 422
    assert (await client.post("/api/exporte/z3", headers=h, json={"von": "2010-01-01", "bis": "2026-01-01"})).status_code == 422
    assert (await client.post("/api/exporte/z3", headers=h, json={"von": "2026-01-01"})).status_code == 422
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    th = auth_headers(await login(client, techniker.email, "pw-123456"))
    assert (await client.post("/api/exporte/z3", headers=th, json={"von": "2026-01-01", "bis": "2026-12-31"})).status_code == 403


def test_formate_sind_deterministisch():
    assert z3_service.fmt_betrag(Decimal("1234.5")) == "1234,50"
    assert z3_service.fmt_betrag(Decimal("-0.005")) in ("-0,01", "0,00", "-0,00")
    assert z3_service.fmt_datum(date(2026, 3, 9)) == "09.03.2026"
    # 23:30 UTC am 31.12. ist in Berlin bereits der 1.1.
    assert z3_service.fmt_datum(datetime(2024, 12, 31, 23, 30, tzinfo=timezone.utc)) == "01.01.2025"
