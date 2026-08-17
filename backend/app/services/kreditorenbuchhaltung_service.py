from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import system_session
from app.models.audit_log import AuditLog
from app.models.eingangsrechnung import Eingangsrechnung
from app.models.notification import Notification
from app.models.user import User
from app.core.config import get_settings
from app.services.eingangsrechnung_service import bezahlter_betrag, brutto_betrag, positionen_fuer, zahlungen_fuer
from app.services.zuweisung_service import abrechnung_verantwortliche_user_ids

KREDITOREN_AKTION = "kreditorenbuchhaltung_faelligkeits_check_run"


async def _verantwortliche(session: AsyncSession, mandant_id: UUID) -> list[User]:
    user_ids = await abrechnung_verantwortliche_user_ids(session, mandant_id)
    if not user_ids:
        return []
    result = await session.execute(select(User).where(User.id.in_(user_ids)))
    return list(result.scalars().all())


async def _hat_offene_notification(
    session: AsyncSession, *, user_id: UUID, ref_entity_type: str, ref_entity_id: UUID
) -> bool:
    result = await session.execute(
        select(Notification.id)
        .where(
            Notification.user_id == user_id,
            Notification.ref_entity_type == ref_entity_type,
            Notification.ref_entity_id == ref_entity_id,
            Notification.gelesen_am.is_(None),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def run_kreditoren_faelligkeits_check(mandant_ids: list[UUID] | None = None) -> dict:
    """Taeglicher Lauf: erinnert die fuer 'abrechnung' verantwortlichen
    Mitarbeitenden intern (keine externe E-Mail -- anders als Mahnwesen
    betrifft das nur die eigene Kreditorenbuchhaltung), wenn eine offene
    Eingangsrechnung bald faellig wird oder eine Skonto-Frist bald verfaellt.
    Dedupliziert ueber die bereits fuer Pruefzyklen/Inventurzyklen genutzte
    "ungelesene Notification mit gleicher ref_entity" Pruefung, damit nicht
    jeden Tag erneut benachrichtigt wird."""
    settings = get_settings()
    heute = date.today()
    faelligkeit_erinnerungen = 0
    skonto_erinnerungen = 0

    async with system_session() as session:
        stmt = select(Eingangsrechnung).where(Eingangsrechnung.status == "offen")
        if mandant_ids is not None:
            stmt = stmt.where(Eingangsrechnung.mandant_id.in_(mandant_ids))
        offene = (await session.execute(stmt)).scalars().all()

        verantwortliche_cache: dict[UUID, list[User]] = {}

        for eingangsrechnung in offene:
            if eingangsrechnung.mandant_id not in verantwortliche_cache:
                verantwortliche_cache[eingangsrechnung.mandant_id] = await _verantwortliche(
                    session, eingangsrechnung.mandant_id
                )
            verantwortliche = verantwortliche_cache[eingangsrechnung.mandant_id]
            if not verantwortliche:
                continue

            if eingangsrechnung.faellig_am is not None:
                tage_bis_faellig = (eingangsrechnung.faellig_am - heute).days
                if tage_bis_faellig <= settings.kreditoren_faelligkeit_erinnerung_tage:
                    hinweis = (
                        f"überfällig seit {-tage_bis_faellig} Tag(en)"
                        if tage_bis_faellig < 0
                        else f"fällig in {tage_bis_faellig} Tag(en)"
                    )
                    titel = (
                        f"Eingangsrechnung {eingangsrechnung.rechnungsnummer_lieferant} "
                        f"({eingangsrechnung.lieferant_name}): {hinweis}"
                    )
                    for user in verantwortliche:
                        if await _hat_offene_notification(
                            session,
                            user_id=user.id,
                            ref_entity_type="eingangsrechnung_faellig",
                            ref_entity_id=eingangsrechnung.id,
                        ):
                            continue
                        session.add(
                            Notification(
                                mandant_id=eingangsrechnung.mandant_id,
                                user_id=user.id,
                                typ="frist",
                                titel=titel,
                                ref_entity_type="eingangsrechnung_faellig",
                                ref_entity_id=eingangsrechnung.id,
                            )
                        )
                        faelligkeit_erinnerungen += 1

            if eingangsrechnung.skonto_prozent is not None and eingangsrechnung.skonto_tage is not None:
                positionen = await positionen_fuer(session, eingangsrechnung.id)
                zahlungen = await zahlungen_fuer(session, eingangsrechnung.id)
                brutto = brutto_betrag(eingangsrechnung, positionen)
                noch_offen = brutto - bezahlter_betrag(zahlungen)
                skonto_frist = eingangsrechnung.rechnungsdatum + timedelta(days=eingangsrechnung.skonto_tage)
                tage_bis_skonto = (skonto_frist - heute).days
                if noch_offen > 0 and 0 <= tage_bis_skonto <= settings.kreditoren_skonto_erinnerung_tage:
                    ersparnis = (noch_offen * eingangsrechnung.skonto_prozent / Decimal("100")).quantize(
                        Decimal("0.01")
                    )
                    titel = (
                        f"Eingangsrechnung {eingangsrechnung.rechnungsnummer_lieferant} "
                        f"({eingangsrechnung.lieferant_name}): Skonto verfällt in {tage_bis_skonto} Tag(en) "
                        f"(Ersparnis {ersparnis} EUR)"
                    )
                    for user in verantwortliche:
                        if await _hat_offene_notification(
                            session,
                            user_id=user.id,
                            ref_entity_type="eingangsrechnung_skonto",
                            ref_entity_id=eingangsrechnung.id,
                        ):
                            continue
                        session.add(
                            Notification(
                                mandant_id=eingangsrechnung.mandant_id,
                                user_id=user.id,
                                typ="frist",
                                titel=titel,
                                ref_entity_type="eingangsrechnung_skonto",
                                ref_entity_id=eingangsrechnung.id,
                            )
                        )
                        skonto_erinnerungen += 1

        ergebnis = {
            "faelligkeit_erinnerungen": faelligkeit_erinnerungen,
            "skonto_erinnerungen": skonto_erinnerungen,
        }
        session.add(
            AuditLog(
                mandant_id=None,
                actor_user_id=None,
                aktion=KREDITOREN_AKTION,
                entity_type="scheduler",
                payload=ergebnis,
            )
        )
        await session.flush()

    return ergebnis
