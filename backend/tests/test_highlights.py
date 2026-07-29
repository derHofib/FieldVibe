import pytest

from app.db.session import system_session
from app.models.vorgang_event import VorgangEvent
from tests.conftest import auth_headers, login


async def _make_foto_event(mandant, vorgang, **kwargs) -> VorgangEvent:
    async with system_session() as session:
        kwargs.setdefault("event_type", "foto")
        kwargs.setdefault("payload", {"key": "fotos/test.jpg", "thumbnail_key": "fotos/test_thumb.jpg"})
        event = VorgangEvent(
            mandant_id=mandant.id,
            vorgang_id=vorgang.id,
            **kwargs,
        )
        session.add(event)
        await session.flush()
        await session.refresh(event)
        return event


@pytest.mark.asyncio
async def test_create_and_list_highlight(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    event = await _make_foto_event(mandant, vorgang)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/highlights", headers=auth_headers(token), json={"vorgang_event_id": event.id, "titel": "Schön geworden"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["vorgang_event_id"] == event.id
    assert body["vorgang_id"] == str(vorgang.id)
    assert body["vorgangsnummer"] == vorgang.vorgangsnummer
    assert body["foto_url"] is not None

    list_resp = await client.get("/api/highlights", headers=auth_headers(token))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


@pytest.mark.asyncio
async def test_cannot_highlight_non_foto_event(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    event = await _make_foto_event(mandant, vorgang, event_type="kommentar", body="Text", payload={})
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/highlights", headers=auth_headers(token), json={"vorgang_event_id": event.id}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_highlight_returns_409(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    event = await _make_foto_event(mandant, vorgang)
    token = await login(client, techniker.email, "pw-123456")

    first = await client.post(
        "/api/highlights", headers=auth_headers(token), json={"vorgang_event_id": event.id}
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/highlights", headers=auth_headers(token), json={"vorgang_event_id": event.id}
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_techniker_can_only_delete_own_highlight(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    techniker1 = await make_user(mandant=mandant, role="techniker", password="pw-123456", email="t1@example.de")
    techniker2 = await make_user(mandant=mandant, role="techniker", password="pw-123456", email="t2@example.de")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    event = await _make_foto_event(mandant, vorgang)
    token1 = await login(client, techniker1.email, "pw-123456")
    token2 = await login(client, techniker2.email, "pw-123456")

    created = await client.post(
        "/api/highlights", headers=auth_headers(token1), json={"vorgang_event_id": event.id}
    )
    highlight_id = created.json()["id"]

    forbidden = await client.delete(f"/api/highlights/{highlight_id}", headers=auth_headers(token2))
    assert forbidden.status_code == 403

    allowed = await client.delete(f"/api/highlights/{highlight_id}", headers=auth_headers(token1))
    assert allowed.status_code == 204


@pytest.mark.asyncio
async def test_admin_can_delete_any_highlight(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456", email="admin@example.de")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456", email="tech@example.de")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    event = await _make_foto_event(mandant, vorgang)
    tech_token = await login(client, techniker.email, "pw-123456")
    admin_token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/highlights", headers=auth_headers(tech_token), json={"vorgang_event_id": event.id}
    )
    highlight_id = created.json()["id"]

    resp = await client.delete(f"/api/highlights/{highlight_id}", headers=auth_headers(admin_token))
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_mandant_isolation_for_highlights(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    techniker1 = await make_user(mandant=mandant1, role="techniker", password="pw-123456")
    techniker2 = await make_user(mandant=mandant2, role="techniker", password="pw-123456")
    kunde1 = await make_kunde(mandant=mandant1)
    vorgang1 = await make_vorgang(mandant=mandant1, kunde=kunde1)
    event1 = await _make_foto_event(mandant1, vorgang1)
    token1 = await login(client, techniker1.email, "pw-123456")
    token2 = await login(client, techniker2.email, "pw-123456")

    created = await client.post(
        "/api/highlights", headers=auth_headers(token1), json={"vorgang_event_id": event1.id}
    )
    assert created.status_code == 201

    list_resp = await client.get("/api/highlights", headers=auth_headers(token2))
    assert list_resp.json() == []
