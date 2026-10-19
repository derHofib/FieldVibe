import re
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.rate_limit import login_account_limiter
from app.core.security import (
    create_kundenportal_password_reset_token,
    create_user_password_reset_token,
)
from app.db.session import system_session
from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.email_service import EmailNichtKonfiguriert, send_email
from tests.conftest import auth_headers, login

_PW = "altes-passwort-123"
_NEU = "brandneues-passwort-456"
_SEND = "app.api.routes.auth.send_email"


async def _vergessen(client, email):
    return await client.post("/api/auth/passwort-vergessen", json={"email": email})


async def _reset_token_aus_mail(client, email) -> str:
    with patch(_SEND, new_callable=AsyncMock) as mocked_send:
        resp = await _vergessen(client, email)
    assert resp.status_code == 202
    mocked_send.assert_called_once()
    match = re.search(r"/passwort-zuruecksetzen\?token=([\w\-.]+)", mocked_send.call_args.kwargs["body"])
    assert match is not None
    return match.group(1)


async def _login_paar(client, email, password=_PW):
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    resp.raise_for_status()
    return resp.json()["access_token"], resp.json()["refresh_token"]


async def _me_status(client, access):
    return (await client.get("/api/auth/me", headers=auth_headers(access))).status_code


async def _refresh_status(client, refresh):
    return (await client.post("/api/auth/refresh", json={"refresh_token": refresh})).status_code


async def _audit(aktion):
    async with system_session() as session:
        return list((await session.execute(select(AuditLog).where(AuditLog.aktion == aktion))).scalars())


# --- passwort-vergessen ---------------------------------------------------


@pytest.mark.asyncio
async def test_vergessen_unbekannte_email_202_ohne_mail(client):
    with patch(_SEND, new_callable=AsyncMock) as mocked_send:
        resp = await _vergessen(client, "gibtsnicht@example.de")
    assert resp.status_code == 202
    mocked_send.assert_not_called()


@pytest.mark.asyncio
async def test_vergessen_inaktiver_user_202_ohne_mail(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password=_PW, aktiv=False)
    with patch(_SEND, new_callable=AsyncMock) as mocked_send:
        resp = await _vergessen(client, user.email)
    assert resp.status_code == 202
    mocked_send.assert_not_called()


@pytest.mark.asyncio
async def test_vergessen_inaktiver_mandant_202_ohne_mail(client, make_mandant, make_user):
    mandant = await make_mandant(status="pausiert")
    user = await make_user(mandant=mandant, role="mandant_admin", password=_PW)
    with patch(_SEND, new_callable=AsyncMock) as mocked_send:
        resp = await _vergessen(client, user.email)
    assert resp.status_code == 202
    mocked_send.assert_not_called()


@pytest.mark.asyncio
async def test_vergessen_bekannte_email_sendet_mail_mit_link(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password=_PW)
    with patch(_SEND, new_callable=AsyncMock) as mocked_send:
        # Gross-/Kleinschreibung und Leerraum duerfen keine Rolle spielen.
        resp = await _vergessen(client, f"  {user.email.upper()} ")
    assert resp.status_code == 202
    mocked_send.assert_called_once()
    args, kwargs = mocked_send.call_args
    assert args[1] == mandant.id
    assert kwargs["to"] == user.email
    assert f"{get_settings().frontend_base_url}/passwort-zuruecksetzen?token=" in kwargs["body"]
    assert "Minuten gültig" in kwargs["body"]


@pytest.mark.asyncio
async def test_vergessen_ohne_smtp_und_bei_zustellfehler_weiter_202(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password=_PW)
    for fehler in (EmailNichtKonfiguriert(), RuntimeError("smtp kaputt")):
        with patch(_SEND, new_callable=AsyncMock, side_effect=fehler):
            resp = await _vergessen(client, user.email)
        assert resp.status_code == 202


@pytest.mark.asyncio
async def test_vergessen_super_admin_ohne_mandant_nutzt_globalen_fallback(client, make_user, monkeypatch):
    super_admin = await make_user(mandant=None, role="super_admin", password=_PW)
    settings = get_settings()
    monkeypatch.setattr(settings, "global_smtp_host", "smtp.fieldvibe.de")
    monkeypatch.setattr(settings, "global_smtp_port", 2525)
    monkeypatch.setattr(settings, "global_smtp_user", None)
    monkeypatch.setattr(settings, "global_smtp_password", None)
    monkeypatch.setattr(settings, "global_smtp_from_address", "account@fieldvibe.de")

    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance
    with patch("app.services.email_service.smtplib.SMTP", return_value=smtp_instance):
        resp = await _vergessen(client, super_admin.email)
    assert resp.status_code == 202
    smtp_instance.send_message.assert_called_once()
    nachricht = smtp_instance.send_message.call_args[0][0]
    assert nachricht["To"] == super_admin.email
    assert nachricht["From"] == "account@fieldvibe.de"


@pytest.mark.asyncio
async def test_send_email_ohne_mandant_und_ohne_smtp_wirft_nicht_konfiguriert(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "global_smtp_host", None)
    async with system_session() as session:
        with pytest.raises(EmailNichtKonfiguriert):
            await send_email(session, None, to="x@example.de", subject="s", body="b")


@pytest.mark.asyncio
async def test_vergessen_rate_limit_pro_ip(client):
    for _ in range(5):
        assert (await _vergessen(client, "spam@example.de")).status_code == 202
    assert (await _vergessen(client, "spam@example.de")).status_code == 429


# --- passwort-zuruecksetzen -----------------------------------------------


@pytest.mark.asyncio
async def test_reset_flow_setzt_passwort_widerruft_tokens_und_ist_einmalig(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password=_PW)
    access, refresh = await _login_paar(client, user.email)
    assert await _me_status(client, access) == 200

    token = await _reset_token_aus_mail(client, user.email)
    resp = await client.post(
        "/api/auth/passwort-zuruecksetzen", json={"token": token, "new_password": _NEU}
    )
    assert resp.status_code == 204

    assert (await client.post("/api/auth/login", json={"email": user.email, "password": _PW})).status_code == 401
    assert (await client.post("/api/auth/login", json={"email": user.email, "password": _NEU})).status_code == 200

    # Bestehende Sitzungen sind entwertet.
    assert await _me_status(client, access) == 401
    assert await _refresh_status(client, refresh) == 401

    # Derselbe Link ein zweites Mal: ungueltig, Passwort bleibt das erste neue.
    zweiter = await client.post(
        "/api/auth/passwort-zuruecksetzen", json={"token": token, "new_password": "noch-ein-anderes-789"}
    )
    assert zweiter.status_code == 400
    assert (
        await client.post("/api/auth/login", json={"email": user.email, "password": "noch-ein-anderes-789"})
    ).status_code == 401

    eintraege = await _audit("passwort_zurueckgesetzt")
    assert len(eintraege) == 1
    assert eintraege[0].actor_user_id == user.id
    assert eintraege[0].payload == {}


@pytest.mark.asyncio
async def test_reset_super_admin_ohne_mandant(client, make_user):
    super_admin = await make_user(mandant=None, role="super_admin", password=_PW)
    token = create_user_password_reset_token(user_id=super_admin.id, token_version=0)
    resp = await client.post(
        "/api/auth/passwort-zuruecksetzen", json={"token": token, "new_password": _NEU}
    )
    assert resp.status_code == 204
    assert (
        await client.post("/api/auth/login", json={"email": super_admin.email, "password": _NEU})
    ).status_code == 200


@pytest.mark.asyncio
async def test_reset_link_nach_anderem_widerruf_ungueltig(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password=_PW)
    token = await _reset_token_aus_mail(client, user.email)
    access, _ = await _login_paar(client, user.email)
    assert (
        await client.post("/api/auth/ueberall-abmelden", headers=auth_headers(access))
    ).status_code == 204

    resp = await client.post(
        "/api/auth/passwort-zuruecksetzen", json={"token": token, "new_password": _NEU}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_reset_abgelaufener_token_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password=_PW)
    settings = get_settings()
    jetzt = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(user.id),
            "type": "user_password_reset",
            "tv": user.token_version,
            "iat": jetzt - timedelta(hours=2),
            "exp": jetzt - timedelta(hours=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    resp = await client.post(
        "/api/auth/passwort-zuruecksetzen", json={"token": token, "new_password": _NEU}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_reset_falsche_signatur_und_muell_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password=_PW)
    gefaelscht = jwt.encode(
        {"sub": str(user.id), "type": "user_password_reset", "tv": 0,
         "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "ein-ganz-anderes-secret-das-lang-genug-ist-123456",
        algorithm=get_settings().jwt_algorithm,
    )
    for token in (gefaelscht, "kaputter-token"):
        resp = await client.post(
            "/api/auth/passwort-zuruecksetzen", json={"token": token, "new_password": _NEU}
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_reset_falscher_token_typ_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password=_PW)
    access, refresh = await _login_paar(client, user.email)
    portal_token = create_kundenportal_password_reset_token(zugang_id=user.id)
    for token in (access, refresh, portal_token):
        resp = await client.post(
            "/api/auth/passwort-zuruecksetzen", json={"token": token, "new_password": _NEU}
        )
        assert resp.status_code == 400
    # Passwort ist unveraendert.
    assert (await client.post("/api/auth/login", json={"email": user.email, "password": _PW})).status_code == 200


@pytest.mark.asyncio
async def test_reset_token_taugt_nicht_als_bearer(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password=_PW)
    token = create_user_password_reset_token(user_id=user.id, token_version=user.token_version)
    assert await _me_status(client, token) == 401


@pytest.mark.asyncio
async def test_reset_inaktiver_user_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password=_PW)
    token = create_user_password_reset_token(user_id=user.id, token_version=user.token_version)
    async with system_session() as session:
        (await session.get(User, user.id)).aktiv = False
    resp = await client.post(
        "/api/auth/passwort-zuruecksetzen", json={"token": token, "new_password": _NEU}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_reset_passwort_zu_kurz_422(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password=_PW)
    token = create_user_password_reset_token(user_id=user.id, token_version=user.token_version)
    resp = await client.post(
        "/api/auth/passwort-zuruecksetzen", json={"token": token, "new_password": "123456789"}
    )
    assert resp.status_code == 422
    # Ein zu kurzes Passwort verbraucht den Link nicht.
    ok = await client.post(
        "/api/auth/passwort-zuruecksetzen", json={"token": token, "new_password": _NEU}
    )
    assert ok.status_code == 204


@pytest.mark.asyncio
async def test_reset_rate_limit_bei_fehlversuchen(client):
    for _ in range(5):
        resp = await client.post(
            "/api/auth/passwort-zuruecksetzen", json={"token": "kaputt", "new_password": _NEU}
        )
        assert resp.status_code == 400
    resp = await client.post(
        "/api/auth/passwort-zuruecksetzen", json={"token": "kaputt", "new_password": _NEU}
    )
    assert resp.status_code == 429


# --- passwort-aendern -----------------------------------------------------


@pytest.mark.asyncio
async def test_aendern_erfolg_widerruft_andere_sitzungen_aktuelle_laeuft_weiter(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password=_PW)
    access, refresh = await _login_paar(client, user.email)
    zweites_geraet, zweites_refresh = await _login_paar(client, user.email)

    resp = await client.post(
        "/api/auth/passwort-aendern",
        headers=auth_headers(access),
        json={"old_password": _PW, "new_password": _NEU},
    )
    assert resp.status_code == 200
    neu = resp.json()

    # Alte Tokens (auch der aufrufenden Sitzung) sind entwertet, das frische Paar gilt.
    assert await _me_status(client, access) == 401
    assert await _me_status(client, zweites_geraet) == 401
    assert await _refresh_status(client, zweites_refresh) == 401
    assert await _me_status(client, neu["access_token"]) == 200
    assert await _refresh_status(client, neu["refresh_token"]) == 200

    assert (await client.post("/api/auth/login", json={"email": user.email, "password": _PW})).status_code == 401
    assert (await client.post("/api/auth/login", json={"email": user.email, "password": _NEU})).status_code == 200

    eintraege = await _audit("passwort_geaendert")
    assert len(eintraege) == 1
    assert eintraege[0].payload == {}
    assert _NEU not in str(eintraege[0].payload)


@pytest.mark.asyncio
async def test_aendern_falsches_altes_passwort_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password=_PW)
    access, _ = await _login_paar(client, user.email)

    resp = await client.post(
        "/api/auth/passwort-aendern",
        headers=auth_headers(access),
        json={"old_password": "falsch-falsch-123", "new_password": _NEU},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Aktuelles Passwort ist falsch"
    # Sitzung bleibt gueltig, Passwort unveraendert.
    assert await _me_status(client, access) == 200
    assert (await client.post("/api/auth/login", json={"email": user.email, "password": _PW})).status_code == 200


@pytest.mark.asyncio
async def test_aendern_neues_passwort_zu_kurz_422(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password=_PW)
    access, _ = await _login_paar(client, user.email)
    resp = await client.post(
        "/api/auth/passwort-aendern",
        headers=auth_headers(access),
        json={"old_password": _PW, "new_password": "kurz"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_aendern_gleiches_passwort_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password=_PW)
    access, _ = await _login_paar(client, user.email)
    resp = await client.post(
        "/api/auth/passwort-aendern",
        headers=auth_headers(access),
        json={"old_password": _PW, "new_password": _PW},
    )
    assert resp.status_code == 400
    assert await _me_status(client, access) == 200


@pytest.mark.asyncio
async def test_aendern_ohne_login_und_mit_fremdem_token_typ_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password=_PW)
    body = {"old_password": _PW, "new_password": _NEU}
    assert (await client.post("/api/auth/passwort-aendern", json=body)).status_code == 401
    reset_token = create_user_password_reset_token(user_id=user.id, token_version=user.token_version)
    resp = await client.post("/api/auth/passwort-aendern", headers=auth_headers(reset_token), json=body)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_aendern_betrifft_nur_den_eigenen_account(client, make_mandant, make_user):
    mandant = await make_mandant()
    ich = await make_user(mandant=mandant, role="techniker", password=_PW)
    anderer = await make_user(mandant=mandant, role="techniker", password="anderes-passwort-1")
    mein_access, _ = await _login_paar(client, ich.email)
    anderer_access, _ = await _login_paar(client, anderer.email, "anderes-passwort-1")

    # Das alte Passwort des anderen Users hilft mit dem eigenen Token nicht.
    resp = await client.post(
        "/api/auth/passwort-aendern",
        headers=auth_headers(mein_access),
        json={"old_password": "anderes-passwort-1", "new_password": _NEU},
    )
    assert resp.status_code == 400

    ok = await client.post(
        "/api/auth/passwort-aendern",
        headers=auth_headers(mein_access),
        json={"old_password": _PW, "new_password": _NEU},
    )
    assert ok.status_code == 200
    # Die Sitzung des anderen Users ist unberuehrt, sein Passwort ebenfalls.
    assert await _me_status(client, anderer_access) == 200
    assert (
        await client.post("/api/auth/login", json={"email": anderer.email, "password": "anderes-passwort-1"})
    ).status_code == 200


@pytest.mark.asyncio
async def test_aendern_rate_limit_teilt_sich_den_login_account_limiter(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password=_PW)
    access, _ = await _login_paar(client, user.email)
    body = {"old_password": "falsch-falsch-123", "new_password": _NEU}

    for _ in range(5):
        resp = await client.post("/api/auth/passwort-aendern", headers=auth_headers(access), json=body)
        assert resp.status_code == 400
    resp = await client.post("/api/auth/passwort-aendern", headers=auth_headers(access), json=body)
    assert resp.status_code == 429
    # Auch das richtige Passwort kommt waehrend der Sperre nicht durch ...
    resp = await client.post(
        "/api/auth/passwort-aendern",
        headers=auth_headers(access),
        json={"old_password": _PW, "new_password": _NEU},
    )
    assert resp.status_code == 429
    # ... und die Sperre gilt derselbe Schluessel wie beim Login.
    assert user.email.lower() in login_account_limiter._failures
    login_resp = await client.post("/api/auth/login", json={"email": user.email, "password": _PW})
    assert login_resp.status_code == 429


@pytest.mark.asyncio
async def test_aendern_waehrend_impersonation_verboten(client, make_mandant, make_user):
    mandant = await make_mandant()
    super_admin = await make_user(mandant=None, role="super_admin", password=_PW)
    token = await login(client, super_admin.email, _PW)
    imp = await client.post(f"/api/admin/mandanten/{mandant.id}/impersonate", headers=auth_headers(token))
    assert imp.status_code == 200
    resp = await client.post(
        "/api/auth/passwort-aendern",
        headers=auth_headers(imp.json()["access_token"]),
        json={"old_password": _PW, "new_password": _NEU},
    )
    assert resp.status_code == 403
