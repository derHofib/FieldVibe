"""Aufbewahrungsfristen und Loeschvorschlaege (nur mandant_admin).

Vorschlag statt Automatik: Belege mit abgelaufener Frist werden aufgelistet; ein Admin
legt sie bewusst in den Papierkorb, endgueltig geloescht werden sie dort von einem
Papierkorb-Konto (loesch_operativ) -- zwei getrennte Schritte, beide protokolliert."""
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, nur_mandant_admin
from app.models.s3_loeschauftrag import S3Loeschauftrag
from app.schemas.aufbewahrung import (
    FristRead,
    LoeschvorschlagListe,
    LoeschvorschlagRead,
    S3LoeschauftragRead,
)
from app.services import aufbewahrung_service, papierkorb_service
from app.services.audit_service import log_action

router = APIRouter(
    prefix="/api/aufbewahrung",
    tags=["aufbewahrung"],
    dependencies=[Depends(nur_mandant_admin)],
)

_RECHTSGRUNDLAGE = {
    "buchungsbeleg": "§ 147 Abs. 1 Nr. 4 und 4a, Abs. 3 AO; § 257 Abs. 1 Nr. 4, Abs. 4 HGB",
    "rechnung": "§ 14b Abs. 1 UStG; § 147 Abs. 3 AO; § 257 Abs. 4 HGB",
    "geschaeftsbrief": "§ 147 Abs. 1 Nr. 2, 3 AO; § 257 Abs. 1 Nr. 2, 3 HGB",
    "angebot": "§ 147 Abs. 1 Nr. 2, 3 AO; § 257 Abs. 1 Nr. 2, 3 HGB (Geschäftsbrief)",
    "buch_jahresabschluss": "§ 147 Abs. 1 Nr. 1 AO; § 257 Abs. 1 Nr. 1 HGB",
}


@router.get("/fristen", response_model=list[FristRead])
async def list_fristen() -> list[FristRead]:
    return [
        FristRead(
            belegart=art,
            label=aufbewahrung_service.BELEGART_LABEL[art],
            jahre=jahre,
            rechtsgrundlage=_RECHTSGRUNDLAGE[art],
        )
        for art, jahre in aufbewahrung_service.AUFBEWAHRUNG_JAHRE.items()
    ]


@router.get("/loeschvorschlaege", response_model=LoeschvorschlagListe)
async def list_loeschvorschlaege(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> LoeschvorschlagListe:
    heute = papierkorb_service.heute_lokal()
    eintraege, gesamt = await aufbewahrung_service.loeschvorschlaege(
        session, heute=heute, limit=limit, offset=offset
    )
    return LoeschvorschlagListe(
        eintraege=[
            LoeschvorschlagRead(
                entity_typ=v.entity_typ,
                id=v.id,
                beleg_nummer=v.beleg_nummer,
                belegart=v.belegart,
                fristende=v.fristende,
                im_papierkorb=v.im_papierkorb,
            )
            for v in eintraege
        ],
        gesamt=gesamt,
        stichtag=heute,
    )


@router.post(
    "/loeschvorschlaege/{entity_typ}/{entity_id}/in-papierkorb", status_code=status.HTTP_204_NO_CONTENT
)
async def vorschlag_in_papierkorb(
    entity_typ: Literal["rechnung", "eingangsrechnung", "angebot"],
    entity_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Bestaetigt einen Vorschlag: der Beleg wandert in den Papierkorb (weich geloescht).
    Nur bei abgelaufener Frist -- vorher bleibt er wie bisher unangetastet."""
    modell = papierkorb_service.ENTITY_REGISTRY[entity_typ].modell
    obj = await session.get(modell, entity_id)
    if obj is None or obj.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Beleg nicht gefunden")
    auf = aufbewahrung_service.aufbewahrung_fuer(entity_typ, obj)
    heute = papierkorb_service.heute_lokal()
    if auf is None or not auf.abgelaufen(heute):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Die Aufbewahrungsfrist dieses Belegs ist noch nicht abgelaufen"
            + (f" (bis {auf.fristende:%d.%m.%Y})" if auf else ""),
        )
    await papierkorb_service.soft_delete(
        session, entity_typ=entity_typ, entity_id=entity_id, actor_user_id=auth.user_id
    )
    await log_action(
        session,
        aktion="aufbewahrung_in_papierkorb",
        mandant_id=auth.mandant_id,
        actor_user_id=auth.user_id,
        entity_type=entity_typ,
        entity_id=entity_id,
        payload={"belegart": auf.belegart, "fristende": auf.fristende.isoformat()},
    )


@router.get("/s3-loeschauftraege", response_model=list[S3LoeschauftragRead])
async def list_s3_loeschauftraege(
    session: AsyncSession = Depends(get_db),
) -> list[S3Loeschauftrag]:
    """Offene und fehlgeschlagene Aufraeumauftraege im Objektspeicher (Retry-Liste)."""
    result = await session.execute(
        select(S3Loeschauftrag)
        .where(S3Loeschauftrag.status.in_(("offen", "fehler")))
        .order_by(S3Loeschauftrag.erstellt_am)
        .limit(200)
    )
    return list(result.scalars().all())
