from datetime import date

import pytest

from app.services.date_utils import add_months
from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_create_pruefmittel_defaults_naechste_kalibrierung(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/pruefmittel",
        headers=auth_headers(token),
        json={"bezeichnung": "Installationstester", "kalibrierintervall_monate": 24},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "aktiv"
    assert body["naechste_kalibrierung_am"] == add_months(date.today(), 24).isoformat()


@pytest.mark.asyncio
async def test_assign_pruefmittel_to_techniker(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/pruefmittel",
        headers=auth_headers(token),
        json={
            "bezeichnung": "Multimeter",
            "kalibrierintervall_monate": 12,
            "zugewiesen_an": str(techniker.id),
        },
    )
    assert resp.status_code == 201
    assert resp.json()["zugewiesen_an"] == str(techniker.id)

    list_resp = await client.get(
        "/api/pruefmittel", headers=auth_headers(token), params={"zugewiesen_an": str(techniker.id)}
    )
    assert len(list_resp.json()) == 1


@pytest.mark.asyncio
async def test_invalid_status_rejected(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/pruefmittel",
        headers=auth_headers(token),
        json={"bezeichnung": "Multimeter", "kalibrierintervall_monate": 12},
    )
    pruefmittel_id = created.json()["id"]

    resp = await client.patch(
        f"/api/pruefmittel/{pruefmittel_id}",
        headers=auth_headers(token),
        json={"status": "kaputt"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_techniker_cannot_create_pruefmittel(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/pruefmittel",
        headers=auth_headers(token),
        json={"bezeichnung": "Multimeter", "kalibrierintervall_monate": 12},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_mandant_isolation_for_pruefmittel(client, make_mandant, make_user):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    admin1 = await make_user(mandant=mandant1, role="mandant_admin", password="pw-123456")
    admin2 = await make_user(mandant=mandant2, role="mandant_admin", password="pw-123456")
    token1 = await login(client, admin1.email, "pw-123456")
    token2 = await login(client, admin2.email, "pw-123456")

    created = await client.post(
        "/api/pruefmittel",
        headers=auth_headers(token1),
        json={"bezeichnung": "Multimeter", "kalibrierintervall_monate": 12},
    )
    assert created.status_code == 201

    list_resp = await client.get("/api/pruefmittel", headers=auth_headers(token2))
    assert list_resp.json() == []
