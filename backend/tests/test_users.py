import pytest

from tests.conftest import auth_headers, login


async def _extrahiere_token(link: str) -> str:
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(link).query)["token"][0]


@pytest.mark.asyncio
async def test_mandant_admin_kann_einladen_und_mitarbeiter_registriert_sich(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/users/einladungen",
        headers=auth_headers(token),
        json={"email": "neu@example.de", "role": "techniker"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "offen"
    assert body["registrierungslink"]  # kein SMTP in Tests konfiguriert -> Link kommt zurueck

    reg_token = await _extrahiere_token(body["registrierungslink"])
    reg_resp = await client.post(
        "/api/auth/registrieren",
        json={"token": reg_token, "name": "Neuer Techniker", "password": "supersecret1"},
    )
    assert reg_resp.status_code == 201
    assert reg_resp.json()["access_token"]

    me = await client.get(
        "/api/auth/me", headers=auth_headers(reg_resp.json()["access_token"])
    )
    assert me.status_code == 200
    assert me.json()["role"] == "techniker"
    assert me.json()["name"] == "Neuer Techniker"

    einladungen = await client.get("/api/users/einladungen", headers=auth_headers(token))
    assert einladungen.json()[0]["status"] == "angenommen"


@pytest.mark.asyncio
async def test_einladung_kann_nicht_zweimal_eingeloest_werden(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/users/einladungen",
        headers=auth_headers(token),
        json={"email": "doppelt@example.de", "role": "techniker"},
    )
    reg_token = await _extrahiere_token(resp.json()["registrierungslink"])
    body = {"token": reg_token, "name": "X", "password": "supersecret1"}

    first = await client.post("/api/auth/registrieren", json=body)
    assert first.status_code == 201
    second = await client.post("/api/auth/registrieren", json=body)
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_mandant_admin_kann_einladung_widerrufen(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/users/einladungen",
        headers=auth_headers(token),
        json={"email": "widerruf@example.de", "role": "techniker"},
    )
    einladung_id = resp.json()["id"]
    reg_token = await _extrahiere_token(resp.json()["registrierungslink"])

    revoke = await client.delete(
        f"/api/users/einladungen/{einladung_id}", headers=auth_headers(token)
    )
    assert revoke.status_code == 204

    reg = await client.post(
        "/api/auth/registrieren",
        json={"token": reg_token, "name": "X", "password": "supersecret1"},
    )
    assert reg.status_code == 400


@pytest.mark.asyncio
async def test_mandant_admin_cannot_invite_to_other_mandant(
    client, make_mandant, make_user
):
    own_mandant = await make_mandant(name="Eigen")
    other_mandant = await make_mandant(name="Fremd")
    admin = await make_user(
        mandant=own_mandant, role="mandant_admin", password="pw-123456"
    )
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/users/einladungen",
        headers=auth_headers(token),
        json={"email": "eindringling@example.de", "role": "techniker", "mandant_id": str(other_mandant.id)},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_einladung_lehnt_super_admin_rolle_ab(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/users/einladungen",
        headers=auth_headers(token),
        json={"email": "wannabe-admin@example.de", "role": "super_admin"},
    )
    assert resp.status_code == 422  # super_admin ist kein gueltiger Wert des Rolle-Literals


@pytest.mark.asyncio
async def test_techniker_can_list_but_not_invite_users(client, make_mandant, make_user):
    """Listing is allowed (needed for the @-mention picker in Phase 3's
    Vorgangs-Chat, and RLS keeps it scoped to the technician's own
    mandant); einladen/patchen bleibt admin-only."""
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    list_resp = await client.get("/api/users", headers=auth_headers(token))
    assert list_resp.status_code == 200

    create_resp = await client.post(
        "/api/users/einladungen",
        headers=auth_headers(token),
        json={"email": "verboten@example.de", "role": "techniker"},
    )
    assert create_resp.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_can_invite_across_mandanten(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")
    token = await login(client, super_admin.email, "pw-123456")

    resp = await client.post(
        "/api/users/einladungen",
        headers=auth_headers(token),
        json={"email": "von-super-admin@example.de", "role": "disponent", "mandant_id": str(mandant.id)},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_admin_can_delete_unused_user(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    target = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.delete(f"/api/users/{target.id}", headers=auth_headers(token))
    assert resp.status_code == 204

    get_resp = await client.get("/api/users", headers=auth_headers(token))
    assert all(u["id"] != str(target.id) for u in get_resp.json())


@pytest.mark.asyncio
async def test_user_delete_blocked_when_zeiterfassung_exists(
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
    token = await login(client, admin.email, "pw-123456")

    start = datetime.now(timezone.utc)
    async with system_session() as session:
        session.add(
            Zeiterfassung(
                mandant_id=mandant.id,
                vorgang_id=vorgang.id,
                techniker_id=techniker.id,
                start_at=start,
                ende_at=start + timedelta(hours=1),
            )
        )
        await session.flush()

    resp = await client.delete(f"/api/users/{techniker.id}", headers=auth_headers(token))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_cannot_delete_own_account(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.delete(f"/api/users/{admin.id}", headers=auth_headers(token))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cannot_delete_last_mandant_admin(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    # super_admin statt eines zweiten mandant_admin als Akteur, damit dieser
    # Test wirklich nur die "letzter Admin"-Regel prueft und nicht versehentlich
    # an der Eigenes-Konto-Sperre haengen bleibt.
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")
    token = await login(client, super_admin.email, "pw-123456")

    resp = await client.delete(f"/api/users/{admin.id}", headers=auth_headers(token))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_can_delete_mandant_admin_when_another_remains(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    other_admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.delete(f"/api/users/{other_admin.id}", headers=auth_headers(token))
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_techniker_cannot_delete_user(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    other = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.delete(f"/api/users/{other.id}", headers=auth_headers(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_deactivate_user(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    target = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/users/{target.id}",
        headers=auth_headers(token),
        json={"aktiv": False},
    )
    assert resp.status_code == 200
    assert resp.json()["aktiv"] is False

    login_resp = await client.post(
        "/api/auth/login", json={"email": target.email, "password": "pw-123456"}
    )
    assert login_resp.status_code == 403
