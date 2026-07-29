import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_mention_in_comment_creates_notification(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    author = await make_user(mandant=mandant, role="techniker", password="pw-123456", name="Ali")
    mentioned = await make_user(
        mandant=mandant, role="disponent", password="pw-123456", name="Jens"
    )
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    author_token = await login(client, author.email, "pw-123456")

    resp = await client.post(
        f"/api/vorgaenge/{vorgang.id}/events",
        headers=auth_headers(author_token),
        json={
            "event_type": "kommentar",
            "body": f"@[Jens]({mentioned.id}) kannst du das übernehmen?",
        },
    )
    assert resp.status_code == 201

    mentioned_token = await login(client, mentioned.email, "pw-123456")
    notif_resp = await client.get("/api/notifications", headers=auth_headers(mentioned_token))
    assert notif_resp.status_code == 200
    notifications = notif_resp.json()
    assert len(notifications) == 1
    assert notifications[0]["typ"] == "mention"
    assert notifications[0]["ref_entity_id"] == str(vorgang.id)
    assert notifications[0]["gelesen_am"] is None


@pytest.mark.asyncio
async def test_self_mention_does_not_notify(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    author = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, author.email, "pw-123456")

    await client.post(
        f"/api/vorgaenge/{vorgang.id}/events",
        headers=auth_headers(token),
        json={"event_type": "kommentar", "body": f"@[Mich]({author.id}) notiere ich mir selbst"},
    )

    resp = await client.get("/api/notifications", headers=auth_headers(token))
    assert resp.json() == []


@pytest.mark.asyncio
async def test_mark_notification_as_read(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    author = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    mentioned = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    author_token = await login(client, author.email, "pw-123456")

    await client.post(
        f"/api/vorgaenge/{vorgang.id}/events",
        headers=auth_headers(author_token),
        json={"event_type": "kommentar", "body": f"@[X]({mentioned.id}) bitte prüfen"},
    )

    mentioned_token = await login(client, mentioned.email, "pw-123456")
    notif = (await client.get("/api/notifications", headers=auth_headers(mentioned_token))).json()[0]

    read_resp = await client.post(
        f"/api/notifications/{notif['id']}/gelesen", headers=auth_headers(mentioned_token)
    )
    assert read_resp.status_code == 200
    assert read_resp.json()["gelesen_am"] is not None

    unread_resp = await client.get(
        "/api/notifications",
        headers=auth_headers(mentioned_token),
        params={"nur_ungelesen": True},
    )
    assert unread_resp.json() == []


@pytest.mark.asyncio
async def test_cannot_mark_other_users_notification_as_read(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    author = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    mentioned = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    bystander = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    author_token = await login(client, author.email, "pw-123456")

    await client.post(
        f"/api/vorgaenge/{vorgang.id}/events",
        headers=auth_headers(author_token),
        json={"event_type": "kommentar", "body": f"@[X]({mentioned.id}) bitte prüfen"},
    )

    mentioned_token = await login(client, mentioned.email, "pw-123456")
    notif = (await client.get("/api/notifications", headers=auth_headers(mentioned_token))).json()[0]

    bystander_token = await login(client, bystander.email, "pw-123456")
    resp = await client.post(
        f"/api/notifications/{notif['id']}/gelesen", headers=auth_headers(bystander_token)
    )
    assert resp.status_code == 404
