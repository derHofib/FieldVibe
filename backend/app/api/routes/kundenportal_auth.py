import logging

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
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
from app.db.session import tenant_session
from app.models.kunde import Kunde
from app.models.kundenportal import KundenportalZugang
from app.models.mandant import Mandant
from app.schemas.auth import LoginRequest, RefreshRequest, RegistrierenRequest, TokenPair
from app.schemas.kunde import KundeLogoUrl
from app.schemas.kundenportal import (
    CurrentKunde,
    KundenPasswortResetRequest,
    KundenPasswortVergessenRequest,
    KundenportalLinkInfo,
)
from app.services import storage_service, system_lookups
from app.services.email_service import EmailNichtKonfiguriert, send_email
from app.services.token_widerruf_service import widerrufe_tokens
from app.services.einladung_service import (
    als_angenommen_markieren,
    mandant_der_einladung,
    resolve_offene_einladung,
)
from app.services.kundenportal_auth_service import authenticate_kunde
from app.schemas.user import MIN_PASSWORT_LAENGE

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


async def _link_fuer_slug(portal_slug: str, *, grund: str) -> system_lookups.KundeLink:
    link = await system_lookups.kunde_link_lookup(portal_slug, grund=grund)
    if link is None or not link.mandant_aktiv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link ungültig")
    return link


@router.get("/link/{portal_slug}", response_model=KundenportalLinkInfo)
async def link_info(portal_slug: str) -> KundenportalLinkInfo:
    """Loest den personalisierten Login-Link auf (/portal/l/{portal_slug}):
    ein Link pro Kunde, den jeder Mitarbeiter dieses Kunden nutzen kann.
    Liefert nur Anzeigedaten (Name/Logo des Kunden), niemals einen Token --
    die Passwort-Eingabe bleibt in jedem Fall Pflicht und ist weiterhin an
    den jeweils eigenen KundenportalZugang gebunden. Absichtlich ohne
    Rate-Limiting: der Slug ist selbst schon ein hochentropisches Geheimnis
    (secrets.token_urlsafe(12), siehe app/api/routes/kunden.py), kein
    erratbarer Bezeichner wie eine E-Mail-Adresse."""
    link = await _link_fuer_slug(portal_slug, grund="portal-auth: link-info")
    return KundenportalLinkInfo(
        kunde_name=link.kunde_name,
        mandant_name=link.mandant_name,
        hat_logo=link.logo_object_key is not None,
    )


@router.get("/link/{portal_slug}/logo-url", response_model=KundeLogoUrl)
async def link_logo_url(portal_slug: str) -> KundeLogoUrl:
    link = await _link_fuer_slug(portal_slug, grund="portal-auth: link-logo-url")
    if link.logo_object_key is None:
        return KundeLogoUrl(url=None)
    return KundeLogoUrl(url=storage_service.presigned_get_url(link.logo_object_key))


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

    zugang = await system_lookups.kundenzugang_by_id(
        payload["sub"], grund="portal-auth: refresh-token einloesen"
    )
    if zugang is None or not zugang.aktiv:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Zugang nicht gültig"
        )
    if payload.get("tv", 0) != zugang.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token widerrufen"
        )
    async with tenant_session(mandant_id=zugang.mandant_id, is_super_admin=False) as session:
        mandant = await session.get(Mandant, zugang.mandant_id)
    if mandant is None or mandant.status != "aktiv":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Mandant ist nicht aktiv"
        )

    return TokenPair(
        access_token=create_kundenportal_access_token(
            token_version=zugang.token_version,
            subject=zugang.id, mandant_id=zugang.mandant_id, kunde_id=zugang.kunde_id
        ),
        refresh_token=create_kundenportal_refresh_token(
            token_version=zugang.token_version,
            subject=zugang.id, mandant_id=zugang.mandant_id, kunde_id=zugang.kunde_id
        ),
    )


@router.post("/registrieren", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def registrieren(body: RegistrierenRequest) -> TokenPair:
    """Schliesst eine Kunden-Einladung ab: legt den Kundenportal-Zugang mit
    dem selbst gewaehlten Passwort an und loggt direkt ein."""
    if len(body.password) < MIN_PASSWORT_LAENGE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Passwort muss mindestens {MIN_PASSWORT_LAENGE} Zeichen haben"
        )
    mandant_id = await mandant_der_einladung(body.token)
    async with tenant_session(mandant_id=mandant_id, is_super_admin=False) as session:
        einladung = await resolve_offene_einladung(session, body.token, erwartete_art="kunde")

        zugang = KundenportalZugang(
            mandant_id=einladung.mandant_id,
            kunde_id=einladung.kunde_id,
            email=einladung.email,
            password_hash=hash_password(body.password),
            name=body.name,
        )
        session.add(zugang)
        await session.flush()
        await als_angenommen_markieren(session, einladung)

        return TokenPair(
            access_token=create_kundenportal_access_token(
                token_version=zugang.token_version,
                subject=zugang.id, mandant_id=zugang.mandant_id, kunde_id=zugang.kunde_id
            ),
            refresh_token=create_kundenportal_refresh_token(
                token_version=zugang.token_version,
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
        portal_slug=kunde.portal_slug,
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

    zugang = await system_lookups.kundenzugang_by_email(body.email, grund="portal-auth: passwort vergessen")
    if zugang is None or not zugang.aktiv:
        return None

    async with tenant_session(mandant_id=zugang.mandant_id, is_super_admin=False) as session:
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

    if len(body.new_password) < MIN_PASSWORT_LAENGE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Passwort muss mindestens {MIN_PASSWORT_LAENGE} Zeichen haben"
        )

    gefunden = await system_lookups.kundenzugang_by_id(
        payload["sub"], grund="portal-auth: passwort zuruecksetzen"
    )
    if gefunden is None:
        password_reset_ip_limiter.record_failure(ip_key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Zugang nicht gültig")

    async with tenant_session(mandant_id=gefunden.mandant_id, is_super_admin=False) as session:
        zugang = await session.get(KundenportalZugang, gefunden.id)
        if zugang is None or not zugang.aktiv:
            password_reset_ip_limiter.record_failure(ip_key)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Zugang nicht gültig")
        zugang.password_hash = hash_password(body.new_password)
        await widerrufe_tokens(session, zugang)
        await session.commit()
    password_reset_ip_limiter.record_success(ip_key)
    return None
