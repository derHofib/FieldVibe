import logging

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import KundenAuthContext, get_current_kunde, get_kunden_db
from app.core.config import get_settings
from app.core.rate_limit import (
    client_ip,
    login_account_limiter,
    login_ip_limiter,
    password_reset_ip_limiter,
)
from app.core.security import (
    create_kundenportal_access_token,
    create_kundenportal_password_reset_token,
    create_kundenportal_refresh_token,
    decode_token,
    hash_password,
)
from app.db.session import system_session
from app.models.kunde import Kunde
from app.models.kundenportal import KundenportalZugang
from app.models.mandant import Mandant
from app.schemas.auth import LoginRequest, RefreshRequest, TokenPair
from app.schemas.kundenportal import (
    CurrentKunde,
    KundenPasswortResetRequest,
    KundenPasswortVergessenRequest,
    KundenportalLinkInfo,
)
from app.services.email_service import EmailNichtKonfiguriert, send_email
from app.services.kundenportal_auth_service import authenticate_kunde

router = APIRouter(prefix="/api/kundenportal/auth", tags=["kundenportal"])
_settings = get_settings()
_logger = logging.getLogger("app.kundenportal")


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, request: Request) -> TokenPair:
    ip_key = client_ip(request)
    account_key = f"portal:{body.email.strip().lower()}"
    login_ip_limiter.check(ip_key)
    login_account_limiter.check(account_key)
    try:
        result = await authenticate_kunde(body.email, body.password)
    except HTTPException:
        login_ip_limiter.record_failure(ip_key)
        login_account_limiter.record_failure(account_key)
        raise
    login_ip_limiter.record_success(ip_key)
    login_account_limiter.record_success(account_key)
    return result


@router.get("/link/{login_slug}", response_model=KundenportalLinkInfo)
async def link_info(login_slug: str) -> KundenportalLinkInfo:
    """Loest den personalisierten Login-Link auf (/portal/l/{login_slug}):
    liefert nur Anzeigedaten zum Vorbefuellen der Login-Seite, niemals einen
    Token -- die Passwort-Eingabe bleibt in jedem Fall Pflicht. Absichtlich
    ohne Rate-Limiting: der Slug ist selbst schon ein hochentropisches
    Geheimnis (secrets.token_urlsafe(16), siehe app/api/routes/kunden.py),
    kein erratbarer Bezeichner wie eine E-Mail-Adresse."""
    async with system_session() as session:
        result = await session.execute(
            select(KundenportalZugang).where(KundenportalZugang.login_slug == login_slug)
        )
        zugang = result.scalar_one_or_none()
        if zugang is None or not zugang.aktiv:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link ungültig")

        kunde = await session.get(Kunde, zugang.kunde_id)
        mandant = await session.get(Mandant, zugang.mandant_id)
        if kunde is None or mandant is None or mandant.status != "aktiv":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link ungültig")

        return KundenportalLinkInfo(
            email=zugang.email, name=zugang.name, kunde_name=kunde.name, mandant_name=mandant.name
        )


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest) -> TokenPair:
    try:
        payload = decode_token(body.refresh_token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiges Refresh-Token"
        ) from exc

    if payload.get("type") != "kundenportal_refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Kein Kundenportal-Refresh-Token"
        )

    async with system_session() as session:
        zugang = await session.get(KundenportalZugang, payload["sub"])
        if zugang is None or not zugang.aktiv:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Zugang nicht gültig"
            )

        return TokenPair(
            access_token=create_kundenportal_access_token(
                subject=zugang.id, mandant_id=zugang.mandant_id, kunde_id=zugang.kunde_id
            ),
            refresh_token=create_kundenportal_refresh_token(
                subject=zugang.id, mandant_id=zugang.mandant_id, kunde_id=zugang.kunde_id
            ),
        )


@router.get("/me", response_model=CurrentKunde)
async def me(
    auth: KundenAuthContext = Depends(get_current_kunde),
    session: AsyncSession = Depends(get_kunden_db),
) -> CurrentKunde:
    zugang = await session.get(KundenportalZugang, auth.zugang_id)
    if zugang is None or zugang.kunde_id != auth.kunde_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zugang nicht gefunden")
    kunde = await session.get(Kunde, auth.kunde_id)
    if kunde is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")

    return CurrentKunde(
        zugang_id=zugang.id,
        kunde_id=kunde.id,
        kunde_name=kunde.name,
        name=zugang.name,
        email=zugang.email,
    )


@router.post("/passwort-vergessen", status_code=status.HTTP_202_ACCEPTED)
async def passwort_vergessen(body: KundenPasswortVergessenRequest, request: Request) -> None:
    """Antwortet immer mit 202, egal ob die E-Mail existiert, der Zugang
    aktiv ist, oder der Mandant ueberhaupt SMTP konfiguriert hat -- sonst
    liesse sich allein am Response-Status ablesen, ob eine E-Mail-Adresse
    im System bekannt ist (Enumeration-Schutz, dieselbe Ueberlegung wie das
    404-statt-403 bei Fremdzugriff auf Vorgaenge/Angebote). Der immer-gleiche
    Status heisst aber auch: Rate-Limiting kann hier nicht an Erfolg/Fehlschlag
    haengen, sondern zaehlt jeden Aufruf pro IP, um Massen-Mailversand zu
    verhindern."""
    ip_key = client_ip(request)
    password_reset_ip_limiter.check(ip_key)
    password_reset_ip_limiter.record_failure(ip_key)

    async with system_session() as session:
        result = await session.execute(
            select(KundenportalZugang).where(func.lower(KundenportalZugang.email) == body.email)
        )
        zugang = result.scalar_one_or_none()
        if zugang is None or not zugang.aktiv:
            return None

        token = create_kundenportal_password_reset_token(zugang_id=zugang.id)
        reset_link = f"{_settings.frontend_base_url}/portal/passwort-zuruecksetzen?token={token}"
        try:
            await send_email(
                session,
                zugang.mandant_id,
                to=zugang.email,
                subject="Passwort zuruecksetzen",
                body=(
                    f"Hallo {zugang.name},\n\n"
                    "fuer Ihr Kundenportal-Konto wurde ein Passwort-Reset angefordert. "
                    f"Falls Sie das waren, setzen Sie hier ein neues Passwort:\n{reset_link}\n\n"
                    f"Der Link ist {_settings.kundenportal_reset_token_expire_minutes} Minuten gueltig. "
                    "Falls Sie das nicht angefordert haben, ignorieren Sie diese E-Mail."
                ),
            )
        except EmailNichtKonfiguriert:
            # Der Mandant hat (noch) kein SMTP hinterlegt -- der Kunde muss
            # sich in diesem Fall an den Betrieb wenden, der das Passwort
            # ueber PATCH /api/kunden/{id}/portal-zugaenge/{zugang_id} direkt
            # setzen kann (siehe kunden.py). Kein Fehler nach aussen, aus
            # demselben Enumeration-Schutz-Grund wie oben.
            pass
        except Exception:
            # Ein tatsaechlicher Zustellungsfehler (falsche SMTP-Zugangsdaten,
            # Netzwerkproblem) darf den Request trotzdem nicht mit einem 500
            # beantworten -- das wuerde nicht nur die Enumeration-Schutz-
            # Zusicherung brechen, sondern dem Kunden auch keinen brauchbaren
            # naechsten Schritt geben. Serverseitig loggen, damit ein
            # Mitarbeiter eine kaputte SMTP-Konfiguration ueberhaupt bemerkt.
            _logger.exception("Kundenportal-Passwort-Reset-Mail konnte nicht verschickt werden")

    return None


@router.post("/passwort-zuruecksetzen", status_code=status.HTTP_204_NO_CONTENT)
async def passwort_zuruecksetzen(body: KundenPasswortResetRequest, request: Request) -> None:
    ip_key = client_ip(request)
    password_reset_ip_limiter.check(ip_key)

    try:
        payload = decode_token(body.token)
    except jwt.PyJWTError as exc:
        password_reset_ip_limiter.record_failure(ip_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Reset-Link ist ungültig oder abgelaufen"
        ) from exc

    if payload.get("type") != "kundenportal_password_reset":
        password_reset_ip_limiter.record_failure(ip_key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ungültiger Reset-Token")

    if len(body.new_password) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Passwort muss mindestens 10 Zeichen haben"
        )

    async with system_session() as session:
        zugang = await session.get(KundenportalZugang, payload["sub"])
        if zugang is None or not zugang.aktiv:
            password_reset_ip_limiter.record_failure(ip_key)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Zugang nicht gültig")
        zugang.password_hash = hash_password(body.new_password)
        await session.commit()
    password_reset_ip_limiter.record_success(ip_key)
    return None
