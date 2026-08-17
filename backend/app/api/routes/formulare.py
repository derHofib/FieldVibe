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
    FormularfeldPosition,
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
    daten = body.model_dump(exclude_unset=True)
    if "anzahl_seiten" in daten and daten["anzahl_seiten"] < formular.anzahl_seiten:
        letzte_seite = daten["anzahl_seiten"]
        felder_auf_wegfallenden_seiten = await session.execute(
            select(Formularfeld).where(
                Formularfeld.formular_id == formular_id, Formularfeld.seite >= letzte_seite
            )
        )
        if felder_auf_wegfallenden_seiten.scalars().first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bitte zuerst Felder von den wegfallenden Seiten entfernen oder verschieben",
            )
    for field, value in daten.items():
        setattr(formular, field, value)
    await session.flush()
    await session.refresh(formular)
    return await formular_service.to_read_model(session, formular)


# --- Formularfelder -------------------------------------------------------


async def _recompute_reihenfolge(session: AsyncSession, formular_id: UUID) -> None:
    """Berechnet die reihenfolge-Cache-Spalte neu aus der aktuellen
    Position (Seite, dann y_mm/x_mm, siehe Formularfeld.reihenfolge-
    Docstring) -- aufgerufen nach jeder Aenderung, die die Anzahl/Position
    der Felder betrifft (Anlegen, Bulk-Positionierung, Loeschen)."""
    felder = await formular_service.felder_fuer(session, formular_id)
    for position, feld in enumerate(felder):
        feld.reihenfolge = position
    await session.flush()


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
    formular = await _get_formular_or_404(session, formular_id)
    if body.seite >= formular.anzahl_seiten:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formular hat nur {formular.anzahl_seiten} Seite(n)",
        )
    y_mm = body.y_mm
    if "y_mm" not in body.model_fields_set:
        # Kein explizites Ziel angegeben (Standardfall "Feld hinzufügen"):
        # neues Feld unterhalb aller bestehenden Felder DERSELBEN Seite
        # anhaengen, damit es garantiert nicht mit etwas Vorhandenem
        # ueberlappt.
        bestehende = await formular_service.felder_fuer(session, formular_id)
        y_mm = max(
            (f.y_mm + f.hoehe_mm for f in bestehende if f.seite == body.seite), default=0
        )
    feld = Formularfeld(
        mandant_id=auth.mandant_id,
        formular_id=formular_id,
        feld_typ=body.feld_typ,
        label=body.label,
        hilfetext=body.hilfetext,
        pflichtfeld=body.pflichtfeld,
        optionen=body.optionen,
        seite=body.seite,
        x_mm=body.x_mm,
        y_mm=y_mm,
        breite_mm=body.breite_mm,
        hoehe_mm=body.hoehe_mm,
        datenquelle=body.datenquelle,
    )
    session.add(feld)
    await session.flush()
    await _recompute_reihenfolge(session, formular_id)
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


@router.put(
    "/{formular_id}/felder/positionen",
    response_model=list[FormularfeldRead],
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def update_formularfeld_positionen(
    formular_id: UUID,
    positionen: list[FormularfeldPosition],
    session: AsyncSession = Depends(get_db),
) -> list[Formularfeld]:
    """Bulk-Update aller freien Positionen nach Drag&Drop/Resize im
    Canvas-Editor -- erspart N einzelne PATCH-Aufrufe. Ueberlappende Felder
    sind erlaubt (wie im MS-Access-Formular-Designer), es wird nur
    geprueft, dass jedes Feld auf eine tatsaechlich vorhandene Seite des
    Formulars gesetzt wird."""
    formular = await _get_formular_or_404(session, formular_id)
    felder = await formular_service.felder_fuer(session, formular_id)
    felder_by_id = {f.id: f for f in felder}
    if {p.id for p in positionen} != set(felder_by_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Positions-Liste stimmt nicht mit den vorhandenen Feldern dieses Formulars überein",
        )
    if any(p.seite >= formular.anzahl_seiten for p in positionen):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formular hat nur {formular.anzahl_seiten} Seite(n)",
        )
    for p in positionen:
        feld = felder_by_id[p.id]
        feld.seite = p.seite
        feld.x_mm = p.x_mm
        feld.y_mm = p.y_mm
        feld.breite_mm = p.breite_mm
        feld.hoehe_mm = p.hoehe_mm
    await session.flush()
    await _recompute_reihenfolge(session, formular_id)
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
    await _recompute_reihenfolge(session, formular_id)


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
