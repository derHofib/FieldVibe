"""Gemeinsame Helfer fuer test_mcp_oauth.py und test_mcp_tools.py: Fixtures fuer den laufenden MCP-Server
und der komplette OAuth-Ablauf (Registrierung -> Einwilligung -> Token) ueber HTTP."""
import asyncio
import base64
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import system_session
from app.main import app
from app.mcp.server import integration
from app.mcp.server import register_limiter
from app.mcp.tools import _basis
from app.models.account_typ import AccountTyp, AccountTypRecht
from app.models.mandant import Mandant
from app.models.organigramm import Position, PositionBesetzung
from app.models.user import User
from tests.conftest import auth_headers, login

REDIRECT = "http://localhost:9999/callback"
PASSWORT = "hunter2!!"
LESEN = "fieldvibe.lesen"
SCHREIBEN = "fieldvibe.schreiben"


@pytest_asyncio.fixture
async def mcp_laeuft():
    """Frischer MCP-Server je Test: der Session-Manager des SDK laeuft nur einmal pro Instanz
    und jeder Test hat seinen eigenen Event-Loop."""
    integration.neu_aufbauen()
    _basis.aufruf_limiter._failures.clear()
    register_limiter._failures.clear()
    bereit, ende = asyncio.Event(), asyncio.Event()

    async def laufen():
        # Eigener Task: die anyio-Task-Gruppe des Session-Managers muss im selben Task betreten
        # und verlassen werden, pytest-asyncio fuehrt Setup und Teardown aber getrennt aus.
        async with integration.lebenszeit():
            bereit.set()
            await ende.wait()

    task = asyncio.create_task(laufen())
    await bereit.wait()
    yield
    ende.set()
    await task


@pytest_asyncio.fixture
async def mcp_client(mcp_laeuft):
    # Host localhost:8000 = api_public_url; "test" wuerde der DNS-Rebinding-Schutz ablehnen.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost:8000") as ac:
        yield ac


async def ki_modul_setzen(mandant: Mandant, *, aktiv: bool = True) -> None:
    async with system_session(grund="test") as session:
        m = await session.get(Mandant, mandant.id)
        m.deaktivierte_module = [x for x in m.deaktivierte_module if x != "ki_zugriff"]
        if not aktiv:
            m.deaktivierte_module = [*m.deaktivierte_module, "ki_zugriff"]


async def custom_nutzer(
    mandant: Mandant, name: str, rechte: dict[str, tuple[str, ...]], scope: str = "mandant", scopes_je_bereich=None
) -> User:
    """Nutzer mit frei definiertem Account-Typ, aktiver Position und genau diesen Rechten."""
    scopes_je_bereich = scopes_je_bereich or {}
    async with system_session(grund="test") as session:
        typ = AccountTyp(mandant_id=mandant.id, name=f"Typ {name}-{uuid.uuid4().hex[:4]}")
        session.add(typ)
        await session.flush()
        for bereich, aktionen in rechte.items():
            for aktion in aktionen:
                session.add(
                    AccountTypRecht(
                        mandant_id=mandant.id,
                        account_typ_id=typ.id,
                        bereich=bereich,
                        aktion=aktion,
                        erlaubt=True,
                        scope=scopes_je_bereich.get(bereich, scope),
                    )
                )
        position = Position(mandant_id=mandant.id, titel=name, account_typ_id=typ.id, typ="linie")
        session.add(position)
        user = User(
            mandant_id=mandant.id,
            email=f"{uuid.uuid4().hex[:10]}@example.de",
            password_hash=hash_password(PASSWORT),
            role="custom",
            account_typ_id=typ.id,
            name=name,
        )
        session.add(user)
        await session.flush()
        session.add(
            PositionBesetzung(
                mandant_id=mandant.id,
                position_id=position.id,
                user_id=user.id,
                gueltig_von=datetime.now(timezone.utc) - timedelta(days=1),
            )
        )
        await session.flush()
        await session.refresh(user)
        return user


def pkce_paar() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


async def client_registrieren(c: AsyncClient, name: str = "Claude") -> dict:
    resp = await c.post(
        "/register",
        json={
            "redirect_uris": [REDIRECT],
            "client_name": name,
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def anfrage_starten(c: AsyncClient, client_id: str, challenge: str, scope: str = LESEN, state: str = "zustand-1") -> str:
    resp = await c.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "scope": scope,
        },
    )
    assert resp.status_code == 302, resp.text
    ziel = urlsplit(resp.headers["location"])
    assert ziel.path == "/ki-verbinden"
    return parse_qs(ziel.query)["anfrage"][0]


async def einwilligen(c: AsyncClient, token: str, anfrage: str, scopes: list[str] | None = None):
    return await c.post(
        "/api/ki/autorisieren",
        json={"anfrage": anfrage, "scopes": scopes or [LESEN]},
        headers=auth_headers(token),
    )


def code_aus(redirect_url: str) -> tuple[str, str | None]:
    abfrage = parse_qs(urlsplit(redirect_url).query)
    return abfrage["code"][0], abfrage.get("state", [None])[0]


async def token_tauschen(c: AsyncClient, client_id: str, code: str, verifier: str):
    return await c.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT,
            "client_id": client_id,
            "code_verifier": verifier,
        },
    )


async def refresh_tauschen(c: AsyncClient, client_id: str, refresh_token: str):
    return await c.post(
        "/token",
        data={"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id},
    )


async def verbinden(c: AsyncClient, user: User, scopes: list[str] | None = None, client_name: str = "Claude") -> dict:
    """Kompletter Ablauf bis zum Access-Token; liefert Tokens, client_id und Login-Token."""
    scopes = scopes or [LESEN]
    login_token = await login(c, user.email, PASSWORT)
    reg = await client_registrieren(c, client_name)
    verifier, challenge = pkce_paar()
    anfrage = await anfrage_starten(c, reg["client_id"], challenge, " ".join(scopes))
    resp = await einwilligen(c, login_token, anfrage, scopes)
    assert resp.status_code == 200, resp.text
    code, state = code_aus(resp.json()["redirect_url"])
    assert state == "zustand-1"
    tok = await token_tauschen(c, reg["client_id"], code, verifier)
    assert tok.status_code == 200, tok.text
    return {**tok.json(), "client_id": reg["client_id"], "login": login_token, "code": code}


async def mcp_rpc(c: AsyncClient, access_token: str | None, methode: str, params: dict | None = None):
    kopf = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if access_token:
        kopf["Authorization"] = f"Bearer {access_token}"
    return await c.post(
        "/mcp",
        content=json.dumps({"jsonrpc": "2.0", "id": 1, "method": methode, "params": params or {}}),
        headers=kopf,
    )


async def tool_aufrufen(c: AsyncClient, access_token: str, name: str, argumente: dict | None = None) -> dict:
    """Ergebnis eines tools/call: {'fehler': bool, 'text': str, 'daten': structuredContent|None}."""
    resp = await mcp_rpc(c, access_token, "tools/call", {"name": name, "arguments": argumente or {}})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "error" not in body, body
    ergebnis = body["result"]
    text = "".join(teil.get("text", "") for teil in ergebnis.get("content", []))
    return {"fehler": bool(ergebnis.get("isError")), "text": text, "daten": ergebnis.get("structuredContent")}


async def nutzer_holen(user_id) -> User:
    async with system_session(grund="test") as session:
        return (await session.execute(select(User).where(User.id == user_id))).scalar_one()
