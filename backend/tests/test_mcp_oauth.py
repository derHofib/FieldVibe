"""OAuth-Ablauf und Zugriffsregeln des MCP-Servers (docs/MCP.md)."""
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select, text

from app.core.security import create_access_token, create_kundenportal_access_token
from app.db.session import system_session
from app.models.audit_log import AuditLog
from app.models.ki_verbindung import KiVerbindung
from app.models.user import User
from tests.conftest import auth_headers, login
from tests.mcp_helfer import (
    LESEN,
    PASSWORT,
    SCHREIBEN,
    anfrage_starten,
    client_registrieren,
    code_aus,
    custom_nutzer,
    einwilligen,
    ki_modul_setzen,
    mcp_client,  # noqa: F401
    mcp_laeuft,  # noqa: F401
    mcp_rpc,
    pkce_paar,
    refresh_tauschen,
    token_tauschen,
    tool_aufrufen,
    verbinden,
)

_APP = Path(__file__).resolve().parent.parent / "app"


async def _admin(make_mandant, make_user, *, ki: bool = True):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant, aktiv=ki)
    return mandant, await make_user(mandant=mandant, role="mandant_admin")


async def _verbindung(verbindung_id) -> KiVerbindung:
    async with system_session(grund="test") as session:
        return await session.get(KiVerbindung, verbindung_id)


async def _verbindungen_von(user_id) -> list[KiVerbindung]:
    async with system_session(grund="test") as session:
        return list((await session.execute(select(KiVerbindung).where(KiVerbindung.user_id == user_id))).scalars())


# --- Metadaten und Grundverhalten ---------------------------------------------------


async def test_metadaten_liegen_an_der_wurzel(mcp_client):
    meta = (await mcp_client.get("/.well-known/oauth-authorization-server")).json()
    assert meta["issuer"].rstrip("/") == "http://localhost:8000"
    assert meta["authorization_endpoint"] == "http://localhost:8000/authorize"
    assert meta["token_endpoint"] == "http://localhost:8000/token"
    assert meta["registration_endpoint"] == "http://localhost:8000/register"
    assert meta["revocation_endpoint"] == "http://localhost:8000/revoke"
    assert meta["code_challenge_methods_supported"] == ["S256"]
    assert set(meta["scopes_supported"]) == {LESEN, SCHREIBEN}

    ressource = (await mcp_client.get("/.well-known/oauth-protected-resource/mcp")).json()
    assert ressource["resource"].rstrip("/") == "http://localhost:8000/mcp"
    assert [a.rstrip("/") for a in ressource["authorization_servers"]] == ["http://localhost:8000"]


async def test_unbekannte_pfade_liefern_weiter_fastapi_json_404(mcp_client):
    resp = await mcp_client.get("/gibt-es-nicht")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not Found"}
    # Auch Pfade, die dem MCP-Namensraum ähneln, bleiben bei FastAPI.
    assert (await mcp_client.get("/mcp/unterpfad")).json() == {"detail": "Not Found"}


async def test_mcp_ohne_token_liefert_401_mit_hinweis_auf_metadaten(mcp_client):
    resp = await mcp_rpc(mcp_client, None, "tools/list")
    assert resp.status_code == 401
    assert "resource_metadata" in resp.headers["www-authenticate"]
    assert "/.well-known/oauth-protected-resource/mcp" in resp.headers["www-authenticate"]


async def test_fremder_host_wird_vom_dns_rebinding_schutz_abgelehnt(make_mandant, make_user, mcp_client):
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    _, admin = await _admin(make_mandant, make_user)
    t = await verbinden(mcp_client, admin)
    assert (await mcp_rpc(mcp_client, t["access_token"], "tools/list")).status_code == 200
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://boese.example") as c:
        resp = await mcp_rpc(c, t["access_token"], "tools/list")
    assert resp.status_code in (400, 421)


# --- Voller Ablauf ----------------------------------------------------------------------


async def test_voller_ablauf_register_authorize_token_und_mcp_aufruf(make_mandant, make_user, mcp_client):
    mandant, admin = await _admin(make_mandant, make_user)
    login_token = await login(mcp_client, admin.email, PASSWORT)
    reg = await client_registrieren(mcp_client, "Claude Desktop")
    assert reg["client_id"] and reg["scope"] == f"{LESEN} {SCHREIBEN}"

    verifier, challenge = pkce_paar()
    anfrage = await anfrage_starten(mcp_client, reg["client_id"], challenge, f"{LESEN} {SCHREIBEN}")

    info = await mcp_client.get("/api/ki/anfrage", params={"anfrage": anfrage}, headers=auth_headers(login_token))
    assert info.status_code == 200, info.text
    assert info.json() == {
        "client_name": "Claude Desktop",
        "scopes_angefragt": [LESEN, SCHREIBEN],
        "schreiben_erlaubt": True,
        "redirect_host": "localhost",
    }

    resp = await einwilligen(mcp_client, login_token, anfrage, [LESEN])
    assert resp.status_code == 200, resp.text
    code, state = code_aus(resp.json()["redirect_url"])
    assert state == "zustand-1"

    tok = await token_tauschen(mcp_client, reg["client_id"], code, verifier)
    assert tok.status_code == 200, tok.text
    daten = tok.json()
    assert daten["token_type"] == "Bearer" and daten["scope"] == LESEN
    assert daten["expires_in"] == 30 * 60 and daten["refresh_token"]

    init = await mcp_rpc(
        mcp_client,
        daten["access_token"],
        "initialize",
        {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
    )
    assert init.status_code == 200
    assert "FieldVibe" in init.json()["result"]["instructions"]

    liste = (await mcp_rpc(mcp_client, daten["access_token"], "tools/list")).json()["result"]["tools"]
    assert "vorgaenge_auflisten" in {t["name"] for t in liste}

    aufruf = await tool_aufrufen(mcp_client, daten["access_token"], "vorgaenge_auflisten")
    assert aufruf["fehler"] is False and aufruf["daten"]["eintraege"] == []

    verbindungen = await mcp_client.get("/api/ki/verbindungen", headers=auth_headers(login_token))
    [eintrag] = verbindungen.json()
    assert eintrag["client_name"] == "Claude Desktop" and eintrag["scopes"] == [LESEN]
    assert eintrag["user_id"] == str(admin.id) and eintrag["zuletzt_genutzt_am"] is not None


async def test_ablehnen_leitet_mit_access_denied_und_state_zurueck(make_mandant, make_user, mcp_client):
    _, admin = await _admin(make_mandant, make_user)
    login_token = await login(mcp_client, admin.email, PASSWORT)
    reg = await client_registrieren(mcp_client)
    _, challenge = pkce_paar()
    anfrage = await anfrage_starten(mcp_client, reg["client_id"], challenge)
    resp = await mcp_client.post("/api/ki/ablehnen", json={"anfrage": anfrage}, headers=auth_headers(login_token))
    assert resp.status_code == 200
    url = resp.json()["redirect_url"]
    assert url.startswith("http://localhost:9999/callback?") and "error=access_denied" in url and "state=zustand-1" in url
    assert await _verbindungen_von(admin.id) == []


async def test_ungueltige_oder_abgelaufene_anfrage_ist_400(make_mandant, make_user, mcp_client):
    _, admin = await _admin(make_mandant, make_user)
    login_token = await login(mcp_client, admin.email, PASSWORT)
    kopf = auth_headers(login_token)
    assert (await mcp_client.get("/api/ki/anfrage", params={"anfrage": "murks"}, headers=kopf)).status_code == 400
    # Ein Zugriffstoken ist keine Anfrage (falscher Typ).
    assert (await mcp_client.get("/api/ki/anfrage", params={"anfrage": login_token}, headers=kopf)).status_code == 400
    assert (await einwilligen(mcp_client, login_token, "murks")).status_code == 400

    import jwt

    from app.core.config import get_settings

    abgelaufen = jwt.encode(
        {"type": "mcp_anfrage", "cid": "x", "cn": "X", "ru": "http://localhost:9999/callback", "sc": [LESEN],
         "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        get_settings().jwt_secret,
        algorithm=get_settings().jwt_algorithm,
    )
    resp = await mcp_client.get("/api/ki/anfrage", params={"anfrage": abgelaufen}, headers=kopf)
    assert resp.status_code == 400 and "abgelaufen" in resp.json()["detail"]


async def test_scopes_nur_teilmenge_der_angefragten(make_mandant, make_user, mcp_client):
    _, admin = await _admin(make_mandant, make_user)
    login_token = await login(mcp_client, admin.email, PASSWORT)
    reg = await client_registrieren(mcp_client)
    _, challenge = pkce_paar()
    anfrage = await anfrage_starten(mcp_client, reg["client_id"], challenge, LESEN)
    resp = await einwilligen(mcp_client, login_token, anfrage, [LESEN, SCHREIBEN])
    assert resp.status_code == 400
    assert (await einwilligen(mcp_client, login_token, anfrage, ["unbekannt"])).status_code == 400


# --- Code, PKCE, Refresh ----------------------------------------------------------------


async def test_pkce_falscher_verifier_wird_abgelehnt(make_mandant, make_user, mcp_client):
    _, admin = await _admin(make_mandant, make_user)
    login_token = await login(mcp_client, admin.email, PASSWORT)
    reg = await client_registrieren(mcp_client)
    _, challenge = pkce_paar()
    anfrage = await anfrage_starten(mcp_client, reg["client_id"], challenge)
    code, _ = code_aus((await einwilligen(mcp_client, login_token, anfrage)).json()["redirect_url"])
    falsch = await token_tauschen(mcp_client, reg["client_id"], code, "x" * 50)
    assert falsch.status_code == 400 and falsch.json()["error"] == "invalid_grant"


async def test_code_ist_nur_einmal_einloesbar_und_zweiter_versuch_sperrt_die_verbindung(
    make_mandant, make_user, mcp_client
):
    _, admin = await _admin(make_mandant, make_user)
    login_token = await login(mcp_client, admin.email, PASSWORT)
    reg = await client_registrieren(mcp_client)
    verifier, challenge = pkce_paar()
    anfrage = await anfrage_starten(mcp_client, reg["client_id"], challenge)
    code, _ = code_aus((await einwilligen(mcp_client, login_token, anfrage)).json()["redirect_url"])

    erst = await token_tauschen(mcp_client, reg["client_id"], code, verifier)
    assert erst.status_code == 200
    zweit = await token_tauschen(mcp_client, reg["client_id"], code, verifier)
    assert zweit.status_code == 400 and zweit.json()["error"] == "invalid_grant"
    # Der abgefangene Code hat die daraus entstandene Verbindung vorsorglich beendet.
    aufruf = await mcp_rpc(mcp_client, erst.json()["access_token"], "tools/list")
    assert aufruf.status_code == 401
    [v] = await _verbindungen_von(admin.id)
    assert v.widerrufen_am is not None


async def test_code_eines_anderen_clients_wird_nicht_akzeptiert(make_mandant, make_user, mcp_client):
    _, admin = await _admin(make_mandant, make_user)
    login_token = await login(mcp_client, admin.email, PASSWORT)
    reg = await client_registrieren(mcp_client)
    fremd = await client_registrieren(mcp_client, "Fremd")
    verifier, challenge = pkce_paar()
    anfrage = await anfrage_starten(mcp_client, reg["client_id"], challenge)
    code, _ = code_aus((await einwilligen(mcp_client, login_token, anfrage)).json()["redirect_url"])
    resp = await token_tauschen(mcp_client, fremd["client_id"], code, verifier)
    assert resp.status_code == 400


async def test_refresh_rotation_und_replay_erkennung(make_mandant, make_user, mcp_client):
    _, admin = await _admin(make_mandant, make_user)
    t = await verbinden(mcp_client, admin)

    neu = await refresh_tauschen(mcp_client, t["client_id"], t["refresh_token"])
    assert neu.status_code == 200, neu.text
    daten = neu.json()
    assert daten["refresh_token"] != t["refresh_token"]
    assert (await tool_aufrufen(mcp_client, daten["access_token"], "suchen", {"text": "x"}))["fehler"] is False

    # Zweite Rotation mit dem neuen Token klappt ...
    dritt = await refresh_tauschen(mcp_client, t["client_id"], daten["refresh_token"])
    assert dritt.status_code == 200

    # ... der alte (bereits eingelöste) Refresh-Token ist ein Replay: Verbindung wird beendet.
    replay = await refresh_tauschen(mcp_client, t["client_id"], t["refresh_token"])
    assert replay.status_code == 400 and replay.json()["error"] == "invalid_grant"
    assert (await mcp_rpc(mcp_client, dritt.json()["access_token"], "tools/list")).status_code == 401
    assert (await refresh_tauschen(mcp_client, t["client_id"], dritt.json()["refresh_token"])).status_code == 400
    [v] = await _verbindungen_von(admin.id)
    assert v.widerrufen_am is not None


async def test_refresh_prueft_zugang_erneut(make_mandant, make_user, mcp_client):
    mandant, admin = await _admin(make_mandant, make_user)
    t = await verbinden(mcp_client, admin)
    await ki_modul_setzen(mandant, aktiv=False)
    resp = await refresh_tauschen(mcp_client, t["client_id"], t["refresh_token"])
    assert resp.status_code == 400 and resp.json()["error"] == "invalid_grant"


async def test_revoke_endpunkt_beendet_die_verbindung(make_mandant, make_user, mcp_client):
    _, admin = await _admin(make_mandant, make_user)
    t = await verbinden(mcp_client, admin)
    resp = await mcp_client.post("/revoke", data={"token": t["refresh_token"], "client_id": t["client_id"], "client_secret": ""})
    assert resp.status_code == 200
    assert (await mcp_rpc(mcp_client, t["access_token"], "tools/list")).status_code == 401


# --- Wer darf ---------------------------------------------------------------------------


async def test_modul_aus_lehnt_einwilligung_ab(make_mandant, make_user, mcp_client):
    _, admin = await _admin(make_mandant, make_user, ki=False)
    login_token = await login(mcp_client, admin.email, PASSWORT)
    reg = await client_registrieren(mcp_client)
    _, challenge = pkce_paar()
    anfrage = await anfrage_starten(mcp_client, reg["client_id"], challenge)
    kopf = auth_headers(login_token)
    resp = await mcp_client.get("/api/ki/anfrage", params={"anfrage": anfrage}, headers=kopf)
    assert resp.status_code == 403 and "nicht freigeschaltet" in resp.json()["detail"]
    assert (await einwilligen(mcp_client, login_token, anfrage)).status_code == 403


async def test_modul_nachtraeglich_aus_wirkt_sofort_auf_den_mcp_zugriff(make_mandant, make_user, mcp_client):
    mandant, admin = await _admin(make_mandant, make_user)
    t = await verbinden(mcp_client, admin)
    assert (await mcp_rpc(mcp_client, t["access_token"], "tools/list")).status_code == 200
    await ki_modul_setzen(mandant, aktiv=False)
    assert (await mcp_rpc(mcp_client, t["access_token"], "tools/list")).status_code == 401


async def test_recht_ki_zugriff_sehen_ist_noetig(make_mandant, mcp_client):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    ohne = await custom_nutzer(mandant, "Ohne KI", {"vorgaenge": ("sehen",)})
    login_token = await login(mcp_client, ohne.email, PASSWORT)
    reg = await client_registrieren(mcp_client)
    _, challenge = pkce_paar()
    anfrage = await anfrage_starten(mcp_client, reg["client_id"], challenge)
    resp = await mcp_client.get("/api/ki/anfrage", params={"anfrage": anfrage}, headers=auth_headers(login_token))
    assert resp.status_code == 403 and "KI-Assistent" in resp.json()["detail"]


async def test_recht_entzogen_beendet_laufende_verbindung(make_mandant, mcp_client):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    nutzer = await custom_nutzer(mandant, "Mit KI", {"ki_zugriff": ("sehen",)})
    t = await verbinden(mcp_client, nutzer)
    assert (await mcp_rpc(mcp_client, t["access_token"], "tools/list")).status_code == 200
    async with system_session(grund="test") as session:
        await session.execute(text("DELETE FROM account_typ_rechte WHERE bereich = 'ki_zugriff'"))
    assert (await mcp_rpc(mcp_client, t["access_token"], "tools/list")).status_code == 401


async def test_schreiben_scope_ohne_recht_nicht_erteilbar(make_mandant, mcp_client):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    nur_lesen = await custom_nutzer(mandant, "Nur lesen", {"ki_zugriff": ("sehen",)})
    login_token = await login(mcp_client, nur_lesen.email, PASSWORT)
    reg = await client_registrieren(mcp_client)
    _, challenge = pkce_paar()
    anfrage = await anfrage_starten(mcp_client, reg["client_id"], challenge, f"{LESEN} {SCHREIBEN}")
    kopf = auth_headers(login_token)
    info = await mcp_client.get("/api/ki/anfrage", params={"anfrage": anfrage}, headers=kopf)
    assert info.json()["schreiben_erlaubt"] is False
    resp = await einwilligen(mcp_client, login_token, anfrage, [LESEN, SCHREIBEN])
    assert resp.status_code == 403 and "bearbeiten" in resp.json()["detail"]
    assert await _verbindungen_von(nur_lesen.id) == []
    # Nur Lesen geht.
    assert (await einwilligen(mcp_client, login_token, anfrage, [LESEN])).status_code == 200


async def test_schreiben_scope_mit_recht_wird_erteilt_und_lesen_ist_immer_dabei(make_mandant, mcp_client):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    nutzer = await custom_nutzer(mandant, "Schreiber", {"ki_zugriff": ("sehen", "bearbeiten")})
    t = await verbinden(mcp_client, nutzer, [LESEN, SCHREIBEN])
    assert set(t["scope"].split()) == {LESEN, SCHREIBEN}
    # Entfällt das Schreibrecht, fällt der Scope aus dem Token heraus (Lesen bleibt).
    async with system_session(grund="test") as session:
        await session.execute(text("DELETE FROM account_typ_rechte WHERE bereich = 'ki_zugriff' AND aktion = 'bearbeiten'"))
    erneuert = await refresh_tauschen(mcp_client, t["client_id"], t["refresh_token"])
    assert erneuert.json()["scope"] == LESEN


async def test_super_admin_wird_abgelehnt(make_user, mcp_client):
    super_admin = await make_user(mandant=None, role="super_admin")
    login_token = await login(mcp_client, super_admin.email, PASSWORT)
    kopf = auth_headers(login_token)
    for resp in (
        await mcp_client.get("/api/ki/anfrage", params={"anfrage": "x"}, headers=kopf),
        await mcp_client.get("/api/ki/verbindungen", headers=kopf),
        await einwilligen(mcp_client, login_token, "x"),
    ):
        assert resp.status_code == 403


async def test_impersonation_wird_abgelehnt(make_mandant, make_user, mcp_client):
    mandant, _ = await _admin(make_mandant, make_user)
    super_admin = await make_user(mandant=None, role="super_admin")
    admin_token = await login(mcp_client, super_admin.email, PASSWORT)
    imp = await mcp_client.post(f"/api/admin/mandanten/{mandant.id}/impersonate", headers=auth_headers(admin_token))
    token = imp.json()["access_token"]
    reg = await client_registrieren(mcp_client)
    _, challenge = pkce_paar()
    anfrage = await anfrage_starten(mcp_client, reg["client_id"], challenge)
    resp = await mcp_client.get("/api/ki/anfrage", params={"anfrage": anfrage}, headers=auth_headers(token))
    assert resp.status_code == 403
    assert (await einwilligen(mcp_client, token, anfrage)).status_code == 403


async def test_kundenportal_konto_wird_abgelehnt(make_mandant, make_kunde, mcp_client):
    import uuid

    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    kunde = await make_kunde(mandant=mandant)
    portal = create_kundenportal_access_token(
        subject=uuid.uuid4(), mandant_id=mandant.id, kunde_id=kunde.id, token_version=0
    )
    reg = await client_registrieren(mcp_client)
    _, challenge = pkce_paar()
    anfrage = await anfrage_starten(mcp_client, reg["client_id"], challenge)
    resp = await mcp_client.get("/api/ki/anfrage", params={"anfrage": anfrage}, headers=auth_headers(portal))
    assert resp.status_code == 401


async def test_loesch_rolle_wird_abgelehnt(make_mandant, make_user, mcp_client):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    papierkorb = await make_user(mandant=mandant, role="loesch_ansicht")
    login_token = await login(mcp_client, papierkorb.email, PASSWORT)
    reg = await client_registrieren(mcp_client)
    _, challenge = pkce_paar()
    anfrage = await anfrage_starten(mcp_client, reg["client_id"], challenge)
    resp = await mcp_client.get("/api/ki/anfrage", params={"anfrage": anfrage}, headers=auth_headers(login_token))
    assert resp.status_code == 403


# --- Widerruf ---------------------------------------------------------------------------


async def test_ueberall_abmelden_entwertet_mcp_token_sofort(make_mandant, make_user, mcp_client):
    _, admin = await _admin(make_mandant, make_user)
    t = await verbinden(mcp_client, admin)
    assert (await mcp_rpc(mcp_client, t["access_token"], "tools/list")).status_code == 200
    resp = await mcp_client.post("/api/auth/ueberall-abmelden", headers=auth_headers(t["login"]))
    assert resp.status_code == 204
    assert (await mcp_rpc(mcp_client, t["access_token"], "tools/list")).status_code == 401
    refresh = await refresh_tauschen(mcp_client, t["client_id"], t["refresh_token"])
    assert refresh.status_code == 400


async def test_code_wird_durch_token_version_ungueltig(make_mandant, make_user, mcp_client):
    _, admin = await _admin(make_mandant, make_user)
    login_token = await login(mcp_client, admin.email, PASSWORT)
    reg = await client_registrieren(mcp_client)
    verifier, challenge = pkce_paar()
    anfrage = await anfrage_starten(mcp_client, reg["client_id"], challenge)
    code, _ = code_aus((await einwilligen(mcp_client, login_token, anfrage)).json()["redirect_url"])
    await mcp_client.post("/api/auth/ueberall-abmelden", headers=auth_headers(login_token))
    resp = await token_tauschen(mcp_client, reg["client_id"], code, verifier)
    assert resp.status_code == 400


async def test_widerruf_ueber_api_wirkt_sofort(make_mandant, make_user, mcp_client):
    _, admin = await _admin(make_mandant, make_user)
    t = await verbinden(mcp_client, admin)
    kopf = auth_headers(t["login"])
    [eintrag] = (await mcp_client.get("/api/ki/verbindungen", headers=kopf)).json()
    assert (await mcp_client.delete(f"/api/ki/verbindungen/{eintrag['id']}", headers=kopf)).status_code == 204
    assert (await mcp_rpc(mcp_client, t["access_token"], "tools/list")).status_code == 401
    assert (await refresh_tauschen(mcp_client, t["client_id"], t["refresh_token"])).status_code == 400
    assert (await mcp_client.get("/api/ki/verbindungen", headers=kopf)).json() == []
    # Wiederholtes Widerrufen ist harmlos.
    assert (await mcp_client.delete(f"/api/ki/verbindungen/{eintrag['id']}", headers=kopf)).status_code == 204


async def test_verbindungen_sichtbarkeit_und_widerruf_fremder(make_mandant, mcp_client):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    from app.db.session import system_session as _s  # noqa: F401

    a = await custom_nutzer(mandant, "Alice", {"ki_zugriff": ("sehen",)})
    b = await custom_nutzer(mandant, "Bob", {"ki_zugriff": ("sehen",)})
    ta = await verbinden(mcp_client, a)
    tb = await verbinden(mcp_client, b)

    liste_a = (await mcp_client.get("/api/ki/verbindungen", headers=auth_headers(ta["login"]))).json()
    assert [e["user_name"] for e in liste_a] == ["Alice"]
    # alle=true nur für Mandant-Admins.
    assert (await mcp_client.get("/api/ki/verbindungen?alle=true", headers=auth_headers(ta["login"]))).status_code == 403
    [eintrag_b] = (await mcp_client.get("/api/ki/verbindungen", headers=auth_headers(tb["login"]))).json()
    assert (await mcp_client.delete(f"/api/ki/verbindungen/{eintrag_b['id']}", headers=auth_headers(ta["login"]))).status_code == 404

    admin = await custom_nutzer(mandant, "Chef", {"ki_zugriff": ("sehen",)})
    async with system_session(grund="test") as session:
        u = await session.get(User, admin.id)
        u.role = "mandant_admin"
    admin_login = await login(mcp_client, admin.email, PASSWORT)
    alle = (await mcp_client.get("/api/ki/verbindungen?alle=true", headers=auth_headers(admin_login))).json()
    assert {e["user_name"] for e in alle} == {"Alice", "Bob"}
    assert (await mcp_client.delete(f"/api/ki/verbindungen/{eintrag_b['id']}", headers=auth_headers(admin_login))).status_code == 204
    assert (await mcp_rpc(mcp_client, tb["access_token"], "tools/list")).status_code == 401
    assert (await mcp_rpc(mcp_client, ta["access_token"], "tools/list")).status_code == 200


async def test_verbindung_anderer_mandant_nicht_sichtbar_und_nicht_widerrufbar(make_mandant, make_user, mcp_client):
    _, admin_a = await _admin(make_mandant, make_user)
    _, admin_b = await _admin(make_mandant, make_user)
    ta = await verbinden(mcp_client, admin_a)
    login_b = await login(mcp_client, admin_b.email, PASSWORT)
    [eintrag] = (await mcp_client.get("/api/ki/verbindungen", headers=auth_headers(ta["login"]))).json()
    assert (await mcp_client.get("/api/ki/verbindungen?alle=true", headers=auth_headers(login_b))).json() == []
    assert (await mcp_client.delete(f"/api/ki/verbindungen/{eintrag['id']}", headers=auth_headers(login_b))).status_code == 404
    assert (await mcp_rpc(mcp_client, ta["access_token"], "tools/list")).status_code == 200


# --- Token-Trennung ---------------------------------------------------------------------


async def test_mcp_token_wird_an_normalen_api_routen_abgelehnt(make_mandant, make_user, mcp_client):
    _, admin = await _admin(make_mandant, make_user)
    t = await verbinden(mcp_client, admin)
    for pfad in ("/api/vorgaenge", "/api/kunden", "/api/auth/me", "/api/ki/verbindungen"):
        resp = await mcp_client.get(pfad, headers=auth_headers(t["access_token"]))
        assert resp.status_code == 401, pfad
    # Auch Refresh-Token und Code taugen nicht als Bearer-Token.
    assert (await mcp_client.get("/api/vorgaenge", headers=auth_headers(t["refresh_token"]))).status_code == 401
    assert (await mcp_client.get("/api/vorgaenge", headers=auth_headers(t["code"]))).status_code == 401


async def test_normales_zugriffstoken_taugt_nicht_am_mcp_endpunkt(make_mandant, make_user, mcp_client):
    _, admin = await _admin(make_mandant, make_user)
    login_token = await login(mcp_client, admin.email, PASSWORT)
    assert (await mcp_rpc(mcp_client, login_token, "tools/list")).status_code == 401


async def test_audit_eintraege_per_ki_tragen_quelle_ki(make_mandant, make_user, mcp_client):
    mandant, admin = await _admin(make_mandant, make_user)
    t = await verbinden(mcp_client, admin)
    [v] = await _verbindungen_von(admin.id)
    ki_token = create_access_token(
        subject=admin.id,
        role=admin.role,
        mandant_id=mandant.id,
        token_version=0,
        via="mcp",
        ki_verbindung_id=v.id,
        expires_delta=timedelta(minutes=2),
    )
    # Ein schreibender Endpunkt mit Audit-Eintrag, aufgerufen wie es der MCP-Adapter tut.
    assert (await mcp_client.post("/api/auth/ueberall-abmelden", headers=auth_headers(ki_token))).status_code == 204
    async with system_session(grund="test") as session:
        eintrag = (
            await session.execute(select(AuditLog).where(AuditLog.aktion == "logout_alle_geraete"))
        ).scalar_one()
    assert eintrag.payload["quelle"] == "ki" and eintrag.payload["ki_verbindung_id"] == str(v.id)
    assert eintrag.akteur_typ == "user"

    # Gegenprobe: derselbe Aufruf mit normalem Token (und ohne Reste im ContextVar) hat keine KI-Quelle.
    neu = await login(mcp_client, admin.email, PASSWORT)
    await mcp_client.post("/api/auth/ueberall-abmelden", headers=auth_headers(neu))
    async with system_session(grund="test") as session:
        letzter = (
            await session.execute(select(AuditLog).where(AuditLog.aktion == "logout_alle_geraete").order_by(AuditLog.id.desc()))
        ).scalars().first()
    assert "quelle" not in letzter.payload
    assert t  # Verbindung wurde ordentlich aufgebaut


async def test_audit_der_einwilligung_und_des_widerrufs(make_mandant, make_user, mcp_client):
    _, admin = await _admin(make_mandant, make_user)
    t = await verbinden(mcp_client, admin)
    [eintrag] = (await mcp_client.get("/api/ki/verbindungen", headers=auth_headers(t["login"]))).json()
    await mcp_client.delete(f"/api/ki/verbindungen/{eintrag['id']}", headers=auth_headers(t["login"]))
    async with system_session(grund="test") as session:
        aktionen = [
            a for (a,) in (await session.execute(select(AuditLog.aktion).where(AuditLog.aktion.like("ki_verbindung%")).order_by(AuditLog.id)))
        ]
    assert aktionen == ["ki_verbindung_erteilt", "ki_verbindung_widerrufen"]


async def test_rate_limit_je_verbindung(make_mandant, make_user, mcp_client, monkeypatch):
    from app.mcp.tools import _basis

    monkeypatch.setattr(_basis.aufruf_limiter, "_max_attempts", 3)
    _, admin = await _admin(make_mandant, make_user)
    t = await verbinden(mcp_client, admin)
    ergebnisse = [await tool_aufrufen(mcp_client, t["access_token"], "suchen", {"text": "x"}) for _ in range(4)]
    assert [e["fehler"] for e in ergebnisse] == [False, False, False, True]
    assert "Zu viele Aufrufe" in ergebnisse[3]["text"]


# --- Architektur ------------------------------------------------------------------------


def test_app_mcp_importiert_kein_system_session():
    verstoesse = []
    for pfad in (_APP / "mcp").rglob("*.py"):
        baum = ast.parse(pfad.read_text(encoding="utf-8"))
        for knoten in ast.walk(baum):
            if (
                (isinstance(knoten, ast.ImportFrom) and any(a.name == "system_session" for a in knoten.names))
                or (isinstance(knoten, ast.Name) and knoten.id == "system_session")
                or (isinstance(knoten, ast.Attribute) and knoten.attr == "system_session")
            ):
                verstoesse.append(str(pfad.relative_to(_APP)))
    assert not verstoesse, f"system_session in app/mcp: {verstoesse}"


def test_ki_routen_benutzen_kein_system_session():
    quelle = (_APP / "api" / "routes" / "ki.py").read_text(encoding="utf-8")
    assert "system_session" not in quelle
