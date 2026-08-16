from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.core.security import encrypt_secret
from app.models.plattform_integration import PLATTFORM_INTEGRATION_TYPEN, PlattformIntegration
from app.schemas.plattform_integration import (
    PlattformIntegrationCreate,
    PlattformIntegrationRead,
    PlattformIntegrationUpdate,
)

router = APIRouter(
    prefix="/api/plattform/integrationen",
    tags=["plattform"],
    dependencies=[Depends(require_roles("super_admin"))],
)


def _to_read_model(integration: PlattformIntegration) -> PlattformIntegrationRead:
    return PlattformIntegrationRead(
        id=integration.id,
        typ=integration.typ,
        config=integration.config,
        aktiv=integration.aktiv,
        hat_secret=integration.secret_ref is not None,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


@router.get("", response_model=list[PlattformIntegrationRead])
async def list_plattform_integrationen(session: AsyncSession = Depends(get_db)) -> list[PlattformIntegrationRead]:
    result = await session.execute(select(PlattformIntegration).order_by(PlattformIntegration.typ))
    return [_to_read_model(i) for i in result.scalars().all()]


@router.post("", response_model=PlattformIntegrationRead, status_code=status.HTTP_201_CREATED)
async def create_plattform_integration(
    body: PlattformIntegrationCreate, session: AsyncSession = Depends(get_db)
) -> PlattformIntegrationRead:
    if body.typ not in PLATTFORM_INTEGRATION_TYPEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unbekannter Integrationstyp: {body.typ}",
        )
    integration = PlattformIntegration(
        typ=body.typ,
        config=body.config,
        secret_ref=encrypt_secret(body.secret) if body.secret else None,
        aktiv=body.aktiv,
    )
    session.add(integration)
    await session.flush()
    await session.refresh(integration)
    return _to_read_model(integration)


@router.patch("/{integration_id}", response_model=PlattformIntegrationRead)
async def update_plattform_integration(
    integration_id: UUID,
    body: PlattformIntegrationUpdate,
    session: AsyncSession = Depends(get_db),
) -> PlattformIntegrationRead:
    integration = await session.get(PlattformIntegration, integration_id)
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration nicht gefunden")

    changes = body.model_dump(exclude_unset=True, exclude={"secret"})
    for field, value in changes.items():
        setattr(integration, field, value)
    # "secret" separat behandelt: nur wenn der Client den Key ueberhaupt
    # mitgeschickt hat (auch mit Wert null, um es zu loeschen) -- sonst
    # wuerde ein Update, das nur "aktiv" aendern will, das bestehende
    # Secret unbeabsichtigt loeschen. Gleiches Muster wie bei
    # app/api/routes/integrationen.py.
    if "secret" in body.model_fields_set:
        integration.secret_ref = encrypt_secret(body.secret) if body.secret else None

    await session.flush()
    await session.refresh(integration)
    return _to_read_model(integration)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plattform_integration(
    integration_id: UUID, session: AsyncSession = Depends(get_db)
) -> None:
    integration = await session.get(PlattformIntegration, integration_id)
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration nicht gefunden")
    await session.delete(integration)
    await session.flush()
