"""Verwaltung der mandanteneigenen Plan-Symbol-Bibliothek (Wallbox,
Leitungsschutzschalter, Leitungsweg, ...) fuer den Feldtyp "foto_plan"
(siehe Migration 0081). Rechte-Bereich "formulare", gleiches Vokabular wie
app/api/routes/form_modul.py -- wer Formulare baut, verwaltet auch die
Symbole dafuer."""
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_recht, require_roles
from app.models.plan_symbol import PlanSymbol
from app.schemas.plan_symbol import PlanSymbolRead, PlanSymbolUpdate
from app.services import storage_service

router = APIRouter(
    prefix="/api/plan-symbole",
    tags=["plan-symbole"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("formulare", "sehen")),
    ],
)

_MAX_BYTES = 2 * 1024 * 1024
_ERLAUBTE_CONTENT_TYPES = ("image/png", "image/svg+xml", "image/jpeg", "image/webp")


def _zu_read(symbol: PlanSymbol) -> PlanSymbolRead:
    return PlanSymbolRead(
        id=symbol.id,
        name=symbol.name,
        content_type=symbol.content_type,
        url=storage_service.presigned_get_url(symbol.object_key),
        erstellt_von=symbol.erstellt_von,
        created_at=symbol.created_at,
        updated_at=symbol.updated_at,
    )


async def _get_symbol_or_404(session: AsyncSession, symbol_id: UUID) -> PlanSymbol:
    symbol = await session.get(PlanSymbol, symbol_id)
    if symbol is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Symbol nicht gefunden")
    return symbol


@router.get("", response_model=list[PlanSymbolRead])
async def list_symbole(session: AsyncSession = Depends(get_db)) -> list[PlanSymbolRead]:
    stmt = select(PlanSymbol).order_by(PlanSymbol.name)
    result = await session.execute(stmt)
    return [_zu_read(s) for s in result.scalars().all()]


@router.post(
    "",
    response_model=PlanSymbolRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recht("formulare", "erstellen"))],
)
async def symbol_hochladen(
    file: UploadFile,
    name: str = Form(...),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PlanSymbolRead:
    if not name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name darf nicht leer sein")
    if file.content_type not in _ERLAUBTE_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur PNG, JPEG, WebP oder SVG werden als Symbol unterstützt",
        )
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Datei zu groß (max. 2 MB)")

    key = storage_service.new_plan_symbol_key(auth.mandant_id, file.filename or "symbol.png")
    await storage_service.upload_bytes(key, data, file.content_type)

    symbol = PlanSymbol(
        mandant_id=auth.mandant_id,
        name=name.strip(),
        object_key=key,
        content_type=file.content_type,
        erstellt_von=auth.user_id,
    )
    session.add(symbol)
    await session.flush()
    await session.refresh(symbol)
    return _zu_read(symbol)


@router.patch(
    "/{symbol_id}",
    response_model=PlanSymbolRead,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def symbol_umbenennen(
    symbol_id: UUID, body: PlanSymbolUpdate, session: AsyncSession = Depends(get_db)
) -> PlanSymbolRead:
    symbol = await _get_symbol_or_404(session, symbol_id)
    if not body.name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name darf nicht leer sein")
    symbol.name = body.name.strip()
    await session.flush()
    await session.refresh(symbol)
    return _zu_read(symbol)


@router.delete(
    "/{symbol_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_recht("formulare", "loeschen"))],
)
async def symbol_loeschen(symbol_id: UUID, session: AsyncSession = Depends(get_db)) -> None:
    # Bewusst kein Schutz vor "Symbol wird noch von einem Feld referenziert"
    # -- form_fields.optionen.symbol_ids ist nur eine lose ID-Liste (siehe
    # Migration 0081), ein geloeschtes Symbol wird beim Rendern einfach
    # uebersprungen (siehe Frontend), kein Fremdschluessel/keine Sperre noetig.
    symbol = await _get_symbol_or_404(session, symbol_id)
    await storage_service.delete_object(symbol.object_key)
    await session.delete(symbol)
    await session.flush()
