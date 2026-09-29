"""Sammelrechnung: mehrere Vorgaenge desselben Kunden per POST .../vorgaenge auf
einer Rechnung, Auswahlliste abrechenbarer Vorgaenge und Bearbeiten von Positionen."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.db.session import system_session
from app.models.leistungsverzeichnis import Leistungsverzeichnis, LeistungsverzeichnisPosition
from app.models.zeiterfassung import Zeiterfassung
from tests.conftest import auth_headers, login


async def _zeit(session, *, mandant, vorgang, techniker, stunden: float, lv_position_id=None, status="gebucht"):
    start = datetime.now(timezone.utc)
    eintrag = Zeiterfassung(
        mandant_id=mandant.id,
        vorgang_id=vorgang.id,
        techniker_id=techniker.id,
        start_at=start,
        ende_at=start + timedelta(hours=stunden),
        kategorie="auftrag",
        abrechenbar=True,
        buchungsstatus=status,
        lv_position_id=lv_position_id,
    )
    session.add(eintrag)
    await session.flush()
    return eintrag.id


async def _svs(session, mandant) -> "LeistungsverzeichnisPosition":
    lv = Leistungsverzeichnis(mandant_id=mandant.id, name="LV")
    session.add(lv)
    await session.flush()
    svs = LeistungsverzeichnisPosition(
        mandant_id=mandant.id,
        leistungsverzeichnis_id=lv.id,
        bezeichnung="Stundensatz Monteur",
        einheit="Std",
        einzelpreis=Decimal("65.00"),
        ist_stundensatz=True,
    )
    session.add(svs)
    await session.flush()
    return svs


async def _setup(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    va = await make_vorgang(mandant=mandant, kunde=kunde, titel="Alpha", vorgangsnummer="V-A")
    vb = await make_vorgang(mandant=mandant, kunde=kunde, titel="Beta", vorgangsnummer="V-B")
    token = await login(client, admin.email, "pw-123456")
    return mandant, admin, kunde, va, vb, token


async def _daten_zwei_vorgaenge(mandant, admin, va, vb):
    async with system_session() as session:
        svs = await _svs(session, mandant)
        a = await _zeit(session, mandant=mandant, vorgang=va, techniker=admin, stunden=2)
        b_ohne = await _zeit(session, mandant=mandant, vorgang=vb, techniker=admin, stunden=1)
        b_svs = await _zeit(session, mandant=mandant, vorgang=vb, techniker=admin, stunden=3, lv_position_id=svs.id)
    return a, b_ohne, b_svs


async def _rechnung_anlegen(client, token, kunde, **extra):
    resp = await client.post(
        "/api/rechnungen", headers=auth_headers(token), json={"kunde_id": str(kunde.id), **extra}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _uebernehmen(client, token, rechnung_id, vorgang, stundensatz="0", nur=None):
    """Nimmt alle (oder nur die per `nur` gefilterten) Vorschlaege des
    Vorgangs in den Entwurf; gibt die Response zurueck."""
    headers = auth_headers(token)
    vorschlaege = await client.get(
        f"/api/rechnungen/{rechnung_id}/vorgaenge/{vorgang.id}/vorschlaege", headers=headers
    )
    assert vorschlaege.status_code == 200, vorschlaege.text
    auswahl = [
        {"quelle": v["quelle"], "lv_position_id": v["lv_position_id"], "material_id": v["material_id"]}
        for v in vorschlaege.json()
        if nur is None or nur(v)
    ]
    return await client.post(
        f"/api/rechnungen/{rechnung_id}/vorgaenge",
        headers=headers,
        json={"vorgang_id": str(vorgang.id), "stundensatz": stundensatz, "auswahl": auswahl},
    )


async def sammelrechnung(client, token, kunde, *vorgaenge):
    """Rechnung anlegen und alle offenen Posten der Vorgaenge uebernehmen."""
    rechnung = await _rechnung_anlegen(client, token, kunde)
    for v in vorgaenge:
        resp = await _uebernehmen(client, token, rechnung["id"], v)
        assert resp.status_code == 200, resp.text
        rechnung = resp.json()
    return rechnung


@pytest.mark.asyncio
async def test_sammelrechnung_zwei_vorgaenge(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    a, b_ohne, b_svs = await _daten_zwei_vorgaenge(mandant, admin, va, vb)

    rechnung = await _rechnung_anlegen(client, token, kunde)
    assert rechnung["positionen"] == [] and rechnung["vorgaenge"] == []
    resp = await _uebernehmen(client, token, rechnung["id"], va, stundensatz="80")
    assert resp.status_code == 200, resp.text
    resp = await _uebernehmen(client, token, rechnung["id"], vb, stundensatz="90")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["vorgang_id"] is None
    pos = body["positionen"]
    assert [p["position"] for p in pos] == [1, 2, 3]

    assert pos[0]["quelle"] == "zeit"
    assert pos[0]["vorgang_id"] == str(va.id)
    assert pos[0]["menge"] == "2.00"
    assert pos[0]["einzelpreis"] == "80.00"
    # Ohne Vorgangsnummer-Suffix: der Gruppenkopf zeigt den Vorgang
    assert pos[0]["beschreibung"] == "Arbeitszeit"

    assert pos[1]["quelle"] == "zeit"
    assert pos[1]["vorgang_id"] == str(vb.id)
    assert pos[1]["menge"] == "1.00"
    assert pos[1]["einzelpreis"] == "90.00"

    assert pos[2]["quelle"] == "leistung"
    assert pos[2]["vorgang_id"] == str(vb.id)
    assert pos[2]["menge"] == "3.00"
    assert pos[2]["einzelpreis"] == "65.00"
    assert pos[2]["beschreibung"] == "Stundensatz Monteur"

    async with system_session() as session:
        for eintrag_id in (a, b_ohne, b_svs):
            e = await session.get(Zeiterfassung, eintrag_id)
            assert e.buchungsstatus == "abgerechnet"
            assert str(e.abgerechnet_rechnung_id) == body["id"]


@pytest.mark.asyncio
async def test_uebernahme_stundensatz_default_null(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    async with system_session() as session:
        await _zeit(session, mandant=mandant, vorgang=va, techniker=admin, stunden=2)

    rechnung = await _rechnung_anlegen(client, token, kunde)
    resp = await _uebernehmen(client, token, rechnung["id"], va)
    assert resp.status_code == 200
    assert resp.json()["positionen"][0]["einzelpreis"] == "0.00"


@pytest.mark.asyncio
async def test_uebernahme_vorgang_ohne_offene_posten(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    rechnung = await _rechnung_anlegen(client, token, kunde)
    # Nicht (mehr) vorhandener Posten in der Auswahl wird ignoriert, kein Fehler
    resp = await client.post(
        f"/api/rechnungen/{rechnung['id']}/vorgaenge",
        headers=auth_headers(token),
        json={"vorgang_id": str(va.id), "auswahl": [{"quelle": "zeit"}]},
    )
    assert resp.status_code == 200
    assert resp.json()["positionen"] == []
    assert resp.json()["vorgaenge"] == []


@pytest.mark.asyncio
async def test_uebernahme_validierung(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    anderer_kunde = await make_kunde(mandant=mandant)
    fremder = await make_vorgang(mandant=mandant, kunde=anderer_kunde)
    headers = auth_headers(token)
    rechnung = await _rechnung_anlegen(client, token, kunde)
    url = f"/api/rechnungen/{rechnung['id']}/vorgaenge"

    r = await client.post(url, headers=headers, json={"vorgang_id": str(fremder.id), "auswahl": [{"quelle": "zeit"}]})
    assert r.status_code == 400

    r = await client.post(url, headers=headers, json={"vorgang_id": str(va.id), "auswahl": []})
    assert r.status_code == 400

    r = await client.post(
        url,
        headers=headers,
        json={"vorgang_id": str(va.id), "stundensatz": "-1", "auswahl": [{"quelle": "zeit"}]},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_uebernahme_fremder_mandant(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    fremder_mandant = await make_mandant(name="Fremd")
    fremder_kunde = await make_kunde(mandant=fremder_mandant)
    fremder_vorgang = await make_vorgang(mandant=fremder_mandant, kunde=fremder_kunde)
    rechnung = await _rechnung_anlegen(client, token, kunde)

    r = await client.post(
        f"/api/rechnungen/{rechnung['id']}/vorgaenge",
        headers=auth_headers(token),
        json={"vorgang_id": str(fremder_vorgang.id), "auswahl": [{"quelle": "zeit"}]},
    )
    assert r.status_code == 400
    r = await client.get(
        f"/api/rechnungen/{rechnung['id']}/vorgaenge/{fremder_vorgang.id}/vorschlaege", headers=auth_headers(token)
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_position_entfernen_entsperrt_nur_eigenen_vorgang(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    async with system_session() as session:
        a = await _zeit(session, mandant=mandant, vorgang=va, techniker=admin, stunden=2)
        b = await _zeit(session, mandant=mandant, vorgang=vb, techniker=admin, stunden=1)

    created = await sammelrechnung(client, token, kunde, va, vb)
    rechnung_id = created["id"]
    pos_a = next(p for p in created["positionen"] if p["vorgang_id"] == str(va.id))

    resp = await client.delete(
        f"/api/rechnungen/{rechnung_id}/positionen/{pos_a['id']}", headers=auth_headers(token)
    )
    assert resp.status_code == 200

    async with system_session() as session:
        ea = await session.get(Zeiterfassung, a)
        eb = await session.get(Zeiterfassung, b)
        assert ea.buchungsstatus == "gebucht"
        assert ea.abgerechnet_rechnung_id is None
        assert eb.buchungsstatus == "abgerechnet"
        assert str(eb.abgerechnet_rechnung_id) == rechnung_id


@pytest.mark.asyncio
async def test_abrechenbare_vorgaenge(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    anderer_kunde = await make_kunde(mandant=mandant)
    fremder = await make_vorgang(mandant=mandant, kunde=anderer_kunde, vorgangsnummer="V-X")
    leer = await make_vorgang(mandant=mandant, kunde=kunde, vorgangsnummer="V-C")
    schon_abgerechnet = await make_vorgang(mandant=mandant, kunde=kunde, vorgangsnummer="V-D")
    async with system_session() as session:
        svs = await _svs(session, mandant)
        await _zeit(session, mandant=mandant, vorgang=va, techniker=admin, stunden=2)
        await _zeit(session, mandant=mandant, vorgang=va, techniker=admin, stunden=0.5, lv_position_id=svs.id)
        await _zeit(session, mandant=mandant, vorgang=vb, techniker=admin, stunden=1.25)
        await _zeit(session, mandant=mandant, vorgang=fremder, techniker=admin, stunden=4)
        await _zeit(session, mandant=mandant, vorgang=schon_abgerechnet, techniker=admin, stunden=4, status="abgerechnet")

    resp = await client.get(
        f"/api/rechnungen/abrechenbare-vorgaenge?kunde_id={kunde.id}", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    assert resp.json() == [
        {
            "vorgang_id": str(vb.id),
            "vorgangsnummer": "V-B",
            "titel": "Beta",
            "stunden_ohne_svs": "1.25",
            "stunden_mit_svs": "0.00",
            "material_offen": 0,
        },
        {
            "vorgang_id": str(va.id),
            "vorgangsnummer": "V-A",
            "titel": "Alpha",
            "stunden_ohne_svs": "2.00",
            "stunden_mit_svs": "0.50",
            "material_offen": 0,
        },
    ]
    assert str(leer.id) not in resp.text


@pytest.mark.asyncio
async def test_position_bearbeiten(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    headers = auth_headers(token)
    async with system_session() as session:
        await _zeit(session, mandant=mandant, vorgang=va, techniker=admin, stunden=2)

    rechnung = await _rechnung_anlegen(client, token, kunde, mwst_satz="0")
    created = await _uebernehmen(client, token, rechnung["id"], va)
    rechnung_id = rechnung["id"]
    position_id = created.json()["positionen"][0]["id"]

    resp = await client.patch(
        f"/api/rechnungen/{rechnung_id}/positionen/{position_id}",
        headers=headers,
        json={"einzelpreis": "75", "beschreibung": "Montage"},
    )
    assert resp.status_code == 200
    p = resp.json()["positionen"][0]
    assert p["einzelpreis"] == "75.00"
    assert p["beschreibung"] == "Montage"
    assert p["menge"] == "2.00"
    assert resp.json()["betrag_netto"] == "150.00"

    neg = await client.patch(
        f"/api/rechnungen/{rechnung_id}/positionen/{position_id}", headers=headers, json={"einzelpreis": "-1"}
    )
    assert neg.status_code == 422

    # Position einer anderen Rechnung -> 404
    andere = await client.post(
        "/api/rechnungen", headers=headers, json={"kunde_id": str(kunde.id), "betrag_netto": "10"}
    )
    r404 = await client.patch(
        f"/api/rechnungen/{andere.json()['id']}/positionen/{position_id}",
        headers=headers,
        json={"einzelpreis": "1"},
    )
    assert r404.status_code == 404

    versendet = await client.patch(f"/api/rechnungen/{rechnung_id}", headers=headers, json={"status": "versendet"})
    assert versendet.status_code == 200
    r400 = await client.patch(
        f"/api/rechnungen/{rechnung_id}/positionen/{position_id}", headers=headers, json={"einzelpreis": "1"}
    )
    assert r400.status_code == 400
