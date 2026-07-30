import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_start_and_stop_timer(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    start_resp = await client.post(
        "/api/zeiterfassung/start",
        headers=auth_headers(token),
        json={"vorgang_id": str(vorgang.id), "taetigkeit": "Fehlersuche"},
    )
    assert start_resp.status_code == 201
    eintrag = start_resp.json()
    assert eintrag["ende_at"] is None

    laufend_resp = await client.get("/api/zeiterfassung/laufend", headers=auth_headers(token))
    assert laufend_resp.json()["id"] == eintrag["id"]

    stop_resp = await client.post(
        f"/api/zeiterfassung/{eintrag['id']}/stop", headers=auth_headers(token)
    )
    assert stop_resp.status_code == 200
    assert stop_resp.json()["ende_at"] is not None

    laufend_after = await client.get("/api/zeiterfassung/laufend", headers=auth_headers(token))
    assert laufend_after.json() is None

    events_resp = await client.get(
        f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(token)
    )
    event_types = [e["event_type"] for e in events_resp.json()]
    assert "zeit_start" in event_types
    assert "zeit_stop" in event_types


@pytest.mark.asyncio
async def test_cannot_start_second_timer(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang1 = await make_vorgang(mandant=mandant, kunde=kunde, titel="V1")
    vorgang2 = await make_vorgang(mandant=mandant, kunde=kunde, titel="V2")
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    first = await client.post(
        "/api/zeiterfassung/start", headers=auth_headers(token), json={"vorgang_id": str(vorgang1.id)}
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/zeiterfassung/start", headers=auth_headers(token), json={"vorgang_id": str(vorgang2.id)}
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_different_technikers_can_each_run_a_timer(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    tech1 = await make_user(mandant=mandant, role="techniker", password="pw-123456", name="Tech1")
    tech2 = await make_user(mandant=mandant, role="techniker", password="pw-123456", name="Tech2")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=tech1)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=tech2)
    token1 = await login(client, tech1.email, "pw-123456")
    token2 = await login(client, tech2.email, "pw-123456")

    resp1 = await client.post(
        "/api/zeiterfassung/start", headers=auth_headers(token1), json={"vorgang_id": str(vorgang.id)}
    )
    resp2 = await client.post(
        "/api/zeiterfassung/start", headers=auth_headers(token2), json={"vorgang_id": str(vorgang.id)}
    )
    assert resp1.status_code == 201
    assert resp2.status_code == 201


@pytest.mark.asyncio
async def test_cannot_stop_someone_elses_timer(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    tech1 = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    tech2 = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=tech1)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=tech2)
    token1 = await login(client, tech1.email, "pw-123456")
    token2 = await login(client, tech2.email, "pw-123456")

    start_resp = await client.post(
        "/api/zeiterfassung/start", headers=auth_headers(token1), json={"vorgang_id": str(vorgang.id)}
    )
    eintrag_id = start_resp.json()["id"]

    resp = await client.post(
        f"/api/zeiterfassung/{eintrag_id}/stop", headers=auth_headers(token2)
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_timer_laeuft_reflected_in_feed(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    before = await client.get("/api/feed", headers=auth_headers(token))
    assert before.json()["items"][0]["timer_laeuft"] is False

    await client.post(
        "/api/zeiterfassung/start", headers=auth_headers(token), json={"vorgang_id": str(vorgang.id)}
    )

    after = await client.get("/api/feed", headers=auth_headers(token))
    card = next(i for i in after.json()["items"] if i["id"] == str(vorgang.id))
    assert card["timer_laeuft"] is True


@pytest.mark.asyncio
async def test_statistik_berechnet_wochen_monats_jahresstunden(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    from datetime import datetime, timedelta, timezone

    from app.db.session import system_session
    from app.models.zeiterfassung import Zeiterfassung

    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)

    heute = datetime.now(timezone.utc)
    diese_woche = heute.replace(hour=8, minute=0, second=0, microsecond=0)
    letzter_monat = (heute - timedelta(days=40)).replace(hour=8, minute=0, second=0, microsecond=0)
    letztes_jahr = (heute - timedelta(days=400)).replace(hour=8, minute=0, second=0, microsecond=0)

    async with system_session() as session:
        for start, dauer_stunden in (
            (diese_woche, 2),
            (letzter_monat, 3),
            (letztes_jahr, 5),
        ):
            session.add(
                Zeiterfassung(
                    mandant_id=mandant.id,
                    vorgang_id=vorgang.id,
                    techniker_id=techniker.id,
                    start_at=start,
                    ende_at=start + timedelta(hours=dauer_stunden),
                )
            )
        await session.flush()

    admin_token = await login(client, admin.email, "pw-123456")
    resp = await client.get(
        "/api/zeiterfassung/statistik",
        headers=auth_headers(admin_token),
        params={"techniker_id": str(techniker.id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["wochenstunden"] == "2.0"
    assert body["jahresstunden"] == "5.0"


@pytest.mark.asyncio
async def test_techniker_kann_nur_eigene_statistik_sehen(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    tech1 = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    tech2 = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token1 = await login(client, tech1.email, "pw-123456")

    eigene = await client.get("/api/zeiterfassung/statistik", headers=auth_headers(token1))
    assert eigene.status_code == 200

    fremde = await client.get(
        "/api/zeiterfassung/statistik",
        headers=auth_headers(token1),
        params={"techniker_id": str(tech2.id)},
    )
    assert fremde.status_code == 403


@pytest.mark.asyncio
async def test_wochenzettel_pdf_wird_zurueckgegeben(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    from datetime import date, timedelta

    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    await client.post(
        "/api/zeiterfassung/start", headers=auth_headers(token), json={"vorgang_id": str(vorgang.id)}
    )
    laufend = (await client.get("/api/zeiterfassung/laufend", headers=auth_headers(token))).json()
    await client.post(f"/api/zeiterfassung/{laufend['id']}/stop", headers=auth_headers(token))

    heute = date.today()
    montag = heute - timedelta(days=heute.weekday())
    resp = await client.get(
        "/api/zeiterfassung/wochenzettel-pdf",
        headers=auth_headers(token),
        params={"woche_start": montag.isoformat()},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_eigene_zeiterfassung_bleibt_sichtbar_nach_entzug_der_zuweisung(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    """Die persoenliche Statistik/Zeitliste eines Technikers darf nicht
    ruecknachtraeglich Eintraege verlieren, nur weil die Kunde-Zuweisung
    inzwischen entzogen wurde -- geleistete Arbeit bleibt geleistete Arbeit."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    await client.post(
        "/api/zeiterfassung/start", headers=auth_headers(token), json={"vorgang_id": str(vorgang.id)}
    )
    laufend = (await client.get("/api/zeiterfassung/laufend", headers=auth_headers(token))).json()
    await client.post(f"/api/zeiterfassung/{laufend['id']}/stop", headers=auth_headers(token))

    admin_token = await login(client, admin.email, "pw-123456")
    await client.put(
        f"/api/kunden/{kunde.id}/techniker", headers=auth_headers(admin_token), json={"user_ids": []}
    )

    resp = await client.get(
        "/api/zeiterfassung",
        headers=auth_headers(token),
        params={"techniker_id": str(techniker.id)},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
