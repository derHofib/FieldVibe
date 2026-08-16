import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_einladung_token, decode_token
from app.models.einladung import Einladung
from app.models.kundenportal import KundenportalZugang
from app.models.partner_zugang import PartnerZugang
from app.models.user import User
from app.services.email_service import EmailNichtKonfiguriert, send_email

_settings = get_settings()
_logger = logging.getLogger("app.einladungen")

_REGISTRIERUNGS_PFAD = {
    "mitarbeiter": "/registrieren",
    "kunde": "/portal/registrieren",
    "partner": "/partnerportal/registrieren",
}
_PORTAL_NAME = {
    "mitarbeiter": "FieldVibe",
    "kunde": "das Kundenportal",
    "partner": "das Partnerportal",
}


async def konto_existiert_bereits(session: AsyncSession, art: str, email: str) -> bool:
    if art == "mitarbeiter":
        stmt = select(User).where(func.lower(User.email) == email)
    elif art == "kunde":
        stmt = select(KundenportalZugang).where(func.lower(KundenportalZugang.email) == email)
    else:
        stmt = select(PartnerZugang).where(func.lower(PartnerZugang.email) == email)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def create_einladung(
    session: AsyncSession,
    *,
    mandant_id: UUID,
    email: str,
    art: str,
    rolle: str | None = None,
    kunde_id: UUID | None = None,
    partner_id: UUID | None = None,
    eingeladen_von: UUID | None,
) -> Einladung:
    if await konto_existiert_bereits(session, art, email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Für diese E-Mail-Adresse existiert bereits ein Account",
        )

    einladung = Einladung(
        mandant_id=mandant_id,
        email=email,
        art=art,
        rolle=rolle,
        kunde_id=kunde_id,
        partner_id=partner_id,
        eingeladen_von=eingeladen_von,
    )
    session.add(einladung)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Für diese E-Mail-Adresse liegt bereits eine offene Einladung vor",
        ) from exc
    return einladung


def _registrierungs_link(einladung: Einladung) -> str:
    token = create_einladung_token(einladung_id=einladung.id)
    pfad = _REGISTRIERUNGS_PFAD[einladung.art]
    return f"{_settings.frontend_base_url}{pfad}?token={token}"


async def versende_einladung(
    session: AsyncSession, einladung: Einladung, *, absender_name: str
) -> str | None:
    """Verschickt die Einladungsmail. Anders als beim Passwort-Reset (dort
    bewusst stiller Fehlschlag zum Enumeration-Schutz) gibt es hier keinen
    Grund, einen Versandfehler vor dem einladenden Mitarbeiter zu
    verstecken -- er kennt die Ziel-Adresse ja bereits selbst. Bei jedem
    Fehlschlag (kein SMTP konfiguriert, oder ein echter Zustellungsfehler)
    wird der Link deshalb direkt zurückgegeben, damit er manuell
    weitergegeben werden kann."""
    link = _registrierungs_link(einladung)
    portal = _PORTAL_NAME[einladung.art]
    try:
        await send_email(
            session,
            einladung.mandant_id,
            to=einladung.email,
            subject=f"Einladung zu {portal}",
            body=(
                f"Hallo,\n\n"
                f"{absender_name} hat Sie eingeladen, sich bei {portal} zu registrieren.\n\n"
                f"Registrieren Sie sich hier:\n{link}\n\n"
                f"Der Link ist {_settings.einladung_token_expire_minutes // (60 * 24)} Tage gültig. "
                "Falls Sie das nicht erwartet haben, ignorieren Sie diese E-Mail."
            ),
        )
        return None
    except EmailNichtKonfiguriert:
        return link
    except Exception:
        _logger.exception("Einladungsmail konnte nicht verschickt werden (Einladung %s)", einladung.id)
        return link


def einladung_ist_abgelaufen(einladung: Einladung) -> bool:
    grenze = einladung.created_at + timedelta(minutes=_settings.einladung_token_expire_minutes)
    return datetime.now(timezone.utc) >= grenze


def to_read_model(einladung: Einladung, *, registrierungslink: str | None = None) -> dict:
    return {
        "id": einladung.id,
        "email": einladung.email,
        "art": einladung.art,
        "rolle": einladung.rolle,
        "kunde_id": einladung.kunde_id,
        "partner_id": einladung.partner_id,
        "status": einladung.status,
        "abgelaufen": einladung.status == "offen" and einladung_ist_abgelaufen(einladung),
        "created_at": einladung.created_at,
        "angenommen_am": einladung.angenommen_am,
        "registrierungslink": registrierungslink,
    }


async def resolve_offene_einladung(session: AsyncSession, token: str, *, erwartete_art: str) -> Einladung:
    try:
        payload = decode_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Einladungslink ist ungültig oder abgelaufen",
        ) from exc

    if payload.get("type") != "einladung":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ungültiger Einladungslink")

    einladung = await session.get(Einladung, payload["sub"])
    if einladung is None or einladung.art != erwartete_art or einladung.status != "offen":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Einladung ist nicht mehr gültig",
        )
    if await konto_existiert_bereits(session, einladung.art, einladung.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Für diese E-Mail-Adresse existiert bereits ein Account",
        )
    return einladung


async def als_angenommen_markieren(session: AsyncSession, einladung: Einladung) -> None:
    einladung.status = "angenommen"
    einladung.angenommen_am = datetime.now(timezone.utc)
    await session.flush()
