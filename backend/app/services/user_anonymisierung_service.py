import logging
import secrets
import uuid

from sqlalchemy import ColumnElement, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.fahrzeug_zuweisung import FahrzeugZuweisung
from app.models.kunde_zuweisung import KundeZuweisung
from app.models.mail_account import MailAccount
from app.models.user import User
from app.models.vorgang import Vorgang
from app.services import storage_service
from app.services.organigramm_sync_service import alle_besetzungen_beenden

logger = logging.getLogger(__name__)

ANONYM_NAME = "Gelöschter Nutzer"
ANONYM_EMAIL_PRAEFIX = "geloescht-"
ANONYM_EMAIL_DOMAIN = "@invalid.fieldvibe"

# Kein eigenes Feld am User-Modell (Migration waere noetig) -- das Kennzeichen
# ist der Platzhalter-E-Mail-Praefix (.invalid ist nach RFC 2606 nie zustellbar).
_ANONYM_EMAIL_LIKE = f"{ANONYM_EMAIL_PRAEFIX}%{ANONYM_EMAIL_DOMAIN}"

# Vorgang-Status ohne die abgeschlossenen/stornierten -- deren Zuweisung bleibt als Historie.
_OFFENE_VORGANG_STATUS = ("neu", "geplant", "in_arbeit", "wartet_kunde")


def ist_anonymisiert(user: User) -> bool:
    return (
        not user.aktiv
        and user.email.startswith(ANONYM_EMAIL_PRAEFIX)
        and user.email.endswith(ANONYM_EMAIL_DOMAIN)
    )


def nicht_anonymisiert() -> ColumnElement[bool]:
    """SQL-Gegenstueck zu ist_anonymisiert() fuer Listen/Dropdowns. Nur auf
    die E-Mail geprueft: aktiv=false allein heisst bloss "deaktiviert"."""
    return ~User.email.like(_ANONYM_EMAIL_LIKE)


async def anonymisiere_user(
    session: AsyncSession, user: User, actor_user_id: uuid.UUID | None = None
) -> None:
    """Entfernt alle personenbezogenen Daten, behaelt aber die Zeile, damit
    Fremdschluessel (Zeiterfassung, Rechnungen, Verlauf ...) intakt bleiben."""
    avatar_key = user.avatar_url
    user.name = ANONYM_NAME
    user.email = f"{ANONYM_EMAIL_PRAEFIX}{uuid.uuid4()}{ANONYM_EMAIL_DOMAIN}"
    # Gueltiger Argon2-Hash eines verworfenen Zufallswerts: ein Platzhalter wie
    # "!" wuerde in verify_password() InvalidHashError (-> 500) statt False liefern.
    user.password_hash = hash_password(secrets.token_urlsafe(48))
    user.aktiv = False
    user.avatar_url = None
    user.bottom_nav_items = None
    user.office_nav_items = None
    user.token_version = User.token_version + 1
    await session.flush()
    await session.refresh(user, ["token_version"])

    if avatar_key and not avatar_key.startswith(("http://", "https://")):
        try:
            await storage_service.delete_object(avatar_key)
        except Exception:
            logger.warning("Avatar-Objekt von anonymisiertem Nutzer nicht loeschbar", exc_info=True)

    # Wie beim echten Loeschen (ON DELETE CASCADE) entfallen diese Zuweisungen;
    # sonst erschiene "Gelöschter Nutzer" als Betreuer/Fahrer.
    await alle_besetzungen_beenden(session, user.id, actor_user_id)
    await session.execute(delete(KundeZuweisung).where(KundeZuweisung.user_id == user.id))
    await session.execute(delete(FahrzeugZuweisung).where(FahrzeugZuweisung.user_id == user.id))
    await session.execute(
        update(Vorgang)
        .where(Vorgang.zugewiesener_user_id == user.id, Vorgang.status.in_(_OFFENE_VORGANG_STATUS))
        .values(zugewiesener_user_id=None)
    )
    # Fremde Postfach-Zugangsdaten duerfen nicht weiterlaufen.
    await session.execute(update(MailAccount).where(MailAccount.user_id == user.id).values(aktiv=False))
