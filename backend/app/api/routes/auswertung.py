from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_module, require_recht, require_roles
from app.schemas.auswertung import OffenePostenBericht, UstVaBericht
from app.services.auswertung_service import datev_export_csv, offene_posten_bericht, ust_va_bericht

router = APIRouter(
    prefix="/api/auswertung",
    tags=["auswertung"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_module("abrechnung")),
        Depends(require_recht("abrechnung", "sehen")),
    ],
)


@router.get("/ust-va", response_model=UstVaBericht)
async def get_ust_va_bericht(
    von: date = Query(...),
    bis: date = Query(...),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> UstVaBericht:
    if bis < von:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'bis' darf nicht vor 'von' liegen")
    return await ust_va_bericht(session, auth.mandant_id, von, bis)


@router.get("/offene-posten", response_model=OffenePostenBericht)
async def get_offene_posten(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> OffenePostenBericht:
    return await offene_posten_bericht(session, auth.mandant_id, date.today())


@router.get("/datev-export")
async def get_datev_export(
    von: date = Query(...),
    bis: date = Query(...),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    if bis < von:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'bis' darf nicht vor 'von' liegen")
    return await datev_export_csv(session, auth.mandant_id, von, bis)
