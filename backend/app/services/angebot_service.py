from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.angebot import Angebot, AngebotPosition
from app.models.mangel import Mangel
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.angebot import AngebotPositionRead, AngebotRead
from app.services.event_bus import event_bus
from app.services.numbering_service import next_vorgangsnummer

_CENT = Decimal("0.01")
GUELTIGE_UEBERGAENGE = {"entwurf": {"versendet"}, "versendet": {"angenommen", "abgelehnt"}}


async def positionen_fuer(session: AsyncSession, angebot_id: UUID) -> list[AngebotPosition]:
    result = await session.execute(
        select(AngebotPosition).where(AngebotPosition.angebot_id == angebot_id).order_by(AngebotPosition.position)
    )
    return list(result.scalars().all())


def summen(positionen: list[AngebotPosition], mwst_satz: Decimal) -> tuple[Decimal, Decimal]:
    netto = sum((p.menge * p.einzelpreis for p in positionen), Decimal("0"))
    brutto = netto + netto * mwst_satz / Decimal("100")
    return netto.quantize(_CENT), brutto.quantize(_CENT)


async def to_read_model(session: AsyncSession, angebot: Angebot) -> AngebotRead:
    positionen = await positionen_fuer(session, angebot.id)
    netto, brutto = summen(positionen, angebot.mwst_satz)
    return AngebotRead(
        **{
            k: getattr(angebot, k)
            for k in AngebotRead.model_fields
            if k not in ("positionen", "gesamt_netto", "gesamt_brutto")
        },
        positionen=[AngebotPositionRead.model_validate(p) for p in positionen],
        gesamt_netto=netto,
        gesamt_brutto=brutto,
    )


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
        angebot.angenommen_am = jetzt
        if maengel:
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
