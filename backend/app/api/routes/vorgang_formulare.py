from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_recht, require_roles
from app.models.anlage import Anlage
from app.models.formular import Formular, VorgangFormular
from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.standort import Standort
from app.models.user import User
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.formular import (
    FormularVerfuegbar,
    VorgangFormularRead,
    VorgangFormularStart,
    VorgangFormularUpdate,
)
from app.services import formular_service, storage_service
from app.services.event_bus import event_bus
from app.services.pdf_service import generate_formular_pdf
from app.services.rechte_service import ist_auf_zugewiesene_kunden_beschraenkt
from app.services.vorgang_completion_service import VORGANG_STATUS_GESCHLOSSEN
from app.services.zuweisung_service import assigned_kunde_ids

router = APIRouter(
    prefix="/api/vorgang-formulare",
    tags=["vorgang-formulare"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("vorgaenge", "sehen")),
    ],
)

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


async def _require_own_vorgang(session: AsyncSession, auth: AuthContext, vorgang_id: UUID) -> Vorgang:
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    beschraenkt = await ist_auf_zugewiesene_kunden_beschraenkt(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    )
    if beschraenkt and vorgang.kunde_id not in await assigned_kunde_ids(session, auth.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    return vorgang


async def _get_own_vorgang_formular(
    session: AsyncSession, auth: AuthContext, vorgang_formular_id: UUID
) -> VorgangFormular:
    vorgang_formular = await session.get(VorgangFormular, vorgang_formular_id)
    if vorgang_formular is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Formular-Ausfüllung nicht gefunden")
    await _require_own_vorgang(session, auth, vorgang_formular.vorgang_id)
    return vorgang_formular


@router.get("/verfuegbar", response_model=list[FormularVerfuegbar])
async def list_verfuegbare_formulare(
    vorgang_id: UUID = Query(...),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[FormularVerfuegbar]:
    vorgang = await _require_own_vorgang(session, auth, vorgang_id)
    return await formular_service.verfuegbare_formulare_fuer(session, vorgang)


@router.get("", response_model=list[VorgangFormularRead])
async def list_vorgang_formulare(
    vorgang_id: UUID = Query(...),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[VorgangFormularRead]:
    await _require_own_vorgang(session, auth, vorgang_id)
    result = await session.execute(
        select(VorgangFormular)
        .where(VorgangFormular.vorgang_id == vorgang_id)
        .order_by(VorgangFormular.created_at.desc())
    )
    return [formular_service.to_vorgang_formular_read(vf) for vf in result.scalars().all()]


@router.post("", response_model=VorgangFormularRead, status_code=status.HTTP_201_CREATED)
async def start_vorgang_formular(
    body: VorgangFormularStart,
    vorgang_id: UUID = Query(...),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorgangFormularRead:
    vorgang = await _require_own_vorgang(session, auth, vorgang_id)
    if vorgang.status in VORGANG_STATUS_GESCHLOSSEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vorgang ist abgeschlossen und kann nicht mehr geändert werden",
        )

    formular = await session.get(Formular, body.formular_id)
    if formular is None or not formular.aktiv:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Formular nicht gefunden")

    felder = await formular_service.felder_fuer(session, formular.id)
    kunde = await session.get(Kunde, vorgang.kunde_id) if vorgang.kunde_id else None
    anlage = await session.get(Anlage, vorgang.anlage_id) if vorgang.anlage_id else None
    standort = await session.get(Standort, vorgang.standort_id) if vorgang.standort_id else None
    zugewiesener = (
        await session.get(User, vorgang.zugewiesener_user_id) if vorgang.zugewiesener_user_id else None
    )
    vorgang_formular = VorgangFormular(
        mandant_id=auth.mandant_id,
        vorgang_id=vorgang_id,
        formular_id=formular.id,
        formular_snapshot=formular_service.snapshot_von(formular, felder),
        antworten=formular_service.auto_fill_werte(
            felder, vorgang, kunde, anlage, standort, zugewiesener.name if zugewiesener else None
        ),
        ausgefuellt_von=auth.user_id,
    )
    session.add(vorgang_formular)
    await session.flush()
    await session.refresh(vorgang_formular)
    return formular_service.to_vorgang_formular_read(vorgang_formular)


@router.get("/{vorgang_formular_id}", response_model=VorgangFormularRead)
async def get_vorgang_formular(
    vorgang_formular_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorgangFormularRead:
    vorgang_formular = await _get_own_vorgang_formular(session, auth, vorgang_formular_id)
    return formular_service.to_vorgang_formular_read(vorgang_formular)


@router.get("/{vorgang_formular_id}/pdf")
async def vorgang_formular_pdf(
    vorgang_formular_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    vorgang_formular = await _get_own_vorgang_formular(session, auth, vorgang_formular_id)
    if vorgang_formular.status != "abgeschlossen":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nur ein abgeschlossenes Formular kann als PDF exportiert werden",
        )
    vorgang = await session.get(Vorgang, vorgang_formular.vorgang_id)
    mandant = await session.get(Mandant, auth.mandant_id)

    bilder: dict[str, bytes] = {}
    for feld in vorgang_formular.formular_snapshot.get("felder", []):
        if feld["feld_typ"] not in formular_service.FELDTYPEN_MIT_DATEI:
            continue
        antwort = vorgang_formular.antworten.get(feld["id"])
        if isinstance(antwort, dict) and antwort.get("key"):
            bilder[feld["id"]] = await storage_service.download_bytes(antwort["key"])

    pdf_bytes = generate_formular_pdf(mandant, vorgang, vorgang_formular, bilder)
    formular_name = vorgang_formular.formular_snapshot.get("name", "Formular")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'inline; filename="{formular_name}-{vorgang.vorgangsnummer}.pdf"'
            )
        },
    )


@router.patch("/{vorgang_formular_id}", response_model=VorgangFormularRead)
async def update_vorgang_formular(
    vorgang_formular_id: UUID,
    body: VorgangFormularUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorgangFormularRead:
    vorgang_formular = await _get_own_vorgang_formular(session, auth, vorgang_formular_id)
    if vorgang_formular.status != "offen":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Formular ist bereits abgeschlossen"
        )
    vorgang_formular.antworten = body.antworten
    await session.flush()
    await session.refresh(vorgang_formular)
    return formular_service.to_vorgang_formular_read(vorgang_formular)


@router.post("/{vorgang_formular_id}/abschliessen", response_model=VorgangFormularRead)
async def abschliessen_vorgang_formular(
    vorgang_formular_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorgangFormularRead:
    vorgang_formular = await _get_own_vorgang_formular(session, auth, vorgang_formular_id)
    if vorgang_formular.status != "offen":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Formular ist bereits abgeschlossen"
        )

    pflichtfelder = [
        f["label"]
        for f in vorgang_formular.formular_snapshot.get("felder", [])
        if f["pflichtfeld"] and not vorgang_formular.antworten.get(f["id"])
    ]
    if pflichtfelder:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Pflichtfelder fehlen: {', '.join(pflichtfelder)}",
        )

    vorgang_formular.status = "abgeschlossen"
    vorgang_formular.abgeschlossen_am = datetime.now(timezone.utc)

    session.add(
        VorgangEvent(
            mandant_id=auth.mandant_id,
            vorgang_id=vorgang_formular.vorgang_id,
            event_type="formular",
            author_user_id=auth.user_id,
            body=vorgang_formular.formular_snapshot.get("name"),
            payload={"vorgang_formular_id": str(vorgang_formular.id)},
            ref_entity_type="vorgang_formular",
            ref_entity_id=vorgang_formular.id,
            kundensichtbar=vorgang_formular.kundensichtbar,
        )
    )
    await session.flush()
    await session.refresh(vorgang_formular)

    await event_bus.publish(
        auth.mandant_id,
        "vorgang_event",
        {"vorgang_id": str(vorgang_formular.vorgang_id), "event_type": "formular"},
    )
    return formular_service.to_vorgang_formular_read(vorgang_formular)


@router.delete("/{vorgang_formular_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vorgang_formular(
    vorgang_formular_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    vorgang_formular = await _get_own_vorgang_formular(session, auth, vorgang_formular_id)
    if vorgang_formular.status != "offen":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nur eine noch nicht abgeschlossene Ausfüllung kann verworfen werden",
        )
    await session.delete(vorgang_formular)
    await session.flush()


@router.post("/{vorgang_formular_id}/dateien")
async def datei_hochladen(
    vorgang_formular_id: UUID,
    feld_id: str,
    file: UploadFile,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Laedt eine Datei fuer ein Foto- oder Unterschrift-Feld hoch und gibt
    den Storage-Key zurueck -- das Frontend legt diesen anschliessend per
    PATCH als Antwort fuer feld_id ab (siehe update_vorgang_formular)."""
    vorgang_formular = await _get_own_vorgang_formular(session, auth, vorgang_formular_id)
    if vorgang_formular.status != "offen":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Formular ist bereits abgeschlossen"
        )
    feld = next(
        (f for f in vorgang_formular.formular_snapshot.get("felder", []) if f["id"] == feld_id),
        None,
    )
    if feld is None or feld["feld_typ"] not in formular_service.FELDTYPEN_MIT_DATEI:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ungültiges Feld")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Nur Bilddateien werden unterstützt"
        )

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Datei zu groß (max. 15 MB)")

    key = storage_service.new_object_key(vorgang_formular.vorgang_id, file.filename or "datei.jpg")
    await storage_service.upload_bytes(key, data, file.content_type)

    return {
        "feld_id": feld_id,
        "key": key,
        "content_type": file.content_type,
        "size": len(data),
        "url": storage_service.presigned_get_url(key),
    }
