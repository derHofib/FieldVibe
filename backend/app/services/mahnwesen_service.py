from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.notification import Notification
from app.models.rechnung import Rechnung
from app.models.user import User
from app.models.vorgang_event import VorgangEvent
from app.db.session import system_session
from app.services.zuweisung_service import abrechnung_verantwortliche_user_ids

MAHNWESEN_AKTION = "mahnwesen_eskalation_run"


def _ziel_mahnstufe(tage_ueberfaellig: int) -> int:
    settings = get_settings()
    if tage_ueberfaellig >= settings.mahnstufe_3_tage:
        return 3
    if tage_ueberfaellig >= settings.mahnstufe_2_tage:
        return 2
    if tage_ueberfaellig >= settings.mahnstufe_1_tage:
        return 1
    return 0


async def _admins_und_disponenten(session: AsyncSession, mandant_id) -> list[User]:
    user_ids = await abrechnung_verantwortliche_user_ids(session, mandant_id)
    if not user_ids:
        return []
    result = await session.execute(select(User).where(User.id.in_(user_ids)))
    return list(result.scalars().all())


async def run_mahnwesen_eskalation(mandant_ids: list[UUID] | None = None) -> dict:
    """Taeglicher Lauf: erhoeht die Mahnstufe ueberfaelliger, noch unbezahlter
    Rechnungen (Status 'versendet' mit faellig_am in der Vergangenheit) nach
    den in Settings konfigurierten Tagesschwellen. Eskaliert nur, wenn sich
    die Stufe tatsaechlich erhoeht -- verhindert taegliches Neu-Benachrich-
    tigen, solange die Rechnung auf derselben Stufe verharrt.

    `mandant_ids` grenzt wie bei run_pruefzyklen_scheduler auf die
    Mandanten ein, deren Scheduler-Stunde gerade erreicht ist; None
    bearbeitet weiterhin alle Mandanten."""
    heute = date.today()
    jetzt = datetime.now(timezone.utc)
    eskaliert = 0

    async with system_session() as session:
        ueberfaellig_stmt = select(Rechnung).where(
            Rechnung.status == "versendet",
            Rechnung.faellig_am.isnot(None),
            Rechnung.faellig_am < heute,
        )
        if mandant_ids is not None:
            ueberfaellig_stmt = ueberfaellig_stmt.where(Rechnung.mandant_id.in_(mandant_ids))
        ueberfaellig = (await session.execute(ueberfaellig_stmt)).scalars().all()

        for rechnung in ueberfaellig:
            tage_ueberfaellig = (heute - rechnung.faellig_am).days
            ziel_stufe = _ziel_mahnstufe(tage_ueberfaellig)
            if ziel_stufe <= rechnung.mahnstufe:
                continue

            rechnung.mahnstufe = ziel_stufe
            rechnung.letzte_mahnung_am = jetzt
            eskaliert += 1

            if rechnung.vorgang_id is not None:
                session.add(
                    VorgangEvent(
                        mandant_id=rechnung.mandant_id,
                        vorgang_id=rechnung.vorgang_id,
                        event_type="rechnung_status",
                        is_system=True,
                        body=(
                            f"Rechnung {rechnung.rechnungsnummer}: {ziel_stufe}. Mahnung "
                            f"({tage_ueberfaellig} Tage ueberfaellig)"
                        ),
                        payload={"rechnung_id": str(rechnung.id), "mahnstufe": ziel_stufe},
                    )
                )

            for empfaenger in await _admins_und_disponenten(session, rechnung.mandant_id):
                session.add(
                    Notification(
                        mandant_id=rechnung.mandant_id,
                        user_id=empfaenger.id,
                        typ="frist",
                        titel=f"Rechnung {rechnung.rechnungsnummer}: {ziel_stufe}. Mahnung faellig",
                        ref_entity_type="rechnung",
                        ref_entity_id=rechnung.id,
                    )
                )

        ergebnis = {"rechnungen_eskaliert": eskaliert}
        session.add(
            AuditLog(
                mandant_id=None,
                actor_user_id=None,
                aktion=MAHNWESEN_AKTION,
                entity_type="scheduler",
                payload=ergebnis,
            )
        )
        await session.flush()

    return ergebnis
