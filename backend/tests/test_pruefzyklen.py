from datetime import date, datetime, timezone

import pytest

from app.services.date_utils import add_intervall
from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_create_pruefzyklus_without_letzte_pruefung_defaults_to_today(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/pruefzyklen",
        headers=auth_headers(token),
        json={
            "anlage_id": str(anlage.id),
            "bezeichnung": "E-Check",
            "intervall_wert": 12,
            "intervall_einheit": "monat",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["letzte_pruefung_am"] is None
    naechste = datetime.fromisoformat(body["naechste_pruefung_am"])
    erwartet = add_intervall(datetime.now(timezone.utc), "monat", 12)
    assert abs((naechste - erwartet).total_seconds()) < 60
    assert body["aktiv"] is True
    assert body["offener_vorgang_id"] is None


@pytest.mark.asyncio
async def test_create_pruefzyklus_with_letzte_pruefung_am(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    letzte = date(2025, 1, 15)
    resp = await client.post(
        "/api/pruefzyklen",
        headers=auth_headers(token),
        json={
            "anlage_id": str(anlage.id),
            "bezeichnung": "DGUV V3",
            "intervall_wert": 6,
            "intervall_einheit": "monat",
            "letzte_pruefung_am": letzte.isoformat(),
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    basis = datetime(2025, 1, 15, tzinfo=timezone.utc)
    assert datetime.fromisoformat(body["naechste_pruefung_am"]) == add_intervall(basis, "monat", 6)


@pytest.mark.asyncio
async def test_create_pruefzyklus_mit_stunden_einheit(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    letzte = date(2025, 1, 15)
    resp = await client.post(
        "/api/pruefzyklen",
        headers=auth_headers(token),
        json={
            "anlage_id": str(anlage.id),
            "bezeichnung": "Betriebsprüfung",
            "intervall_wert": 48,
            "intervall_einheit": "stunde",
            "letzte_pruefung_am": letzte.isoformat(),
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    basis = datetime(2025, 1, 15, tzinfo=timezone.utc)
    assert datetime.fromisoformat(body["naechste_pruefung_am"]) == add_intervall(basis, "stunde", 48)
    assert body["intervall_einheit"] == "stunde"
    assert body["intervall_wert"] == 48


@pytest.mark.asyncio
async def test_techniker_can_list_but_not_create(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    token = await login(client, techniker.email, "pw-123456")

    list_resp = await client.get("/api/pruefzyklen", headers=auth_headers(token))
    assert list_resp.status_code == 200

    create_resp = await client.post(
        "/api/pruefzyklen",
        headers=auth_headers(token),
        json={"anlage_id": str(anlage.id), "bezeichnung": "E-Check", "intervall_wert": 12, "intervall_einheit": "monat"},
    )
    assert create_resp.status_code == 403


@pytest.mark.asyncio
async def test_updating_letzte_pruefung_am_recomputes_naechste_and_clears_offener_vorgang(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/pruefzyklen",
        headers=auth_headers(token),
        json={"anlage_id": str(anlage.id), "bezeichnung": "E-Check", "intervall_wert": 12, "intervall_einheit": "monat"},
    )
    pruefzyklus_id = created.json()["id"]

    neue_pruefung = date(2026, 3, 1)
    resp = await client.patch(
        f"/api/pruefzyklen/{pruefzyklus_id}",
        headers=auth_headers(token),
        json={"letzte_pruefung_am": neue_pruefung.isoformat()},
    )
    assert resp.status_code == 200
    body = resp.json()
    basis = datetime(2026, 3, 1, tzinfo=timezone.utc)
    assert datetime.fromisoformat(body["letzte_pruefung_am"]) == basis
    assert datetime.fromisoformat(body["naechste_pruefung_am"]) == add_intervall(basis, "monat", 12)
    assert body["offener_vorgang_id"] is None


@pytest.mark.asyncio
async def test_mandant_isolation_for_pruefzyklen(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    admin1 = await make_user(mandant=mandant1, role="mandant_admin", password="pw-123456")
    admin2 = await make_user(mandant=mandant2, role="mandant_admin", password="pw-123456")
    kunde1 = await make_kunde(mandant=mandant1)
    anlage1 = await make_anlage(mandant=mandant1, kunde=kunde1)
    token1 = await login(client, admin1.email, "pw-123456")
    token2 = await login(client, admin2.email, "pw-123456")

    created = await client.post(
        "/api/pruefzyklen",
        headers=auth_headers(token1),
        json={"anlage_id": str(anlage1.id), "bezeichnung": "E-Check", "intervall_wert": 12, "intervall_einheit": "monat"},
    )
    assert created.status_code == 201

    list_resp = await client.get("/api/pruefzyklen", headers=auth_headers(token2))
    assert list_resp.json() == []
