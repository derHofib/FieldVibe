import jwt
import pytest

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_kundenportal_access_token,
    create_partner_access_token,
    hash_password,
)
from app.db.session import system_session
from app.models.kundenportal import KundenportalZugang
from app.models.mandant import Mandant
from app.models.partner_zugang import PartnerZugang
from app.models.user import User
from tests.conftest import auth_headers

_settings = get_settings()
_PW = "pw-123456"


async def _login_paar(client, email, password=_PW):
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    resp.raise_for_status()
    return resp.json()["access_token"], resp.json()["refresh_token"]


async def _me(client, access):
    return (await client.get("/api/auth/me", headers=auth_headers(access))).status_code


async def _refresh(client, refresh):
    return (await client.post("/api/auth/refresh", json={"refresh_token": refresh})).status_code


async def _setup(client, make_mandant, make_user, role="techniker"):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=_PW)
    user = await make_user(mandant=mandant, role=role, password=_PW)
    admin_access, _ = await _login_paar(client, admin.email)
    access, refresh = await _login_paar(client, user.email)
    assert await _me(client, access) == 200
    return mandant, admin, admin_access, user, access, refresh


async def _assert_widerrufen(client, access, refresh):
    assert await _me(client, access) == 401
    assert await _refresh(client, refresh) == 401


def _ohne_tv(token: str) -> str:
    claims = jwt.decode(token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm])
    claims.pop("tv")
    return jwt.encode(claims, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)


@pytest.mark.asyncio
async def test_token_ohne_tv_claim_gilt_als_tv_0(client, make_mandant, make_user):
    _, _, _, _, access, refresh = await _setup(client, make_mandant, make_user)
    assert await _me(client, _ohne_tv(access)) == 200
    assert await _refresh(client, _ohne_tv(refresh)) == 200


@pytest.mark.asyncio
async def test_token_ohne_tv_claim_nach_widerruf_ungueltig(client, make_mandant, make_user):
    _, _, admin_access, user, access, refresh = await _setup(client, make_mandant, make_user)
    alt_access, alt_refresh = _ohne_tv(access), _ohne_tv(refresh)
    resp = await client.post(f"/api/users/{user.id}/abmelden", headers=auth_headers(admin_access))
    assert resp.status_code == 204
    await _assert_widerrufen(client, alt_access, alt_refresh)


@pytest.mark.asyncio
async def test_impersonation_token_ohne_tv_ungueltig(client, make_mandant, make_user):
    mandant = await make_mandant()
    super_admin = await make_user(mandant=None, role="super_admin", password=_PW)
    sa_access, _ = await _login_paar(client, super_admin.email)
    imp = (
        await client.post(f"/api/admin/mandanten/{mandant.id}/impersonate", headers=auth_headers(sa_access))
    ).json()["access_token"]
    assert await _me(client, _ohne_tv(imp)) == 401


@pytest.mark.asyncio
async def test_token_mit_falschem_tv_ist_ungueltig(client, make_mandant, make_user):
    mandant, _, _, user, _, _ = await _setup(client, make_mandant, make_user)
    falsch = create_access_token(
        subject=user.id, role=user.role, mandant_id=mandant.id,
        account_typ_id=user.account_typ_id, token_version=7,
    )
    assert await _me(client, falsch) == 401


@pytest.mark.asyncio
async def test_refresh_liefert_tokens_mit_aktuellem_tv(client, make_mandant, make_user):
    _, _, _, _, _, refresh = await _setup(client, make_mandant, make_user)
    resp = await client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    assert await _me(client, resp.json()["access_token"]) == 200
    assert await _refresh(client, resp.json()["refresh_token"]) == 200


@pytest.mark.asyncio
async def test_deaktivieren_widerruft(client, make_mandant, make_user):
    _, _, admin_access, user, access, refresh = await _setup(client, make_mandant, make_user)
    resp = await client.patch(f"/api/users/{user.id}", json={"aktiv": False}, headers=auth_headers(admin_access))
    assert resp.status_code == 200
    await _assert_widerrufen(client, access, refresh)


@pytest.mark.asyncio
async def test_passwortwechsel_durch_admin_widerruft(client, make_mandant, make_user):
    _, _, admin_access, user, access, refresh = await _setup(client, make_mandant, make_user)
    resp = await client.patch(
        f"/api/users/{user.id}", json={"password": "neues-passwort-1"}, headers=auth_headers(admin_access)
    )
    assert resp.status_code == 200
    await _assert_widerrufen(client, access, refresh)
    neu, _ = await _login_paar(client, user.email, "neues-passwort-1")
    assert await _me(client, neu) == 200


@pytest.mark.asyncio
async def test_rollenwechsel_widerruft(client, make_mandant, make_user):
    _, _, admin_access, user, access, refresh = await _setup(client, make_mandant, make_user)
    resp = await client.patch(
        f"/api/users/{user.id}", json={"role": "mandant_admin"}, headers=auth_headers(admin_access)
    )
    assert resp.status_code == 200
    await _assert_widerrufen(client, access, refresh)


@pytest.mark.asyncio
async def test_unveraenderter_patch_widerruft_nicht(client, make_mandant, make_user):
    _, _, admin_access, user, access, refresh = await _setup(client, make_mandant, make_user)
    resp = await client.patch(
        f"/api/users/{user.id}", json={"name": "Neuer Name", "aktiv": True}, headers=auth_headers(admin_access)
    )
    assert resp.status_code == 200
    assert await _me(client, access) == 200
    assert await _refresh(client, refresh) == 200


@pytest.mark.asyncio
async def test_loeschen_widerruft(client, make_mandant, make_user):
    _, _, admin_access, user, access, refresh = await _setup(client, make_mandant, make_user)
    resp = await client.delete(f"/api/users/{user.id}", headers=auth_headers(admin_access))
    assert resp.status_code == 204
    await _assert_widerrufen(client, access, refresh)


@pytest.mark.asyncio
async def test_anonymisieren_erhoeht_token_version(client, make_mandant, make_user):
    from app.services.user_anonymisierung_service import anonymisiere_user

    _, _, _, user, access, refresh = await _setup(client, make_mandant, make_user)
    async with system_session() as session:
        db_user = await session.get(User, user.id)
        await anonymisiere_user(session, db_user)
    await _assert_widerrufen(client, access, refresh)


@pytest.mark.asyncio
async def test_ueberall_abmelden_eigener_user(client, make_mandant, make_user):
    _, _, admin_access, user, access, refresh = await _setup(client, make_mandant, make_user)
    zweites_geraet, _ = await _login_paar(client, user.email)

    resp = await client.post("/api/auth/ueberall-abmelden", headers=auth_headers(access))
    assert resp.status_code == 204
    await _assert_widerrufen(client, access, refresh)
    assert await _me(client, zweites_geraet) == 401
    assert await _me(client, admin_access) == 200  # andere Nutzer unberuehrt

    neu, _ = await _login_paar(client, user.email)
    assert await _me(client, neu) == 200


@pytest.mark.asyncio
async def test_admin_abmelden_erzwingen(client, make_mandant, make_user):
    _, _, admin_access, user, access, refresh = await _setup(client, make_mandant, make_user)
    resp = await client.post(f"/api/users/{user.id}/abmelden", headers=auth_headers(admin_access))
    assert resp.status_code == 204
    await _assert_widerrufen(client, access, refresh)
    assert await _me(client, admin_access) == 200
    # Account bleibt aktiv, Neuanmeldung moeglich
    neu, _ = await _login_paar(client, user.email)
    assert await _me(client, neu) == 200


@pytest.mark.asyncio
async def test_admin_abmelden_rechtegrenzen(client, make_mandant, make_user):
    mandant, _, admin_access, user, access, _ = await _setup(client, make_mandant, make_user)
    anderer = await make_mandant(name="Anderer Betrieb")
    fremd = await make_user(mandant=anderer, role="techniker", password=_PW)
    super_admin = await make_user(mandant=None, role="super_admin", password=_PW)

    # Techniker selbst darf nicht
    resp = await client.post(f"/api/users/{user.id}/abmelden", headers=auth_headers(access))
    assert resp.status_code == 403
    # Fremder Mandant: 404 (RLS)
    resp = await client.post(f"/api/users/{fremd.id}/abmelden", headers=auth_headers(admin_access))
    assert resp.status_code == 404
    # super_admin-Account tabu fuer mandant_admin
    resp = await client.post(f"/api/users/{super_admin.id}/abmelden", headers=auth_headers(admin_access))
    assert resp.status_code in (403, 404)
    # super_admin darf mandantenuebergreifend
    sa_access, _ = await _login_paar(client, super_admin.email)
    resp = await client.post(f"/api/users/{fremd.id}/abmelden", headers=auth_headers(sa_access))
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_refresh_bei_inaktivem_mandant_401(client, make_mandant, make_user):
    mandant, _, _, _, access, refresh = await _setup(client, make_mandant, make_user)
    async with system_session() as session:
        (await session.get(Mandant, mandant.id)).status = "pausiert"
    assert await _refresh(client, refresh) == 401


@pytest.mark.asyncio
async def test_impersonation_token_folgt_tv_des_super_admins(client, make_mandant, make_user):
    mandant = await make_mandant()
    super_admin = await make_user(mandant=None, role="super_admin", password=_PW)
    sa_access, _ = await _login_paar(client, super_admin.email)
    resp = await client.post(
        f"/api/admin/mandanten/{mandant.id}/impersonate", headers=auth_headers(sa_access)
    )
    imp = resp.json()["access_token"]
    assert await _me(client, imp) == 200

    resp = await client.post("/api/auth/ueberall-abmelden", headers=auth_headers(sa_access))
    assert resp.status_code == 204
    assert await _me(client, imp) == 401
    assert await _me(client, sa_access) == 401


@pytest.mark.asyncio
async def test_impersonation_unabhaengig_vom_widerruf_des_mandant_admins(client, make_mandant, make_user):
    """Widerruf eines Mandanten-Admins beruehrt Impersonation nicht: das
    Token haengt am Super-Admin, nicht am Ziel-Mandanten."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=_PW)
    super_admin = await make_user(mandant=None, role="super_admin", password=_PW)
    sa_access, _ = await _login_paar(client, super_admin.email)
    imp = (
        await client.post(f"/api/admin/mandanten/{mandant.id}/impersonate", headers=auth_headers(sa_access))
    ).json()["access_token"]
    admin_access, _ = await _login_paar(client, admin.email)
    await client.post("/api/auth/ueberall-abmelden", headers=auth_headers(admin_access))
    assert await _me(client, imp) == 200


# --- Kundenportal -----------------------------------------------------------

async def _kunden_zugang(mandant, kunde, password="kunden-pw-123"):
    async with system_session() as session:
        zugang = KundenportalZugang(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            email=f"portal-{kunde.id}@example.de",
            password_hash=hash_password(password),
            name="Portal",
        )
        session.add(zugang)
        await session.flush()
        await session.refresh(zugang)
        return zugang


async def _portal_login(client, pfad, email, password):
    resp = await client.post(f"{pfad}/login", json={"email": email, "password": password})
    resp.raise_for_status()
    return resp.json()["access_token"], resp.json()["refresh_token"]


@pytest.mark.asyncio
async def test_kundenportal_widerruf(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    admin = await make_user(mandant=mandant, role="mandant_admin", password=_PW)
    admin_access, _ = await _login_paar(client, admin.email)
    zugang = await _kunden_zugang(mandant, kunde)
    base = "/api/kundenportal/auth"

    access, refresh = await _portal_login(client, base, zugang.email, "kunden-pw-123")
    assert (await client.get(f"{base}/me", headers=auth_headers(access))).status_code == 200

    # Passwort durch Betrieb gesetzt -> widerrufen
    resp = await client.patch(
        f"/api/kunden/{kunde.id}/portal-zugaenge/{zugang.id}",
        json={"password": "neues-kunden-pw-1"},
        headers=auth_headers(admin_access),
    )
    assert resp.status_code == 200
    assert (await client.get(f"{base}/me", headers=auth_headers(access))).status_code == 401
    assert (await client.post(f"{base}/refresh", json={"refresh_token": refresh})).status_code == 401

    # Sperren -> widerrufen
    access, refresh = await _portal_login(client, base, zugang.email, "neues-kunden-pw-1")
    assert (await client.get(f"{base}/me", headers=auth_headers(access))).status_code == 200
    resp = await client.patch(
        f"/api/kunden/{kunde.id}/portal-zugaenge/{zugang.id}",
        json={"aktiv": False},
        headers=auth_headers(admin_access),
    )
    assert resp.status_code == 200
    assert (await client.get(f"{base}/me", headers=auth_headers(access))).status_code == 401
    assert (await client.post(f"{base}/refresh", json={"refresh_token": refresh})).status_code == 401


@pytest.mark.asyncio
async def test_kundenportal_token_ohne_tv_und_mandant_inaktiv(client, make_mandant, make_kunde):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    zugang = await _kunden_zugang(mandant, kunde)
    base = "/api/kundenportal/auth"

    access, refresh = await _portal_login(client, base, zugang.email, "kunden-pw-123")
    assert (await client.get(f"{base}/me", headers=auth_headers(_ohne_tv(access)))).status_code == 200
    assert (await client.post(f"{base}/refresh", json={"refresh_token": _ohne_tv(refresh)})).status_code == 200
    alt = create_kundenportal_access_token(
        subject=zugang.id, mandant_id=mandant.id, kunde_id=kunde.id, token_version=3
    )
    assert (await client.get(f"{base}/me", headers=auth_headers(alt))).status_code == 401

    async with system_session() as session:
        (await session.get(Mandant, mandant.id)).status = "pausiert"
    assert (await client.post(f"{base}/refresh", json={"refresh_token": refresh})).status_code == 401


@pytest.mark.asyncio
async def test_kundenportal_passwort_reset_widerruft(client, make_mandant, make_kunde):
    from app.core.security import create_kundenportal_password_reset_token

    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    zugang = await _kunden_zugang(mandant, kunde)
    base = "/api/kundenportal/auth"
    access, refresh = await _portal_login(client, base, zugang.email, "kunden-pw-123")

    resp = await client.post(
        f"{base}/passwort-zuruecksetzen",
        json={"token": create_kundenportal_password_reset_token(zugang_id=zugang.id), "new_password": "reset-passwort-12"},
    )
    assert resp.status_code == 204
    assert (await client.get(f"{base}/me", headers=auth_headers(access))).status_code == 401
    assert (await client.post(f"{base}/refresh", json={"refresh_token": refresh})).status_code == 401


# --- Partnerportal ----------------------------------------------------------

async def _partner_zugang(mandant, partner, password="partner-pw-123"):
    async with system_session() as session:
        zugang = PartnerZugang(
            mandant_id=mandant.id,
            partner_id=partner.id,
            email=f"partner-{partner.id}@example.de",
            password_hash=hash_password(password),
            name="Partner",
        )
        session.add(zugang)
        await session.flush()
        await session.refresh(zugang)
        return zugang


@pytest.mark.asyncio
async def test_partnerportal_widerruf(client, make_mandant, make_user, make_partner):
    mandant = await make_mandant()
    partner = await make_partner(mandant=mandant)
    admin = await make_user(mandant=mandant, role="mandant_admin", password=_PW)
    admin_access, _ = await _login_paar(client, admin.email)
    zugang = await _partner_zugang(mandant, partner)
    base = "/api/partnerportal/auth"

    access, refresh = await _portal_login(client, base, zugang.email, "partner-pw-123")
    assert (await client.get(f"{base}/me", headers=auth_headers(access))).status_code == 200

    resp = await client.patch(
        f"/api/partner/{partner.id}/zugaenge/{zugang.id}",
        json={"aktiv": False},
        headers=auth_headers(admin_access),
    )
    assert resp.status_code == 200
    assert (await client.get(f"{base}/me", headers=auth_headers(access))).status_code == 401
    assert (await client.post(f"{base}/refresh", json={"refresh_token": refresh})).status_code == 401


@pytest.mark.asyncio
async def test_partnerportal_ohne_tv_passwort_und_mandant(client, make_mandant, make_partner):
    from app.core.security import create_partner_password_reset_token

    mandant = await make_mandant()
    partner = await make_partner(mandant=mandant)
    zugang = await _partner_zugang(mandant, partner)
    base = "/api/partnerportal/auth"
    access, refresh = await _portal_login(client, base, zugang.email, "partner-pw-123")

    assert (await client.get(f"{base}/me", headers=auth_headers(_ohne_tv(access)))).status_code == 200
    alt_access, alt_refresh = _ohne_tv(access), _ohne_tv(refresh)
    alt = create_partner_access_token(
        subject=zugang.id, mandant_id=mandant.id, partner_id=partner.id, token_version=9
    )
    assert (await client.get(f"{base}/me", headers=auth_headers(alt))).status_code == 401

    resp = await client.post(
        f"{base}/passwort-zuruecksetzen",
        json={"token": create_partner_password_reset_token(zugang_id=zugang.id), "new_password": "reset-passwort-12"},
    )
    assert resp.status_code == 204
    assert (await client.get(f"{base}/me", headers=auth_headers(access))).status_code == 401
    assert (await client.post(f"{base}/refresh", json={"refresh_token": refresh})).status_code == 401
    # Altbestand ohne tv ist nach dem Widerruf ebenfalls ungueltig
    assert (await client.get(f"{base}/me", headers=auth_headers(alt_access))).status_code == 401
    assert (await client.post(f"{base}/refresh", json={"refresh_token": alt_refresh})).status_code == 401

    neu_access, neu_refresh = await _portal_login(client, base, zugang.email, "reset-passwort-12")
    async with system_session() as session:
        (await session.get(Mandant, mandant.id)).status = "pausiert"
    assert (await client.post(f"{base}/refresh", json={"refresh_token": neu_refresh})).status_code == 401


@pytest.mark.asyncio
async def test_portal_token_nicht_als_staff_token(client, make_mandant, make_kunde):
    """Zaehler-Raeume getrennt: ein Portal-Token mit passender ID-Kollision
    waere nie ein User-Token (Typ-Pruefung bleibt vor dem tv-Abgleich)."""
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    zugang = await _kunden_zugang(mandant, kunde)
    token = create_kundenportal_access_token(
        subject=zugang.id, mandant_id=mandant.id, kunde_id=kunde.id, token_version=0
    )
    assert await _me(client, token) == 401
