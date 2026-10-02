import logging

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import PartnerAuthContext, get_current_partner, get_partner_db
from app.core.config import get_settings
from app.core.rate_limit import (
    client_ip,
    login_account_limiter,
    login_ip_limiter,
    password_reset_ip_limiter,
)
from app.core.security import (
    create_partner_access_token,
    create_partner_password_reset_token,
    create_partner_refresh_token,
    decode_token,
    hash_password,
)
from app.db.session import system_session
from app.models.mandant import Mandant
from app.models.partner import Partner
from app.models.partner_zugang import PartnerZugang
from app.schemas.auth import LoginRequest, RefreshRequest, RegistrierenRequest, TokenPair
from app.schemas.partner import (
    CurrentPartner,
    PartnerPasswortResetRequest,
    PartnerPasswortVergessenRequest,
)
from app.services.email_service import EmailNichtKonfiguriert, send_email
from app.services.einladung_service import als_angenommen_markieren, resolve_offene_einladung
from app.services import storage_service
from app.services.partner_auth_service import authenticate_partner

router = APIRouter(prefix="/api/partnerportal/auth", tags=["partnerportal"])
_settings = get_settings()
_logger = logging.getLogger("app.partnerportal")


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, request: Request) -> TokenPair:
    ip_key = client_ip(request)
    account_key = f"partner:{body.email.strip().lower()}"
    login_ip_limiter.check(ip_key)
    login_account_limiter.check(account_key)
    try:
        result = await authenticate_partner(body.email, body.password)
    except HTTPException:
        login_ip_limiter.record_failure(ip_key)
        login_account_limiter.record_failure(account_key)
        raise
    login_ip_limiter.record_success(ip_key)
    login_account_limiter.record_success(account_key)
    return result


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest) -> TokenPair:
    try:
        payload = decode_token(body.refresh_token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiges Refresh-Token"
        ) from exc

    if payload.get("type") != "partner_refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Kein Partnerportal-Refresh-Token"
        )

    async with system_session() as session:
        zugang = await session.get(PartnerZugang, payload["sub"])
        if zugang is None or not zugang.aktiv:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Zugang nicht gültig"
            )

        return TokenPair(
            access_token=create_partner_access_token(
                subject=zugang.id, mandant_id=zugang.mandant_id, partner_id=zugang.partner_id
            ),
            refresh_token=create_partner_refresh_token(
                subject=zugang.id, mandant_id=zugang.mandant_id, partner_id=zugang.partner_id
            ),
        )


@router.post("/registrieren", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def registrieren(body: RegistrierenRequest) -> TokenPair:
    """Schliesst eine Partner-Einladung ab: legt den Partnerportal-Zugang
    mit dem selbst gewaehlten Passwort an und loggt direkt ein."""
    if len(body.password) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Passwort muss mindestens 10 Zeichen haben"
        )
    async with system_session() as session:
        einladung = await resolve_offene_einladung(session, body.token, erwartete_art="partner")

        zugang = PartnerZugang(
            mandant_id=einladung.mandant_id,
            partner_id=einladung.partner_id,
            email=einladung.email,
            password_hash=hash_password(body.password),
            name=body.name,
        )
        session.add(zugang)
        await session.flush()
        await als_angenommen_markieren(session, einladung)

        return TokenPair(
            access_token=create_partner_access_token(
                subject=zugang.id, mandant_id=zugang.mandant_id, partner_id=zugang.partner_id
            ),
            refresh_token=create_partner_refresh_token(
                subject=zugang.id, mandant_id=zugang.mandant_id, partner_id=zugang.partner_id
            ),
        )


@router.get("/me", response_model=CurrentPartner)
async def me(
    auth: PartnerAuthContext = Depends(get_current_partner),
    session: AsyncSession = Depends(get_partner_db),
) -> CurrentPartner:
    zugang = await session.get(PartnerZugang, auth.zugang_id)
    if zugang is None or zugang.partner_id != auth.partner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zugang nicht gefunden")
    partner = await session.get(Partner, auth.partner_id)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner nicht gefunden")

    mandant = await session.get(Mandant, auth.mandant_id)

    return CurrentPartner(
        zugang_id=zugang.id,
        partner_id=partner.id,
        partner_name=partner.name,
        name=zugang.name,
        email=zugang.email,
        mandant_name=mandant.name if mandant else "",
        mandant_logo_url=(
            storage_service.presigned_get_url(mandant.logo_object_key)
            if mandant and mandant.logo_object_key
            else None
        ),
    )


@router.post("/passwort-vergessen", status_code=status.HTTP_202_ACCEPTED)
async def passwort_vergessen(body: PartnerPasswortVergessenRequest, request: Request) -> None:
    """Enumeration-Schutz wie beim Kundenportal-Pendant: antwortet immer mit
    202, unabhaengig davon, ob die E-Mail existiert oder SMTP konfiguriert
    ist. Da der Status immer gleich ist, zaehlt das Limit jeden Aufruf pro IP
    (Massen-Mailversand), nicht nur Fehlschlaege."""
    ip_key = client_ip(request)
    password_reset_ip_limiter.check(ip_key)
    password_reset_ip_limiter.record_failure(ip_key)

    async with system_session() as session:
        result = await session.execute(
            select(PartnerZugang).where(func.lower(PartnerZugang.email) == body.email)
        )
        zugang = result.scalar_one_or_none()
        if zugang is None or not zugang.aktiv:
            return None

        token = create_partner_password_reset_token(zugang_id=zugang.id)
        reset_link = f"{_settings.frontend_base_url}/partnerportal/passwort-zuruecksetzen?token={token}"
        try:
            await send_email(
                session,
                zugang.mandant_id,
                to=zugang.email,
                subject="Passwort zuruecksetzen",
                body=(
                    f"Hallo {zugang.name},\n\n"
                    "fuer Ihr Partnerportal-Konto wurde ein Passwort-Reset angefordert. "
                    f"Falls Sie das waren, setzen Sie hier ein neues Passwort:\n{reset_link}\n\n"
                    f"Der Link ist {_settings.partner_reset_token_expire_minutes} Minuten gueltig. "
                    "Falls Sie das nicht angefordert haben, ignorieren Sie diese E-Mail."
                ),
            )
        except EmailNichtKonfiguriert:
            pass
        except Exception:
            _logger.exception("Partnerportal-Passwort-Reset-Mail konnte nicht verschickt werden")

    return None


@router.post("/passwort-zuruecksetzen", status_code=status.HTTP_204_NO_CONTENT)
async def passwort_zuruecksetzen(body: PartnerPasswortResetRequest, request: Request) -> None:
    ip_key = client_ip(request)
    password_reset_ip_limiter.check(ip_key)

    try:
        payload = decode_token(body.token)
    except jwt.PyJWTError as exc:
        password_reset_ip_limiter.record_failure(ip_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Reset-Link ist ungültig oder abgelaufen"
        ) from exc

    if payload.get("type") != "partner_password_reset":
        password_reset_ip_limiter.record_failure(ip_key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ungültiger Reset-Token")

    if len(body.new_password) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Passwort muss mindestens 10 Zeichen haben"
        )

    async with system_session() as session:
        zugang = await session.get(PartnerZugang, payload["sub"])
        if zugang is None or not zugang.aktiv:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Zugang nicht gültig")
        zugang.password_hash = hash_password(body.new_password)
        await session.commit()
    return None
