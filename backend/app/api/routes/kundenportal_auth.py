import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import KundenAuthContext, get_current_kunde, get_kunden_db
from app.core.security import (
    create_kundenportal_access_token,
    create_kundenportal_refresh_token,
    decode_token,
)
from app.db.session import system_session
from app.models.kunde import Kunde
from app.models.kundenportal import KundenportalZugang
from app.schemas.auth import LoginRequest, RefreshRequest, TokenPair
from app.schemas.kundenportal import CurrentKunde
from app.services.kundenportal_auth_service import authenticate_kunde

router = APIRouter(prefix="/api/kundenportal/auth", tags=["kundenportal"])


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest) -> TokenPair:
    return await authenticate_kunde(body.email, body.password)


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest) -> TokenPair:
    try:
        payload = decode_token(body.refresh_token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiges Refresh-Token"
        ) from exc

    if payload.get("type") != "kundenportal_refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Kein Kundenportal-Refresh-Token"
        )

    async with system_session() as session:
        zugang = await session.get(KundenportalZugang, payload["sub"])
        if zugang is None or not zugang.aktiv:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Zugang nicht gültig"
            )

        return TokenPair(
            access_token=create_kundenportal_access_token(
                subject=zugang.id, mandant_id=zugang.mandant_id, kunde_id=zugang.kunde_id
            ),
            refresh_token=create_kundenportal_refresh_token(
                subject=zugang.id, mandant_id=zugang.mandant_id, kunde_id=zugang.kunde_id
            ),
        )


@router.get("/me", response_model=CurrentKunde)
async def me(
    auth: KundenAuthContext = Depends(get_current_kunde),
    session: AsyncSession = Depends(get_kunden_db),
) -> CurrentKunde:
    zugang = await session.get(KundenportalZugang, auth.zugang_id)
    if zugang is None or zugang.kunde_id != auth.kunde_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zugang nicht gefunden")
    kunde = await session.get(Kunde, auth.kunde_id)
    if kunde is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")

    return CurrentKunde(
        zugang_id=zugang.id,
        kunde_id=kunde.id,
        kunde_name=kunde.name,
        name=zugang.name,
        email=zugang.email,
    )
