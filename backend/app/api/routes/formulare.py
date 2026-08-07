from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_recht, require_roles
from app.models.formular import Formular, FormularAuftragstypZuordnung, Formularfeld
from app.schemas.formular import (
    FormularAuftragstypZuordnungCreate,
    FormularAuftragstypZuordnungRead,
    FormularAuftragstypZuordnungUpdate,
    FormularCreate,
    FormularfeldCreate,
    FormularfeldRead,
    FormularfeldUpdate,
    FormularRead,
    FormularUpdate,
)
from app.services import formular_service

router = APIRouter(
    prefix="/api/formulare",
    tags=["formulare"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("formulare", "sehen")),
    ],
)


async def _get_formular_or_404(session: AsyncSession, formular_id: UUID) -> Formular:
    formular = await session.get(Formular, formular_id)
    if formular is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Formular nicht gefunden")
    return formular


@router.get("", response_model=list[FormularRead])
async def list_formulare(
    aktiv: bool | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> list[FormularRead]:
    stmt = select(Formular).order_by(Formular.name)
    if aktiv is not None:
        stmt = stmt.where(Formular.aktiv == aktiv)
    formulare = list((await session.execute(stmt)).scalars().all())
    return [await formular_service.to_read_model(session, f) for f in formulare]


@router.post(
    "",
    response_model=FormularRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recht("formulare", "erstellen"))],
)
async def create_formular(
    body: FormularCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FormularRead:
    formular = Formular(
        mandant_id=auth.mandant_id,
        name=body.name,
        beschreibung=body.beschreibung,
        erstellt_von=auth.user_id,
    )
    session.add(formular)
    await session.flush()
    await session.refresh(formular)
    return await formular_service.to_read_model(session, formular)


@router.get("/{formular_id}", response_model=FormularRead)
async def get_formular(formular_id: UUID, session: AsyncSession = Depends(get_db)) -> FormularRead:
    formular = await _get_formular_or_404(session, formular_id)
    return await formular_service.to_read_model(session, formular)


@router.patch(
    "/{formular_id}",
    response_model=FormularRead,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def update_formular(
    formular_id: UUID,
    body: FormularUpdate,
    session: AsyncSession = Depends(get_db),
) -> FormularRead:
    formular = await _get_formular_or_404(session, formular_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(formular, field, value)
    await session.flush()
    await session.refresh(formular)
    return await formular_service.to_read_model(session, formular)


# --- Formularfelder -------------------------------------------------------


@router.post(
    "/{formular_id}/felder",
    response_model=FormularfeldRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def create_formularfeld(
    formular_id: UUID,
    body: FormularfeldCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Formularfeld:
    await _get_formular_or_404(session, formular_id)
    feld = Formularfeld(
        mandant_id=auth.mandant_id,
        formular_id=formular_id,
        feld_typ=body.feld_typ,
        label=body.label,
        hilfetext=body.hilfetext,
        pflichtfeld=body.pflichtfeld,
        reihenfolge=body.reihenfolge,
        optionen=body.optionen,
    )
    session.add(feld)
    await session.flush()
    await session.refresh(feld)
    return feld


@router.patch(
    "/{formular_id}/felder/{feld_id}",
    response_model=FormularfeldRead,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def update_formularfeld(
    formular_id: UUID,
    feld_id: UUID,
    body: FormularfeldUpdate,
    session: AsyncSession = Depends(get_db),
) -> Formularfeld:
    feld = await session.get(Formularfeld, feld_id)
    if feld is None or feld.formular_id != formular_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feld nicht gefunden")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(feld, field, value)
    await session.flush()
    await session.refresh(feld)
    return feld


@router.post(
    "/{formular_id}/felder/reihenfolge",
    response_model=list[FormularfeldRead],
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def umsortieren_formularfelder(
    formular_id: UUID,
    feld_ids: list[UUID],
    session: AsyncSession = Depends(get_db),
) -> list[Formularfeld]:
    """Setzt reihenfolge anhand der uebergebenen Feld-Id-Reihenfolge in
    einem Zug -- erspart dem Baukasten-Editor N einzelne PATCH-Aufrufe bei
    Drag&Drop/Auf-Ab-Sortierung."""
    felder = await formular_service.felder_fuer(session, formular_id)
    felder_by_id = {f.id: f for f in felder}
    if set(feld_ids) != set(felder_by_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feld-Liste stimmt nicht mit den vorhandenen Feldern dieses Formulars überein",
        )
    for position, feld_id in enumerate(feld_ids):
        felder_by_id[feld_id].reihenfolge = position
    await session.flush()
    return await formular_service.felder_fuer(session, formular_id)


@router.delete(
    "/{formular_id}/felder/{feld_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_recht("formulare", "loeschen"))],
)
async def delete_formularfeld(
    formular_id: UUID, feld_id: UUID, session: AsyncSession = Depends(get_db)
) -> None:
    feld = await session.get(Formularfeld, feld_id)
    if feld is None or feld.formular_id != formular_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feld nicht gefunden")
    await session.delete(feld)
    await session.flush()


# --- Zuordnungen zu Auftragstypen (Leistungstyp) --------------------------


@router.post(
    "/{formular_id}/zuordnungen",
    response_model=FormularAuftragstypZuordnungRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def create_zuordnung(
    formular_id: UUID,
    body: FormularAuftragstypZuordnungCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FormularAuftragstypZuordnung:
    await _get_formular_or_404(session, formular_id)
    zuordnung = FormularAuftragstypZuordnung(
        mandant_id=auth.mandant_id,
        formular_id=formular_id,
        leistungstyp=body.leistungstyp,
        pflicht_vor_abschluss=body.pflicht_vor_abschluss,
    )
    session.add(zuordnung)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dieses Formular ist diesem Auftragstyp bereits zugeordnet",
        ) from exc
    await session.refresh(zuordnung)
    return zuordnung


@router.patch(
    "/{formular_id}/zuordnungen/{zuordnung_id}",
    response_model=FormularAuftragstypZuordnungRead,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def update_zuordnung(
    formular_id: UUID,
    zuordnung_id: UUID,
    body: FormularAuftragstypZuordnungUpdate,
    session: AsyncSession = Depends(get_db),
) -> FormularAuftragstypZuordnung:
    zuordnung = await session.get(FormularAuftragstypZuordnung, zuordnung_id)
    if zuordnung is None or zuordnung.formular_id != formular_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zuordnung nicht gefunden")
    zuordnung.pflicht_vor_abschluss = body.pflicht_vor_abschluss
    await session.flush()
    await session.refresh(zuordnung)
    return zuordnung


@router.delete(
    "/{formular_id}/zuordnungen/{zuordnung_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def delete_zuordnung(
    formular_id: UUID, zuordnung_id: UUID, session: AsyncSession = Depends(get_db)
) -> None:
    zuordnung = await session.get(FormularAuftragstypZuordnung, zuordnung_id)
    if zuordnung is None or zuordnung.formular_id != formular_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zuordnung nicht gefunden")
    await session.delete(zuordnung)
    await session.flush()
