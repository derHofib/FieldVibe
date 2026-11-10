"""DATEV-Export: Stammdaten je Mandant, Header, feste Personenkonten, Kodierung.

Die Header-Reihenfolge ist aus dem Gedaechtnis rekonstruiert (siehe
datev_service) -- diese Tests sichern den implementierten Stand ab, sie
beweisen nicht die Konformitaet zur DATEV-Spezifikation."""
import asyncio
import csv
import os
import re
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db.session import system_session, tenant_session
from app.models.kunde import Kunde
from app.models.lieferant import Lieferant
from app.services import datev_service
from tests.conftest import auth_headers
from tests.datev_helfer import (
    BELEGDATUM,
    BELEG1,
    BU,
    GEGENKONTO,
    KONTO,
    SH,
    STAMMDATEN,
    TEXT,
    UMSATZ,
    buchhaltung,
    parse,
    stammdaten_setzen,
)
from tests.test_rechnungsarten import _admin, _versendete_rechnung

_ZEITRAUM = "von=2026-01-01&bis=2026-12-31"
_URL = f"/api/auswertung/datev-export?{_ZEITRAUM}"


async def _export(client, h, url=_URL):
    antwort = await client.get(url, headers=h)
    assert antwort.status_code == 200, antwort.text
    return antwort


async def _rechnung_heute(client, h, kunde):
    return await _versendete_rechnung(client, h, kunde, [{"beschreibung": "Material", "einzelpreis": "100"}])


def _heute_zeitraum() -> str:
    jahr = datetime.now(timezone.utc).year
    return f"/api/auswertung/datev-export?von={jahr}-01-01&bis={jahr}-12-31"


# --- Header und Spaltenkopf ---------------------------------------------------------


async def test_header_felder_und_reihenfolge(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde, firmendaten=buchhaltung())
    await _rechnung_heute(client, h, kunde)
    antwort = await _export(client, h, "/api/auswertung/datev-export?von=2026-02-01&bis=2026-02-28")
    header, spaltenkoepfe, _ = parse(antwort.text)
    assert len(header) == 31
    assert header[:5] == ["EXTF", "700", "21", "Buchungsstapel", "13"]
    assert re.fullmatch(r"\d{17}", header[5])  # YYYYMMDDHHMMSSfff
    assert datetime.strptime(header[5][:14], "%Y%m%d%H%M%S")
    assert header[6] == "" and header[9] == ""  # importiert / importiert von
    assert header[7] == "FV" and header[8] == "FieldVibe"  # Herkunft, exportiert von
    assert (header[10], header[11]) == ("29098", "55003")  # Berater, Mandant
    assert header[12] == "20260101"  # Wirtschaftsjahr-Beginn (Default Januar)
    assert header[13] == "4"  # Sachkontenlaenge
    assert (header[14], header[15]) == ("20260201", "20260228")  # Datum von/bis
    assert 0 < len(header[16]) <= 30  # Bezeichnung
    assert header[17] == ""  # Diktatkuerzel
    assert (header[18], header[19], header[20], header[21]) == ("1", "0", "0", "EUR")
    assert header[26] == "03"  # SKR

    assert spaltenkoepfe[:14] == [
        "Umsatz (ohne Soll/Haben-Kz)",
        "Soll/Haben-Kennzeichen",
        "WKZ Umsatz",
        "Kurs",
        "Basis-Umsatz",
        "WKZ Basis-Umsatz",
        "Konto",
        "Gegenkonto (ohne BU-Schlüssel)",
        "BU-Schlüssel",
        "Belegdatum",
        "Belegfeld 1",
        "Belegfeld 2",
        "Skonto",
        "Buchungstext",
    ]


async def test_header_roh_text_quoting_und_zeilenenden(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde, firmendaten=buchhaltung())
    await _rechnung_heute(client, h, kunde)
    antwort = await _export(client, h, _heute_zeitraum())
    zeilen = antwort.content.decode("cp1252").split("\r\n")
    assert zeilen[0].startswith('"EXTF";700;21;"Buchungsstapel";13;')
    assert zeilen[-1] == ""  # jede Zeile, auch die letzte, endet mit CRLF
    assert b"\n" not in antwort.content.replace(b"\r\n", b"")
    buchung = zeilen[2].split(";")
    assert len(buchung) == 14
    assert re.fullmatch(r"\d+,\d{2}", buchung[UMSATZ])  # Komma, keine Tausenderpunkte
    assert buchung[SH] == '"S"'
    assert re.fullmatch(r"\d{4}", buchung[BELEGDATUM])  # TTMM


async def test_wirtschaftsjahr_beginn_aus_monat(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(
        client, make_mandant, make_user, make_kunde, firmendaten=buchhaltung(wirtschaftsjahr_beginn_monat=4)
    )
    vor, _, _ = parse((await _export(client, h, "/api/auswertung/datev-export?von=2026-02-01&bis=2026-02-28")).text)
    nach, _, _ = parse((await _export(client, h, "/api/auswertung/datev-export?von=2026-05-01&bis=2026-05-31")).text)
    assert vor[12] == "20250401"
    assert nach[12] == "20260401"


async def test_skr04_und_sachkontenlaenge_5(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(
        client, make_mandant, make_user, make_kunde, firmendaten=buchhaltung(kontenrahmen="SKR04", sachkontenlaenge=5)
    )
    await _rechnung_heute(client, h, kunde)
    header, _, zeilen = parse((await _export(client, h, _heute_zeitraum())).text)
    assert (header[13], header[26]) == ("5", "04")
    [zeile] = zeilen
    assert zeile[GEGENKONTO] == "44000"  # SKR04-Erloes 19 %, auf 5 Stellen aufgefuellt
    assert zeile[KONTO] == "100000"  # Personenkonto = Sachkontenlaenge + 1 Stellen


async def test_konfiguriertes_erloeskonto_muss_zur_sachkontenlaenge_passen(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(
        client,
        make_mandant,
        make_user,
        make_kunde,
        firmendaten=buchhaltung(sachkontenlaenge=5, erloeskonten={"S:19.00": {"konto": "8400", "bu": "3"}}),
    )
    await _rechnung_heute(client, h, kunde)
    antwort = await client.get(_heute_zeitraum(), headers=h)
    assert antwort.status_code == 422
    assert "Sachkontenlänge" in antwort.json()["detail"]


# --- Stammdaten fehlen ----------------------------------------------------------------


async def test_export_ohne_berater_und_mandantennummer_422(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    await _rechnung_heute(client, h, kunde)
    antwort = await client.get(_heute_zeitraum(), headers=h)
    assert antwort.status_code == 422
    detail = antwort.json()["detail"]
    assert "DATEV-Stammdaten unvollständig" in detail
    assert "Beraternummer und Mandantennummer" in detail
    assert "Einstellungen" in detail


async def test_export_mit_nur_einer_nummer_nennt_die_fehlende(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(
        client, make_mandant, make_user, make_kunde, firmendaten={"buchhaltung": {"berater_nr": 29098}}
    )
    antwort = await client.get(_heute_zeitraum(), headers=h)
    assert antwort.status_code == 422
    assert "Mandantennummer nicht hinterlegt" in antwort.json()["detail"]
    assert "Beraternummer" not in antwort.json()["detail"]


@pytest.mark.parametrize(
    "buchhaltung_",
    [
        {"berater_nr": 1000},
        {"berater_nr": 10000000},
        {"berater_nr": "abc"},
        {"berater_nr": 29098.5},
        {"berater_nr": True},
        {"mandant_nr": 0},
        {"mandant_nr": 100000},
        {"wirtschaftsjahr_beginn_monat": 0},
        {"wirtschaftsjahr_beginn_monat": 13},
        {"kontenrahmen": "SKR05"},
        {"sachkontenlaenge": 3},
        {"sachkontenlaenge": 9},
    ],
)
async def test_stammdaten_validierung_422(client, make_mandant, make_user, buchhaltung_):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    from tests.conftest import login

    h = auth_headers(await login(client, admin.email, "pw-123456"))
    antwort = await client.patch("/api/mandant/einstellungen", headers=h, json={"firmendaten": {"buchhaltung": buchhaltung_}})
    assert antwort.status_code == 422, antwort.text


async def test_stammdaten_werden_normalisiert_und_koennen_entfallen(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    from tests.conftest import login

    h = auth_headers(await login(client, admin.email, "pw-123456"))
    antwort = await client.patch(
        "/api/mandant/einstellungen",
        headers=h,
        json={
            "firmendaten": {
                "buchhaltung": {
                    "berater_nr": " 0029098 ",
                    "mandant_nr": "55003",
                    "wirtschaftsjahr_beginn_monat": "7",
                    "kontenrahmen": "SKR04",
                    "sachkontenlaenge": 6,
                }
            }
        },
    )
    assert antwort.status_code == 200, antwort.text
    assert antwort.json()["firmendaten"]["buchhaltung"] == {
        "berater_nr": 29098,
        "mandant_nr": 55003,
        "wirtschaftsjahr_beginn_monat": 7,
        "kontenrahmen": "SKR04",
        "sachkontenlaenge": 6,
    }
    # Leere Felder entfallen (buchhaltung wird als Ganzes ersetzt).
    leer = await client.patch(
        "/api/mandant/einstellungen",
        headers=h,
        json={"firmendaten": {"buchhaltung": {"berater_nr": "", "mandant_nr": None}}},
    )
    assert leer.status_code == 200
    assert leer.json()["firmendaten"]["buchhaltung"] == {}


# --- Debitorenkonten -----------------------------------------------------------------


async def _kunden_anlegen(mandant_id, anzahl: int) -> None:
    async with system_session() as session:
        for i in range(anzahl):
            session.add(
                Kunde(
                    mandant_id=mandant_id,
                    kundennummer=f"K-{i:04d}",
                    name=f"Kunde {i}",
                    portal_slug=uuid.uuid4().hex,
                )
            )


async def _vergeben(mandant_id, laenge: int = 4) -> dict:
    async with tenant_session(mandant_id=mandant_id, is_super_admin=False) as session:
        kunden = list((await session.execute(select(Kunde).where(Kunde.mandant_id == mandant_id))).scalars())
        await datev_service.debitorenkonten_vergeben(session, mandant_id, kunden, laenge)
        return {k.id: k.debitorenkonto for k in kunden}


async def test_200_kunden_kollisionsfrei_und_gleichzeitiger_export(make_mandant):
    mandant = await make_mandant()
    await _kunden_anlegen(mandant.id, 200)
    a, b = await asyncio.gather(_vergeben(mandant.id), _vergeben(mandant.id))
    assert a == b  # der zweite Export sieht die Konten des ersten, vergibt nichts neu
    konten = list(a.values())
    assert len(konten) == 200 and len(set(konten)) == 200
    assert all(len(k) == 5 and 10000 <= int(k) <= 69999 for k in konten)
    assert sorted(konten, key=int)[0] == "10000" and sorted(konten, key=int)[-1] == "10199"
    # Stabil: weitere Laeufe aendern nichts.
    assert await _vergeben(mandant.id) == a


async def test_sachkontenlaenge_bestimmt_die_kontolaenge(make_mandant):
    mandant = await make_mandant()
    await _kunden_anlegen(mandant.id, 3)
    konten = (await _vergeben(mandant.id, laenge=7)).values()
    assert sorted(konten) == ["10000000", "10000001", "10000002"]


async def test_numerische_kundennummer_hat_vorrang_wenn_frei(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        for nummer in ("K-1", "10002", "99", "70000", "10000"):
            session.add(
                Kunde(mandant_id=mandant.id, kundennummer=nummer, name=nummer, portal_slug=uuid.uuid4().hex)
            )
    async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
        kunden = list((await session.execute(select(Kunde).where(Kunde.mandant_id == mandant.id))).scalars())
        await datev_service.debitorenkonten_vergeben(session, mandant.id, kunden, 4)
        konto = {k.kundennummer: k.debitorenkonto for k in kunden}
    # 10000 und 10002 wie gewuenscht; 70000 liegt im Kreditorenbereich, "99" ist zu kurz, "K-1" nicht numerisch.
    assert konto["10000"] == "10000" and konto["10002"] == "10002"
    assert sorted((konto["K-1"], konto["99"], konto["70000"])) == ["10001", "10003", "10004"]


async def test_export_vergibt_stabile_konten_und_neue_kunden_bekommen_die_naechste_freie(
    client, make_mandant, make_user, make_kunde
):
    mandant, kunde1, h = await _admin(client, make_mandant, make_user, make_kunde, firmendaten=buchhaltung())
    kunde2 = await make_kunde(mandant=mandant, name="Zweiter")
    await _rechnung_heute(client, h, kunde1)
    await _rechnung_heute(client, h, kunde2)
    erste = (await _export(client, h, _heute_zeitraum())).text
    konten1 = sorted(z[KONTO] for z in parse(erste)[2])
    assert konten1 == ["10000", "10001"]

    kunde3 = await make_kunde(mandant=mandant, name="Dritter")
    await _rechnung_heute(client, h, kunde3)
    zweite = parse((await _export(client, h, _heute_zeitraum())).text)[2]
    assert sorted(z[KONTO] for z in zweite) == ["10000", "10001", "10002"]
    # Die Konten der ersten beiden Kunden haben sich nicht verschoben.
    assert {z[BELEG1]: z[KONTO] for z in parse(erste)[2]}.items() <= {z[BELEG1]: z[KONTO] for z in zweite}.items()
    antwort = await client.get(f"/api/kunden/{kunde1.id}", headers=h)
    assert antwort.json()["debitorenkonto"] in ("10000", "10001")


async def test_gleichzeitige_exporte_ueber_die_api(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde, firmendaten=buchhaltung())
    kunden = [kunde] + [await make_kunde(mandant=mandant, name=f"Kunde {i}") for i in range(7)]
    for k in kunden:
        await _rechnung_heute(client, h, k)
    a, b = await asyncio.gather(
        client.get(_heute_zeitraum(), headers=h), client.get(_heute_zeitraum(), headers=h)
    )
    assert a.status_code == b.status_code == 200
    zeilen_a, zeilen_b = parse(a.text)[2], parse(b.text)[2]
    assert zeilen_a == zeilen_b
    assert len({z[KONTO] for z in zeilen_a}) == 8


async def test_manuelles_debitorenkonto_wird_im_export_verwendet_und_nicht_neu_vergeben(
    client, make_mandant, make_user, make_kunde
):
    mandant, kunde1, h = await _admin(client, make_mandant, make_user, make_kunde, firmendaten=buchhaltung())
    kunde2 = await make_kunde(mandant=mandant, name="Zweiter")
    antwort = await client.patch(f"/api/kunden/{kunde1.id}", headers=h, json={"debitorenkonto": "10000"})
    assert antwort.status_code == 200 and antwort.json()["debitorenkonto"] == "10000"
    await _rechnung_heute(client, h, kunde1)
    await _rechnung_heute(client, h, kunde2)
    zeilen = parse((await _export(client, h, _heute_zeitraum())).text)[2]
    assert sorted(z[KONTO] for z in zeilen) == ["10000", "10001"]


async def test_debitorenkonto_unique_konflikt_409_und_validierung(client, make_mandant, make_user, make_kunde):
    mandant, kunde1, h = await _admin(client, make_mandant, make_user, make_kunde)
    kunde2 = await make_kunde(mandant=mandant, name="Zweiter")
    assert (await client.patch(f"/api/kunden/{kunde1.id}", headers=h, json={"debitorenkonto": "12345"})).status_code == 200
    doppelt = await client.patch(f"/api/kunden/{kunde2.id}", headers=h, json={"debitorenkonto": "12345"})
    assert doppelt.status_code == 409
    assert doppelt.json()["detail"] == "Debitorenkonto bereits vergeben"
    # Beim Anlegen genauso.
    neu = await client.post("/api/kunden", headers=h, json={"name": "Neu", "debitorenkonto": "12345"})
    assert neu.status_code == 409 and neu.json()["detail"] == "Debitorenkonto bereits vergeben"

    for ungueltig in ("1234", "ab123", "1234567890", "70000", "9999 9"):
        antwort = await client.patch(f"/api/kunden/{kunde2.id}", headers=h, json={"debitorenkonto": ungueltig})
        assert antwort.status_code == 422, ungueltig
    # Sachkontenlaenge 5 -> 6 Stellen noetig.
    await stammdaten_setzen(client, h, sachkontenlaenge=5)
    zu_kurz = await client.patch(f"/api/kunden/{kunde2.id}", headers=h, json={"debitorenkonto": "12346"})
    assert zu_kurz.status_code == 422 and "6 Ziffern" in zu_kurz.json()["detail"]
    ok = await client.patch(f"/api/kunden/{kunde2.id}", headers=h, json={"debitorenkonto": "123456"})
    assert ok.status_code == 200
    # Leer entfernt das Konto wieder.
    leer = await client.patch(f"/api/kunden/{kunde2.id}", headers=h, json={"debitorenkonto": ""})
    assert leer.status_code == 200 and leer.json()["debitorenkonto"] is None


async def test_debitorenkonto_mandantentrennung(client, make_mandant, make_user, make_kunde):
    mandant_a, kunde_a, h_a = await _admin(client, make_mandant, make_user, make_kunde)
    mandant_b, kunde_b, h_b = await _admin(client, make_mandant, make_user, make_kunde)
    assert (await client.patch(f"/api/kunden/{kunde_a.id}", headers=h_a, json={"debitorenkonto": "12345"})).status_code == 200
    # Dasselbe Konto in einem anderen Mandanten ist kein Konflikt ...
    assert (await client.patch(f"/api/kunden/{kunde_b.id}", headers=h_b, json={"debitorenkonto": "12345"})).status_code == 200
    # ... und kein Mandant sieht das Konto des anderen.
    async with tenant_session(mandant_id=mandant_b.id, is_super_admin=False) as session:
        sichtbar = (await session.execute(select(Kunde.id, Kunde.debitorenkonto))).all()
    assert [(r.id, r.debitorenkonto) for r in sichtbar] == [(kunde_b.id, "12345")]
    # Auch die automatische Vergabe zaehlt nur den eigenen Mandanten.
    ergebnis = await _vergeben(mandant_a.id)
    assert ergebnis == {kunde_a.id: "12345"}


async def test_papierkorb_kunde_behaelt_sein_konto_im_export(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde, firmendaten=buchhaltung())
    await _rechnung_heute(client, h, kunde)
    konto = parse((await _export(client, h, _heute_zeitraum())).text)[2][0][KONTO]
    assert (await client.delete(f"/api/kunden/{kunde.id}", headers=h)).status_code == 204
    zeilen = parse((await _export(client, h, _heute_zeitraum())).text)[2]
    assert [z[KONTO] for z in zeilen] == [konto]
    # Das Konto bleibt belegt: ein neuer Kunde bekommt eine andere Nummer.
    neu = await make_kunde(mandant=mandant, name="Neu")
    await _rechnung_heute(client, h, neu)
    konten = sorted(z[KONTO] for z in parse((await _export(client, h, _heute_zeitraum())).text)[2])
    assert len(set(konten)) == 2 and konto in konten


# --- Kreditorenkonten ----------------------------------------------------------------


async def test_kreditorenkonten_lieferant_und_sammelkonto(client, make_mandant, make_user, make_kunde):
    _, _, h = await _admin(client, make_mandant, make_user, make_kunde, firmendaten=buchhaltung())
    lieferant = (await client.post("/api/lieferanten", headers=h, json={"name": "Sonepar"})).json()
    assert lieferant["kreditorenkonto"] is None
    heute = datetime.now(timezone.utc).date().isoformat()
    for nummer, extra in (("RE-1", {"lieferant_id": lieferant["id"]}), ("RE-2", {"lieferant_name": "Freitext GmbH"})):
        antwort = await client.post(
            "/api/eingangsrechnungen",
            headers=h,
            json={
                "rechnungsnummer_lieferant": nummer,
                "rechnungsdatum": heute,
                "betrag_netto": "100.00",
                "mwst_satz": "19.00",
                **extra,
            },
        )
        assert antwort.status_code == 201, antwort.text
    zeilen = {z[BELEG1]: z for z in parse((await _export(client, h, _heute_zeitraum())).text)[2]}
    assert zeilen["RE-1"][GEGENKONTO] == "70001"  # erster frei vergebener Kreditor
    assert zeilen["RE-2"][GEGENKONTO] == "70000"  # Sammelkonto ohne Lieferantenstamm
    assert (zeilen["RE-1"][KONTO], zeilen["RE-1"][SH], zeilen["RE-1"][BU]) == ("4900", "S", "9")
    assert zeilen["RE-1"][UMSATZ] == "119,00"
    # Stabil und am Lieferanten sichtbar.
    liste = (await client.get("/api/lieferanten", headers=h)).json()
    assert liste[0]["kreditorenkonto"] == "70001"


async def test_kreditorenkonto_manuell_validierung_und_konflikt(client, make_mandant, make_user, make_kunde):
    _, _, h = await _admin(client, make_mandant, make_user, make_kunde)
    eins = (await client.post("/api/lieferanten", headers=h, json={"name": "Eins", "kreditorenkonto": "70500"})).json()
    assert eins["kreditorenkonto"] == "70500"
    zwei = (await client.post("/api/lieferanten", headers=h, json={"name": "Zwei"})).json()
    konflikt = await client.patch(f"/api/lieferanten/{zwei['id']}", headers=h, json={"kreditorenkonto": "70500"})
    assert konflikt.status_code == 409 and konflikt.json()["detail"] == "Kreditorenkonto bereits vergeben"
    for ungueltig in ("69999", "7050", "100000", "70000"):  # Debitorenbereich, zu kurz, zu lang, Sammelkonto
        antwort = await client.patch(f"/api/lieferanten/{zwei['id']}", headers=h, json={"kreditorenkonto": ungueltig})
        assert antwort.status_code == 422, ungueltig


async def test_lieferant_vergabe_kollisionsfrei(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        for i in range(50):
            session.add(Lieferant(mandant_id=mandant.id, name=f"L{i}"))

    async def vergeben():
        async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
            lieferanten = list((await session.execute(select(Lieferant))).scalars())
            await datev_service.kreditorenkonten_vergeben(session, mandant.id, lieferanten, 4)
            return {li.id: li.kreditorenkonto for li in lieferanten}

    a, b = await asyncio.gather(vergeben(), vergeben())
    assert a == b
    assert sorted(a.values(), key=int) == [str(70001 + i) for i in range(50)]


# --- Kodierung und Feldlaengen -----------------------------------------------------------


async def test_cp1252_roundtrip_mit_umlauten_und_unabbildbaren_zeichen(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(
        client, make_mandant, make_user, make_kunde, firmendaten=buchhaltung(), name="Müller – Größe €→ő\U0001F600"
    )
    await _rechnung_heute(client, h, kunde)
    antwort = await _export(client, h, _heute_zeitraum())
    assert antwort.headers["content-type"] == "text/csv; charset=windows-1252"
    roh = antwort.content
    assert b"\xfc" in roh and b"\xf6" in roh and b"\xdf" in roh  # ü ö ß
    assert b"\x96" in roh and b"\x80" in roh  # Gedankenstrich und Euro-Zeichen liegen in CP1252
    assert "→".encode("utf-8") not in roh  # kein UTF-8 im Stapel
    text_ = parse(antwort.text)[2][0][TEXT]
    assert text_.endswith("Müller – Größe €?o?")  # Pfeil und Emoji -> "?", ő -> o


async def test_feldlaengen_werden_abgeschnitten(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(
        client, make_mandant, make_user, make_kunde, firmendaten=buchhaltung(), name="X" * 120
    )
    await _rechnung_heute(client, h, kunde)
    [zeile] = parse((await _export(client, h, _heute_zeitraum())).text)[2]
    assert len(zeile[TEXT]) == 60
    assert len(zeile[BELEG1]) <= 36


def test_belegfeld_und_buchungstext_laengen_im_format():
    buchung = datev_service.Buchung(
        betrag=datev_service.betrag(-1234567.5),
        soll_haben="H",
        konto="10000",
        gegenkonto="8400",
        bu_schluessel="",
        belegdatum=datetime(2026, 3, 5).date(),
        belegfeld1="R" * 50,
        buchungstext='Text "mit" Semikolon; und\nZeilenumbruch ' * 4,
    )
    zeile = datev_service.buchungszeile(buchung)
    felder = zeile.split(";")
    assert felder[0] == "1234567,50"  # positiv, Komma, ohne Tausenderpunkt
    assert felder[9] == "0503"
    assert felder[10] == '"' + "R" * 36 + '"'
    assert "\n" not in zeile
    # Anfuehrungszeichen und Semikolon im Text bleiben innerhalb einer Zelle.
    zellen = next(csv.reader([zeile], delimiter=";"))
    assert len(zellen) == 14 and len(zellen[13]) == 60
    assert len(datev_service.bereinigen("é" * 100, 60)) == 60


def test_bereinigen_ersetzt_sicher():
    assert datev_service.bereinigen("Ünïcödé ś ő ł → 😀 \u0081") == "Ünïcödé s o ? ? ?"
    assert datev_service.bereinigen("a\tb\r\nc") == "a b  c"
    assert datev_service.bereinigen("€ ƒ „") == "€ ƒ „"  # 0x80-0x9F-Zeichen, die CP1252 kennt
    assert datev_service.bereinigen("\u0081") == ""  # in CP1252 nicht belegt, ohnehin ein Steuerzeichen


# --- Migration -----------------------------------------------------------------------------


def test_migration_0110_up_down_up():
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from app.core.config import get_settings

    backend = os.path.dirname(os.path.dirname(__file__))
    cfg = Config(os.path.join(backend, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(backend, "alembic"))
    engine = create_engine(os.environ.get("DATABASE_URL_SYNC") or get_settings().database_url_sync)

    def spalten(tabelle):
        return {c["name"] for c in inspect(engine).get_columns(tabelle)}

    def indizes(tabelle):
        return {i["name"]: i for i in inspect(engine).get_indexes(tabelle)}

    try:
        command.downgrade(cfg, "0109")
        assert "debitorenkonto" not in spalten("kunden") and "kreditorenkonto" not in spalten("lieferanten")
        assert "uq_kunden_mandant_debitorenkonto" not in indizes("kunden")
        command.upgrade(cfg, "head")
        assert "debitorenkonto" in spalten("kunden") and "kreditorenkonto" in spalten("lieferanten")
        kunden_index = indizes("kunden")["uq_kunden_mandant_debitorenkonto"]
        assert kunden_index["unique"] and kunden_index["column_names"] == ["mandant_id", "debitorenkonto"]
        assert indizes("lieferanten")["uq_lieferanten_mandant_kreditorenkonto"]["unique"]
    finally:
        engine.dispose()
