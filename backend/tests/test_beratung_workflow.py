from decimal import Decimal

import pytest

from app.db.session import system_session
from app.models.material import Material
from tests.conftest import auth_headers, login


async def _make_material(mandant, **kwargs) -> Material:
    async with system_session() as session:
        material = Material(
            mandant_id=mandant.id,
            bezeichnung=kwargs.pop("bezeichnung", "Kabel NYM 3x1.5"),
            einheit=kwargs.pop("einheit", "m"),
            einzelpreis=kwargs.pop("einzelpreis", Decimal("2.50")),
            artikelnummer=kwargs.pop("artikelnummer", "ART-001"),
            **kwargs,
        )
        session.add(material)
        await session.flush()
        await session.refresh(material)
        return material


@pytest.mark.asyncio
async def test_beratung_abschluss_mit_folge_leistungstyp_legt_folgevorgang_an(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, leistungstyp="beratung")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}",
        headers=auth_headers(token),
        json={"status": "abgeschlossen", "folge_leistungstyp": "planung"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "abgeschlossen"
    folge_vorgang_id = body["folge_vorgang_id"]
    assert folge_vorgang_id is not None

    folge_resp = await client.get(
        f"/api/vorgaenge/{folge_vorgang_id}", headers=auth_headers(token)
    )
    assert folge_resp.status_code == 200
    folge = folge_resp.json()
    assert folge["leistungstyp"] == "planung"
    assert folge["parent_vorgang_id"] == str(vorgang.id)
    assert folge["kunde_id"] == str(kunde.id)
    assert folge["status"] == "neu"


@pytest.mark.asyncio
async def test_folge_leistungstyp_nur_bei_beratung_erlaubt(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, leistungstyp="wartung")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}",
        headers=auth_headers(token),
        json={"status": "abgeschlossen", "folge_leistungstyp": "planung"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_folge_leistungstyp_ohne_gleichzeitigen_abschluss_abgelehnt(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, leistungstyp="beratung")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}",
        headers=auth_headers(token),
        json={"folge_leistungstyp": "planung"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_offene_angebots_bedarfe_werden_uebertragen_ohne_informationsverlust(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, leistungstyp="beratung")
    material = await _make_material(mandant)
    token = await login(client, admin.email, "pw-123456")

    bedarf_resp = await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(token),
        json={
            "material_id": str(material.id),
            "vorgang_id": str(vorgang.id),
            "menge": "10",
            "zweck": "angebot",
        },
    )
    alter_bedarf_id = bedarf_resp.json()["id"]

    close_resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}",
        headers=auth_headers(token),
        json={"status": "abgeschlossen", "folge_leistungstyp": "planung"},
    )
    folge_vorgang_id = close_resp.json()["folge_vorgang_id"]

    alter_bedarf = await client.get(
        "/api/material-bedarfe", headers=auth_headers(token), params={"vorgang_id": str(vorgang.id)}
    )
    [alt] = alter_bedarf.json()
    assert alt["id"] == alter_bedarf_id
    assert alt["status"] == "uebertragen"

    neuer_bedarf = await client.get(
        "/api/material-bedarfe", headers=auth_headers(token), params={"vorgang_id": folge_vorgang_id}
    )
    [neu] = neuer_bedarf.json()
    assert neu["status"] == "offen"
    assert neu["uebernommen_von_id"] == alter_bedarf_id
    assert neu["menge"] == "10.00"

    # Nur EIN offener Bedarf insgesamt -- kein doppeltes Melden.
    alle_offenen = await client.get(
        "/api/material-bedarfe", headers=auth_headers(token), params={"status": "offen"}
    )
    assert len(alle_offenen.json()) == 1


@pytest.mark.asyncio
async def test_angebot_aus_vorgang_uebernimmt_offene_bedarfe(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, leistungstyp="planung")
    material = await _make_material(mandant, artikelnummer="B-3025-078")
    token = await login(client, admin.email, "pw-123456")

    await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(token),
        json={
            "material_id": str(material.id),
            "vorgang_id": str(vorgang.id),
            "menge": "4",
            "zweck": "angebot",
        },
    )

    resp = await client.post(
        "/api/angebote/from-vorgang",
        headers=auth_headers(token),
        json={"vorgang_id": str(vorgang.id)},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["kunde_id"] == str(kunde.id)
    [position] = body["positionen"]
    assert position["artikelnummer"] == "B-3025-078"
    assert position["menge"] == "4.00"
    assert position["positionstyp"] == "material"

    bedarfe = await client.get(
        "/api/material-bedarfe", headers=auth_headers(token), params={"vorgang_id": str(vorgang.id)}
    )
    assert bedarfe.json()[0]["status"] == "in_angebot"


@pytest.mark.asyncio
async def test_angebot_aus_vorgang_ohne_material_bedarfe_ist_leer(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, leistungstyp="beratung")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/angebote/from-vorgang",
        headers=auth_headers(token),
        json={"vorgang_id": str(vorgang.id)},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["kunde_id"] == str(kunde.id)
    assert body["vorgang_id"] == str(vorgang.id)
    assert body["positionen"] == []


@pytest.mark.asyncio
async def test_angebotsposition_arbeitszeit_typ(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/angebote",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id)},
    )
    angebot_id = created.json()["id"]

    resp = await client.post(
        f"/api/angebote/{angebot_id}/positionen",
        headers=auth_headers(token),
        json={
            "beschreibung": "Beratung vor Ort",
            "menge": "3",
            "einheit": "Std",
            "einzelpreis": "75.00",
            "positionstyp": "arbeitszeit",
        },
    )
    assert resp.status_code == 200
    [position] = resp.json()["positionen"]
    assert position["positionstyp"] == "arbeitszeit"
