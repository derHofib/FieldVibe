"""MCP-Server (Streamable HTTP, stateless) mit OAuth-Authorization-Server im Backend-Prozess.

Das SDK liefert eine fertige Starlette-App mit /mcp, /authorize, /token, /register, /revoke und den
/.well-known-Metadaten. Sie wird nicht per Mount unter "/" eingehaengt (das wuerde FastAPIs
JSON-404 fuer alle unbekannten Pfade durch Starlettes Text-404 ersetzen), sondern ueber eine
schmale ASGI-Weiche nur fuer genau diese Pfade angesprochen (McpWeiche, main.py)."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings
from app.core.rate_limit import SlidingWindowRateLimiter
from app.mcp.oauth_provider import FieldVibeOAuthProvider, KiAccessToken, resource_url
from app.mcp import prompts
from app.mcp.tools import auswertung, lesen, protokolle, schreiben
from app.mcp.zugang import ALLE_SCOPES, SCOPE_LESEN, SCOPE_SCHREIBEN

logger = logging.getLogger(__name__)

# /register ist offen (Dynamic Client Registration vor jedem Login): je IP begrenzen, damit niemand
# die Tabelle ki_clients vollschreibt.
register_limiter = SlidingWindowRateLimiter(max_attempts=30, window_seconds=60 * 60)

# Muss mit docs/BEGRIFFE.md uebereinstimmen (Test). Eine Kopie, weil das Backend-Image
# nur backend/ enthaelt (docker-compose: build.context ./backend), docs/ also fehlt.
_BEGRIFFE = Path(__file__).with_name("begriffe.md")

ANLEITUNG = """\
FieldVibe ist ein CRM für Handwerksbetriebe (Aufträge, Kunden, Anlagen, Termine, Rechnungen).
Du arbeitest hier im Namen eines Mitarbeiters; alle Daten kommen mit genau dessen Rechten, was er in
der App nicht sehen darf, fehlt oder liefert eine Fehlermeldung. Antworte auf Deutsch.

Begriffe, wie sie in der App verwendet werden:
- Vorgang: das Ticket/der Einsatz (Titel, Status, Chat/Verlauf, Zeit). Das ist, was Mitarbeiter im Alltag "Auftrag" nennen.
- Auftrag: eine eigene, übergeordnete Entität, die mehrere Vorgänge bündeln kann.
- Projekt: Kanban/Zeitplan mit Aufgaben, kann Aufträge und Vorgänge enthalten.
- Anlage: Betriebsmittel beim Kunden (z. B. Heizung); Standort: Betriebsstätte eines Kunden.
- Prüfzyklus/Prüfmittel: Wartungsintervalle von Anlagen bzw. Messgeräte mit Kalibrierfrist.
- Mangel: Defekt, der zu Angebot und Rechnung führt.
Das Glossar steht vollständig in der Ressource fieldvibe://begriffe.

Einstieg: mit "suchen" nach Kunde, Titel oder Nummer suchen, dann mit den *_lesen-Tools Details holen.
Listen sind auf 100 Einträge je Aufruf begrenzt (Parameter seite); bei großen Mengen Filter nutzen.
Lesend ist alles erlaubt, was der Nutzer in der App sehen darf. Mit Schreibzugriff (nur wenn der Nutzer ihn
erteilt hat) legst du Neues an: Kommentare, Mängel, Vorgänge (Status neu), Protokoll-Entwürfe und Entwürfe
für Protokoll-Vorlagen. Du löschst, schließt, unterschreibst, veröffentlichst oder versendest nichts; das
bleibt beim Menschen in der App. Sage dem Nutzer nach dem Anlegen immer, was er in der App noch tun muss.
"""


def _transport_security() -> TransportSecuritySettings:
    """DNS-Rebinding-Schutz: nur der Host der oeffentlichen API-URL (plus lokale Hosts in Dev/Test)."""
    einstellungen = get_settings()
    host = urlsplit(einstellungen.api_public_url).netloc
    erlaubte_hosts = [host]
    herkuenfte = {einstellungen.frontend_base_url.rstrip("/"), *(o.rstrip("/") for o in einstellungen.cors_origins)}
    if einstellungen.ist_dev_umgebung:
        erlaubte_hosts += ["localhost:*", "127.0.0.1:*", "localhost", "testserver", "intern"]
        herkuenfte |= {"http://localhost:*", "http://127.0.0.1:*"}
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=erlaubte_hosts,
        allowed_origins=sorted(herkuenfte),
    )


SCHREIB_TOOLS = schreiben.SCHREIB_TOOLS | protokolle.SCHREIB_TOOLS


def _schreib_tools_nach_scope_listen(server: MCPServer) -> None:
    """Ohne Schreib-Scope (nicht erteilt oder Recht ki_zugriff.bearbeiten entzogen, siehe load_access_token)
    sind Schreib-Tools gar nicht gelistet. Das ist nur Komfort: aufgerufen werden sie trotzdem nur mit Scope
    (tools/_basis.zugriff)."""
    original = server.list_tools

    async def list_tools():
        tools = await original()
        token = get_access_token()
        if isinstance(token, KiAccessToken) and SCOPE_SCHREIBEN in token.scopes:
            return tools
        return [t for t in tools if t.name not in SCHREIB_TOOLS]

    server.list_tools = list_tools  # type: ignore[method-assign]


def baue_mcp_server() -> tuple[MCPServer, ASGIApp] | None:
    """None, wenn api_public_url fuer OAuth nicht taugt (Issuer muss HTTPS sein, nur localhost darf HTTP);
    der Rest der API laeuft dann unveraendert, nur der KI-Zugriff fehlt."""
    einstellungen = get_settings()
    issuer = einstellungen.api_public_url.rstrip("/")
    try:
        auth = AuthSettings(
            issuer_url=issuer,
            resource_server_url=resource_url(),
            required_scopes=[SCOPE_LESEN],
            client_registration_options=ClientRegistrationOptions(
                enabled=True, valid_scopes=list(ALLE_SCOPES), default_scopes=[SCOPE_LESEN]
            ),
            revocation_options=RevocationOptions(enabled=True),
            # Das Token wird immer fuer genau diese Resource ausgestellt (oauth_provider).
            validate_token_resource=True,
        )
        server = MCPServer(
            "FieldVibe",
            title="FieldVibe",
            instructions=ANLEITUNG,
            auth_server_provider=FieldVibeOAuthProvider(),
            auth=auth,
        )
        lesen.registrieren(server)
        auswertung.registrieren(server)
        protokolle.registrieren(server)
        schreiben.registrieren(server)
        prompts.registrieren(server)
        _schreib_tools_nach_scope_listen(server)

        @server.resource(
            "fieldvibe://begriffe",
            name="begriffe",
            title="FieldVibe-Begriffe",
            description="Glossar: Vorgang, Auftrag, Anlage, Standort, Mandant, Mangel u. a. wie in der App.",
            mime_type="text/markdown",
        )
        def begriffe() -> str:
            return _BEGRIFFE.read_text(encoding="utf-8")

        app = server.streamable_http_app(
            streamable_http_path="/mcp",
            json_response=True,
            stateless_http=True,
            transport_security=_transport_security(),
            host=urlsplit(einstellungen.api_public_url).hostname or "127.0.0.1",
        )
    except ValueError as exc:
        logger.warning("MCP-Server deaktiviert (FIELDVIBE_API_PUBLIC_URL=%s): %s", issuer, exc)
        return None
    return server, app


class McpIntegration:
    """Haelt Server und ASGI-App; neu_aufbauen() gibt es fuer Tests, weil der Session-Manager des SDK
    nur einmal pro Instanz laufen darf und jeder Test einen eigenen Event-Loop hat."""

    # Pfade der SDK-App (create_auth_routes, create_protected_resource_routes, Streamable-HTTP-Route).
    PFADE = frozenset(
        {
            "/mcp",
            "/mcp/",
            "/authorize",
            "/token",
            "/register",
            "/revoke",
            "/.well-known/oauth-authorization-server",
            "/.well-known/oauth-protected-resource/mcp",
        }
    )

    def __init__(self) -> None:
        self.server: MCPServer | None = None
        self.app: ASGIApp | None = None
        self.neu_aufbauen()

    def neu_aufbauen(self) -> None:
        gebaut = baue_mcp_server()
        self.server, self.app = gebaut if gebaut else (None, None)

    @asynccontextmanager
    async def lebenszeit(self):
        """Laeuft im FastAPI-Lifespan: der Session-Manager braucht seine Task-Gruppe."""
        if self.server is None:
            yield
            return
        async with self.server.session_manager.run():
            yield


integration = McpIntegration()


class McpWeiche:
    """ASGI-Middleware: reicht genau die MCP-/OAuth-Pfade an die SDK-App weiter, alles andere an FastAPI."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and integration.app is not None and scope["path"] in McpIntegration.PFADE:
            if scope["path"] == "/register" and scope["method"] == "POST":
                client = scope.get("client")
                try:
                    register_limiter.hit(client[0] if client else "unknown")
                except HTTPException as exc:
                    antwort = JSONResponse(
                        {"error": "temporarily_unavailable", "error_description": exc.detail},
                        status_code=exc.status_code,
                        headers=exc.headers,
                    )
                    await antwort(scope, receive, send)
                    return
            await integration.app(scope, receive, send)
            return
        await self.app(scope, receive, send)
