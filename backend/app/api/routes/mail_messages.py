import base64
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_module, require_roles
from app.models.mail_account import MailAccount
from app.models.mail_attachment import MailAttachment
from app.models.mail_folder import MailFolder
from app.models.mail_message import MailMessage
from app.schemas.mail_message import (
    MailAttachmentRead,
    MailFolderRead,
    MailMessageDetail,
    MailMessageListItem,
    MailMessageListResponse,
    MailMessageUpdate,
    MailNachrichtAntworten,
    MailNachrichtSenden,
    MailNachrichtWeiterleiten,
)
from app.services import storage_service
from app.services.mail_send_service import sende_nachricht

router = APIRouter(
    tags=["mail-messages"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_module("postfach")),
    ],
)

_SEITENGROESSE = 30


async def _eigenes_konto(session: AsyncSession, auth: AuthContext, account_id: UUID) -> MailAccount:
    account = await session.get(MailAccount, account_id)
    if account is None or account.user_id != auth.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Postfach nicht gefunden")
    return account


async def _eigene_nachricht(session: AsyncSession, auth: AuthContext, message_id: UUID) -> MailMessage:
    nachricht = await session.get(MailMessage, message_id)
    if nachricht is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nachricht nicht gefunden")
    account = await session.get(MailAccount, nachricht.mail_account_id)
    if account is None or account.user_id != auth.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nachricht nicht gefunden")
    return nachricht


def _ausschnitt(text: str | None, laenge: int = 140) -> str:
    if not text:
        return ""
    einzeilig = " ".join(text.split())
    return einzeilig if len(einzeilig) <= laenge else einzeilig[:laenge].rstrip() + "…"


def _encode_cursor(datum: datetime, id_: UUID) -> str:
    raw = f"{datum.isoformat()}|{id_}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        datum, id_ = raw.rsplit("|", 1)
        return datetime.fromisoformat(datum), UUID(id_)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ungültiger Cursor") from exc


@router.get("/api/mail-accounts/{account_id}/folders", response_model=list[MailFolderRead])
async def list_folders(
    account_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[MailFolder]:
    await _eigenes_konto(session, auth, account_id)
    result = await session.execute(
        select(MailFolder)
        .where(MailFolder.mail_account_id == account_id)
        .order_by(MailFolder.sortierung, MailFolder.anzeigename)
    )
    return list(result.scalars().all())


@router.get("/api/mail-folders/{folder_id}/messages", response_model=MailMessageListResponse)
async def list_messages(
    folder_id: UUID,
    suche: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MailMessageListResponse:
    ordner = await session.get(MailFolder, folder_id)
    if ordner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ordner nicht gefunden")
    await _eigenes_konto(session, auth, ordner.mail_account_id)

    # coalesce(datum, created_at) als Sortierschluessel -- ohne Date-Header
    # (kommt vereinzelt vor) faellt eine Nachricht sonst still aus jeder
    # zeitbasierten Sortierung/Cursor-Paginierung heraus.
    sortierdatum = func.coalesce(MailMessage.datum, MailMessage.created_at)
    stmt = select(MailMessage).where(MailMessage.folder_id == folder_id)
    if suche:
        stmt = stmt.where(MailMessage.search_vector.op("@@")(func.plainto_tsquery("german", suche)))
    if cursor:
        cursor_datum, cursor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                sortierdatum < cursor_datum,
                (sortierdatum == cursor_datum) & (MailMessage.id < cursor_id),
            )
        )
    stmt = stmt.order_by(sortierdatum.desc(), MailMessage.id.desc()).limit(_SEITENGROESSE + 1)

    zeilen = list((await session.execute(stmt)).scalars().all())
    weitere_seite = len(zeilen) > _SEITENGROESSE
    zeilen = zeilen[:_SEITENGROESSE]

    anhang_zahlen: dict[UUID, int] = {}
    if zeilen:
        anhang_stmt = (
            select(MailAttachment.message_id, func.count())
            .where(MailAttachment.message_id.in_([z.id for z in zeilen]))
            .group_by(MailAttachment.message_id)
        )
        anhang_zahlen = dict((await session.execute(anhang_stmt)).all())

    items = [
        MailMessageListItem(
            id=z.id,
            folder_id=z.folder_id,
            von_name=z.von_name,
            von_adresse=z.von_adresse,
            betreff=z.betreff,
            ausschnitt=_ausschnitt(z.body_text),
            datum=z.datum,
            gelesen=z.gelesen,
            hat_anhang=anhang_zahlen.get(z.id, 0) > 0,
        )
        for z in zeilen
    ]
    next_cursor = None
    if weitere_seite and zeilen:
        letzte = zeilen[-1]
        next_cursor = _encode_cursor(letzte.datum or letzte.created_at, letzte.id)
    return MailMessageListResponse(items=items, next_cursor=next_cursor)


@router.get("/api/mail-messages/{message_id}", response_model=MailMessageDetail)
async def get_message(
    message_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MailMessageDetail:
    nachricht = await _eigene_nachricht(session, auth, message_id)
    anhaenge = list(
        (
            await session.execute(select(MailAttachment).where(MailAttachment.message_id == message_id))
        ).scalars().all()
    )
    return MailMessageDetail(
        id=nachricht.id,
        folder_id=nachricht.folder_id,
        von_name=nachricht.von_name,
        von_adresse=nachricht.von_adresse,
        an=nachricht.an,
        cc=nachricht.cc,
        betreff=nachricht.betreff,
        body_text=nachricht.body_text,
        body_html=nachricht.body_html,
        datum=nachricht.datum,
        gelesen=nachricht.gelesen,
        message_id_header=nachricht.message_id_header,
        anhaenge=[MailAttachmentRead.model_validate(a) for a in anhaenge],
    )


@router.patch("/api/mail-messages/{message_id}", response_model=MailMessageDetail)
async def update_message(
    message_id: UUID,
    body: MailMessageUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MailMessageDetail:
    nachricht = await _eigene_nachricht(session, auth, message_id)
    nachricht.gelesen = body.gelesen
    await session.flush()
    return await get_message(message_id, auth=auth, session=session)


@router.get("/api/mail-messages/{message_id}/attachments/{attachment_id}/url")
async def get_attachment_url(
    message_id: UUID,
    attachment_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    await _eigene_nachricht(session, auth, message_id)
    anhang = await session.get(MailAttachment, attachment_id)
    if anhang is None or anhang.message_id != message_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anhang nicht gefunden")
    return {"url": storage_service.presigned_get_url(anhang.object_key)}


@router.post("/api/mail-accounts/{account_id}/senden", status_code=status.HTTP_204_NO_CONTENT)
async def senden(
    account_id: UUID,
    body: MailNachrichtSenden,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    account = await _eigenes_konto(session, auth, account_id)
    await sende_nachricht(
        account, an=body.an, cc=body.cc, bcc=body.bcc, betreff=body.betreff, text=body.text
    )


@router.post("/api/mail-messages/{message_id}/antworten", status_code=status.HTTP_204_NO_CONTENT)
async def antworten(
    message_id: UUID,
    body: MailNachrichtAntworten,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    original = await _eigene_nachricht(session, auth, message_id)
    account = await session.get(MailAccount, original.mail_account_id)
    betreff = original.betreff if original.betreff.lower().startswith("re:") else f"Re: {original.betreff}"
    references = " ".join(
        filter(None, [original.references_header, original.message_id_header])
    ) or None
    await sende_nachricht(
        account,
        an=body.an,
        cc=body.cc,
        betreff=betreff,
        text=body.text,
        in_reply_to=original.message_id_header,
        references=references,
    )


@router.post("/api/mail-messages/{message_id}/weiterleiten", status_code=status.HTTP_204_NO_CONTENT)
async def weiterleiten(
    message_id: UUID,
    body: MailNachrichtWeiterleiten,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    original = await _eigene_nachricht(session, auth, message_id)
    account = await session.get(MailAccount, original.mail_account_id)
    betreff = original.betreff if original.betreff.lower().startswith("fwd:") else f"Fwd: {original.betreff}"
    zitat = (
        f"\n\n---------- Weitergeleitete Nachricht ----------\n"
        f"Von: {original.von_name or ''} <{original.von_adresse or ''}>\n"
        f"Betreff: {original.betreff}\n\n{original.body_text or ''}"
    )
    await sende_nachricht(
        account, an=body.an, betreff=betreff, text=f"{body.text}{zitat}"
    )
