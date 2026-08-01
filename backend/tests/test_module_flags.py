import secrets

import pytest

from app.core.security import hash_password
from app.db.session import system_session
from app.models.kundenportal import KundenportalZugang
from tests.conftest import auth_headers, login


async def _deaktiviere_module(client, super_admin_token, mandant_id, module: list[str]) -> None:
    resp = await client.patch(
        f"/api/admin/mandanten/{mandant_id}",
        headers=auth_headers(super_admin_token),
        json={"deaktivierte_module": module},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_me_enthaelt_deaktivierte_module(client, make_mandant, make_user):
    mandant = await make_mandant()
    super_admin = await make_user(mandant=None, role="super_admin", password="admin-pass-1")
    super_admin_token = await login(client, super_admin.email, "admin-pass-1")
    await _deaktiviere_module(client, super_admin_token, mandant.id, ["material"])

    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["deaktivierte_module"] == ["material"]


@pytest.mark.asyncio
async def test_deaktiviertes_modul_blockiert_endpunkt(client, make_mandant, make_user):
    mandant = await make_mandant()
    super_admin = await make_user(mandant=None, role="super_admin", password="admin-pass-1")
    super_admin_token = await login(client, super_admin.email, "admin-pass-1")
    await _deaktiviere_module(client, super_admin_token, mandant.id, ["material"])

    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/material", headers=auth_headers(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_modul_standardmaessig_aktiv(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/material", headers=auth_headers(token))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_anlage_create_erlaubt_wenn_nur_eines_von_zwei_modulen_aus(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    super_admin = await make_user(mandant=None, role="super_admin", password="admin-pass-1")
    super_admin_token = await login(client, super_admin.email, "admin-pass-1")
    # "material" aus, "kundenverwaltung" bleibt an -- eine Kundenanlage
    # gehoert zu Letzterem, muss also weiterhin anlegbar sein.
    await _deaktiviere_module(client, super_admin_token, mandant.id, ["material"])

    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/anlagen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "bezeichnung": "Hauptverteilung"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_anlage_create_blockiert_wenn_beide_module_aus(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    super_admin = await make_user(mandant=None, role="super_admin", password="admin-pass-1")
    super_admin_token = await login(client, super_admin.email, "admin-pass-1")
    await _deaktiviere_module(client, super_admin_token, mandant.id, ["material", "kundenverwaltung"])

    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/anlagen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "bezeichnung": "Hauptverteilung"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_kundenverwaltung_deaktiviert_blockiert_kunde_profil_aber_nicht_liste(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    super_admin = await make_user(mandant=None, role="super_admin", password="admin-pass-1")
    super_admin_token = await login(client, super_admin.email, "admin-pass-1")
    await _deaktiviere_module(client, super_admin_token, mandant.id, ["kundenverwaltung"])

    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    # Grundfunktionen fuers Anlegen eines Vorgangs bleiben unangetastet.
    list_resp = await client.get("/api/kunden", headers=auth_headers(token))
    assert list_resp.status_code == 200
    create_resp = await client.post(
        "/api/kunden", headers=auth_headers(token), json={"name": "Neuer Kunde"}
    )
    assert create_resp.status_code == 201

    # Die dedizierte Verwaltung ist blockiert.
    profil_resp = await client.get(f"/api/kunden/{kunde.id}/profil", headers=auth_headers(token))
    assert profil_resp.status_code == 403
    delete_resp = await client.delete(f"/api/kunden/{kunde.id}", headers=auth_headers(token))
    assert delete_resp.status_code == 403


@pytest.mark.asyncio
async def test_kundenportal_login_blockiert_wenn_modul_deaktiviert(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    super_admin = await make_user(mandant=None, role="super_admin", password="admin-pass-1")
    super_admin_token = await login(client, super_admin.email, "admin-pass-1")

    kunde = await make_kunde(mandant=mandant)
    async with system_session() as session:
        zugang = KundenportalZugang(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            email="kunde@example.de",
            password_hash=hash_password("kunden-pw-123"),
            name="Kundenportal-Nutzer",
            login_slug=secrets.token_urlsafe(16),
        )
        session.add(zugang)
        await session.flush()

    await _deaktiviere_module(client, super_admin_token, mandant.id, ["kundenportal"])

    resp = await client.post(
        "/api/kundenportal/auth/login",
        json={"email": "kunde@example.de", "password": "kunden-pw-123"},
    )
    assert resp.status_code == 403
