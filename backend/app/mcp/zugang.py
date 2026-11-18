"""Wer darf per KI auf FieldVibe zugreifen -- eine einzige Pruefung, die bei der
Einwilligung, bei jedem Token-Refresh und bei jedem MCP-Aufruf laeuft, weil sich
Modul, Rechte und Konto zwischendurch aendern koennen.

Bewusst ohne system_session: alles laeuft in der tenant_session des Mandanten aus
dem signierten Token (Test: tests/test_mcp_oauth.py)."""
from dataclasses import dataclass
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rollen import ist_mitarbeiter_account
from app.models.mandant import Mandant
from app.models.user import User
from app.services import berechtigung_service

KI_MODUL = "ki_zugriff"
SCOPE_LESEN = "fieldvibe.lesen"
SCOPE_SCHREIBEN = "fieldvibe.schreiben"
ALLE_SCOPES = (SCOPE_LESEN, SCOPE_SCHREIBEN)


class KiZugangAbgelehnt(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class KiZugang:
    user: User
    schreiben_erlaubt: bool


async def pruefe_ki_zugang(
    session: AsyncSession,
    *,
    user_id: UUID,
    mandant_id: UUID | None,
    impersonated_by: UUID | None = None,
) -> KiZugang:
    if mandant_id is None:
        raise KiZugangAbgelehnt("KI-Zugriff gibt es nur für Mitarbeiter eines Betriebs.")
    if impersonated_by is not None:
        raise KiZugangAbgelehnt("KI-Zugriff ist während einer Impersonation nicht möglich.")
    user = await session.get(User, user_id)
    if user is None or not user.aktiv or user.mandant_id != mandant_id:
        raise KiZugangAbgelehnt("Das Konto ist nicht (mehr) verfügbar.")
    if not ist_mitarbeiter_account(user):
        raise KiZugangAbgelehnt("Dieses Konto darf den KI-Assistenten nicht nutzen.")
    mandant = await session.get(Mandant, mandant_id)
    if mandant is None or KI_MODUL in mandant.deaktivierte_module:
        raise KiZugangAbgelehnt(
            "Der KI-Zugriff ist für Ihren Betrieb nicht freigeschaltet. "
            "Bitte wenden Sie sich an Ihren Administrator."
        )
    wer = SimpleNamespace(user_id=user.id, role=user.role)
    if not await berechtigung_service.hat_recht(session, wer, "ki_zugriff", "sehen"):
        raise KiZugangAbgelehnt(
            "Dir fehlt das Recht „KI-Assistent (Claude) › sehen“. Bitte deinen Administrator."
        )
    schreiben = await berechtigung_service.hat_recht(session, wer, "ki_zugriff", "bearbeiten")
    return KiZugang(user=user, schreiben_erlaubt=schreiben)
