"""In-Process-Aufruf der bestehenden REST-API fuer die MCP-Tools.

Rechte (require_recht, Scopes, Kundenbeschraenkung, Module) sitzen in den Routen. Jedes
Tool ruft deshalb die Route mit einem frisch ausgestellten, 2 Minuten gueltigen
Access-Token des Nutzers auf, statt ORM/Services zu duplizieren: Token -> AuthContext ->
tenant_session (RLS) -> Fachrecht -> Modul -> Audit laufen exakt wie in der App."""
import logging
import re
from contextvars import ContextVar
from datetime import timedelta
from typing import Any
from uuid import UUID

import httpx
from mcp.server.mcpserver.exceptions import ToolError

from app.api.deps import KI_AKTION_HEADER
from app.core.security import create_access_token
from app.mcp.aktionen import AKTIONEN, GESPERRTE_VORGANG_STATUS, UUID_MUSTER, rueckweg_erlaubt, schreibaufruf_erlaubt
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


# Schreibaufrufe sind fail-closed: nur was in app/mcp/aktionen.py steht, darf ein Tool absetzen (Registry mit
# Aktionsart und Stufe). Bewusst kein DELETE, keine Abschluss-Routen, keine Veroeffentlichung von Vorlagen, keine
# Angebote, Rechnungen, Mails, Exporte oder Rechte -- das bleibt beim Menschen in der App (docs/MCP.md).
# DELETE und Gegenoperationen gibt es nur im Rueckweg-Modus (ki_rueckgaengig).
SCHREIB_ALLOWLIST = tuple((r.methode, r.regex) for r in AKTIONEN)

# Journal-ID der laufenden Tool-Aktion; wird als Header mitgeschickt, damit die Audit-Eintraege der Fachroute
# darauf verweisen (deps.get_current_user, nur bei via=mcp).
aktion_id_var: ContextVar[UUID | None] = ContextVar("mcp_aktion_id", default=None)


def _pruefe_erlaubt(methode: str, pfad: str, body: Any, rueckweg: bool) -> None:
    if methode == "GET":
        return
    erlaubt = rueckweg_erlaubt(methode, pfad) if rueckweg else schreibaufruf_erlaubt(methode, pfad)
    if not erlaubt:
        # Programmierfehler, kein Nutzerfehler: das Tool hat einen nicht freigegebenen Schreibweg gewaehlt.
        raise PermissionError(f"MCP-Schreibaufruf nicht erlaubt: {methode} {pfad}")
    # Harte Sperre unabhaengig vom Tool: Abschliessen/Stornieren (Stufe 3) kommt erst mit Etappe B, "abgerechnet"
    # setzt nur der Rechnungs-Workflow.
    if (
        methode == "PATCH"
        and isinstance(body, dict)
        and body.get("status") in GESPERRTE_VORGANG_STATUS
        and re.fullmatch(rf"/api/vorgaenge/{UUID_MUSTER}", pfad)
    ):
        raise PermissionError(f"MCP-Schreibaufruf nicht erlaubt: Vorgang-Status {body['status']!r} per KI")


async def _anfrage_mit_token(
    token: str,
    methode: str,
    pfad: str,
    *,
    params: dict[str, Any] | None = None,
    body: Any = None,
    rueckweg: bool = False,
) -> httpx.Response:
    """Ruft die App-Route in-process mit einem fertigen Access-Token auf. Gemeinsamer Unterbau fuer die Tools
    (Aufruf-Token der KI-Verbindung) und das Rueckgaengig aus der App (Token des angemeldeten Nutzers)."""
    from app.main import app  # lokal: main importiert den MCP-Server

    _pruefe_erlaubt(methode, pfad, body, rueckweg)
    saubere = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
    kopf = {"Authorization": f"Bearer {token}"}
    aktion_id = aktion_id_var.get()
    if aktion_id is not None and methode != "GET":
        kopf[KI_AKTION_HEADER] = str(aktion_id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://intern",
        timeout=_TIMEOUT_SEKUNDEN,
    ) as client:
        antwort = await client.request(methode, pfad, params=saubere, json=body, headers=kopf)
    if antwort.status_code >= 400:
        raise fehler_fuer(antwort)
    return antwort


async def _anfrage(
    zugriff: KiAccessToken,
    methode: str,
    pfad: str,
    *,
    params: dict[str, Any] | None = None,
    body: Any = None,
    rueckweg: bool = False,
) -> httpx.Response:
    # Die Erlaubnis-Pruefung kommt vor der Token-Ausstellung (Test: kein Token noetig fuer den Abbruch).
    _pruefe_erlaubt(methode, pfad, body, rueckweg)
    return await _anfrage_mit_token(_aufruf_token(zugriff), methode, pfad, params=params, body=body, rueckweg=rueckweg)


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

