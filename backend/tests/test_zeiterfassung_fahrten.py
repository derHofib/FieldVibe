"""Zeiterfassung Stufe 3 (docs/konzepte/ZEITERFASSUNG.md): Fahrten mit km."""
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_km_nur_bei_kategorie_fahrzeit(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    start = datetime.now(timezone.utc)
    resp = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": start.isoformat(),
            "ende_at": (start + timedelta(hours=1)).isoformat(),
            "kategorie": "sonstiges",
            "km": "12.5",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_fahrzeug_nur_bei_kategorie_fahrzeit(client, make_mandant, make_user, make_anlage):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter 1")
    token = await login(client, techniker.email, "pw-123456")

    start = datetime.now(timezone.utc)
    resp = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": start.isoformat(),
            "ende_at": (start + timedelta(hours=1)).isoformat(),
            "kategorie": "verwaltung",
            "fahrzeug_id": str(fahrzeug.id),
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_fahrzeug_muss_objekttyp_fahrzeug_haben(client, make_mandant, make_user, make_kunde, make_anlage):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    keine_anlage_fahrzeug = await make_anlage(mandant=mandant, kunde=kunde)
    token = await login(client, techniker.email, "pw-123456")

    start = datetime.now(timezone.utc)
    resp = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": start.isoformat(),
            "ende_at": (start + timedelta(hours=1)).isoformat(),
            "kategorie": "fahrzeit",
            "km": "42.0",
            "fahrzeug_id": str(keine_anlage_fahrzeug.id),
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_fahrt_mit_km_und_fahrzeug_anlegen(client, make_mandant, make_user, make_anlage):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter 1")
    token = await login(client, techniker.email, "pw-123456")

    start = datetime.now(timezone.utc)
    resp = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": start.isoformat(),
            "ende_at": (start + timedelta(hours=1)).isoformat(),
            "kategorie": "fahrzeit",
            "km": "37.5",
            "fahrzeug_id": str(fahrzeug.id),
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["km"] == "37.5"
    assert body["fahrzeug_id"] == str(fahrzeug.id)
    assert body["quelle"] == "manuell"


@pytest.mark.asyncio
async def test_start_timer_setzt_quelle_timer(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/zeiterfassung/start",
        headers=auth_headers(token),
        json={"vorgang_id": str(vorgang.id)},
    )
    assert resp.status_code == 201
    assert resp.json()["quelle"] == "timer"


@pytest.mark.asyncio
async def test_patch_km_ohne_fahrzeit_kategorie_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    start = datetime.now(timezone.utc)
    erstellt = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": start.isoformat(),
            "ende_at": (start + timedelta(hours=1)).isoformat(),
            "kategorie": "sonstiges",
        },
    )
    assert erstellt.status_code == 201
    eintrag_id = erstellt.json()["id"]

    resp = await client.patch(
        f"/api/zeiterfassung/{eintrag_id}",
        headers=auth_headers(token),
        json={"km": "5.0"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patch_km_bei_fahrzeit_erlaubt(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    start = datetime.now(timezone.utc)
    erstellt = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": start.isoformat(),
            "ende_at": (start + timedelta(hours=1)).isoformat(),
            "kategorie": "fahrzeit",
        },
    )
    assert erstellt.status_code == 201
    eintrag_id = erstellt.json()["id"]

    resp = await client.patch(
        f"/api/zeiterfassung/{eintrag_id}",
        headers=auth_headers(token),
        json={"km": "5.5"},
    )
    assert resp.status_code == 200
    assert resp.json()["km"] == "5.5"
