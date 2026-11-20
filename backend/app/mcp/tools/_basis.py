"""Gemeinsame Pruefungen jedes Tool-Aufrufs: Anmeldung, Scope, Rate-Limit."""
from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from app.core.rate_limit import SlidingWindowRateLimiter
from app.mcp.oauth_provider import KiAccessToken
from app.mcp.zugang import SCOPE_LESEN, SCOPE_SCHREIBEN

NUR_LESEN = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

# Schreib-Tools legen nur Neues an (nie loeschen/ueberschreiben/abschliessen) und wiederholen sich nicht
# folgenlos: ein zweiter Aufruf erzeugt einen zweiten Eintrag.
NUR_ADDITIV = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

# Aendern/Speichern/Verknuepfen/Rueckgaengig: veraendert Bestehendes, aber nie destruktiv (Rueckweg im KI-Journal) und
# wiederholbar (zweiter Aufruf mit denselben Werten aendert nichts mehr).
AENDERND = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)

# Je Verbindung (nicht je Nutzer), damit eine ausser Kontrolle geratene Sitzung andere nicht ausbremst.
aufruf_limiter = SlidingWindowRateLimiter(max_attempts=120, window_seconds=60)


def zugriff(scope: str = SCOPE_LESEN) -> KiAccessToken:
    token = get_access_token()
    if not isinstance(token, KiAccessToken):
        raise ToolError("Nicht angemeldet. Bitte die Verbindung zu FieldVibe in Claude neu herstellen.")
    if scope not in token.scopes:
        if scope == SCOPE_SCHREIBEN:
            # load_access_token streicht den Schreib-Scope, sobald das Recht ki_zugriff.bearbeiten
            # fehlt -- das Recht wird so bei jedem Aufruf neu geprueft, auch nach Erteilung.
            raise ToolError(
                "Schreiben ist nicht möglich: Die Verbindung hat den Zugriffsbereich „fieldvibe.schreiben“ nicht "
                "oder dir fehlt das Recht „KI-Assistent (Claude) › bearbeiten“ (z. B. nachträglich entzogen). "
                "Bitte Administrator fragen und ggf. neu verbinden."
            )
        raise ToolError(f"Dafür fehlt der Zugriffsbereich „{scope}“. Bitte die Verbindung mit diesem Bereich neu erteilen.")
    try:
        aufruf_limiter.hit(str(token.kv))
    except HTTPException as exc:
        raise ToolError("Zu viele Aufrufe in kurzer Zeit. Bitte kurz warten und erneut versuchen.") from exc
    return token
