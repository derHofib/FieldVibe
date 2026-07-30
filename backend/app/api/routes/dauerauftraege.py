from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.anlage import Anlage
from app.models.dauerauftrag import Dauerauftrag
from app.models.dauerauftrag_ziel import DauerauftragZiel
from app.models.kunde import Kunde
from app.models.vorgang import Vorgang
from app.schemas.dauerauftrag import (
    DauerauftragCreate,
    DauerauftragMitVerlauf,
    DauerauftragRead,
    DauerauftragUpdate,
    DauerauftragZieleUpdate,
    DauerauftragZielRead,
)
from app.services.zuweisung_service import assigned_kunde_ids

router = APIRouter(
    prefix="/api/dauerauftraege",
    tags=["dauerauftraege"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)


async def _ziele_fuer(session: AsyncSession, dauerauftrag_id: UUID) -> list[DauerauftragZiel]:
    result = await session.execute(
        select(DauerauftragZiel)
        .where(DauerauftragZiel.dauerauftrag_id == dauerauftrag_id)
        .order_by(DauerauftragZiel.created_at.asc())
    )
    return list(result.scalars().all())


def _read_mit_zielen(dauerauftrag: Dauerauftrag, ziele: list[DauerauftragZiel]) -> DauerauftragRead:
    faelligkeiten = [z.naechste_faelligkeit_am for z in ziele if z.offener_vorgang_id is None]
    return DauerauftragRead(
        id=dauerauftrag.id,
        kunde_id=dauerauftrag.kunde_id,
        titel=dauerauftrag.titel,
        beschreibung=dauerauftrag.beschreibung,
        abrechnungsart=dauerauftrag.abrechnungsart,
        leistungstyp=dauerauftrag.leistungstyp,
        intervall_tage=dauerauftrag.intervall_tage,
        modus=dauerauftrag.modus,
        toleranz_frueh_tage=dauerauftrag.toleranz_frueh_tage,
        toleranz_spaet_tage=dauerauftrag.toleranz_spaet_tage,
        aktiv=dauerauftrag.aktiv,
        created_at=dauerauftrag.created_at,
        updated_at=dauerauftrag.updated_at,
        ziele=[DauerauftragZielRead.model_validate(z) for z in ziele],
        anzahl_ziele=len(ziele),
        naechste_faelligkeit_am=min(faelligkeiten) if faelligkeiten else None,
    )


@router.get("", response_model=list[DauerauftragRead])
async def list_dauerauftraege(
    kunde_id: UUID | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[DauerauftragRead]:
    stmt = select(Dauerauftrag).order_by(Dauerauftrag.created_at.asc())
    if kunde_id:
        stmt = stmt.where(Dauerauftrag.kunde_id == kunde_id)
    if auth.role == "techniker":
        stmt = stmt.where(Dauerauftrag.kunde_id.in_(await assigned_kunde_ids(session, auth.user_id)))
    dauerauftraege = list((await session.execute(stmt)).scalars().all())

    reads = []
    for auftrag in dauerauftraege:
        ziele = await _ziele_fuer(session, auftrag.id)
        reads.append(_read_mit_zielen(auftrag, ziele))
    reads.sort(key=lambda r: (r.naechste_faelligkeit_am is None, r.naechste_faelligkeit_am))
    return reads


async def _validierte_anlage_ids(
    session: AsyncSession, kunde_id: UUID, anlage_ids: list[UUID]
) -> list[UUID]:
    eindeutig = list(dict.fromkeys(anlage_ids))
    for anlage_id in eindeutig:
        anlage = await session.get(Anlage, anlage_id)
        if anlage is None or anlage.kunde_id != kunde_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Anlage nicht gefunden oder gehört nicht zum angegebenen Kunden",
            )
    return eindeutig


@router.post(
    "",
    response_model=DauerauftragRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_dauerauftrag(
    body: DauerauftragCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DauerauftragRead:
    if await session.get(Kunde, body.kunde_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kunde nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    anlage_ids = await _validierte_anlage_ids(session, body.kunde_id, body.anlage_ids)

    dauerauftrag = Dauerauftrag(
        mandant_id=auth.mandant_id,
        kunde_id=body.kunde_id,
        titel=body.titel,
        beschreibung=body.beschreibung,
        abrechnungsart=body.abrechnungsart,
        leistungstyp=body.leistungstyp,
        intervall_tage=body.intervall_tage,
        modus=body.modus,
        toleranz_frueh_tage=body.toleranz_frueh_tage,
        toleranz_spaet_tage=body.toleranz_spaet_tage,
    )
    session.add(dauerauftrag)
    await session.flush()

    ziel_anlage_ids: list[UUID | None] = list(anlage_ids) if anlage_ids else [None]
    ziele = []
    for anlage_id in ziel_anlage_ids:
        ziel = DauerauftragZiel(
            mandant_id=auth.mandant_id,
            dauerauftrag_id=dauerauftrag.id,
            anlage_id=anlage_id,
            naechste_faelligkeit_am=body.naechste_faelligkeit_am,
        )
        session.add(ziel)
        ziele.append(ziel)
    await session.flush()
    await session.refresh(dauerauftrag)
    for ziel in ziele:
        await session.refresh(ziel)
    return _read_mit_zielen(dauerauftrag, ziele)


async def _require_dauerauftrag_zugriff(
    session: AsyncSession, auth: AuthContext, dauerauftrag: Dauerauftrag
) -> None:
    if auth.role == "techniker" and dauerauftrag.kunde_id not in await assigned_kunde_ids(
        session, auth.user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dauerauftrag nicht gefunden"
        )


@router.get("/{dauerauftrag_id}", response_model=DauerauftragMitVerlauf)
async def get_dauerauftrag(
    dauerauftrag_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DauerauftragMitVerlauf:
    dauerauftrag = await session.get(Dauerauftrag, dauerauftrag_id)
    if dauerauftrag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dauerauftrag nicht gefunden"
        )
    await _require_dauerauftrag_zugriff(session, auth, dauerauftrag)

    ziele = await _ziele_fuer(session, dauerauftrag_id)
    vorgaenge_result = await session.execute(
        select(Vorgang)
        .where(Vorgang.dauerauftrag_id == dauerauftrag_id)
        .order_by(Vorgang.created_at.desc())
    )
    return DauerauftragMitVerlauf(
        **_read_mit_zielen(dauerauftrag, ziele).model_dump(),
        vorgaenge=list(vorgaenge_result.scalars().all()),
    )


@router.patch(
    "/{dauerauftrag_id}",
    response_model=DauerauftragRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_dauerauftrag(
    dauerauftrag_id: UUID,
    body: DauerauftragUpdate,
    session: AsyncSession = Depends(get_db),
) -> DauerauftragRead:
    dauerauftrag = await session.get(Dauerauftrag, dauerauftrag_id)
    if dauerauftrag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dauerauftrag nicht gefunden"
        )

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(dauerauftrag, field, value)
    await session.flush()
    if changes:
        await session.refresh(dauerauftrag)
    ziele = await _ziele_fuer(session, dauerauftrag_id)
    return _read_mit_zielen(dauerauftrag, ziele)


@router.put(
    "/{dauerauftrag_id}/anlagen",
    response_model=DauerauftragRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def set_dauerauftrag_anlagen(
    dauerauftrag_id: UUID,
    body: DauerauftragZieleUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DauerauftragRead:
    """Ersetzt die Menge der an diesem Buendel haengenden Anlagen -- neue
    Anlagen bekommen ein frisches Ziel, entfallene verlieren nur ihren
    Zyklus-Datensatz, ihre ggf. bereits erzeugten Vorgaenge bleiben
    unangetastet (siehe DauerauftragZieleUpdate-Docstring)."""
    dauerauftrag = await session.get(Dauerauftrag, dauerauftrag_id)
    if dauerauftrag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dauerauftrag nicht gefunden"
        )
    neue_anlage_ids = set(
        await _validierte_anlage_ids(session, dauerauftrag.kunde_id, body.anlage_ids)
    )

    bestehende_ziele = await _ziele_fuer(session, dauerauftrag_id)
    bestehende_anlage_ziele = {z.anlage_id: z for z in bestehende_ziele if z.anlage_id is not None}

    for anlage_id, ziel in bestehende_anlage_ziele.items():
        if anlage_id not in neue_anlage_ids:
            await session.delete(ziel)

    for anlage_id in neue_anlage_ids - bestehende_anlage_ziele.keys():
        session.add(
            DauerauftragZiel(
                mandant_id=auth.mandant_id,
                dauerauftrag_id=dauerauftrag_id,
                anlage_id=anlage_id,
                naechste_faelligkeit_am=body.naechste_faelligkeit_am,
            )
        )
    await session.flush()

    ziele = await _ziele_fuer(session, dauerauftrag_id)
    return _read_mit_zielen(dauerauftrag, ziele)


@router.delete(
    "/{dauerauftrag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def delete_dauerauftrag(
    dauerauftrag_id: UUID, session: AsyncSession = Depends(get_db)
) -> None:
    # Bereits erzeugte Vorgaenge bleiben unangetastet -- sie verlieren nur
    # ihre dauerauftrag_id (ON DELETE SET NULL, siehe Migration 0013), sind
    # aber ganz normale Vorgaenge und werden nicht geloescht. Die Ziele des
    # Buendels werden per ON DELETE CASCADE (Migration 0014) mitentfernt.
    dauerauftrag = await session.get(Dauerauftrag, dauerauftrag_id)
    if dauerauftrag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dauerauftrag nicht gefunden"
        )
    await session.delete(dauerauftrag)
    await session.flush()
