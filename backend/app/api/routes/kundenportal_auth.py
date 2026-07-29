import logging

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import KundenAuthContext, get_current_kunde, get_kunden_db
from app.core.config import get_settings
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
from app.schemas.auth import LoginRequest, RefreshRequest, TokenPair
from app.schemas.kundenportal import (
    CurrentKunde,
    KundenPasswortResetRequest,
    KundenPasswortVergessenRequest,
)
from app.services.email_service import EmailNichtKonfiguriert, send_email
from app.services.kundenportal_auth_service import authenticate_kunde

router = APIRouter(prefix="/api/kundenportal/auth", tags=["kundenportal"])
_settings = get_settings()
_logger = logging.getLogger("app.kundenportal")


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest) -> TokenPair:
    return await authenticate_kunde(body.email, body.password)


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
async def passwort_vergessen(body: KundenPasswortVergessenRequest) -> None:
    """Antwortet immer mit 202, egal ob die E-Mail existiert, der Zugang
    aktiv ist, oder der Mandant ueberhaupt SMTP konfiguriert hat -- sonst
    liesse sich allein am Response-Status ablesen, ob eine E-Mail-Adresse
    im System bekannt ist (Enumeration-Schutz, dieselbe Ueberlegung wie das
    404-statt-403 bei Fremdzugriff auf Vorgaenge/Angebote)."""
    async with system_session() as session:
        result = await session.execute(
            select(KundenportalZugang).where(KundenportalZugang.email == body.email)
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
async def passwort_zuruecksetzen(body: KundenPasswortResetRequest) -> None:
    try:
        payload = decode_token(body.token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Reset-Link ist ungültig oder abgelaufen"
        ) from exc

    if payload.get("type") != "kundenportal_password_reset":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ungültiger Reset-Token")

    if len(body.new_password) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Passwort muss mindestens 10 Zeichen haben"
        )

    async with system_session() as session:
        zugang = await session.get(KundenportalZugang, payload["sub"])
        if zugang is None or not zugang.aktiv:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Zugang nicht gültig")
        zugang.password_hash = hash_password(body.new_password)
        await session.commit()
    return None
