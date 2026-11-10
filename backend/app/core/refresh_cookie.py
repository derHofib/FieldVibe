"""Refresh-Token der Mitarbeiter als HttpOnly-Cookie.

Das Cookie gehoert dem API-Host (host-only, kein Domain-Attribut): app.<domain>
und office.<domain> sprechen beide mit api.<domain>, teilen sich damit eine
Sitzung und sind gegenueber fremden Subdomains abgeschottet. Path=/api/auth
haelt es aus allen uebrigen Requests heraus. SameSite=Strict genuegt, weil
Frontend und API dieselbe registrierbare Domain haben ("same-site"); zusaetzlich
prueft /refresh bei Cookie-Nutzung den Origin-Header (siehe origin_erlaubt).
"""

from datetime import date

from fastapi import HTTPException, Request, Response, status

from app.core.config import get_settings
from app.schemas.auth import TokenPair

COOKIE_NAME = "fv_refresh"
COOKIE_PFAD = "/api/auth"
# Neue Clients melden sich damit an; sie bekommen das Token nie im Body zu sehen.
CLIENT_HEADER = "x-refresh-cookie"


def body_token_erlaubt(heute: date | None = None) -> bool:
    bis = get_settings().refresh_body_bis
    return bis is not None and (heute or date.today()) <= bis


def _attribute() -> dict:
    return {
        "httponly": True,
        "secure": get_settings().refresh_cookie_secure_aktiv,
        "samesite": "strict",
        "path": COOKIE_PFAD,
    }


def setze_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME, token, max_age=get_settings().refresh_token_expire_minutes * 60, **_attribute()
    )


def loesche_refresh_cookie(response: Response) -> None:
    # Gleiche Attribute wie beim Setzen, sonst loescht der Browser ein anderes Cookie.
    response.delete_cookie(COOKIE_NAME, **_attribute())


def paar_mit_cookie(request: Request, response: Response, paar: TokenPair) -> TokenPair:
    """Setzt das Cookie und entfernt das Refresh-Token aus der Antwort, sobald
    der Client Cookies spricht oder die Uebergangsfrist vorbei ist."""
    setze_refresh_cookie(response, paar.refresh_token)
    if request.headers.get(CLIENT_HEADER) == "1" or not body_token_erlaubt():
        return paar.model_copy(update={"refresh_token": None})
    return paar


def origin_pruefen(request: Request) -> None:
    """CSRF-Zusatzschutz fuer die Cookie-Nutzung: Browser senden bei POST immer
    einen Origin-Header; fehlt er oder ist er fremd, wird abgelehnt."""
    origin = request.headers.get("origin")
    if origin is None or origin not in get_settings().cors_origins:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origin nicht erlaubt")
