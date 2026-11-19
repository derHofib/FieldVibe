"""In-Process-Aufruf der bestehenden REST-API fuer die MCP-Tools.

Rechte (require_recht, Scopes, Kundenbeschraenkung, Module) sitzen in den Routen. Jedes
Tool ruft deshalb die Route mit einem frisch ausgestellten, 2 Minuten gueltigen
Access-Token des Nutzers auf, statt ORM/Services zu duplizieren: Token -> AuthContext ->
tenant_session (RLS) -> Fachrecht -> Modul -> Audit laufen exakt wie in der App."""
import logging
import re
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
        return ToolError(
            f"Nicht gefunden: {detail.rstrip('.') or 'der Eintrag existiert nicht oder ist für dich nicht sichtbar'}."
        )
    if status == 422:
        return ToolError(f"Ungültige Eingabe: {detail or 'die Parameter passen nicht'}.")
    if status == 429:
        return ToolError("Zu viele Anfragen. Bitte kurz warten und erneut versuchen.")
    if status < 500:
        return ToolError(f"Die Anfrage wurde abgelehnt ({detail or f'HTTP {status}'}).")
    logger.error("MCP-Tool: interne API antwortete mit %s", status)
    return ToolError("FieldVibe konnte die Anfrage gerade nicht bearbeiten. Bitte später erneut versuchen.")


# Schreibaufrufe sind fail-closed: nur was hier steht, darf ein Tool absetzen. Bewusst kein
# DELETE, keine Status-/Abschluss-Routen (Vorgang-PATCH, /abschliessen), keine Veroeffentlichung
# von Vorlagen (PATCH /api/form-schemas/{id}), keine Zuordnung zu Auftragstypen, keine Angebote,
# Rechnungen, Mails, Exporte oder Rechte -- das bleibt beim Menschen in der App (docs/MCP.md).
_UUID = r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}"
SCHREIB_ALLOWLIST: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (methode, re.compile(muster))
    for methode, muster in (
        ("POST", r"/api/vorgaenge"),
        ("POST", rf"/api/vorgaenge/{_UUID}/events"),
        ("POST", r"/api/maengel"),
        ("POST", r"/api/telefonate"),
        ("POST", r"/api/form-submissions"),
        ("PATCH", rf"/api/form-submissions/{_UUID}"),
        ("POST", r"/api/form-schemas"),
        ("POST", rf"/api/form-schemas/{_UUID}/groups"),
        ("POST", rf"/api/form-schemas/{_UUID}/fields"),
        ("PATCH", rf"/api/form-schemas/{_UUID}/fields/{_UUID}"),
        # Ansichten (Erfassung/Druck) nur anlegen, nie aendern oder loeschen: ohne Druckansicht scheitert das PDF
        # eines Protokolls. Wie die Felder-Routen nur auf Entwuerfen, die das Tool selbst entwirft/ueberarbeitet.
        ("POST", rf"/api/form-schemas/{_UUID}/views"),
    )
)


def schreibaufruf_erlaubt(methode: str, pfad: str) -> bool:
    return any(m == methode and muster.fullmatch(pfad) for m, muster in SCHREIB_ALLOWLIST)


async def _anfrage(
    zugriff: KiAccessToken,
    methode: str,
    pfad: str,
    *,
    params: dict[str, Any] | None = None,
    body: Any = None,
) -> httpx.Response:
    from app.main import app  # lokal: main importiert den MCP-Server

    if methode != "GET" and not schreibaufruf_erlaubt(methode, pfad):
        # Programmierfehler, kein Nutzerfehler: das Tool hat einen nicht freigegebenen Schreibweg gewaehlt.
        raise PermissionError(f"MCP-Schreibaufruf nicht erlaubt: {methode} {pfad}")
    saubere = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://intern",
        timeout=_TIMEOUT_SEKUNDEN,
    ) as client:
        antwort = await client.request(
            methode,
            pfad,
            params=saubere,
            json=body,
            headers={"Authorization": f"Bearer {_aufruf_token(zugriff)}"},
        )
    if antwort.status_code >= 400:
        raise fehler_fuer(antwort)
    return antwort


async def api_get(zugriff: KiAccessToken, pfad: str, params: dict[str, Any] | None = None) -> Any:
    """GET gegen die eigene App. Leere Parameter werden weggelassen."""
    return (await _anfrage(zugriff, "GET", pfad, params=params)).json()


async def api_get_binaer(
    zugriff: KiAccessToken, pfad: str, params: dict[str, Any] | None = None
) -> tuple[bytes, str]:
    """GET einer Datei (PDF): Rohbytes und Content-Type."""
    antwort = await _anfrage(zugriff, "GET", pfad, params=params)
    return antwort.content, antwort.headers.get("content-type", "application/octet-stream")


async def api_post(
    zugriff: KiAccessToken, pfad: str, body: Any = None, params: dict[str, Any] | None = None
) -> Any:
    return (await _anfrage(zugriff, "POST", pfad, params=params, body=body)).json()


async def api_patch(zugriff: KiAccessToken, pfad: str, body: Any) -> Any:
    return (await _anfrage(zugriff, "PATCH", pfad, body=body)).json()
