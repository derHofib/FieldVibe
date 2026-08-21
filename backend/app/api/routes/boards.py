from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.board import Board
from app.schemas.board import (
    BoardAnhangUpload,
    BoardAnhangUrl,
    BoardCreate,
    BoardHintergrundUrl,
    BoardListItem,
    BoardRead,
    BoardUpdate,
)
from app.services import storage_service

router = APIRouter(
    prefix="/api/boards",
    tags=["boards"],
    dependencies=[Depends(require_roles("mandant_admin", "custom"))],
)

_HINTERGRUND_MAX_BYTES = 8 * 1024 * 1024
_ANHANG_MAX_BYTES = 15 * 1024 * 1024


def _anhang_praefix(board_id: UUID) -> str:
    return f"boards/{board_id}/anhang/"


def _anhang_key_pruefen(board_id: UUID, key: str) -> None:
    # Der Key kommt vom Client (steckt im Node-data, nicht in der DB) --
    # ohne diese Pruefung koennte ein Nutzer ueber die Query-Param beliebige
    # Objekte eines fremden Boards/Mandanten abfragen oder loeschen.
    if not key.startswith(_anhang_praefix(board_id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anhang nicht gefunden")


async def _get_board(session: AsyncSession, board_id: UUID) -> Board:
    board = await session.get(Board, board_id)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board nicht gefunden")
    return board


@router.get("", response_model=list[BoardListItem])
async def list_boards(
    session: AsyncSession = Depends(get_db),
) -> list[Board]:
    stmt = select(Board).order_by(Board.updated_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=BoardRead, status_code=status.HTTP_201_CREATED)
async def create_board(
    body: BoardCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Board:
    board = Board(
        mandant_id=auth.mandant_id,
        name=body.name,
        board_typ=body.board_typ,
        inhalt_json=body.inhalt_json,
        erstellt_von=auth.user_id,
    )
    session.add(board)
    await session.flush()
    return board


@router.get("/{board_id}", response_model=BoardRead)
async def get_board(
    board_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> Board:
    return await _get_board(session, board_id)


@router.patch("/{board_id}", response_model=BoardRead)
async def update_board(
    board_id: UUID,
    body: BoardUpdate,
    session: AsyncSession = Depends(get_db),
) -> Board:
    board = await _get_board(session, board_id)
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(board, field, value)
    await session.flush()
    if changes:
        await session.refresh(board)
    return board


@router.delete("/{board_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_board(
    board_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> None:
    board = await _get_board(session, board_id)
    if board.hintergrund_object_key is not None:
        await storage_service.delete_object(board.hintergrund_object_key)
    await session.delete(board)
    await session.flush()


@router.post("/{board_id}/hintergrund", response_model=BoardRead)
async def upload_board_hintergrund(
    board_id: UUID,
    file: UploadFile,
    session: AsyncSession = Depends(get_db),
) -> Board:
    board = await _get_board(session, board_id)
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Nur Bilddateien werden unterstützt"
        )

    data = await file.read()
    if len(data) > _HINTERGRUND_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Datei zu groß (max. 8 MB)"
        )

    alter_key = board.hintergrund_object_key
    key = storage_service.new_board_hintergrund_key(board_id, file.filename or "grundriss.png")
    await storage_service.upload_bytes(key, data, file.content_type)
    board.hintergrund_object_key = key
    await session.flush()
    await session.refresh(board)

    if alter_key is not None:
        await storage_service.delete_object(alter_key)
    return board


@router.delete("/{board_id}/hintergrund", response_model=BoardRead)
async def remove_board_hintergrund(
    board_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> Board:
    board = await _get_board(session, board_id)
    alter_key = board.hintergrund_object_key
    board.hintergrund_object_key = None
    await session.flush()
    await session.refresh(board)

    if alter_key is not None:
        await storage_service.delete_object(alter_key)
    return board


@router.get("/{board_id}/hintergrund-url", response_model=BoardHintergrundUrl)
async def get_board_hintergrund_url(
    board_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> BoardHintergrundUrl:
    board = await _get_board(session, board_id)
    if board.hintergrund_object_key is None:
        return BoardHintergrundUrl(url=None)
    return BoardHintergrundUrl(url=storage_service.presigned_get_url(board.hintergrund_object_key))


@router.post("/{board_id}/anhang", response_model=BoardAnhangUpload)
async def upload_board_anhang(
    board_id: UUID,
    file: UploadFile,
    session: AsyncSession = Depends(get_db),
) -> BoardAnhangUpload:
    await _get_board(session, board_id)
    data = await file.read()
    if len(data) > _ANHANG_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Datei zu groß (max. 15 MB)"
        )

    dateiname = file.filename or "anhang"
    key = storage_service.new_board_anhang_key(board_id, dateiname)
    await storage_service.upload_bytes(key, data, file.content_type or "application/octet-stream")
    return BoardAnhangUpload(object_key=key, url=storage_service.presigned_get_url(key), dateiname=dateiname)


@router.get("/{board_id}/anhang-url", response_model=BoardAnhangUrl)
async def get_board_anhang_url(
    board_id: UUID,
    key: str,
    session: AsyncSession = Depends(get_db),
) -> BoardAnhangUrl:
    await _get_board(session, board_id)
    _anhang_key_pruefen(board_id, key)
    return BoardAnhangUrl(url=storage_service.presigned_get_url(key))


@router.delete("/{board_id}/anhang", status_code=status.HTTP_204_NO_CONTENT)
async def delete_board_anhang(
    board_id: UUID,
    key: str,
    session: AsyncSession = Depends(get_db),
) -> None:
    await _get_board(session, board_id)
    _anhang_key_pruefen(board_id, key)
    await storage_service.delete_object(key)
