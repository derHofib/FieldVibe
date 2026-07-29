from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.material import Material, MaterialVerwendung
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.material import (
    MaterialCreate,
    MaterialRead,
    MaterialUpdate,
    MaterialVerwendungCreate,
    MaterialVerwendungRead,
)

router = APIRouter(
    prefix="/api/material",
    tags=["material"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)


@router.get("", response_model=list[MaterialRead])
async def list_material(session: AsyncSession = Depends(get_db)) -> list[Material]:
    result = await session.execute(select(Material).order_by(Material.bezeichnung))
    return list(result.scalars().all())


@router.post(
    "",
    response_model=MaterialRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_material(
    body: MaterialCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Material:
    material = Material(
        mandant_id=auth.mandant_id,
        bezeichnung=body.bezeichnung,
        einheit=body.einheit,
        bestand=body.bestand,
        mindestbestand=body.mindestbestand,
        einzelpreis=body.einzelpreis,
    )
    session.add(material)
    await session.flush()
    await session.refresh(material)
    return material


@router.patch(
    "/{material_id}",
    response_model=MaterialRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_material(
    material_id: UUID, body: MaterialUpdate, session: AsyncSession = Depends(get_db)
) -> Material:
    material = await session.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material nicht gefunden")

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(material, field, value)
    await session.flush()
    if changes:
        await session.refresh(material)
    return material


@router.post("/{material_id}/verwendung", response_model=MaterialVerwendungRead, status_code=status.HTTP_201_CREATED)
async def verwendung_erfassen(
    material_id: UUID,
    body: MaterialVerwendungCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MaterialVerwendung:
    material = await session.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material nicht gefunden")
    vorgang = await session.get(Vorgang, body.vorgang_id)
    if vorgang is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if body.menge > material.bestand:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nicht genug Bestand: {material.bestand} {material.einheit} verfügbar, {body.menge} angefragt",
        )

    material.bestand -= body.menge
    verwendung = MaterialVerwendung(
        mandant_id=auth.mandant_id,
        material_id=material_id,
        vorgang_id=body.vorgang_id,
        menge=body.menge,
        verwendet_von=auth.user_id,
    )
    session.add(verwendung)

    session.add(
        VorgangEvent(
            mandant_id=auth.mandant_id,
            vorgang_id=body.vorgang_id,
            event_type="material",
            author_user_id=auth.user_id,
            body=f"{body.menge:g} {material.einheit} {material.bezeichnung} verwendet",
            payload={"material_id": str(material_id), "menge": str(body.menge)},
        )
    )

    await session.flush()
    await session.refresh(verwendung)
    return verwendung
