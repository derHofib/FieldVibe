from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.dsgvo_dokument import DSGVO_DOKUMENT_TYPEN, DsgvoDokument
from app.schemas.dsgvo_dokument import DsgvoDokumentRead
from app.services import storage_service
from app.services.audit_service import log_action

# Erlaubte Dateitypen fuer Compliance-Dokumente (Vertraege/Vorlagen/
# gescannte Unterschriften-Seiten) -- kein Bild-only-Limit wie beim
# Kunden-Logo, aber trotzdem eingeschraenkt statt "alles".
_ERLAUBTE_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/png",
    "image/jpeg",
}
_MAX_BYTES = 10 * 1024 * 1024

router = APIRouter(
    prefix="/api/admin/dsgvo-dokumente",
    tags=["super-admin: dsgvo"],
    dependencies=[Depends(require_roles("super_admin"))],
)


@router.get("", response_model=list[DsgvoDokumentRead])
async def list_dsgvo_dokumente(session: AsyncSession = Depends(get_db)) -> list[DsgvoDokument]:
    result = await session.execute(select(DsgvoDokument).order_by(DsgvoDokument.typ))
    return list(result.scalars().all())


@router.post("/{typ}", response_model=DsgvoDokumentRead, status_code=status.HTTP_201_CREATED)
async def upload_dsgvo_dokument(
    typ: str,
    file: UploadFile,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DsgvoDokument:
    if typ not in DSGVO_DOKUMENT_TYPEN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unbekannter Dokumenttyp")
    if not file.content_type or file.content_type not in _ERLAUBTE_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur PDF, Word (.doc/.docx) oder Bilddateien (PNG/JPEG) werden unterstützt",
        )

    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Datei zu groß (max. 10 MB)")

    result = await session.execute(select(DsgvoDokument).where(DsgvoDokument.typ == typ))
    bestehend = result.scalar_one_or_none()
    alter_key = bestehend.object_key if bestehend else None

    key = storage_service.new_dsgvo_dokument_key(typ, file.filename or "dokument")
    await storage_service.upload_bytes(key, data, file.content_type)

    if bestehend is not None:
        bestehend.dateiname = file.filename or "dokument"
        bestehend.object_key = key
        bestehend.content_type = file.content_type
        bestehend.groesse_bytes = len(data)
        bestehend.hochgeladen_von = auth.user_id
        dokument = bestehend
    else:
        dokument = DsgvoDokument(
            typ=typ,
            dateiname=file.filename or "dokument",
            object_key=key,
            content_type=file.content_type,
            groesse_bytes=len(data),
            hochgeladen_von=auth.user_id,
        )
        session.add(dokument)

    await session.flush()
    await session.refresh(dokument)

    if alter_key is not None:
        await storage_service.delete_object(alter_key)

    await log_action(
        session,
        aktion="dsgvo_dokument_hochgeladen",
        actor_user_id=auth.user_id,
        entity_type="dsgvo_dokument",
        entity_id=dokument.id,
        payload={"typ": typ, "dateiname": dokument.dateiname},
    )
    return dokument


@router.get("/{typ}/download-url")
async def get_dsgvo_dokument_download_url(
    typ: str, session: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    result = await session.execute(select(DsgvoDokument).where(DsgvoDokument.typ == typ))
    dokument = result.scalar_one_or_none()
    if dokument is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kein Dokument hochgeladen")
    return {"url": storage_service.presigned_get_url(dokument.object_key)}


@router.delete("/{typ}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dsgvo_dokument(
    typ: str,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    result = await session.execute(select(DsgvoDokument).where(DsgvoDokument.typ == typ))
    dokument = result.scalar_one_or_none()
    if dokument is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kein Dokument hochgeladen")

    object_key = dokument.object_key
    await session.delete(dokument)
    await session.flush()
    await storage_service.delete_object(object_key)

    await log_action(
        session,
        aktion="dsgvo_dokument_geloescht",
        actor_user_id=auth.user_id,
        entity_type="dsgvo_dokument",
        entity_id=dokument.id,
        payload={"typ": typ},
    )
