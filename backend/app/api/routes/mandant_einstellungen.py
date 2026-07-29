from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.core.config import get_settings
from app.models.mandant import Mandant
from app.schemas.mandant_einstellungen import MandantEinstellungenRead, MandantEinstellungenUpdate

router = APIRouter(
    prefix="/api/mandant/einstellungen",
    tags=["mandant-einstellungen"],
    dependencies=[Depends(require_roles("mandant_admin"))],
)


def _to_read_model(mandant: Mandant) -> MandantEinstellungenRead:
    settings = get_settings()
    return MandantEinstellungenRead(
        scheduler_stunde_utc=mandant.scheduler_stunde_utc,
        effektive_scheduler_stunde_utc=(
            mandant.scheduler_stunde_utc
            if mandant.scheduler_stunde_utc is not None
            else settings.scheduler_default_stunde_utc
        ),
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
    mandant.scheduler_stunde_utc = body.scheduler_stunde_utc
    await session.flush()
    await session.refresh(mandant)
    return _to_read_model(mandant)
