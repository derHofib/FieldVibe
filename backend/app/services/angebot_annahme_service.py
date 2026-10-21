"""Annahmenachweis und Widerruf eines Angebots im Kundenportal.

Der Nachweis (Tabelle angebot_annahmen) entsteht bei jeder Portal-Entscheidung,
auch fuer Geschaeftskunden. Der Widerruf (§ 356a BGB) und die Bestaetigungs-
mails gelten nur im B2C-Ablauf (siehe verbraucherschutz_service)."""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.zeit import in_lokal
from app.models.angebot import Angebot
from app.models.angebot_annahme import AngebotAnnahme
from app.models.kunde import Kunde
from app.models.kundenportal import KundenportalZugang
from app.models.mandant import Mandant
from app.models.mangel import Mangel
from app.models.notification import Notification
from app.models.rechnung import Rechnung
from app.models.user import User
from app.models.vorgang_event import VorgangEvent
from app.services import verbraucherschutz_service as vs
from app.services.audit_service import log_action
from app.services.angebot_service import positionen_fuer, summen
from app.services.mail_outbox_service import enqueue_email_and_log
from app.services.event_bus import event_bus
from app.services.zuweisung_service import dispo_verantwortliche_user_ids

logger = logging.getLogger(__name__)

USER_AGENT_MAX = 300


def _euro(betrag: Decimal) -> str:
    return f"{betrag:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".") + " €"


def _zeit(zeitpunkt: datetime) -> str:
    return in_lokal(zeitpunkt).strftime("%d.%m.%Y %H:%M")


def nachweis_referenz(nachweis: AngebotAnnahme) -> str:
    return str(nachweis.id)


async def protokolliere(
    session: AsyncSession,
    *,
    angebot: Angebot,
    aktion: str,
    zugang: KundenportalZugang,
    ip: str,
    user_agent: str | None,
    fassung_sha256: str,
    zeitpunkt: datetime,
    b2c: bool,
    belehrung: vs.Belehrung | None = None,
) -> AngebotAnnahme:
    nachweis = AngebotAnnahme(
        mandant_id=angebot.mandant_id,
        angebot_id=angebot.id,
        aktion=aktion,
        kunden_portal_zugang_id=zugang.id,
        zugang_email=zugang.email,
        zugang_name=zugang.name,
        ip=ip,
        user_agent=(user_agent or "")[:USER_AGENT_MAX],
        fassung_sha256=fassung_sha256,
        b2c_flag=b2c,
        belehrung_version=belehrung.version if belehrung else None,
        belehrung_text=belehrung.text if belehrung else None,
        created_at=zeitpunkt,
    )
    session.add(nachweis)
    await session.flush()
    # Nur die Verknuepfung zum Nachweis, nicht dessen Inhalt (E-Mail, IP, User-Agent):
    # die Beweisdaten bleiben in angebot_annahmen, das Protokoll haelt Zeitpunkt und Hash.
    await log_action(
        session,
        aktion=f"angebot_{aktion}",
        mandant_id=angebot.mandant_id,
        akteur_typ="portal",
        entity_type="angebot",
        entity_id=angebot.id,
        payload={
            "angebotsnummer": angebot.angebotsnummer,
            "annahme_id": str(nachweis.id),
            "kunden_portal_zugang_id": str(zugang.id),
            "fassung_sha256": fassung_sha256,
            "b2c": b2c,
        },
    )
    return nachweis


async def letzte_annahme(session: AsyncSession, angebot_id: UUID) -> AngebotAnnahme | None:
    return (
        await session.execute(
            select(AngebotAnnahme)
            .where(AngebotAnnahme.angebot_id == angebot_id, AngebotAnnahme.aktion == "annahme")
            .order_by(AngebotAnnahme.created_at.desc(), AngebotAnnahme.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _maengel(session: AsyncSession, angebot: Angebot) -> list[Mangel]:
    return list((await session.execute(select(Mangel).where(Mangel.angebot_id == angebot.id))).scalars().all())


async def _angebot_vorgang_ids(session: AsyncSession, angebot: Angebot) -> set[UUID]:
    maengel = await _maengel(session, angebot)
    ids = {angebot.vorgang_id, angebot.auftrag_vorgang_id}
    for m in maengel:
        ids |= {m.vorgang_id, m.reparatur_vorgang_id}
    return {i for i in ids if i is not None}


async def _hat_versendete_rechnung(session: AsyncSession, angebot: Angebot) -> bool:
    # Auch Rechnungen, die erst nach der Annahme direkt am entstandenen Auftrag
    # (statt ueber das Angebot) erzeugt wurden: sie haengen nicht an angebot_id,
    # betreffen aber dieselbe Leistung. Lieber zu vorsichtig sperren als einen
    # Widerruf nach erfolgter Abrechnung zulassen.
    vorgang_ids = {angebot.auftrag_vorgang_id} | {m.reparatur_vorgang_id for m in await _maengel(session, angebot)}
    vorgang_ids.discard(None)
    bedingung = Rechnung.angebot_id == angebot.id
    if vorgang_ids:
        bedingung = or_(bedingung, Rechnung.vorgang_id.in_(vorgang_ids))
    gefunden = await session.execute(
        select(Rechnung.id)
        .where(bedingung, Rechnung.status != "entwurf", Rechnung.geloescht_am.is_(None))
        .limit(1)
    )
    return gefunden.first() is not None


async def widerruf_pruefung(
    session: AsyncSession, angebot: Angebot, jetzt: datetime
) -> tuple[str | None, datetime | None]:
    """(Hinderungsgrund, Fristende). Ohne Grund ist der Widerruf zulaessig.
    Das Fristende ist nur gesetzt, wenn es ein B2C-Annahme-Nachweis gibt."""
    if angebot.status == "widerrufen":
        return "Dieses Angebot wurde bereits widerrufen.", None
    if angebot.status != "angenommen" or angebot.angenommen_am is None:
        return "Nur ein angenommenes Angebot kann widerrufen werden.", None
    annahme = await letzte_annahme(session, angebot.id)
    if annahme is None or not annahme.b2c_flag:
        return "Für dieses Angebot besteht über das Portal kein Widerrufsrecht.", None
    ende = vs.widerrufsfrist_ende(angebot.angenommen_am)
    if jetzt >= ende:
        return (
            f"Die Widerrufsfrist ist am {in_lokal(ende).strftime('%d.%m.%Y')} abgelaufen "
            "(14 Tage nach der Beauftragung).",
            ende,
        )
    if await _hat_versendete_rechnung(session, angebot):
        return (
            "Zu diesem Auftrag wurde bereits eine Rechnung versendet. Bitte kontaktieren Sie den Betrieb direkt.",
            ende,
        )
    return None, ende


async def widerrufe(session: AsyncSession, angebot: Angebot, *, mandant_id: UUID) -> datetime:
    """Setzt Status 'widerrufen'. Wirft 409 mit Klartext, wenn der Widerruf
    nicht (mehr) zulaessig ist. Gibt den Widerrufszeitpunkt zurueck."""
    # Gleiche Sperre wie apply_status_transition: Widerruf und eine gleichzeitige
    # Rechnungsstellung/Annahme duerfen sich nicht ueberholen.
    await session.flush()
    await session.execute(
        select(Angebot).where(Angebot.id == angebot.id).with_for_update().execution_options(populate_existing=True)
    )
    jetzt = datetime.now(timezone.utc)
    grund, _ = await widerruf_pruefung(session, angebot, jetzt)
    if grund is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=grund)

    angebot.status = "widerrufen"
    angebot.widerrufen_am = jetzt
    for vorgang_id in await _angebot_vorgang_ids(session, angebot):
        session.add(
            VorgangEvent(
                mandant_id=mandant_id,
                vorgang_id=vorgang_id,
                event_type="angebot",
                author_user_id=None,
                body=(
                    f"Angebot {angebot.angebotsnummer}: vom Kunden widerrufen (Widerrufsbutton, "
                    "bitte Auftrag prüfen)"
                ),
                payload={"angebot_id": str(angebot.id), "status": "widerrufen"},
            )
        )
    await session.flush()
    return jetzt


def _anrede(zugang: KundenportalZugang) -> str:
    return f"Guten Tag {zugang.name},"


def baue_annahme_mail(
    *,
    mandant: Mandant,
    angebot: Angebot,
    zugang: KundenportalZugang,
    brutto: Decimal,
    nachweis: AngebotAnnahme,
    belehrung: vs.Belehrung,
) -> tuple[str, str]:
    betreff = f"Bestätigung Ihrer Beauftragung – Angebot {angebot.angebotsnummer}"
    text = (
        f"{_anrede(zugang)}\n\n"
        f"vielen Dank für Ihren Auftrag. Wir bestätigen, dass Sie das Angebot {angebot.angebotsnummer} "
        f"von {mandant.name} am {_zeit(nachweis.created_at)} Uhr verbindlich und zahlungspflichtig "
        f"beauftragt haben.\n\n"
        f"Gesamtpreis (brutto): {_euro(brutto)}\n"
        f"Referenz Ihrer Beauftragung: {nachweis_referenz(nachweis)}\n\n"
        "Das Angebot erhalten Sie als PDF im Anhang.\n\n"
        f"Widerrufsbelehrung (Stand {belehrung.version})\n"
        f"{'-' * 40}\n{belehrung.text}\n\n"
        f"{vs.muster_widerrufsformular(mandant)}\n\n"
        f"Ihren Widerruf können Sie bis zum Ablauf der Widerrufsfrist auch direkt im Kundenportal über "
        f"den Button „Vertrag widerrufen“ erklären.\n\n"
        f"Freundliche Grüße\n{mandant.name}"
    )
    return betreff, text


def baue_widerruf_mail(
    *, mandant: Mandant, angebot: Angebot, zugang: KundenportalZugang, nachweis: AngebotAnnahme
) -> tuple[str, str]:
    betreff = f"Eingangsbestätigung Ihres Widerrufs – Angebot {angebot.angebotsnummer}"
    text = (
        f"{_anrede(zugang)}\n\n"
        f"wir bestätigen den Eingang Ihres Widerrufs zum Angebot {angebot.angebotsnummer} "
        f"am {_zeit(nachweis.created_at)} Uhr.\n\n"
        f"Referenz Ihres Widerrufs: {nachweis_referenz(nachweis)}\n\n"
        "Wir melden uns bei Ihnen, falls zur Abwicklung noch Rückfragen bestehen.\n\n"
        f"Freundliche Grüße\n{mandant.name}"
    )
    return betreff, text


async def sende_kundenmail(
    session: AsyncSession,
    *,
    angebot: Angebot,
    zugang: KundenportalZugang,
    betreff: str,
    text: str,
    anhang: tuple[str, bytes, str] | None = None,
) -> bool:
    """Mail an den Portal-Zugang, ueber die Outbox: die Portal-Aktion haengt weder an der
    Erreichbarkeit des Mailservers noch wird sie durch einen Mailfehler rueckgaengig gemacht;
    der Worker sendet nach dem Commit und wiederholt bei Fehlern (Status im E-Mail-Verlauf des
    Angebots). Rueckgabe: ob die Mail eingereiht wurde. Der Savepoint haelt die
    Request-Transaktion am Leben, falls das Einreihen selbst scheitert."""
    try:
        async with session.begin_nested():
            await enqueue_email_and_log(
                session,
                angebot.mandant_id,
                entity_type="angebot",
                entity_id=angebot.id,
                to=zugang.email,
                subject=betreff,
                body=text,
                gesendet_von=None,
                attachment=anhang,
            )
        return True
    except Exception:
        logger.exception("Portal-Mail zu Angebot %s konnte nicht eingereiht werden (%s)", angebot.angebotsnummer, betreff)
        return False


async def benachrichtige_mandant_widerruf(
    session: AsyncSession, *, mandant: Mandant, angebot: Angebot, kunde: Kunde, nachweis: AngebotAnnahme
) -> None:
    """In-App-Benachrichtigung an Ersteller und Dispo-Verantwortliche, dazu eine
    Mail an Ersteller und Firmen-Adresse. Fehler werden geloggt, nie hochgereicht."""
    try:
        async with session.begin_nested():
            empfaenger_ids = set(await dispo_verantwortliche_user_ids(session, mandant.id))
            empfaenger_ids.add(angebot.erstellt_von)
            titel = (
                f"Angebot {angebot.angebotsnummer} wurde von {kunde.name} widerrufen "
                f"(Widerrufsbutton, {_zeit(nachweis.created_at)} Uhr)"
            )
            for user_id in empfaenger_ids:
                session.add(
                    Notification(
                        mandant_id=mandant.id,
                        user_id=user_id,
                        typ="angebot",
                        titel=titel,
                        ref_entity_type="angebot",
                        ref_entity_id=angebot.id,
                    )
                )
            await session.flush()
        await event_bus.publish(
            mandant.id, "notification", {"typ": "angebot", "angebot_id": str(angebot.id)}
        )
    except Exception:
        logger.exception("Widerruf-Benachrichtigung zu Angebot %s fehlgeschlagen", angebot.angebotsnummer)

    adressen: list[str] = []
    ersteller = await session.get(User, angebot.erstellt_von)
    firmen_mail = (mandant.firmendaten or {}).get("email")
    for adresse in (ersteller.email if ersteller else None, firmen_mail):
        if isinstance(adresse, str) and adresse.strip() and adresse.strip().lower() not in {a.lower() for a in adressen}:
            adressen.append(adresse.strip())
    positionen = await positionen_fuer(session, angebot.id)
    brutto = summen(positionen, angebot.mwst_satz)[1]
    for adresse in adressen:
        try:
            async with session.begin_nested():
                await enqueue_email_and_log(
                    session,
                    mandant.id,
                    entity_type="angebot",
                    entity_id=angebot.id,
                    to=adresse,
                    subject=f"Widerruf: Angebot {angebot.angebotsnummer} ({kunde.name})",
                    body=(
                        f"{kunde.name} hat das Angebot {angebot.angebotsnummer} "
                        f"(Gesamtpreis brutto {_euro(brutto)}) am {_zeit(nachweis.created_at)} Uhr über den "
                        "Widerrufsbutton im Kundenportal widerrufen.\n\n"
                        "Bereits angelegte Aufträge werden nicht automatisch storniert – bitte prüfen. "
                        f"Nachweis-Referenz: {nachweis_referenz(nachweis)}"
                    ),
                    gesendet_von=None,
                )
        except Exception:
            logger.exception("Widerruf-Mail an %s konnte nicht eingereiht werden", adresse)
