"""Gemeinsame Pruefungen jedes Tool-Aufrufs: Anmeldung, Scope, Rate-Limit."""
from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver.exceptions import ToolError

from app.core.rate_limit import SlidingWindowRateLimiter
from app.mcp.oauth_provider import KiAccessToken
from app.mcp.zugang import SCOPE_LESEN

# Je Verbindung (nicht je Nutzer), damit eine ausser Kontrolle geratene Sitzung andere nicht ausbremst.
aufruf_limiter = SlidingWindowRateLimiter(max_attempts=120, window_seconds=60)


def zugriff(scope: str = SCOPE_LESEN) -> KiAccessToken:
    token = get_access_token()
    if not isinstance(token, KiAccessToken):
        raise ToolError("Nicht angemeldet. Bitte die Verbindung zu FieldVibe in Claude neu herstellen.")
    if scope not in token.scopes:
        raise ToolError(f"Dafür fehlt der Zugriffsbereich „{scope}“. Bitte die Verbindung mit diesem Bereich neu erteilen.")
    try:
        aufruf_limiter.hit(str(token.kv))
    except HTTPException as exc:
        raise ToolError("Zu viele Aufrufe in kurzer Zeit. Bitte kurz warten und erneut versuchen.") from exc
    return token
