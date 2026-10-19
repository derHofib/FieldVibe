from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.zeit import in_lokal
from app.models.angebot import Angebot, AngebotPosition
from app.models.mandant import Mandant
from app.models.mangel import Mangel
from app.models.rechnung import Rechnung
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.angebot import AngebotAbschlagRead, AngebotPositionRead, AngebotRead
from app.services import rechnung_service
from app.services.event_bus import event_bus
from app.services.numbering_service import next_vorgangsnummer
from app.services.steuer_service import ist_kleinunternehmer, runde_cent

STANDARD_MWST_SATZ = Decimal("19.00")
GUELTIGE_UEBERGAENGE = {"entwurf": {"versendet"}, "versendet": {"angenommen", "abgelehnt"}}


async def positionen_fuer(session: AsyncSession, angebot_id: UUID) -> list[AngebotPosition]:
    result = await session.execute(
        select(AngebotPosition).where(AngebotPosition.angebot_id == angebot_id).order_by(AngebotPosition.position)
    )
    return list(result.scalars().all())


def summen(positionen: list[AngebotPosition], mwst_satz: Decimal) -> tuple[Decimal, Decimal]:
    # Wie bei Rechnungen: Netto auf Cent runden, Steuer aus dem gerundeten
    # Netto -- sonst weicht das Angebot vom spaeteren Beleg um einen Cent ab.
    netto = runde_cent(sum((p.menge * p.einzelpreis for p in positionen), Decimal("0")))
    return netto, netto + runde_cent(netto * mwst_satz / Decimal("100"))


def effektiver_mwst_satz(mandant: Mandant, gewuenscht: Decimal | None) -> Decimal:
    """Kleinunternehmer (§ 19 UStG) weisen keine Umsatzsteuer aus -- der Satz
    wird serverseitig auf 0 gezwungen, egal was der Client sendet."""
    if ist_kleinunternehmer(mandant):
        return Decimal("0.00")
    return gewuenscht if gewuenscht is not None else STANDARD_MWST_SATZ


def ist_abgelaufen(angebot: Angebot, heute: date | None = None) -> bool:
    """Nur ein versendetes Angebot laeuft ab; gueltig_bis gilt einschliesslich.
    Der Tag ist der lokale Betriebstag, nicht der UTC-Tag -- sonst kippt die
    Gueltigkeit nachts um 1-2 Stunden zu frueh/spaet."""
    if angebot.status != "versendet" or angebot.gueltig_bis is None:
        return False
    if heute is None:
        heute = in_lokal(datetime.now(timezone.utc)).date()
    return angebot.gueltig_bis < heute


async def positionen_neu_nummerieren(session: AsyncSession, angebot_id: UUID) -> None:
    for nummer, position in enumerate(await positionen_fuer(session, angebot_id), start=1):
        if position.position != nummer:
            position.position = nummer
    await session.flush()


async def to_read_model(session: AsyncSession, angebot: Angebot) -> AngebotRead:
    positionen = await positionen_fuer(session, angebot.id)
    netto, brutto = summen(positionen, angebot.mwst_satz)
    abschlaege, schlussrechnung_id, rechnung_id = await _abrechnung_fuer(session, angebot)
    abgerechnet = sum((a.netto for a in abschlaege), Decimal("0")).quantize(Decimal("0.01"))
    return AngebotRead(
        **{
            k: getattr(angebot, k)
            for k in AngebotRead.model_fields
            if k
            not in (
                "positionen",
                "gesamt_netto",
                "gesamt_brutto",
                "ist_abgelaufen",
                "abschlaege",
                "abgerechnet_netto",
                "rest_netto",
                "schlussrechnung_id",
                "rechnung_id",
            )
        },
        positionen=[AngebotPositionRead.model_validate(p) for p in positionen],
        gesamt_netto=netto,
        gesamt_brutto=brutto,
        ist_abgelaufen=ist_abgelaufen(angebot),
        abschlaege=abschlaege,
        abgerechnet_netto=abgerechnet,
        rest_netto=netto - abgerechnet,
        schlussrechnung_id=schlussrechnung_id,
        rechnung_id=rechnung_id,
    )


async def _abrechnung_fuer(
    session: AsyncSession, angebot: Angebot
) -> tuple[list[AngebotAbschlagRead], UUID | None, UUID | None]:
    """Abschlaege sowie Schluss- und Vollrechnung des Angebots."""
    belege = (
        (
            await session.execute(
                select(Rechnung)
                .where(
                    Rechnung.angebot_id == angebot.id,
                    Rechnung.rechnungsart.in_(("rechnung", "abschlag", "schluss")),
                    Rechnung.status != "storniert",
                    Rechnung.geloescht_am.is_(None),
                    Rechnung.ist_storno.is_(False),
                )
                .order_by(Rechnung.created_at, Rechnung.id)
            )
        )
        .scalars()
        .all()
    )
    positionen_je = await rechnung_service.positionen_fuer_mehrere(session, [b.id for b in belege])
    abschlaege = [
        AngebotAbschlagRead(
            rechnung_id=b.id,
            rechnungsnummer=b.rechnungsnummer,
            status=b.status,
            netto=rechnung_service.netto_betrag(b, positionen_je[b.id]),
        )
        for b in belege
        if b.rechnungsart == "abschlag"
    ]
    schluss = next((b.id for b in belege if b.rechnungsart == "schluss"), None)
    voll = next((b.id for b in belege if b.rechnungsart == "rechnung"), None)
    return abschlaege, schluss, voll


async def _auftrag_zur_annahme(session: AsyncSession, angebot: Angebot, mandant_id: UUID) -> UUID:
    """Hat das Angebot schon einen Vorgang, ist der Auftrag dieser Vorgang (das
    Statusereignis schreibt apply_status_transition). Sonst entsteht ein neuer."""
    if angebot.vorgang_id is not None:
        bestehender = await session.get(Vorgang, angebot.vorgang_id)
        if bestehender is not None and bestehender.geloescht_am is None:
            return bestehender.id

    vorgang = Vorgang(
        mandant_id=mandant_id,
        vorgangsnummer=await next_vorgangsnummer(session, mandant_id),
        kunde_id=angebot.kunde_id,
        titel=f"Auftrag aus Angebot {angebot.angebotsnummer}",
        beschreibung="Automatisch angelegt nach Annahme des Angebots.",
        abrechnungsart="festpreis",
        # Das Angebot sagt nicht, um welche Leistung es geht; "installation" ist
        # der Regelfall eines angenommenen Handwerksangebots (der Mangel-Pfad
        # nimmt "stoerung" fuer Reparaturen).
        leistungstyp="installation",
    )
    session.add(vorgang)
    await session.flush()
    session.add(
        VorgangEvent(
            mandant_id=mandant_id,
            vorgang_id=vorgang.id,
            event_type="system",
            is_system=True,
            body=f"Angelegt aus angenommenem Angebot {angebot.angebotsnummer}",
            payload={"angebot_id": str(angebot.id)},
        )
    )
    await event_bus.publish(mandant_id, "feed_update", {"vorgang_id": str(vorgang.id), "reason": "erstellt"})
    return vorgang.id


async def apply_status_transition(
    session: AsyncSession,
    angebot: Angebot,
    neuer_status: str,
    *,
    mandant_id: UUID,
    actor_user_id: UUID | None,
) -> None:
    """Shared by the staff-facing PATCH /api/angebote/{id} and the
    Kundenportal (Kunde nimmt an/lehnt ab). `actor_user_id` is None when a
    Kunde (kein User-Account) den Uebergang ausloest -- VorgangEvent.
    author_user_id ist dafuer nullable."""
    # Sperre + frischer Stand: Kunde (Portal) und Mitarbeiter koennten dasselbe
    # Angebot gleichzeitig annehmen und sonst zwei Auftraege ausloesen.
    await session.flush()
    await session.execute(
        select(Angebot).where(Angebot.id == angebot.id).with_for_update().execution_options(populate_existing=True)
    )
    if neuer_status not in GUELTIGE_UEBERGAENGE.get(angebot.status, set()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Statuswechsel von '{angebot.status}' nach '{neuer_status}' nicht erlaubt",
        )

    maengel = list(
        (await session.execute(select(Mangel).where(Mangel.angebot_id == angebot.id))).scalars().all()
    )
    jetzt = datetime.now(timezone.utc)

    if neuer_status == "versendet":
        positionen = await positionen_fuer(session, angebot.id)
        if not positionen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Angebot ohne Positionen kann nicht versendet werden"
            )
        angebot.versendet_am = jetzt

    elif neuer_status == "angenommen":
        if ist_abgelaufen(angebot):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Das Angebot ist abgelaufen")
        angebot.angenommen_am = jetzt
        if not maengel:
            angebot.auftrag_vorgang_id = await _auftrag_zur_annahme(session, angebot, mandant_id)
        else:
            vorgangsnummer = await next_vorgangsnummer(session, mandant_id)
            repair_anlage_id = next((m.anlage_id for m in maengel if m.anlage_id), None)
            reparatur_vorgang = Vorgang(
                mandant_id=mandant_id,
                vorgangsnummer=vorgangsnummer,
                kunde_id=angebot.kunde_id,
                anlage_id=repair_anlage_id,
                titel=f"Reparatur aus Angebot {angebot.angebotsnummer}",
                beschreibung="Automatisch angelegt nach Annahme des Angebots.",
                abrechnungsart="festpreis",
                leistungstyp="stoerung",
            )
            session.add(reparatur_vorgang)
            await session.flush()

            session.add(
                VorgangEvent(
                    mandant_id=mandant_id,
                    vorgang_id=reparatur_vorgang.id,
                    event_type="system",
                    is_system=True,
                    body=f"Angelegt aus angenommenem Angebot {angebot.angebotsnummer}",
                    payload={"angebot_id": str(angebot.id)},
                )
            )
            for mangel in maengel:
                mangel.status = "in_bearbeitung"
                mangel.reparatur_vorgang_id = reparatur_vorgang.id

            await event_bus.publish(
                mandant_id, "feed_update", {"vorgang_id": str(reparatur_vorgang.id), "reason": "erstellt"}
            )

    elif neuer_status == "abgelehnt":
        angebot.abgelehnt_am = jetzt
        for mangel in maengel:
            mangel.status = "offen"
            mangel.angebot_id = None

    angebot.status = neuer_status
    betroffene_vorgang_ids = {angebot.vorgang_id} if angebot.vorgang_id else set()
    betroffene_vorgang_ids |= {m.vorgang_id for m in maengel}
    for vid in betroffene_vorgang_ids:
        if vid is None:
            continue
        session.add(
            VorgangEvent(
                mandant_id=mandant_id,
                vorgang_id=vid,
                event_type="angebot",
                author_user_id=actor_user_id,
                body=f"Angebot {angebot.angebotsnummer}: Status '{neuer_status}'",
                payload={"angebot_id": str(angebot.id), "status": neuer_status},
            )
        )
