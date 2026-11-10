from datetime import date

import pyotp
import pytest

from app.core.config import get_settings
from app.core.refresh_cookie import COOKIE_NAME
from tests.conftest import auth_headers

_PW = "pw-123456"
_ORIGIN = get_settings().cors_origins[0]
_COOKIE_HEADER = {"X-Refresh-Cookie": "1"}


def _set_cookie(resp) -> str:
    werte = [v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie" and v.startswith(f"{COOKIE_NAME}=")]
    assert len(werte) == 1, resp.headers
    return werte[0]


async def _user(make_mandant, make_user):
    return await make_user(mandant=await make_mandant(), role="techniker", password=_PW)


@pytest.mark.asyncio
async def test_login_setzt_httponly_strict_cookie_auf_auth_pfad(client, make_mandant, make_user):
    user = await _user(make_mandant, make_user)
    resp = await client.post("/api/auth/login", json={"email": user.email, "password": _PW}, headers=_COOKIE_HEADER)

    cookie = _set_cookie(resp).lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api/auth" in cookie
    assert "domain=" not in cookie  # host-only: gehoert dem API-Host
    assert "max-age=" in cookie
    assert "secure" not in cookie.replace("samesite", "")  # Dev/Test: kein Secure


@pytest.mark.asyncio
async def test_secure_flag_in_produktion(client, make_mandant, make_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "refresh_cookie_secure", True)
    user = await _user(make_mandant, make_user)
    resp = await client.post("/api/auth/login", json={"email": user.email, "password": _PW})
    assert "; secure" in _set_cookie(resp).lower()


def test_secure_default_folgt_der_umgebung():
    from app.core.config import Settings

    assert Settings(_env_file=None, environment="development").refresh_cookie_secure_aktiv is False
    assert Settings(_env_file=None, environment="development", FIELDVIBE_REFRESH_COOKIE_SECURE=True).refresh_cookie_secure_aktiv
    prod = dict(
        environment="production",
        jwt_secret="s" * 48,
        s3_secret_key="s" * 40,
        database_url="postgresql+asyncpg://u:3f9a8c7d6e5b4a3f@db:5432/x",
        database_url_sync="postgresql+psycopg2://u:3f9a8c7d6e5b4a3f@db:5432/x",
    )
    assert Settings(_env_file=None, **prod).refresh_cookie_secure_aktiv is True
    assert Settings(_env_file=None, FIELDVIBE_REFRESH_COOKIE_SECURE=False, **prod).refresh_cookie_secure_aktiv is False


@pytest.mark.asyncio
async def test_cookie_client_bekommt_kein_refresh_token_im_body(client, make_mandant, make_user):
    user = await _user(make_mandant, make_user)
    neu = await client.post("/api/auth/login", json={"email": user.email, "password": _PW}, headers=_COOKIE_HEADER)
    assert neu.json()["refresh_token"] is None and neu.json()["access_token"]
    alt = await client.post("/api/auth/login", json={"email": user.email, "password": _PW})
    assert alt.json()["refresh_token"]


@pytest.mark.asyncio
async def test_refresh_ohne_body_per_cookie(client, make_mandant, make_user):
    user = await _user(make_mandant, make_user)
    await client.post("/api/auth/login", json={"email": user.email, "password": _PW}, headers=_COOKIE_HEADER)

    resp = await client.post("/api/auth/refresh", headers={**_COOKIE_HEADER, "Origin": _ORIGIN})

    assert resp.status_code == 200, resp.text
    assert resp.json()["refresh_token"] is None
    assert (await client.get("/api/auth/me", headers=auth_headers(resp.json()["access_token"]))).status_code == 200
    assert COOKIE_NAME in _set_cookie(resp)  # rotiert


@pytest.mark.asyncio
async def test_refresh_per_cookie_verlangt_erlaubten_origin(client, make_mandant, make_user):
    user = await _user(make_mandant, make_user)
    await client.post("/api/auth/login", json={"email": user.email, "password": _PW}, headers=_COOKIE_HEADER)

    assert (await client.post("/api/auth/refresh")).status_code == 403
    assert (await client.post("/api/auth/refresh", headers={"Origin": "https://boese.example"})).status_code == 403
    assert (await client.post("/api/auth/refresh", headers={"Origin": "null"})).status_code == 403
    assert (await client.post("/api/auth/refresh", headers={"Origin": _ORIGIN})).status_code == 200


@pytest.mark.asyncio
async def test_refresh_ohne_cookie_und_body_401(client):
    assert (await client.post("/api/auth/refresh", headers={"Origin": _ORIGIN})).status_code == 401
    assert (await client.post("/api/auth/refresh", json={}, headers={"Origin": _ORIGIN})).status_code == 401


@pytest.mark.asyncio
async def test_altclient_body_token_in_uebergangsfrist_ohne_origin(client, make_mandant, make_user):
    user = await _user(make_mandant, make_user)
    alt = (await client.post("/api/auth/login", json={"email": user.email, "password": _PW})).json()
    client.cookies.clear()

    resp = await client.post("/api/auth/refresh", json={"refresh_token": alt["refresh_token"]})

    assert resp.status_code == 200
    assert resp.json()["refresh_token"]  # Altclient ohne Header bekommt es weiter im Body
    assert COOKIE_NAME in _set_cookie(resp)  # und nebenbei das Cookie


@pytest.mark.asyncio
async def test_nach_der_frist_zaehlt_nur_noch_das_cookie(client, make_mandant, make_user, monkeypatch):
    user = await _user(make_mandant, make_user)
    alt = (await client.post("/api/auth/login", json={"email": user.email, "password": _PW})).json()
    client.cookies.clear()
    monkeypatch.setattr(get_settings(), "refresh_body_bis", date(2020, 1, 1))

    assert (await client.post("/api/auth/refresh", json={"refresh_token": alt["refresh_token"]})).status_code == 401
    neu = await client.post("/api/auth/login", json={"email": user.email, "password": _PW})
    assert neu.json()["refresh_token"] is None  # auch ohne Header kein Token mehr im Body
    assert (await client.post("/api/auth/refresh", headers={"Origin": _ORIGIN})).status_code == 200


@pytest.mark.asyncio
async def test_ohne_frist_einstellung_ist_uebergang_beendet(client, make_mandant, make_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "refresh_body_bis", None)
    user = await _user(make_mandant, make_user)
    assert (await client.post("/api/auth/login", json={"email": user.email, "password": _PW})).json()["refresh_token"] is None


@pytest.mark.asyncio
async def test_abmelden_loescht_das_cookie(client, make_mandant, make_user):
    user = await _user(make_mandant, make_user)
    await client.post("/api/auth/login", json={"email": user.email, "password": _PW}, headers=_COOKIE_HEADER)

    resp = await client.post("/api/auth/abmelden")

    assert resp.status_code == 204
    geloescht = _set_cookie(resp).lower()
    assert "max-age=0" in geloescht and "path=/api/auth" in geloescht and "httponly" in geloescht
    assert (await client.post("/api/auth/refresh", headers={"Origin": _ORIGIN})).status_code == 401


@pytest.mark.asyncio
async def test_ueberall_abmelden_loescht_cookie_und_entwertet_es(client, make_mandant, make_user):
    user = await _user(make_mandant, make_user)
    login = await client.post("/api/auth/login", json={"email": user.email, "password": _PW}, headers=_COOKIE_HEADER)
    altes_cookie = client.cookies.get(COOKIE_NAME)

    resp = await client.post("/api/auth/ueberall-abmelden", headers=auth_headers(login.json()["access_token"]))

    assert resp.status_code == 204 and "max-age=0" in _set_cookie(resp).lower()
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, altes_cookie, path="/api/auth")
    assert (await client.post("/api/auth/refresh", headers={"Origin": _ORIGIN})).status_code == 401


@pytest.mark.asyncio
async def test_passwort_aendern_erneuert_cookie(client, make_mandant, make_user):
    user = await _user(make_mandant, make_user)
    login = await client.post("/api/auth/login", json={"email": user.email, "password": _PW}, headers=_COOKIE_HEADER)
    alt = client.cookies.get(COOKIE_NAME)

    resp = await client.post(
        "/api/auth/passwort-aendern",
        headers={**auth_headers(login.json()["access_token"]), **_COOKIE_HEADER},
        json={"old_password": _PW, "new_password": "ein-ganz-neues-pw-1"},
    )

    assert resp.status_code == 200 and resp.json()["refresh_token"] is None
    assert client.cookies.get(COOKIE_NAME) != alt
    assert (await client.post("/api/auth/refresh", headers={"Origin": _ORIGIN})).status_code == 200


@pytest.mark.asyncio
async def test_mfa_verifizieren_setzt_cookie(client, make_mandant, make_user):
    import time

    user = await _user(make_mandant, make_user)
    login = (await client.post("/api/auth/login", json={"email": user.email, "password": _PW}, headers=_COOKIE_HEADER)).json()
    h = auth_headers(login["access_token"])
    secret = (await client.post("/api/auth/mfa/einrichten", headers=h)).json()["secret"]
    await client.post("/api/auth/mfa/bestaetigen", headers={**h, **_COOKIE_HEADER}, json={"code": pyotp.TOTP(secret).now()})
    client.cookies.clear()

    mfa = (await client.post("/api/auth/login", json={"email": user.email, "password": _PW}, headers=_COOKIE_HEADER)).json()
    assert mfa["mfa_erforderlich"] and COOKIE_NAME not in client.cookies  # vor dem zweiten Faktor kein Cookie
    resp = await client.post(
        "/api/auth/mfa/verifizieren",
        json={"mfa_token": mfa["mfa_token"], "code": pyotp.TOTP(secret).at(time.time() + 30)},
        headers=_COOKIE_HEADER,
    )
    assert resp.status_code == 200 and resp.json()["refresh_token"] is None
    assert COOKIE_NAME in _set_cookie(resp)
