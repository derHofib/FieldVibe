from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_recht, require_roles
from app.models.anlage import Anlage
from app.models.standort import Standort
from app.models.vorgang import Vorgang
from app.models.vorgang_anfrage import VorgangAnfrage
from app.models.vorgang_event import VorgangEvent
from app.schemas.vorgang_anfrage import (
    VorgangAnfrageAblehnen,
    VorgangAnfrageAnnehmen,
    VorgangAnfrageRead,
)
from app.services.event_bus import event_bus
from app.services.numbering_service import next_vorgangsnummer

router = APIRouter(
    prefix="/api/vorgang-anfragen",
    tags=["vorgang-anfragen"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("vorgaenge", "bearbeiten")),
    ],
)


@router.get("", response_model=list[VorgangAnfrageRead])
async def list_anfragen(
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_db),
) -> list[VorgangAnfrage]:
    stmt = (
        select(VorgangAnfrage)
        .where(VorgangAnfrage.geloescht_am.is_(None))
        .order_by(VorgangAnfrage.created_at.desc())
    )
    if status_filter:
        stmt = stmt.where(VorgangAnfrage.status == status_filter)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/{anfrage_id}", response_model=VorgangAnfrageRead)
async def get_anfrage(anfrage_id: UUID, session: AsyncSession = Depends(get_db)) -> VorgangAnfrage:
    anfrage = await session.get(VorgangAnfrage, anfrage_id)
    if anfrage is None or anfrage.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anfrage nicht gefunden")
    return anfrage


def _require_offen(anfrage: VorgangAnfrage) -> None:
    if anfrage.status != "offen":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Anfrage wurde bereits bearbeitet",
        )


@router.post("/{anfrage_id}/annehmen", response_model=VorgangAnfrageRead)
async def annehmen(
    anfrage_id: UUID,
    body: VorgangAnfrageAnnehmen,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorgangAnfrage:
    anfrage = await session.get(VorgangAnfrage, anfrage_id)
    if anfrage is None or anfrage.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anfrage nicht gefunden")
    _require_offen(anfrage)

    # Zwischen Anfrage und Annahme koennen Anlage/Standort inzwischen
    # deaktiviert worden sein -- dieselbe Regel wie bei einer direkt vom
    # Mitarbeiter angelegten Vorgangs-Neuanlage gilt daher auch hier.
    if anfrage.anlage_id is not None:
        anlage = await session.get(Anlage, anfrage.anlage_id)
        if anlage is None or not anlage.aktiv:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Verknüpfte Anlage ist inzwischen inaktiv oder gelöscht",
            )
    if anfrage.standort_id is not None:
        standort = await session.get(Standort, anfrage.standort_id)
        if standort is None or not standort.aktiv:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Verknüpfter Standort ist inzwischen inaktiv oder gelöscht",
            )

    vorgangsnummer = await next_vorgangsnummer(session, auth.mandant_id)
    vorgang = Vorgang(
        mandant_id=auth.mandant_id,
        vorgangsnummer=vorgangsnummer,
        kunde_id=anfrage.kunde_id,
        anlage_id=anfrage.anlage_id,
        standort_id=anfrage.standort_id,
        titel=anfrage.titel,
        beschreibung=anfrage.beschreibung,
        abrechnungsart=body.abrechnungsart,
        leistungstyp=anfrage.leistungstyp,
        prioritaet=body.prioritaet,
        erstellt_von_kundenportal_zugang_id=anfrage.kundenportal_zugang_id,
    )
    session.add(vorgang)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Vorgangsnummer bereits vergeben"
        ) from exc

    session.add(
        VorgangEvent(
            mandant_id=auth.mandant_id,
            vorgang_id=vorgang.id,
            event_type="system",
            author_user_id=auth.user_id,
            is_system=True,
            kundensichtbar=True,
            body="Vorgang aus Kundenanfrage angenommen",
            payload={"status": vorgang.status, "vorgang_anfrage_id": str(anfrage.id)},
        )
    )

    anfrage.status = "angenommen"
    anfrage.vorgang_id = vorgang.id
    anfrage.bearbeitet_von = auth.user_id
    anfrage.bearbeitet_am = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(anfrage)

    await event_bus.publish(
        auth.mandant_id, "feed_update", {"vorgang_id": str(vorgang.id), "reason": "erstellt"}
    )
    return anfrage


@router.post("/{anfrage_id}/ablehnen", response_model=VorgangAnfrageRead)
async def ablehnen(
    anfrage_id: UUID,
    body: VorgangAnfrageAblehnen,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorgangAnfrage:
    anfrage = await session.get(VorgangAnfrage, anfrage_id)
    if anfrage is None or anfrage.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anfrage nicht gefunden")
    _require_offen(anfrage)

    anfrage.status = "abgelehnt"
    anfrage.ablehnungsgrund = body.ablehnungsgrund
    anfrage.bearbeitet_von = auth.user_id
    anfrage.bearbeitet_am = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(anfrage)
    return anfrage
