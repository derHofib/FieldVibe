from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.angebot import Angebot, AngebotPosition
from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.mangel import Mangel
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.angebot import (
    AngebotAusMaengelnCreate,
    AngebotCreate,
    AngebotPositionCreate,
    AngebotPositionRead,
    AngebotRead,
    AngebotUpdate,
)
from app.services.event_bus import event_bus
from app.services.numbering_service import next_angebotsnummer, next_vorgangsnummer
from app.services.pdf_service import generate_angebot_pdf

router = APIRouter(
    prefix="/api/angebote",
    tags=["angebote"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)


async def _positionen_fuer(session: AsyncSession, angebot_id: UUID) -> list[AngebotPosition]:
    result = await session.execute(
        select(AngebotPosition).where(AngebotPosition.angebot_id == angebot_id).order_by(AngebotPosition.position)
    )
    return list(result.scalars().all())


_CENT = Decimal("0.01")


def _summen(positionen: list[AngebotPosition], mwst_satz: Decimal) -> tuple[Decimal, Decimal]:
    netto = sum((p.menge * p.einzelpreis for p in positionen), Decimal("0"))
    brutto = netto + netto * mwst_satz / Decimal("100")
    return netto.quantize(_CENT), brutto.quantize(_CENT)


async def _to_read_model(session: AsyncSession, angebot: Angebot) -> AngebotRead:
    positionen = await _positionen_fuer(session, angebot.id)
    netto, brutto = _summen(positionen, angebot.mwst_satz)
    return AngebotRead(
        **{k: getattr(angebot, k) for k in AngebotRead.model_fields if k not in ("positionen", "gesamt_netto", "gesamt_brutto")},
        positionen=[AngebotPositionRead.model_validate(p) for p in positionen],
        gesamt_netto=netto,
        gesamt_brutto=brutto,
    )


@router.get("", response_model=list[AngebotRead])
async def list_angebote(
    kunde_id: UUID | None = Query(default=None),
    vorgang_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_db),
) -> list[AngebotRead]:
    stmt = select(Angebot).order_by(Angebot.created_at.desc())
    if kunde_id:
        stmt = stmt.where(Angebot.kunde_id == kunde_id)
    if vorgang_id:
        stmt = stmt.where(Angebot.vorgang_id == vorgang_id)
    if status_filter:
        stmt = stmt.where(Angebot.status == status_filter)
    result = await session.execute(stmt)
    return [await _to_read_model(session, a) for a in result.scalars().all()]


@router.get("/{angebot_id}", response_model=AngebotRead)
async def get_angebot(angebot_id: UUID, session: AsyncSession = Depends(get_db)) -> AngebotRead:
    angebot = await session.get(Angebot, angebot_id)
    if angebot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Angebot nicht gefunden")
    return await _to_read_model(session, angebot)


async def _validate_kunde_vorgang(session: AsyncSession, kunde_id: UUID, vorgang_id: UUID | None) -> None:
    if await session.get(Kunde, kunde_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kunde nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if vorgang_id is not None:
        vorgang = await session.get(Vorgang, vorgang_id)
        if vorgang is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
        if vorgang.kunde_id != kunde_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Vorgang gehört nicht zum angegebenen Kunden"
            )


def _neue_positionen(angebot_id: UUID, mandant_id: UUID, eintraege: list[AngebotPositionCreate]) -> list[AngebotPosition]:
    return [
        AngebotPosition(
            mandant_id=mandant_id,
            angebot_id=angebot_id,
            position=i + 1,
            beschreibung=e.beschreibung,
            menge=e.menge,
            einheit=e.einheit,
            einzelpreis=e.einzelpreis,
        )
        for i, e in enumerate(eintraege)
    ]


@router.post(
    "",
    response_model=AngebotRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_angebot(
    body: AngebotCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AngebotRead:
    await _validate_kunde_vorgang(session, body.kunde_id, body.vorgang_id)

    angebotsnummer = await next_angebotsnummer(session, auth.mandant_id)
    angebot = Angebot(
        mandant_id=auth.mandant_id,
        kunde_id=body.kunde_id,
        vorgang_id=body.vorgang_id,
        angebotsnummer=angebotsnummer,
        erstellt_von=auth.user_id,
        gueltig_bis=body.gueltig_bis,
    )
    session.add(angebot)
    await session.flush()

    for p in _neue_positionen(angebot.id, auth.mandant_id, body.positionen):
        session.add(p)
    await session.flush()
    await session.refresh(angebot)
    return await _to_read_model(session, angebot)


@router.post(
    "/from-maengel",
    response_model=AngebotRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_angebot_from_maengel(
    body: AngebotAusMaengelnCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AngebotRead:
    if not body.mangel_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Keine Mängel angegeben")

    maengel: list[Mangel] = []
    for mangel_id in body.mangel_ids:
        mangel = await session.get(Mangel, mangel_id)
        if mangel is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Mangel {mangel_id} nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
        if mangel.status != "offen":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Mangel {mangel_id} ist nicht offen (Status: {mangel.status})",
            )
        maengel.append(mangel)

    vorgang_ids = {m.vorgang_id for m in maengel}
    vorgaenge = {vid: await session.get(Vorgang, vid) for vid in vorgang_ids}
    kunde_ids = {v.kunde_id for v in vorgaenge.values() if v is not None}
    if len(kunde_ids) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Alle Mängel müssen zum selben Kunden gehören",
        )
    kunde_id = next(iter(kunde_ids))
    # Ein gemeinsamer Vorgang wird uebernommen, wenn alle Maengel aus
    # demselben Vorgang stammen -- sonst bleibt vorgang_id leer und die
    # Verknuepfung laeuft ausschliesslich ueber die einzelnen Maengel.
    gemeinsamer_vorgang_id = next(iter(vorgang_ids)) if len(vorgang_ids) == 1 else None

    angebotsnummer = await next_angebotsnummer(session, auth.mandant_id)
    angebot = Angebot(
        mandant_id=auth.mandant_id,
        kunde_id=kunde_id,
        vorgang_id=gemeinsamer_vorgang_id,
        angebotsnummer=angebotsnummer,
        erstellt_von=auth.user_id,
        gueltig_bis=body.gueltig_bis,
    )
    session.add(angebot)
    await session.flush()

    # Einzelpreis startet bei 0 -- der Mangeltext beschreibt das Problem,
    # nicht dessen Marktpreis; der Disponent traegt die Kalkulation vor dem
    # Versenden nach, wie auf einem Papier-Angebot auch.
    positionen = [
        AngebotPositionCreate(beschreibung=m.beschreibung, menge=Decimal("1"), einheit="Stk", einzelpreis=Decimal("0"))
        for m in maengel
    ]
    for p in _neue_positionen(angebot.id, auth.mandant_id, positionen):
        session.add(p)

    for mangel in maengel:
        mangel.angebot_id = angebot.id
        mangel.status = "in_angebot"

    for vid in vorgang_ids:
        session.add(
            VorgangEvent(
                mandant_id=auth.mandant_id,
                vorgang_id=vid,
                event_type="angebot",
                author_user_id=auth.user_id,
                body=f"Angebot {angebotsnummer} aus {len(maengel)} Mangel/Mängeln erstellt",
                payload={"angebot_id": str(angebot.id), "status": "entwurf"},
            )
        )

    await session.flush()
    await session.refresh(angebot)
    return await _to_read_model(session, angebot)


@router.post(
    "/{angebot_id}/positionen",
    response_model=AngebotRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def add_position(
    angebot_id: UUID,
    body: AngebotPositionCreate,
    session: AsyncSession = Depends(get_db),
) -> AngebotRead:
    angebot = await session.get(Angebot, angebot_id)
    if angebot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Angebot nicht gefunden")
    if angebot.status != "entwurf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Positionen können nur im Entwurf ergänzt werden"
        )

    bestehende = await _positionen_fuer(session, angebot_id)
    naechste_position = max((p.position for p in bestehende), default=0) + 1
    session.add(
        AngebotPosition(
            mandant_id=angebot.mandant_id,
            angebot_id=angebot_id,
            position=naechste_position,
            beschreibung=body.beschreibung,
            menge=body.menge,
            einheit=body.einheit,
            einzelpreis=body.einzelpreis,
        )
    )
    await session.flush()
    return await _to_read_model(session, angebot)


@router.patch(
    "/{angebot_id}",
    response_model=AngebotRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_angebot(
    angebot_id: UUID,
    body: AngebotUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AngebotRead:
    angebot = await session.get(Angebot, angebot_id)
    if angebot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Angebot nicht gefunden")

    if body.gueltig_bis is not None:
        angebot.gueltig_bis = body.gueltig_bis

    neuer_status = body.status
    if neuer_status is not None:
        _GUELTIGE_UEBERGAENGE = {"entwurf": {"versendet"}, "versendet": {"angenommen", "abgelehnt"}}
        if neuer_status not in _GUELTIGE_UEBERGAENGE.get(angebot.status, set()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Statuswechsel von '{angebot.status}' nach '{neuer_status}' nicht erlaubt",
            )

        maengel = list(
            (await session.execute(select(Mangel).where(Mangel.angebot_id == angebot.id))).scalars().all()
        )
        jetzt = datetime.now(timezone.utc)

        if neuer_status == "versendet":
            positionen = await _positionen_fuer(session, angebot.id)
            if not positionen:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Angebot ohne Positionen kann nicht versendet werden"
                )
            angebot.versendet_am = jetzt

        elif neuer_status == "angenommen":
            angebot.angenommen_am = jetzt
            if maengel:
                vorgangsnummer = await next_vorgangsnummer(session, auth.mandant_id)
                repair_anlage_id = next((m.anlage_id for m in maengel if m.anlage_id), None)
                reparatur_vorgang = Vorgang(
                    mandant_id=auth.mandant_id,
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
                        mandant_id=auth.mandant_id,
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
                    auth.mandant_id, "feed_update", {"vorgang_id": str(reparatur_vorgang.id), "reason": "erstellt"}
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
                    mandant_id=auth.mandant_id,
                    vorgang_id=vid,
                    event_type="angebot",
                    author_user_id=auth.user_id,
                    body=f"Angebot {angebot.angebotsnummer}: Status '{neuer_status}'",
                    payload={"angebot_id": str(angebot.id), "status": neuer_status},
                )
            )

    await session.flush()
    await session.refresh(angebot)
    return await _to_read_model(session, angebot)


@router.get("/{angebot_id}/pdf")
async def angebot_pdf(
    angebot_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    angebot = await session.get(Angebot, angebot_id)
    if angebot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Angebot nicht gefunden")
    kunde = await session.get(Kunde, angebot.kunde_id)
    positionen = await _positionen_fuer(session, angebot.id)
    mandant = await session.get(Mandant, auth.mandant_id)

    pdf_bytes = generate_angebot_pdf(mandant, angebot, positionen, kunde)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{angebot.angebotsnummer}.pdf"'},
    )
