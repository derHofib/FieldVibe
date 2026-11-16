"""Mandantenuebergreifende Lookups des Workers, gebuendelt an einer Stelle.

Nur hier (und in job_runner/health_service fuer die systemweiten job_laeufe-Zeilen)
umgeht der Worker die RLS: er holt schmale Rueckgabewerte (IDs, Tupel) -- die
eigentliche Arbeit laeuft danach je Mandant in tenant_session.
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import system_session, tenant_session
from app.models.audit_log import AuditLog
from app.models.fehlerbericht import Fehlerbericht
from app.models.import_lauf import ImportLauf
from app.models.integration import MandantIntegration
from app.models.mail_account import MailAccount
from app.models.mail_outbox import MailOutbox
from app.models.mandant import Mandant
from app.models.mandant_export import MandantExport
from app.models.plattform_integration import PlattformIntegration
from app.models.s3_loeschauftrag import S3Loeschauftrag


async def aktive_mandanten_ids() -> list[UUID]:
    async with system_session(grund="worker: aktive mandanten", drosselung_s=300) as session:
        return list((await session.execute(select(Mandant.id).where(Mandant.status == "aktiv"))).scalars().all())


async def aktive_mandanten_mit_stunde() -> list[tuple[UUID, int | None]]:
    async with system_session(grund="worker: aktive mandanten mit scheduler-stunde", drosselung_s=300) as session:
        zeilen = (await session.execute(
            select(Mandant.id, Mandant.scheduler_stunde_utc).where(Mandant.status == "aktiv")
        )).all()
    return [(m, stunde) for m, stunde in zeilen]


async def letzter_scheduler_lauf(aktion: str) -> datetime | None:
    # Die Scheduler-Eintraege liegen je Mandant im audit_log; /healthz fragt plattformweit.
    async with system_session(grund="scheduler: letzter lauf lesen", drosselung_s=300) as session:
        return (await session.execute(
            select(AuditLog.created_at).where(AuditLog.aktion == aktion).order_by(AuditLog.created_at.desc()).limit(1)
        )).scalar_one_or_none()


async def plattform_smtp() -> tuple[dict, str | None] | None:
    """(config, secret_ref) der aktiven plattformweiten smtp-Integration. Eigener Zugriff,
    weil die App-Rolle plattform_integrationen nicht mehr lesen darf."""
    async with system_session(grund="mail: plattform-smtp lesen", drosselung_s=300) as session:
        plattform = (await session.execute(
            select(PlattformIntegration).where(PlattformIntegration.typ == "smtp", PlattformIntegration.aktiv.is_(True))
        )).scalar_one_or_none()
        if plattform is None:
            return None
        return dict(plattform.config), plattform.secret_ref


async def heartbeat_schreiben(job: str, jetzt: datetime | None = None) -> None:
    # Lazy: job_state_service.heartbeat delegiert hierher, der Import-Zyklus waere sonst offen.
    from app.services.job_state_service import markiere_lauf

    async with system_session(grund="worker: job-state heartbeat", drosselung_s=300) as session:
        await markiere_lauf(session, job, None, erfolg=True, jetzt=jetzt)


async def mandanten_mit_imap(mandant_ids: list[UUID] | None = None) -> list[UUID]:
    async with system_session(grund="worker: email-ingest postfaecher", drosselung_s=300) as session:
        stmt = select(MandantIntegration.mandant_id).where(
            MandantIntegration.typ == "imap", MandantIntegration.aktiv.is_(True)
        ).distinct()
        if mandant_ids is not None:
            stmt = stmt.where(MandantIntegration.mandant_id.in_(mandant_ids))
        return list((await session.execute(stmt)).scalars().all())


async def aktive_postfaecher(account_ids: list | None = None) -> list[tuple[UUID, UUID]]:
    """(account_id, mandant_id) aller aktiven Postfaecher."""
    async with system_session(grund="worker: mail-sync postfaecher", drosselung_s=300) as session:
        stmt = select(MailAccount.id, MailAccount.mandant_id).where(MailAccount.aktiv.is_(True))
        if account_ids is not None:
            stmt = stmt.where(MailAccount.id.in_(account_ids))
        return [(a, m) for a, m in (await session.execute(stmt)).all()]


async def outbox_faellige_mandanten(jetzt: datetime) -> list[UUID | None]:
    """Mandanten (None = Plattform-Mails ohne Mandant) mit faelligen Outbox-Eintraegen, aelteste zuerst."""
    async with system_session(grund="worker: mail-outbox faellige", drosselung_s=300) as session:
        zeilen = (await session.execute(
            select(MailOutbox.mandant_id)
            .where(MailOutbox.status == "pending", MailOutbox.naechster_versuch_am <= jetzt)
            .group_by(MailOutbox.mandant_id)
            .order_by(func.min(MailOutbox.naechster_versuch_am))
        )).all()
    return [m for (m,) in zeilen]


async def outbox_haengende_mandanten(grenze: datetime) -> list[UUID | None]:
    async with system_session(grund="worker: mail-outbox haengende bereinigen", drosselung_s=300) as session:
        zeilen = (await session.execute(
            select(MailOutbox.mandant_id)
            .where(MailOutbox.status == "sending", MailOutbox.sending_seit < grenze)
            .group_by(MailOutbox.mandant_id)
        )).all()
    return [m for (m,) in zeilen]


@asynccontextmanager
async def outbox_session(mandant_id: UUID | None) -> AsyncIterator[AsyncSession]:
    """Mandanten-Session; nur Plattform-Mails ohne Mandant (mandant_id NULL) sind unter RLS
    unsichtbar und brauchen die System-Session."""
    if mandant_id is not None:
        async with tenant_session(mandant_id=mandant_id, is_super_admin=False) as session:
            yield session
    else:
        async with system_session(grund="worker: mail-outbox ohne mandant", drosselung_s=300) as session:
            yield session


async def export_haengende(grenze: datetime) -> list[tuple[UUID, UUID]]:
    """(export_id, mandant_id) laufender Exporte, die vor `grenze` gestartet wurden."""
    async with system_session(grund="worker: export-job haengende", drosselung_s=300) as session:
        zeilen = (await session.execute(
            select(MandantExport.id, MandantExport.mandant_id).where(
                MandantExport.status == "laeuft", MandantExport.gestartet_am < grenze
            )
        )).all()
    return [(i, m) for i, m in zeilen]


async def export_wartende_mandanten() -> list[UUID]:
    async with system_session(grund="worker: export-job beanspruchen", drosselung_s=300) as session:
        zeilen = (await session.execute(
            select(MandantExport.mandant_id)
            .where(MandantExport.status == "wartend")
            .group_by(MandantExport.mandant_id)
            .order_by(func.min(MandantExport.angefordert_am))
        )).all()
    return [m for (m,) in zeilen]


async def export_abgelaufene_mandanten(jetzt: datetime) -> list[UUID]:
    async with system_session(grund="worker: export-jobs aufraeumen", drosselung_s=300) as session:
        return list((await session.execute(
            select(MandantExport.mandant_id)
            .where(MandantExport.status == "fertig", MandantExport.laeuft_ab_am < jetzt)
            .distinct()
        )).scalars().all())


async def s3_mandanten_mit_offenen_auftraegen(jetzt: datetime) -> list[UUID]:
    async with system_session(grund="worker: s3-loeschauftraege", drosselung_s=300) as session:
        zeilen = (await session.execute(
            select(S3Loeschauftrag.mandant_id)
            .where(S3Loeschauftrag.status == "offen", S3Loeschauftrag.naechster_versuch_am <= jetzt)
            .group_by(S3Loeschauftrag.mandant_id)
            .order_by(func.min(S3Loeschauftrag.erstellt_am))
        )).all()
    return [m for (m,) in zeilen]


async def mandanten_mit_abgelaufenen_fehlerberichten(grenze: datetime) -> list[UUID]:
    async with system_session(grund="worker: fehlerberichte aufbewahrung", drosselung_s=300) as session:
        return list((await session.execute(
            select(Fehlerbericht.mandant_id).where(Fehlerbericht.created_at < grenze).distinct()
        )).scalars().all())


async def mandanten_mit_import_altlasten(quelle_grenze: datetime, bericht_grenze: datetime) -> list[UUID]:
    """Mandanten mit Importlaeufen, deren Quelldatei bzw. Fehlerbericht aufzuraeumen ist."""
    async with system_session(grund="worker: datenimport aufraeumen") as session:
        return list((await session.execute(
            select(ImportLauf.mandant_id).where(
                (ImportLauf.object_key.is_not(None) & (ImportLauf.created_at < quelle_grenze))
                | (
                    ImportLauf.fehlerbericht_key.is_not(None)
                    & (ImportLauf.updated_at < bericht_grenze)
                    & ImportLauf.status.in_(("abgeschlossen", "rueckgaengig", "abgelaufen", "abgebrochen"))
                )
            ).distinct()
        )).scalars().all())
