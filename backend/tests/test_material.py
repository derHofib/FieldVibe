from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.session import system_session
from app.models.material import Material
from tests.conftest import auth_headers, login


async def _make_material(mandant, **kwargs) -> Material:
    async with system_session() as session:
        material = Material(
            mandant_id=mandant.id,
            bezeichnung=kwargs.pop("bezeichnung", "Kabel NYM 3x1.5"),
            einheit=kwargs.pop("einheit", "m"),
            bestand=kwargs.pop("bestand", Decimal("10")),
            mindestbestand=kwargs.pop("mindestbestand", Decimal("5")),
            **kwargs,
        )
        session.add(material)
        await session.flush()
        await session.refresh(material)
        return material


@pytest.mark.asyncio
async def test_admin_can_create_material(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/material",
        headers=auth_headers(token),
        json={"bezeichnung": "Sicherung 16A", "einheit": "Stk", "bestand": "20", "mindestbestand": "5"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["bezeichnung"] == "Sicherung 16A"
    assert body["bestand"] == "20.00"


@pytest.mark.asyncio
async def test_techniker_cannot_create_or_update_material(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    material = await _make_material(mandant)
    token = await login(client, techniker.email, "pw-123456")

    create_resp = await client.post(
        "/api/material", headers=auth_headers(token), json={"bezeichnung": "Draht"}
    )
    assert create_resp.status_code == 403

    update_resp = await client.patch(
        f"/api/material/{material.id}", headers=auth_headers(token), json={"bestand": "1"}
    )
    assert update_resp.status_code == 403


@pytest.mark.asyncio
async def test_techniker_can_record_verwendung_and_stock_decrements(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    material = await _make_material(mandant, bestand=Decimal("10"))
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        f"/api/material/{material.id}/verwendung",
        headers=auth_headers(token),
        json={"vorgang_id": str(vorgang.id), "menge": "3"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["menge"] == "3.00"
    assert body["verwendet_von"] == str(techniker.id)

    async with system_session() as session:
        refreshed = await session.get(Material, material.id)
        assert refreshed.bestand == Decimal("7")

    events_resp = await client.get(f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(token))
    event_types = [e["event_type"] for e in events_resp.json()]
    assert "material" in event_types


@pytest.mark.asyncio
async def test_verwendung_rejected_when_bestand_insufficient(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    material = await _make_material(mandant, bestand=Decimal("2"))
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        f"/api/material/{material.id}/verwendung",
        headers=auth_headers(token),
        json={"vorgang_id": str(vorgang.id), "menge": "5"},
    )
    assert resp.status_code == 400

    async with system_session() as session:
        refreshed = await session.get(Material, material.id)
        assert refreshed.bestand == Decimal("2")


@pytest.mark.asyncio
async def test_material_bestand_cannot_go_negative_at_db_level(client, make_mandant):
    mandant = await make_mandant()

    with pytest.raises(IntegrityError):
        async with system_session() as session:
            material = Material(mandant_id=mandant.id, bezeichnung="Test", bestand=Decimal("-1"))
            session.add(material)
            await session.flush()


@pytest.mark.asyncio
async def test_mandant_isolation_for_material(client, make_mandant, make_user):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    admin1 = await make_user(mandant=mandant1, role="mandant_admin", password="pw-123456")
    admin2 = await make_user(mandant=mandant2, role="mandant_admin", password="pw-123456")
    await _make_material(mandant1)
    token2 = await login(client, admin2.email, "pw-123456")

    list_resp = await client.get("/api/material", headers=auth_headers(token2))
    assert list_resp.json() == []
