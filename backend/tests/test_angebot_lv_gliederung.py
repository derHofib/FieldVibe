"""Angebot: Gliederung, Lohn-/Materialanteil, Uebernahme aus dem Leistungsverzeichnis."""
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import pdf_service
from app.services.angebot_gliederung import ordnungszahlen, zwischensummen
from tests.conftest import auth_headers, login
from tests.test_angebot_pdf_layout import _angebot as _pdf_angebot
from tests.test_angebot_pdf_layout import _text
from tests.test_leistungsverzeichnis import _make_lv, _make_lv_position
from tests.test_rechnung_pdf_layout import _kunde, _mandant
from app.models.angebot import AngebotPosition


def _z(position, zeilentyp="position", ebene=1, menge="1", preis="10"):
    return SimpleNamespace(
        id=uuid4(), position=position, zeilentyp=zeilentyp, ebene=ebene, menge=Decimal(menge), einzelpreis=Decimal(preis)
    )


def test_ordnungszahlen_und_zwischensummen():
    t1, p1, p2 = _z(1, "titel"), _z(2, menge="2", preis="5.005"), _z(3, preis="1")
    t2, a1, a2 = _z(4, "titel", 2), _z(5, preis="100"), _z(6, preis="50")
    t3, p3 = _z(7, "titel"), _z(8, preis="7")
    alle = [t3, p3, t2, a1, p1, a2, t1, p2]  # Reihenfolge der Liste ist egal, position zaehlt
    oz = ordnungszahlen(alle)
    assert [oz[x.id] for x in (t1, p1, p2, t2, a1, a2, t3, p3)] == ["1", "1.1", "1.2", "1.1", "1.1.1", "1.1.2", "2", "2.1"]
    zs = zwischensummen(alle)
    # Ebene-1-Titel schliesst seinen Ebene-2-Abschnitt mit ein; Zeilen einzeln gerundet (2 x 5.005 = 10.01).
    assert zs[t1.id] == Decimal("10.01") + 1 + 150
    assert zs[t2.id] == Decimal("150")
    assert zs[t3.id] == Decimal("7")


def test_positionen_vor_erstem_titel_zaehlen_durch():
    a, t, b = _z(1), _z(2, "titel"), _z(3)
    oz = ordnungszahlen([a, t, b])
    assert (oz[a.id], oz[t.id], oz[b.id]) == ("1", "1", "1.1")


def test_pdf_zeigt_titel_ordnungszahl_und_zwischensumme():
    pos = [
        AngebotPosition(position=1, zeilentyp="titel", ebene=1, beschreibung="Elektro Erdgeschoss",
                        menge=Decimal("0"), einheit="", einzelpreis=Decimal("0")),
        AngebotPosition(position=2, beschreibung="Steckdose setzen", menge=Decimal("4"), einheit="Stk",
                        einzelpreis=Decimal("25.00")),
        AngebotPosition(position=3, zeilentyp="titel", ebene=1, beschreibung="Verteilung",
                        menge=Decimal("0"), einheit="", einzelpreis=Decimal("0")),
        AngebotPosition(position=4, beschreibung="Zaehlerschrank", menge=Decimal("1"), einheit="Stk",
                        einzelpreis=Decimal("300.00")),
    ]
    pdf = pdf_service.generate_angebot_pdf(_mandant(), _pdf_angebot(), pos, _kunde())
    _, text = _text(pdf)
    assert "Elektro Erdgeschoss" in text and "Verteilung" in text
    assert "1.1" in text and "2.1" in text
    assert text.count("Zwischensumme") == 2
    assert "100,00" in text and "300,00" in text
    assert "400,00" in text  # Angebotssumme netto


async def _setup(client, make_mandant, make_user, make_kunde, *, zuweisen=True):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    h = auth_headers(await login(client, admin.email, "pw-123456"))
    lv = await _make_lv(mandant, kunde if zuweisen else None)
    haupt = await _make_lv_position(
        mandant, lv, bezeichnung="Elektro", einheit="psch", einzelpreis=Decimal("0"), ist_stundensatz=False
    )
    kind_a = await _make_lv_position(
        mandant, lv, bezeichnung="Steckdose", einheit="Stk", einzelpreis=Decimal("30.00"), ist_stundensatz=False,
        eltern_position_id=haupt.id, kalkulationsmodus="berechnet",
        lohn_gesamt=Decimal("20.00"), material_gesamt=Decimal("10.00"),
    )
    kind_b = await _make_lv_position(
        mandant, lv, bezeichnung="Pauschale Pruefung", einheit="psch", einzelpreis=Decimal("50.00"),
        ist_stundensatz=False, eltern_position_id=haupt.id,
    )
    frei = await _make_lv_position(mandant, lv, bezeichnung="Monteurstunde", einzelpreis=Decimal("65.00"))
    angebot = (await client.post("/api/angebote", headers=h, json={"kunde_id": str(kunde.id)})).json()
    return SimpleNamespace(mandant=mandant, h=h, kunde=kunde, lv=lv, haupt=haupt, a=kind_a, b=kind_b, frei=frei,
                           angebot=angebot, url=f"/api/angebote/{angebot['id']}/positionen/aus-lv")


@pytest.mark.asyncio
async def test_aus_lv_hauptpunkt_wird_titel_mit_kindern(client, make_mandant, make_user, make_kunde):
    s = await _setup(client, make_mandant, make_user, make_kunde)
    resp = await client.post(
        s.url,
        headers=s.h,
        json={
            "lv_id": str(s.lv.id),
            "eintraege": [
                {"lv_position_id": str(s.haupt.id), "menge": "2"},
                {"lv_position_id": str(s.b.id), "menge": "1"},
                {"lv_position_id": str(s.frei.id), "menge": "3"},
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    pos = {p["beschreibung"]: p for p in resp.json()["positionen"]}
    assert pos["Elektro"]["zeilentyp"] == "titel" and pos["Elektro"]["ordnungszahl"] == "1"
    steck = pos["Steckdose"]
    assert (steck["menge"], steck["einzelpreis_lohn"], steck["einzelpreis_material"]) == ("2.00", "20.00", "10.00")
    assert steck["einzelpreis"] == "30.00" and steck["positionstyp"] == "material"
    assert steck["ordnungszahl"] == "1.2"  # LV-Reihenfolge ist alphabetisch and steck["lv_position_id"] == str(s.a.id)
    # Kind-Eintrag gewinnt gegen die Menge des Hauptpunkts; Festpreis ohne Split.
    pausch = pos["Pauschale Pruefung"]
    assert pausch["menge"] == "1.00" and pausch["einzelpreis_lohn"] is None
    assert pos["Monteurstunde"]["positionstyp"] == "arbeitszeit"
    assert pos["Elektro"]["zwischensumme"] == "110.00"  # 2 x 30 + 1 x 50
    antwort = resp.json()
    assert antwort["gesamt_netto"] == "305.00"  # 110 + 3 x 65
    # Lohn: 2 x 20 + 3 x 65 (Stundensatz-Position ohne Split zaehlt als Arbeitszeit); Rest Material.
    assert antwort["summe_lohn"] == "235.00" and antwort["summe_material"] == "70.00"


@pytest.mark.asyncio
async def test_aus_lv_ohne_gliederung_und_leaf_unter_hauptpunkt(client, make_mandant, make_user, make_kunde):
    s = await _setup(client, make_mandant, make_user, make_kunde)
    resp = await client.post(
        s.url, headers=s.h,
        json={"lv_id": str(s.lv.id), "mit_gliederung": False,
              "eintraege": [{"lv_position_id": str(s.a.id), "menge": "5"}]},
    )
    assert resp.status_code == 200, resp.text
    assert [p["zeilentyp"] for p in resp.json()["positionen"]] == ["position"]


@pytest.mark.asyncio
async def test_aus_lv_fehlerfaelle(client, make_mandant, make_user, make_kunde):
    s = await _setup(client, make_mandant, make_user, make_kunde)
    ein = {"lv_position_id": str(s.frei.id), "menge": "1"}
    assert (await client.post(s.url, headers=s.h, json={"lv_id": str(s.lv.id), "eintraege": [ein, ein]})).status_code == 422
    fremd = {"lv_position_id": str(uuid4()), "menge": "1"}
    assert (await client.post(s.url, headers=s.h, json={"lv_id": str(s.lv.id), "eintraege": [fremd]})).status_code == 422
    assert (await client.post(s.url, headers=s.h, json={"lv_id": str(uuid4()), "eintraege": [ein]})).status_code == 404
    assert (await client.post(s.url, headers=s.h, json={"lv_id": str(s.lv.id), "eintraege": []})).status_code == 422

    assert (await client.post(s.url, headers=s.h, json={"lv_id": str(s.lv.id), "eintraege": [ein]})).status_code == 200
    r = await client.patch(f"/api/angebote/{s.angebot['id']}", headers=s.h, json={"status": "versendet"})
    assert r.status_code == 200, r.text
    resp = await client.post(s.url, headers=s.h, json={"lv_id": str(s.lv.id), "eintraege": [ein]})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_aus_lv_falscher_kunde_und_fremder_mandant(client, make_mandant, make_user, make_kunde):
    s = await _setup(client, make_mandant, make_user, make_kunde)
    anderer = await make_kunde(mandant=s.mandant, name="Anderer")
    lv2 = await _make_lv(s.mandant, anderer)
    p2 = await _make_lv_position(s.mandant, lv2, bezeichnung="X")
    resp = await client.post(
        s.url, headers=s.h, json={"lv_id": str(lv2.id), "eintraege": [{"lv_position_id": str(p2.id)}]}
    )
    assert resp.status_code == 422

    fremd = await make_mandant(name="Fremd")
    lv3 = await _make_lv(fremd)
    p3 = await _make_lv_position(fremd, lv3, bezeichnung="Y")
    resp = await client.post(
        s.url, headers=s.h, json={"lv_id": str(lv3.id), "eintraege": [{"lv_position_id": str(p3.id)}]}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_anteile_titel_und_hash_stabilitaet(client, make_mandant, make_user, make_kunde):
    s = await _setup(client, make_mandant, make_user, make_kunde)
    base = f"/api/angebote/{s.angebot['id']}/positionen"
    r = await client.post(base, headers=s.h, json={"beschreibung": "Leistung", "menge": "2", "einheit": "Std",
                                                   "einzelpreis_lohn": "40", "einzelpreis_material": "5"})
    assert r.status_code == 200, r.text
    pos = r.json()["positionen"][0]
    assert pos["einzelpreis"] == "45.00"
    alt_hash = r.json()["fassung_sha256"]

    # Gesamtpreis setzen verwirft die Aufteilung; beides gleichzeitig ist ein Fehler.
    r = await client.patch(f"{base}/{pos['id']}", headers=s.h, json={"einzelpreis": "50"})
    assert r.json()["positionen"][0]["einzelpreis_lohn"] is None
    r = await client.patch(f"{base}/{pos['id']}", headers=s.h, json={"einzelpreis": "50", "einzelpreis_lohn": "1"})
    assert r.status_code == 422
    r = await client.patch(f"{base}/{pos['id']}", headers=s.h, json={"einzelpreis_lohn": "30", "einzelpreis_material": "7"})
    assert r.json()["positionen"][0]["einzelpreis"] == "37.00"

    # Titel: keine Preise; der Hash eines Angebots ohne Titel enthaelt kein "titel".
    r = await client.post(base, headers=s.h, json={"beschreibung": "Abschnitt", "zeilentyp": "titel", "einzelpreis": "99"})
    titel = r.json()["positionen"][-1]
    assert titel["einzelpreis"] == "0.00" and titel["menge"] == "0.00"
    assert (await client.patch(f"{base}/{titel['id']}", headers=s.h, json={"einzelpreis": "5"})).status_code == 422
    assert r.json()["fassung_sha256"] != alt_hash


@pytest.mark.asyncio
async def test_rechnung_aus_gegliedertem_angebot_ohne_titelzeilen(client, make_mandant, make_user, make_kunde):
    s = await _setup(client, make_mandant, make_user, make_kunde)
    r = await client.post(
        s.url, headers=s.h,
        json={"lv_id": str(s.lv.id), "eintraege": [{"lv_position_id": str(s.haupt.id), "menge": "1"}]},
    )
    assert r.status_code == 200
    angebot = r.json()
    await client.patch(f"/api/angebote/{angebot['id']}", headers=s.h, json={"status": "versendet"})
    await client.patch(f"/api/angebote/{angebot['id']}", headers=s.h, json={"status": "angenommen"})
    resp = await client.post(
        "/api/rechnungen/aus-angebot", headers=s.h,
        json={"angebot_id": angebot["id"], "rechnungsart": "rechnung", "leistungsdatum": "2026-08-10"},
    )
    assert resp.status_code == 201, resp.text
    rechnung = resp.json()
    assert [p["beschreibung"] for p in rechnung["positionen"]] == ["Pauschale Pruefung", "Steckdose"]


def test_fassung_bestehender_angebote_bleibt_unveraendert():
    from app.services.angebot_service import kanonische_fassung

    pos = [AngebotPosition(position=1, beschreibung="A", menge=Decimal("1"), einheit="Stk",
                           einzelpreis=Decimal("10"), einzelpreis_lohn=Decimal("4"), einzelpreis_material=Decimal("6"))]
    fassung = kanonische_fassung(_pdf_angebot(), pos)
    assert "zeilentyp" not in fassung and "ebene" not in fassung and "lohn" not in fassung
    titel = AngebotPosition(position=2, zeilentyp="titel", ebene=1, beschreibung="T", menge=Decimal("0"),
                            einheit="", einzelpreis=Decimal("0"))
    assert '"zeilentyp":"titel"' in kanonische_fassung(_pdf_angebot(), pos + [titel])
