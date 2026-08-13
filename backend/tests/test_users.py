import pytest
from sqlalchemy import update

from app.db.session import system_session
from app.models.user import User
from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_mandant_admin_can_create_user_in_own_mandant(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    account_typ_resp = await client.post(
        "/api/account-typen", headers=auth_headers(token), json={"name": "Techniker"}
    )
    account_typ_id = account_typ_resp.json()["id"]

    resp = await client.post(
        "/api/users",
        headers=auth_headers(token),
        json={
            "mandant_id": str(mandant.id),
            "email": "neu@example.de",
            "password": "supersecret1",
            "role": "custom",
            "account_typ_id": account_typ_id,
            "name": "Neuer Techniker",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "custom"
    assert resp.json()["account_typ_id"] == account_typ_id


@pytest.mark.asyncio
async def test_mandant_admin_cannot_create_user_in_other_mandant(
    client, make_mandant, make_user
):
    own_mandant = await make_mandant(name="Eigen")
    other_mandant = await make_mandant(name="Fremd")
    admin = await make_user(
        mandant=own_mandant, role="mandant_admin", password="pw-123456"
    )
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/users",
        headers=auth_headers(token),
        json={
            "mandant_id": str(other_mandant.id),
            "email": "eindringling@example.de",
            "password": "supersecret1",
            "role": "mandant_admin",
            "name": "Eindringling",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_mandant_admin_cannot_create_super_admin(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/users",
        headers=auth_headers(token),
        json={
            "mandant_id": None,
            "email": "wannabe-admin@example.de",
            "password": "supersecret1",
            "role": "super_admin",
            "name": "Wannabe",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_techniker_can_list_but_not_create_users(client, make_mandant, make_user):
    """Listing is allowed (needed for the @-mention picker in Phase 3's
    Vorgangs-Chat, and RLS keeps it scoped to the technician's own
    mandant); creating/patching accounts remains admin-only."""
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    list_resp = await client.get("/api/users", headers=auth_headers(token))
    assert list_resp.status_code == 200

    create_resp = await client.post(
        "/api/users",
        headers=auth_headers(token),
        json={
            "mandant_id": str(mandant.id),
            "email": "verboten@example.de",
            "password": "supersecret1",
            "role": "techniker",
            "name": "Verboten",
        },
    )
    assert create_resp.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_can_create_users_across_mandanten(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")
    token = await login(client, super_admin.email, "pw-123456")

    resp = await client.post(
        "/api/users",
        headers=auth_headers(token),
        json={
            "mandant_id": str(mandant.id),
            "email": "von-super-admin@example.de",
            "password": "supersecret1",
            "role": "mandant_admin",
            "name": "Von Super Admin",
        },
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


@pytest.mark.asyncio
async def test_bottom_nav_defaults_to_null(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, user.email, "pw-123456")

    resp = await client.get("/api/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["bottom_nav_items"] is None


@pytest.mark.asyncio
async def test_user_can_set_and_reset_own_bottom_nav(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, user.email, "pw-123456")

    resp = await client.patch(
        "/api/users/me/bottom-nav",
        headers=auth_headers(token),
        json={"links": ["feed", "profil"], "rotunde": ["dispo", "zeiterfassung", "geschaeft"]},
    )
    assert resp.status_code == 200
    assert resp.json()["links"] == ["feed", "profil"]
    assert resp.json()["rotunde"] == ["dispo", "zeiterfassung", "geschaeft"]

    me_resp = await client.get("/api/auth/me", headers=auth_headers(token))
    assert me_resp.json()["bottom_nav_items"] == {
        "links": ["feed", "profil"],
        "rotunde": ["dispo", "zeiterfassung", "geschaeft"],
    }

    reset_resp = await client.patch(
        "/api/users/me/bottom-nav",
        headers=auth_headers(token),
        json={"links": None, "rotunde": None},
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["links"] is None
    assert reset_resp.json()["rotunde"] is None

    me_resp_2 = await client.get("/api/auth/me", headers=auth_headers(token))
    assert me_resp_2.json()["bottom_nav_items"] is None


@pytest.mark.asyncio
async def test_bottom_nav_is_a_pure_self_service_preference(client, make_mandant, make_user):
    # Kein mitarbeiterverwaltung-Recht noetig -- jede Rolle darf ihre eigene
    # Praeferenz setzen, auch ohne jede Verwaltungsberechtigung.
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    other = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, user.email, "pw-123456")

    resp = await client.patch(
        "/api/users/me/bottom-nav",
        headers=auth_headers(token),
        json={"links": ["feed", "profil"], "rotunde": []},
    )
    assert resp.status_code == 200

    other_token = await login(client, other.email, "pw-123456")
    other_me = await client.get("/api/auth/me", headers=auth_headers(other_token))
    assert other_me.json()["bottom_nav_items"] is None


@pytest.mark.asyncio
async def test_me_tolerates_legacy_flat_list_bottom_nav_items(client, make_mandant, make_user):
    # Vor der Aufteilung in links/rotunde war bottom_nav_items eine flache
    # Liste (siehe Migration 0059). Ein Nutzer mit einem noch nicht
    # migrierten Altwert darf sich weiterhin einloggen -- /me faellt dann
    # nur auf die Standardauswahl zurueck, statt komplett zu scheitern.
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    async with system_session() as session:
        await session.execute(
            update(User).where(User.id == user.id).values(bottom_nav_items=["dispo", "feed"])
        )

    token = await login(client, user.email, "pw-123456")
    resp = await client.get("/api/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["bottom_nav_items"] is None
