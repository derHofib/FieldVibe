import re
import time

import pyotp
import pytest
from sqlalchemy import select, text

from app.core.security import decrypt_secret
from app.db.session import system_session, tenant_session
from app.models.audit_log import AuditLog
from app.models.mandant import Mandant
from app.models.user import User
from app.services import mfa_service
from tests.conftest import auth_headers

_PW = "pw-123456"
_RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # ASCII "12345678901234567890" (RFC 6238, Anhang B)


# --- Hilfen -----------------------------------------------------------------
async def _login(client, email, password=_PW):
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _tokens(client, email, password=_PW):
    body = await _login(client, email, password)
    return body["access_token"], body["refresh_token"]


async def _einrichten(client, access, *, offset=0):
    """Vollstaendige Einrichtung; liefert (secret, codes, access, refresh)."""
    resp = await client.post("/api/auth/mfa/einrichten", headers=auth_headers(access))
    assert resp.status_code == 200, resp.text
    secret = resp.json()["secret"]
    code = pyotp.TOTP(secret).at(time.time() + offset)
    resp = await client.post("/api/auth/mfa/bestaetigen", headers=auth_headers(access), json={"code": code})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return secret, body["wiederherstellungscodes"], body["access_token"], body["refresh_token"]


def _code(secret, offset=0):
    return pyotp.TOTP(secret).at(time.time() + offset)


async def _user_laden(user_id):
    async with system_session() as session:
        return await session.get(User, user_id)


async def _audit_aktionen():
    async with system_session() as session:
        return [a.aktion for a in (await session.execute(select(AuditLog))).scalars()]


async def _mit_mfa(client, make_mandant, make_user, role="mandant_admin", mandant=None):
    mandant = mandant or await make_mandant()
    user = await make_user(mandant=mandant, role=role, password=_PW)
    access, _ = await _tokens(client, user.email)
    secret, codes, access, refresh = await _einrichten(client, access)
    return mandant, user, secret, codes, access, refresh


async def _pflicht_setzen(mandant_id, wert=True):
    async with system_session() as session:
        mandant = await session.get(Mandant, mandant_id)
        mandant.firmendaten = {**(mandant.firmendaten or {}), "mfa_pflicht": wert}


# --- Einheit: TOTP ----------------------------------------------------------
def test_totp_rfc6238_testvektor():
    assert pyotp.TOTP(_RFC_SECRET).at(59) == "287082"
    assert mfa_service.pruefe_totp(_RFC_SECRET, "287082", None, jetzt=59) == 1


def test_totp_zeitfenster_plus_minus_ein_schritt():
    code = "287082"  # Schritt 1 (t = 30..59)
    assert mfa_service.pruefe_totp(_RFC_SECRET, code, None, jetzt=59 + 30) == 1  # ein Schritt spaeter
    assert mfa_service.pruefe_totp(_RFC_SECRET, code, None, jetzt=30 - 30) == 1  # ein Schritt frueher
    assert mfa_service.pruefe_totp(_RFC_SECRET, code, None, jetzt=59 + 90) is None  # drei Schritte spaeter


def test_totp_replay_und_format():
    assert mfa_service.pruefe_totp(_RFC_SECRET, "287082", 1, jetzt=59) is None
    assert mfa_service.pruefe_totp(_RFC_SECRET, "287082", 0, jetzt=59) == 1
    assert mfa_service.pruefe_totp(_RFC_SECRET, "28708", None, jetzt=59) is None
    assert mfa_service.pruefe_totp(_RFC_SECRET, "abcdef", None, jetzt=59) is None
    assert mfa_service.pruefe_totp(_RFC_SECRET, "287 082", None, jetzt=59) == 1


# --- Einrichtung -------------------------------------------------------------
@pytest.mark.asyncio
async def test_einrichtung_liefert_secret_uri_und_lokalen_qr(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password=_PW)
    access, _ = await _tokens(client, user.email)

    resp = await client.post("/api/auth/mfa/einrichten", headers=auth_headers(access))

    assert resp.status_code == 200
    body = resp.json()
    assert re.fullmatch(r"[A-Z2-7]{32}", body["secret"])
    assert body["otpauth_uri"].startswith("otpauth://totp/FieldVibe:")
    assert f"secret={body['secret']}" in body["otpauth_uri"]
    assert "issuer=FieldVibe" in body["otpauth_uri"]
    assert body["qr_svg_data_uri"].startswith("data:image/svg+xml")
    # Noch nicht aktiv, Secret nur verschluesselt gespeichert.
    gespeichert = await _user_laden(user.id)
    assert gespeichert.mfa_aktiv is False
    assert gespeichert.mfa_secret_enc and body["secret"] not in gespeichert.mfa_secret_enc
    assert decrypt_secret(gespeichert.mfa_secret_enc) == body["secret"]
    status_ = (await client.get("/api/auth/mfa/status", headers=auth_headers(access))).json()
    assert status_["aktiv"] is False and status_["pflicht"] is False


@pytest.mark.asyncio
async def test_bestaetigen_mit_falschem_code_aktiviert_nicht(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password=_PW)
    access, _ = await _tokens(client, user.email)
    secret = (await client.post("/api/auth/mfa/einrichten", headers=auth_headers(access))).json()["secret"]
    falsch = f"{(int(_code(secret)) + 1) % 1000000:06d}"

    resp = await client.post("/api/auth/mfa/bestaetigen", headers=auth_headers(access), json={"code": falsch})

    assert resp.status_code == 400
    assert (await _user_laden(user.id)).mfa_aktiv is False


@pytest.mark.asyncio
async def test_bestaetigen_ohne_einrichtung_scheitert(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password=_PW)
    access, _ = await _tokens(client, user.email)
    resp = await client.post("/api/auth/mfa/bestaetigen", headers=auth_headers(access), json={"code": "123456"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_bestaetigen_liefert_zehn_codes_nur_gehasht_und_widerruft_tokens(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password=_PW)
    alt_access, alt_refresh = await _tokens(client, user.email)
    secret, codes, neu_access, neu_refresh = await _einrichten(client, alt_access)

    assert len(codes) == 10 and len(set(codes)) == 10
    assert all(re.fullmatch(r"[A-Z2-7]{4}(-[A-Z2-7]{4}){3}", c) for c in codes)
    gespeichert = await _user_laden(user.id)
    assert gespeichert.mfa_aktiv is True and gespeichert.mfa_aktiviert_am is not None
    assert len(gespeichert.mfa_wiederherstellung) == 10
    roh = str(gespeichert.mfa_wiederherstellung)
    assert not any(c in roh or c.replace("-", "") in roh for c in codes)
    # Widerruf: alte Sitzung weg, die zurueckgegebene laeuft weiter.
    assert (await client.get("/api/auth/me", headers=auth_headers(alt_access))).status_code == 401
    assert (await client.post("/api/auth/refresh", json={"refresh_token": alt_refresh})).status_code == 401
    me = (await client.get("/api/auth/me", headers=auth_headers(neu_access))).json()
    assert me["mfa_aktiv"] is True
    assert (await client.post("/api/auth/refresh", json={"refresh_token": neu_refresh})).status_code == 200


@pytest.mark.asyncio
async def test_einrichten_bei_aktiver_mfa_ist_konflikt(client, make_mandant, make_user):
    _, _, _, _, access, _ = await _mit_mfa(client, make_mandant, make_user)
    resp = await client.post("/api/auth/mfa/einrichten", headers=auth_headers(access))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_mfa_endpunkte_brauchen_login(client):
    for pfad in ("status", "einrichten", "bestaetigen", "deaktivieren", "wiederherstellungscodes"):
        methode = client.get if pfad == "status" else client.post
        resp = await methode(f"/api/auth/mfa/{pfad}")
        assert resp.status_code == 401, pfad


# --- Login in zwei Stufen ----------------------------------------------------
@pytest.mark.asyncio
async def test_login_mit_mfa_liefert_nur_zwischen_token(client, make_mandant, make_user):
    _, user, secret, _, _, _ = await _mit_mfa(client, make_mandant, make_user)

    body = await _login(client, user.email)

    assert body["mfa_erforderlich"] is True and body["mfa_token"]
    assert body["access_token"] is None and body["refresh_token"] is None


@pytest.mark.asyncio
async def test_mfa_token_ist_kein_bearer_und_kein_refresh_token(client, make_mandant, make_user):
    _, user, *_ = await _mit_mfa(client, make_mandant, make_user)
    mfa_token = (await _login(client, user.email))["mfa_token"]

    assert (await client.get("/api/auth/me", headers=auth_headers(mfa_token))).status_code == 401
    assert (await client.post("/api/auth/refresh", json={"refresh_token": mfa_token})).status_code == 401


@pytest.mark.asyncio
async def test_verifizieren_mit_gueltigem_code_gibt_token_paar(client, make_mandant, make_user):
    _, user, secret, *_ = await _mit_mfa(client, make_mandant, make_user)
    mfa_token = (await _login(client, user.email))["mfa_token"]

    # Der Code der Einrichtung ist verbraucht -- naechster Schritt.
    resp = await client.post(
        "/api/auth/mfa/verifizieren", json={"mfa_token": mfa_token, "code": _code(secret, +30)}
    )

    assert resp.status_code == 200, resp.text
    me = await client.get("/api/auth/me", headers=auth_headers(resp.json()["access_token"]))
    assert me.status_code == 200 and me.json()["email"] == user.email
    assert (await client.post("/api/auth/refresh", json={"refresh_token": resp.json()["refresh_token"]})).status_code == 200


@pytest.mark.asyncio
async def test_verifizieren_mit_falschem_code_401(client, make_mandant, make_user):
    _, user, secret, *_ = await _mit_mfa(client, make_mandant, make_user)
    mfa_token = (await _login(client, user.email))["mfa_token"]
    falsch = f"{(int(_code(secret, +30)) + 1) % 1000000:06d}"

    resp = await client.post("/api/auth/mfa/verifizieren", json={"mfa_token": mfa_token, "code": falsch})

    assert resp.status_code == 401
    assert "access_token" not in resp.json()


@pytest.mark.asyncio
async def test_verifizieren_lehnt_fremde_tokentypen_ab(client, make_mandant, make_user):
    _, user, secret, _, access, refresh = await _mit_mfa(client, make_mandant, make_user)
    for token in (access, refresh, "kein.jwt.token"):
        resp = await client.post(
            "/api/auth/mfa/verifizieren", json={"mfa_token": token, "code": _code(secret, +30)}
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mfa_token_nach_widerruf_ungueltig(client, make_mandant, make_user):
    _, user, secret, _, access, _ = await _mit_mfa(client, make_mandant, make_user)
    mfa_token = (await _login(client, user.email))["mfa_token"]
    await client.post("/api/auth/ueberall-abmelden", headers=auth_headers(access))

    resp = await client.post(
        "/api/auth/mfa/verifizieren", json={"mfa_token": mfa_token, "code": _code(secret, +30)}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_totp_replay_wird_abgelehnt(client, make_mandant, make_user):
    _, user, secret, *_ = await _mit_mfa(client, make_mandant, make_user)
    code = _code(secret, +30)

    erster = await client.post(
        "/api/auth/mfa/verifizieren", json={"mfa_token": (await _login(client, user.email))["mfa_token"], "code": code}
    )
    zweiter = await client.post(
        "/api/auth/mfa/verifizieren", json={"mfa_token": (await _login(client, user.email))["mfa_token"], "code": code}
    )
    aelterer = await client.post(
        "/api/auth/mfa/verifizieren",
        json={"mfa_token": (await _login(client, user.email))["mfa_token"], "code": _code(secret)},
    )

    assert erster.status_code == 200
    assert zweiter.status_code == 401
    # Auch ein aelterer Schritt als der zuletzt akzeptierte zaehlt nicht.
    assert aelterer.status_code == 401


@pytest.mark.asyncio
async def test_der_einrichtungscode_ist_nicht_wiederverwendbar(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password=_PW)
    access, _ = await _tokens(client, user.email)
    secret = (await client.post("/api/auth/mfa/einrichten", headers=auth_headers(access))).json()["secret"]
    code = _code(secret)
    await client.post("/api/auth/mfa/bestaetigen", headers=auth_headers(access), json={"code": code})

    resp = await client.post(
        "/api/auth/mfa/verifizieren", json={"mfa_token": (await _login(client, user.email))["mfa_token"], "code": code}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_wiederherstellungscode_nur_einmal_gueltig(client, make_mandant, make_user):
    _, user, _, codes, *_ = await _mit_mfa(client, make_mandant, make_user)

    async def versuch(code):
        token = (await _login(client, user.email))["mfa_token"]
        return await client.post("/api/auth/mfa/verifizieren", json={"mfa_token": token, "code": code})

    assert (await versuch(codes[0].lower().replace("-", " "))).status_code == 200  # Schreibweise egal
    assert (await versuch(codes[0])).status_code == 401
    assert (await versuch(codes[1])).status_code == 200
    gespeichert = await _user_laden(user.id)
    assert len(gespeichert.mfa_wiederherstellung) == 8
    assert "mfa_wiederherstellungscode_verwendet" in await _audit_aktionen()


@pytest.mark.asyncio
async def test_fehlversuche_beim_code_loesen_sperre_aus(client, make_mandant, make_user):
    _, user, secret, *_ = await _mit_mfa(client, make_mandant, make_user)
    mfa_token = (await _login(client, user.email))["mfa_token"]
    falsch = f"{(int(_code(secret, +30)) + 1) % 1000000:06d}"

    for _ in range(5):
        r = await client.post("/api/auth/mfa/verifizieren", json={"mfa_token": mfa_token, "code": falsch})
        assert r.status_code == 401
    # Selbst der richtige Code wird jetzt nicht mehr geprueft.
    gesperrt = await client.post(
        "/api/auth/mfa/verifizieren", json={"mfa_token": mfa_token, "code": _code(secret, +30)}
    )
    assert gesperrt.status_code == 429
    assert "Retry-After" in gesperrt.headers
    # Und das Passwort-Login derselben Adresse ist ebenfalls gesperrt.
    login = await client.post("/api/auth/login", json={"email": user.email, "password": _PW})
    assert login.status_code == 429


@pytest.mark.asyncio
async def test_erneutes_passwort_login_setzt_code_zaehler_nicht_zurueck(client, make_mandant, make_user):
    _, user, secret, *_ = await _mit_mfa(client, make_mandant, make_user)
    falsch = f"{(int(_code(secret, +30)) + 1) % 1000000:06d}"

    for _ in range(4):
        token = (await _login(client, user.email))["mfa_token"]
        r = await client.post("/api/auth/mfa/verifizieren", json={"mfa_token": token, "code": falsch})
        assert r.status_code == 401
    token = (await _login(client, user.email))["mfa_token"]
    assert (
        await client.post("/api/auth/mfa/verifizieren", json={"mfa_token": token, "code": falsch})
    ).status_code == 401
    # Fuenf Fehlversuche trotz dazwischenliegender erfolgreicher Passwort-Logins: gesperrt.
    assert (await client.post("/api/auth/login", json={"email": user.email, "password": _PW})).status_code == 429


@pytest.mark.asyncio
async def test_erfolgreiche_verifizierung_leert_zaehler(client, make_mandant, make_user):
    _, user, secret, *_ = await _mit_mfa(client, make_mandant, make_user)
    token = (await _login(client, user.email))["mfa_token"]
    falsch = f"{(int(_code(secret, +30)) + 1) % 1000000:06d}"
    for _ in range(3):
        await client.post("/api/auth/mfa/verifizieren", json={"mfa_token": token, "code": falsch})
    ok = await client.post("/api/auth/mfa/verifizieren", json={"mfa_token": token, "code": _code(secret, +30)})
    assert ok.status_code == 200
    for _ in range(4):
        r = await client.post("/api/auth/mfa/verifizieren", json={"mfa_token": token, "code": falsch})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_verifizieren_blockt_deaktivierten_account_und_mandanten(client, make_mandant, make_user):
    mandant, user, secret, *_ = await _mit_mfa(client, make_mandant, make_user)
    token = (await _login(client, user.email))["mfa_token"]
    async with system_session() as session:
        (await session.get(Mandant, mandant.id)).status = "pausiert"
    resp = await client.post("/api/auth/mfa/verifizieren", json={"mfa_token": token, "code": _code(secret, +30)})
    assert resp.status_code == 403


# --- Deaktivieren / Codes erneuern -------------------------------------------
@pytest.mark.asyncio
async def test_deaktivieren_braucht_passwort_und_code(client, make_mandant, make_user):
    _, user, secret, _, access, _ = await _mit_mfa(client, make_mandant, make_user)
    h = auth_headers(access)
    code = _code(secret, +30)

    falsches_pw = await client.post("/api/auth/mfa/deaktivieren", headers=h, json={"password": "falsch-123", "code": code})
    falscher_code = await client.post("/api/auth/mfa/deaktivieren", headers=h, json={"password": _PW, "code": "000000"})
    assert falsches_pw.status_code == 400 and falscher_code.status_code == 400
    assert (await _user_laden(user.id)).mfa_aktiv is True

    ok = await client.post("/api/auth/mfa/deaktivieren", headers=h, json={"password": _PW, "code": code})
    assert ok.status_code == 200
    gespeichert = await _user_laden(user.id)
    assert gespeichert.mfa_aktiv is False and gespeichert.mfa_secret_enc is None
    assert gespeichert.mfa_wiederherstellung is None
    # Alte Sitzung widerrufen, neue funktioniert; Login ist wieder einstufig.
    assert (await client.get("/api/auth/me", headers=h)).status_code == 401
    assert (await client.get("/api/auth/me", headers=auth_headers(ok.json()["access_token"]))).status_code == 200
    assert "access_token" in await _login(client, user.email)
    assert "mfa_deaktiviert" in await _audit_aktionen()


@pytest.mark.asyncio
async def test_deaktivieren_mit_wiederherstellungscode(client, make_mandant, make_user):
    _, user, _, codes, access, _ = await _mit_mfa(client, make_mandant, make_user)
    ok = await client.post(
        "/api/auth/mfa/deaktivieren", headers=auth_headers(access), json={"password": _PW, "code": codes[3]}
    )
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_deaktivieren_zaehlt_fehlversuche_im_login_limiter(client, make_mandant, make_user):
    _, user, secret, _, access, _ = await _mit_mfa(client, make_mandant, make_user)
    for _ in range(5):
        r = await client.post(
            "/api/auth/mfa/deaktivieren", headers=auth_headers(access), json={"password": _PW, "code": "000000"}
        )
        assert r.status_code == 400
    r = await client.post(
        "/api/auth/mfa/deaktivieren", headers=auth_headers(access), json={"password": _PW, "code": _code(secret, +30)}
    )
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_wiederherstellungscodes_erneuern_macht_alte_ungueltig(client, make_mandant, make_user):
    _, user, secret, alt, access, _ = await _mit_mfa(client, make_mandant, make_user)
    resp = await client.post(
        "/api/auth/mfa/wiederherstellungscodes",
        headers=auth_headers(access),
        json={"password": _PW, "code": _code(secret, +30)},
    )
    assert resp.status_code == 200
    neu = resp.json()["wiederherstellungscodes"]
    assert len(neu) == 10 and not set(neu) & set(alt)

    token = (await _login(client, user.email))["mfa_token"]
    assert (await client.post("/api/auth/mfa/verifizieren", json={"mfa_token": token, "code": alt[0]})).status_code == 401
    assert (await client.post("/api/auth/mfa/verifizieren", json={"mfa_token": token, "code": neu[0]})).status_code == 200


@pytest.mark.asyncio
async def test_passwort_reset_umgeht_mfa_nicht(client, make_mandant, make_user):
    _, user, *_ = await _mit_mfa(client, make_mandant, make_user)
    from app.core.security import create_user_password_reset_token

    token = create_user_password_reset_token(user_id=user.id, token_version=(await _user_laden(user.id)).token_version)
    resp = await client.post("/api/auth/passwort-zuruecksetzen", json={"token": token, "new_password": "ganz-neues-pw-1"})
    assert resp.status_code == 204
    assert (await _login(client, user.email, "ganz-neues-pw-1"))["mfa_erforderlich"] is True


# --- Pflicht je Mandant ------------------------------------------------------
@pytest.mark.asyncio
async def test_pflicht_laesst_nur_den_einrichtungsweg_zu(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password=_PW)
    await _pflicht_setzen(mandant.id)

    access, refresh = await _tokens(client, user.email)
    h = auth_headers(access)

    me = (await client.get("/api/auth/me", headers=h)).json()
    assert me["mfa_einrichtung_erforderlich"] is True and me["mfa_pflicht"] is True
    for pfad in ("/api/users", "/api/mandant/einstellungen", "/api/vorgaenge", "/api/kunden"):
        resp = await client.get(pfad, headers=h)
        assert resp.status_code == 403, pfad
        assert resp.json()["detail"] == "MFA-Einrichtung erforderlich"
    assert (await client.post("/api/auth/ueberall-abmelden", headers=h)).status_code == 403
    # Refresh haelt den Account im Einrichtungsmodus.
    neu = (await client.post("/api/auth/refresh", json={"refresh_token": refresh})).json()["access_token"]
    assert (await client.get("/api/users", headers=auth_headers(neu))).status_code == 403

    secret, _, voll_access, _ = await _einrichten(client, access)
    assert (await client.get("/api/users", headers=auth_headers(voll_access))).status_code == 200
    me = (await client.get("/api/auth/me", headers=auth_headers(voll_access))).json()
    assert me["mfa_einrichtung_erforderlich"] is False and me["mfa_aktiv"] is True


@pytest.mark.asyncio
async def test_pflicht_gilt_fuer_alle_mitarbeiterrollen(client, make_mandant, make_user):
    mandant = await make_mandant()
    await _pflicht_setzen(mandant.id)
    for rolle in ("mandant_admin", "techniker", "disponent"):
        user = await make_user(mandant=mandant, role=rolle, password=_PW)
        access, _ = await _tokens(client, user.email)
        me = (await client.get("/api/auth/me", headers=auth_headers(access))).json()
        assert me["mfa_einrichtung_erforderlich"] is True, rolle


@pytest.mark.asyncio
async def test_pflicht_ist_je_mandant(client, make_mandant, make_user):
    mit, ohne = await make_mandant("Mit"), await make_mandant("Ohne")
    await _pflicht_setzen(mit.id)
    user_ohne = await make_user(mandant=ohne, role="mandant_admin", password=_PW)
    access, _ = await _tokens(client, user_ohne.email)
    assert (await client.get("/api/users", headers=auth_headers(access))).status_code == 200


@pytest.mark.asyncio
async def test_pflicht_nimmt_super_admin_aus_und_mfa_ist_trotzdem_moeglich(client, make_user):
    sa = await make_user(mandant=None, role="super_admin", password=_PW)
    access, _ = await _tokens(client, sa.email)
    me = (await client.get("/api/auth/me", headers=auth_headers(access))).json()
    assert me["mfa_einrichtung_erforderlich"] is False

    secret, codes, access, _ = await _einrichten(client, access)
    login = await _login(client, sa.email)
    assert login["mfa_erforderlich"] is True
    ok = await client.post(
        "/api/auth/mfa/verifizieren", json={"mfa_token": login["mfa_token"], "code": _code(secret, +30)}
    )
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_bei_pflicht_laesst_sich_mfa_nicht_deaktivieren(client, make_mandant, make_user):
    mandant, user, secret, _, access, _ = await _mit_mfa(client, make_mandant, make_user)
    await _pflicht_setzen(mandant.id)
    resp = await client.post(
        "/api/auth/mfa/deaktivieren", headers=auth_headers(access), json={"password": _PW, "code": _code(secret, +30)}
    )
    assert resp.status_code == 403
    assert (await _user_laden(user.id)).mfa_aktiv is True


@pytest.mark.asyncio
async def test_pflicht_ueber_einstellungen_schalten_validiert_und_auditiert(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=_PW)
    access, _ = await _tokens(client, admin.email)
    h = auth_headers(access)

    schlecht = await client.patch("/api/mandant/einstellungen", headers=h, json={"firmendaten": {"mfa_pflicht": "ja"}})
    assert schlecht.status_code == 422
    ok = await client.patch("/api/mandant/einstellungen", headers=h, json={"firmendaten": {"mfa_pflicht": True}})
    assert ok.status_code == 200 and ok.json()["firmendaten"]["mfa_pflicht"] is True
    assert "mfa_pflicht_geaendert" in await _audit_aktionen()
    # Default ohne Eintrag: aus.
    anderer = await make_mandant("Anderer")
    anderer_admin = await make_user(mandant=anderer, role="mandant_admin", password=_PW)
    a2, _ = await _tokens(client, anderer_admin.email)
    assert (await client.get("/api/mandant/einstellungen", headers=auth_headers(a2))).json()["firmendaten"].get("mfa_pflicht") is None


@pytest.mark.asyncio
async def test_neu_registrierter_nutzer_landet_bei_pflicht_im_einrichtungsmodus(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=_PW)
    admin_access, _ = await _tokens(client, admin.email)
    secret, _, admin_access, _ = await _einrichten(client, admin_access)
    await _pflicht_setzen(mandant.id)
    einl = await client.post(
        "/api/users/einladungen",
        headers=auth_headers(admin_access),
        json={"email": "neu@example.de", "role": "mandant_admin"},
    )
    assert einl.status_code == 201, einl.text
    from app.core.security import create_einladung_token

    token = create_einladung_token(einladung_id=einl.json()["id"])
    reg = await client.post("/api/auth/registrieren", json={"token": token, "name": "Neu", "password": "pw-neu-12345"})
    assert reg.status_code == 201, reg.text
    me = (await client.get("/api/auth/me", headers=auth_headers(reg.json()["access_token"]))).json()
    assert me["mfa_einrichtung_erforderlich"] is True


# --- Admin-Reset, Rechte, Mandantentrennung -----------------------------------
@pytest.mark.asyncio
async def test_admin_setzt_mfa_zurueck_mit_audit_und_abmeldung(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=_PW)
    _, user, secret, _, user_access, _ = await _mit_mfa(client, make_mandant, make_user, role="techniker", mandant=mandant)
    admin_access, _ = await _tokens(client, admin.email)

    resp = await client.post(f"/api/users/{user.id}/mfa-zuruecksetzen", headers=auth_headers(admin_access))

    assert resp.status_code == 204
    gespeichert = await _user_laden(user.id)
    assert gespeichert.mfa_aktiv is False and gespeichert.mfa_secret_enc is None
    assert (await client.get("/api/auth/me", headers=auth_headers(user_access))).status_code == 401
    assert "access_token" in await _login(client, user.email)
    async with system_session() as session:
        eintrag = (
            await session.execute(select(AuditLog).where(AuditLog.aktion == "mfa_zurueckgesetzt"))
        ).scalar_one()
    assert eintrag.actor_user_id == admin.id and eintrag.entity_id == user.id and eintrag.mandant_id == mandant.id


@pytest.mark.asyncio
async def test_admin_reset_ohne_aktive_mfa_und_fuer_sich_selbst_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=_PW)
    user = await make_user(mandant=mandant, role="techniker", password=_PW)
    access, _ = await _tokens(client, admin.email)
    h = auth_headers(access)
    assert (await client.post(f"/api/users/{user.id}/mfa-zuruecksetzen", headers=h)).status_code == 400
    assert (await client.post(f"/api/users/{admin.id}/mfa-zuruecksetzen", headers=h)).status_code == 400


@pytest.mark.asyncio
async def test_reset_rechte_nur_admins(client, make_mandant, make_user):
    mandant = await make_mandant()
    _, ziel, *_ = await _mit_mfa(client, make_mandant, make_user, role="techniker", mandant=mandant)
    techniker = await make_user(mandant=mandant, role="techniker", password=_PW)
    access, _ = await _tokens(client, techniker.email)
    resp = await client.post(f"/api/users/{ziel.id}/mfa-zuruecksetzen", headers=auth_headers(access))
    assert resp.status_code == 403
    assert (await _user_laden(ziel.id)).mfa_aktiv is True


@pytest.mark.asyncio
async def test_reset_ueber_mandantengrenze_ist_404(client, make_mandant, make_user):
    mandant_a, mandant_b = await make_mandant("A"), await make_mandant("B")
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin", password=_PW)
    _, ziel_b, *_ = await _mit_mfa(client, make_mandant, make_user, role="techniker", mandant=mandant_b)
    access, _ = await _tokens(client, admin_a.email)

    resp = await client.post(f"/api/users/{ziel_b.id}/mfa-zuruecksetzen", headers=auth_headers(access))

    assert resp.status_code == 404
    assert (await _user_laden(ziel_b.id)).mfa_aktiv is True


@pytest.mark.asyncio
async def test_super_admin_darf_mandanten_nutzer_zuruecksetzen(client, make_mandant, make_user):
    sa = await make_user(mandant=None, role="super_admin", password=_PW)
    _, ziel, *_ = await _mit_mfa(client, make_mandant, make_user, role="techniker")
    access, _ = await _tokens(client, sa.email)
    resp = await client.post(f"/api/users/{ziel.id}/mfa-zuruecksetzen", headers=auth_headers(access))
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_mfa_spalten_sind_unter_fremder_rls_unsichtbar(make_mandant, make_user, client):
    mandant_a, mandant_b = await make_mandant("A"), await make_mandant("B")
    _, user_b, *_ = await _mit_mfa(client, make_mandant, make_user, role="techniker", mandant=mandant_b)
    async with tenant_session(mandant_id=mandant_a.id, is_super_admin=False) as session:
        zeilen = (await session.execute(select(User.mfa_secret_enc).where(User.id == user_b.id))).all()
        gesamt = (await session.execute(text("SELECT count(*) FROM users WHERE mfa_aktiv"))).scalar_one()
    assert zeilen == [] and gesamt == 0


@pytest.mark.asyncio
async def test_mfa_waehrend_impersonation_gesperrt(client, make_mandant, make_user):
    mandant = await make_mandant()
    sa = await make_user(mandant=None, role="super_admin", password=_PW)
    access, _ = await _tokens(client, sa.email)
    imp = await client.post(f"/api/admin/mandanten/{mandant.id}/impersonate", headers=auth_headers(access))
    token = imp.json()["access_token"]
    assert (await client.post("/api/auth/mfa/einrichten", headers=auth_headers(token))).status_code == 403


@pytest.mark.asyncio
async def test_anonymisierung_entfernt_mfa(client, make_mandant, make_user):
    from app.services.user_anonymisierung_service import anonymisiere_user

    _, user, *_ = await _mit_mfa(client, make_mandant, make_user, role="techniker")
    async with system_session() as session:
        await anonymisiere_user(session, await session.get(User, user.id))
    gespeichert = await _user_laden(user.id)
    assert gespeichert.mfa_aktiv is False and gespeichert.mfa_secret_enc is None
    assert gespeichert.mfa_wiederherstellung is None


def test_nur_einrichtungsendpunkte_akzeptieren_das_eingeschraenkte_token():
    """Wachposten gegen versehentliches Aufweichen: jede weitere Route, die an
    get_current_user_mfa_einrichtung haengt, umgeht die Pflicht-MFA."""
    import importlib
    import pkgutil

    from fastapi import APIRouter
    from fastapi.routing import APIRoute

    import app.api.routes as routen_paket
    from app.api.deps import get_current_user_mfa_einrichtung

    # Direkt an den Router-Objekten statt an app.routes: FastAPI verpackt
    # eingebundene Router dort in undurchsichtige Wrapper.
    routen = [
        r
        for info in pkgutil.iter_modules(routen_paket.__path__)
        for obj in vars(importlib.import_module(f"app.api.routes.{info.name}")).values()
        if isinstance(obj, APIRouter)
        for r in obj.routes
        if isinstance(r, APIRoute)
    ]
    assert len(routen) > 300

    def haengt_an(dependant) -> bool:
        return dependant.call is get_current_user_mfa_einrichtung or any(
            haengt_an(d) for d in dependant.dependencies
        )

    erlaubt = {
        ("GET", "/api/auth/me"),
        ("GET", "/api/auth/mfa/status"),
        ("POST", "/api/auth/mfa/einrichten"),
        ("POST", "/api/auth/mfa/bestaetigen"),
    }
    gefunden = {(m, r.path) for r in routen if haengt_an(r.dependant) for m in r.methods}
    assert gefunden == erlaubt
