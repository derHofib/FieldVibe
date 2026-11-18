"""In-Process-Aufruf der bestehenden REST-API fuer die MCP-Tools.

Rechte (require_recht, Scopes, Kundenbeschraenkung, Module) sitzen in den Routen. Jedes
Tool ruft deshalb die Route mit einem frisch ausgestellten, 2 Minuten gueltigen
Access-Token des Nutzers auf, statt ORM/Services zu duplizieren: Token -> AuthContext ->
tenant_session (RLS) -> Fachrecht -> Modul -> Audit laufen exakt wie in der App."""
import logging
from datetime import timedelta
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError

from app.core.security import create_access_token
from app.mcp.oauth_provider import KiAccessToken

logger = logging.getLogger(__name__)

_AUFRUF_TOKEN_LEBENSDAUER = timedelta(minutes=2)
_TIMEOUT_SEKUNDEN = 30


def _aufruf_token(zugriff: KiAccessToken) -> str:
    return create_access_token(
        subject=zugriff.user_id,
        role=zugriff.role,
        mandant_id=zugriff.mandant_id,
        token_version=zugriff.tv,
        account_typ_id=zugriff.account_typ_id,
        via="mcp",
        ki_verbindung_id=zugriff.kv,
        expires_delta=_AUFRUF_TOKEN_LEBENSDAUER,
    )


def _detail(antwort: httpx.Response) -> str:
    try:
        detail = antwort.json().get("detail")
    except (ValueError, AttributeError):
        return ""
    if isinstance(detail, list):
        # Pydantic-Validierungsfehler: Feld + Meldung, ohne eingegebene Werte.
        return "; ".join(
            f"{'.'.join(str(p) for p in e.get('loc', []) if p not in ('query', 'path', 'body'))}: {e.get('msg')}"
            for e in detail
            if isinstance(e, dict)
        )
    return detail if isinstance(detail, str) else ""


def fehler_fuer(antwort: httpx.Response) -> ToolError:
    """Uebersetzt Fehlerantworten der API in verstaendliche Tool-Fehler (keine Stacktraces)."""
    detail = _detail(antwort)
    status = antwort.status_code
    if status == 401:
        return ToolError("Die Verbindung zu FieldVibe ist nicht mehr gültig. Bitte in Claude neu verbinden.")
    if status == 403:
        return ToolError(
            "Dafür fehlt dir das Recht oder die Funktion ist für deinen Betrieb nicht freigeschaltet"
            + (f" ({detail})." if detail else ".")
        )
    if status == 404:
        return ToolError(f"Nicht gefunden: {detail or 'der Eintrag existiert nicht oder ist für dich nicht sichtbar'}.")
    if status == 422:
        return ToolError(f"Ungültige Eingabe: {detail or 'die Parameter passen nicht'}.")
    if status == 429:
        return ToolError("Zu viele Anfragen. Bitte kurz warten und erneut versuchen.")
    if status < 500:
        return ToolError(f"Die Anfrage wurde abgelehnt ({detail or f'HTTP {status}'}).")
    logger.error("MCP-Tool: interne API antwortete mit %s", status)
    return ToolError("FieldVibe konnte die Anfrage gerade nicht bearbeiten. Bitte später erneut versuchen.")


async def api_get(zugriff: KiAccessToken, pfad: str, params: dict[str, Any] | None = None) -> Any:
    """GET gegen die eigene App. Leere Parameter werden weggelassen."""
    from app.main import app  # lokal: main importiert den MCP-Server

    saubere = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://intern",
        timeout=_TIMEOUT_SEKUNDEN,
    ) as client:
        antwort = await client.get(
            pfad,
            params=saubere,
            headers={"Authorization": f"Bearer {_aufruf_token(zugriff)}"},
        )
    if antwort.status_code >= 400:
        raise fehler_fuer(antwort)
    return antwort.json()
