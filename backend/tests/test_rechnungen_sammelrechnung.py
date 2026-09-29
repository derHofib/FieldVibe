"""Sammelrechnung: mehrere Vorgaenge desselben Kunden auf einer Rechnung,
Auswahlliste abrechenbarer Vorgaenge und Bearbeiten von Positionen."""
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


@pytest.mark.asyncio
async def test_sammelrechnung_zwei_vorgaenge(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    a, b_ohne, b_svs = await _daten_zwei_vorgaenge(mandant, admin, va, vb)

    resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "vorgaenge": [
                {"vorgang_id": str(va.id), "stundensatz": "80"},
                {"vorgang_id": str(vb.id), "stundensatz": "90"},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["vorgang_id"] is None
    pos = body["positionen"]
    assert [p["position"] for p in pos] == [1, 2, 3]

    assert pos[0]["quelle"] == "zeit"
    assert pos[0]["vorgang_id"] == str(va.id)
    assert pos[0]["menge"] == "2.00"
    assert pos[0]["einzelpreis"] == "80.00"
    assert pos[0]["beschreibung"] == "Arbeitszeit – V-A Alpha"

    assert pos[1]["quelle"] == "zeit"
    assert pos[1]["vorgang_id"] == str(vb.id)
    assert pos[1]["menge"] == "1.00"
    assert pos[1]["einzelpreis"] == "90.00"

    assert pos[2]["quelle"] == "leistung"
    assert pos[2]["vorgang_id"] == str(vb.id)
    assert pos[2]["menge"] == "3.00"
    assert pos[2]["einzelpreis"] == "65.00"
    assert pos[2]["beschreibung"] == "Stundensatz Monteur – V-B Beta"

    async with system_session() as session:
        for eintrag_id in (a, b_ohne):
            e = await session.get(Zeiterfassung, eintrag_id)
            assert e.buchungsstatus == "abgerechnet"
            assert str(e.abgerechnet_rechnung_id) == body["id"]
        # "leistung" sperrt bewusst nicht (siehe zeiterfassung_abrechnen) --
        # das gilt auch fuer die SVS-Zeit, hier also kein Status-Assert.


@pytest.mark.asyncio
async def test_sammelrechnung_ein_vorgang_setzt_rechnung_vorgang_id(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    async with system_session() as session:
        await _zeit(session, mandant=mandant, vorgang=va, techniker=admin, stunden=2)

    resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "vorgaenge": [{"vorgang_id": str(va.id)}]},
    )
    assert resp.status_code == 201
    assert resp.json()["vorgang_id"] == str(va.id)
    assert resp.json()["positionen"][0]["einzelpreis"] == "0.00"


@pytest.mark.asyncio
async def test_sammelrechnung_vorgang_ohne_stunden_keine_positionen(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "vorgaenge": [{"vorgang_id": str(va.id)}, {"vorgang_id": str(vb.id)}]},
    )
    assert resp.status_code == 201
    assert resp.json()["positionen"] == []


@pytest.mark.asyncio
async def test_sammelrechnung_validierung(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    anderer_kunde = await make_kunde(mandant=mandant)
    fremder = await make_vorgang(mandant=mandant, kunde=anderer_kunde)
    headers = auth_headers(token)

    r = await client.post(
        "/api/rechnungen",
        headers=headers,
        json={"kunde_id": str(kunde.id), "vorgaenge": [{"vorgang_id": str(va.id)}, {"vorgang_id": str(fremder.id)}]},
    )
    assert r.status_code == 400

    r = await client.post(
        "/api/rechnungen",
        headers=headers,
        json={"kunde_id": str(kunde.id), "vorgang_id": str(va.id), "vorgaenge": [{"vorgang_id": str(vb.id)}]},
    )
    assert r.status_code == 400

    r = await client.post(
        "/api/rechnungen",
        headers=headers,
        json={"kunde_id": str(kunde.id), "vorgaenge": [{"vorgang_id": str(va.id)}, {"vorgang_id": str(va.id)}]},
    )
    assert r.status_code == 400

    r = await client.post(
        "/api/rechnungen",
        headers=headers,
        json={"kunde_id": str(kunde.id), "vorgaenge": [{"vorgang_id": str(va.id), "stundensatz": "-1"}]},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_sammelrechnung_fremder_mandant_400(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    fremder_mandant = await make_mandant(name="Fremd")
    fremder_kunde = await make_kunde(mandant=fremder_mandant)
    fremder_vorgang = await make_vorgang(mandant=fremder_mandant, kunde=fremder_kunde)

    r = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "vorgaenge": [{"vorgang_id": str(fremder_vorgang.id)}]},
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

    created = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "vorgaenge": [{"vorgang_id": str(va.id)}, {"vorgang_id": str(vb.id)}]},
    )
    rechnung_id = created.json()["id"]
    pos_a = next(p for p in created.json()["positionen"] if p["vorgang_id"] == str(va.id))

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
        },
        {
            "vorgang_id": str(va.id),
            "vorgangsnummer": "V-A",
            "titel": "Alpha",
            "stunden_ohne_svs": "2.00",
            "stunden_mit_svs": "0.50",
        },
    ]
    assert str(leer.id) not in resp.text


@pytest.mark.asyncio
async def test_position_bearbeiten(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    headers = auth_headers(token)
    async with system_session() as session:
        await _zeit(session, mandant=mandant, vorgang=va, techniker=admin, stunden=2)

    created = await client.post(
        "/api/rechnungen",
        headers=headers,
        json={"kunde_id": str(kunde.id), "mwst_satz": "0", "vorgaenge": [{"vorgang_id": str(va.id)}]},
    )
    rechnung_id = created.json()["id"]
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
