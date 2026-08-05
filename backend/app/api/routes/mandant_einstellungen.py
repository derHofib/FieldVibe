from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.core.config import get_settings
from app.models.mandant import Mandant
from app.schemas.mandant_einstellungen import (
    MandantEinstellungenRead,
    MandantEinstellungenUpdate,
    MandantLogoUrl,
)
from app.services import storage_service

router = APIRouter(
    prefix="/api/mandant/einstellungen",
    tags=["mandant-einstellungen"],
    dependencies=[Depends(require_roles("mandant_admin"))],
)

_LOGO_MAX_BYTES = 3 * 1024 * 1024


def _to_read_model(mandant: Mandant) -> MandantEinstellungenRead:
    settings = get_settings()
    return MandantEinstellungenRead(
        scheduler_stunde_utc=mandant.scheduler_stunde_utc,
        effektive_scheduler_stunde_utc=(
            mandant.scheduler_stunde_utc
            if mandant.scheduler_stunde_utc is not None
            else settings.scheduler_default_stunde_utc
        ),
        firmendaten=mandant.firmendaten,
        logo_object_key=mandant.logo_object_key,
    )


@router.get("", response_model=MandantEinstellungenRead)
async def get_einstellungen(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> MandantEinstellungenRead:
    mandant = await session.get(Mandant, auth.mandant_id)
    return _to_read_model(mandant)


@router.patch("", response_model=MandantEinstellungenRead)
async def update_einstellungen(
    body: MandantEinstellungenUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MandantEinstellungenRead:
    mandant = await session.get(Mandant, auth.mandant_id)
    # exclude_unset statt blindem Ueberschreiben: seit firmendaten dazugekommen
    # ist, wuerde ein Aufruf, der nur firmendaten aendern will, sonst
    # scheduler_stunde_utc unbeabsichtigt auf den globalen Default
    # zuruecksetzen (fehlt das Feld im Request, waere body.scheduler_stunde_utc
    # sonst still auf seinen Pydantic-Default None gefallen).
    updates = body.model_dump(exclude_unset=True)
    if "scheduler_stunde_utc" in updates:
        mandant.scheduler_stunde_utc = updates["scheduler_stunde_utc"]
    if updates.get("firmendaten") is not None:
        mandant.firmendaten = updates["firmendaten"]
    await session.flush()
    await session.refresh(mandant)
    return _to_read_model(mandant)


@router.post("/logo", response_model=MandantEinstellungenRead)
async def upload_mandant_logo(
    file: UploadFile,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MandantEinstellungenRead:
    mandant = await session.get(Mandant, auth.mandant_id)
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Nur Bilddateien werden unterstützt"
        )

    data = await file.read()
    if len(data) > _LOGO_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Datei zu groß (max. 3 MB)"
        )

    alter_key = mandant.logo_object_key
    key = storage_service.new_mandant_logo_key(mandant.id, file.filename or "logo.png")
    await storage_service.upload_bytes(key, data, file.content_type)
    mandant.logo_object_key = key
    await session.flush()
    await session.refresh(mandant)

    if alter_key is not None:
        await storage_service.delete_object(alter_key)
    return _to_read_model(mandant)


@router.delete("/logo", response_model=MandantEinstellungenRead)
async def remove_mandant_logo(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> MandantEinstellungenRead:
    mandant = await session.get(Mandant, auth.mandant_id)
    alter_key = mandant.logo_object_key
    mandant.logo_object_key = None
    await session.flush()
    await session.refresh(mandant)

    if alter_key is not None:
        await storage_service.delete_object(alter_key)
    return _to_read_model(mandant)


@router.get("/logo-url", response_model=MandantLogoUrl)
async def get_mandant_logo_url(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> MandantLogoUrl:
    mandant = await session.get(Mandant, auth.mandant_id)
    if mandant.logo_object_key is None:
        return MandantLogoUrl(url=None)
    return MandantLogoUrl(url=storage_service.presigned_get_url(mandant.logo_object_key))
