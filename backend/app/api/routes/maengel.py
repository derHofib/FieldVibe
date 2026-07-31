from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_module, require_roles
from app.models.mandant import Mandant
from app.models.mangel import MANGEL_SCHWEREGRADE, Mangel
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.mangel import MangelCreate, MangelRead, MangelUpdate
from app.services.pdf_service import generate_maengel_protokoll_pdf

router = APIRouter(
    prefix="/api/maengel",
    tags=["maengel"],
    dependencies=[
        Depends(require_roles("mandant_admin", "disponent", "techniker")),
        Depends(require_module("abrechnung")),
    ],
)

# Direkt per PATCH darf ein Nutzer einen Mangel nur "vor Ort" abschliessen
# oder verwerfen -- der Weg über ein Angebot (in_angebot/in_bearbeitung)
# wird ausschliesslich von den Angebot-Routen gesteuert (siehe
# app/api/routes/angebote.py), damit der Status konsistent mit einem
# tatsaechlich existierenden Angebot/Reparatur-Vorgang bleibt.
_ERLAUBTE_DIREKTE_STATUS = ("behoben", "abgelehnt")


@router.get("", response_model=list[MangelRead])
async def list_maengel(
    vorgang_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_db),
) -> list[Mangel]:
    stmt = select(Mangel).order_by(Mangel.created_at.desc())
    if vorgang_id:
        stmt = stmt.where(Mangel.vorgang_id == vorgang_id)
    if status_filter:
        stmt = stmt.where(Mangel.status == status_filter)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/protokoll/pdf")
async def maengel_protokoll_pdf(
    vorgang_id: UUID = Query(...),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    mandant = await session.get(Mandant, auth.mandant_id)
    maengel = list(
        (await session.execute(select(Mangel).where(Mangel.vorgang_id == vorgang_id))).scalars().all()
    )

    pdf_bytes = generate_maengel_protokoll_pdf(mandant, vorgang, maengel)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="Maengel-{vorgang.vorgangsnummer}.pdf"'},
    )


@router.get("/{mangel_id}", response_model=MangelRead)
async def get_mangel(mangel_id: UUID, session: AsyncSession = Depends(get_db)) -> Mangel:
    mangel = await session.get(Mangel, mangel_id)
    if mangel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mangel nicht gefunden")
    return mangel


@router.post("", response_model=MangelRead, status_code=status.HTTP_201_CREATED)
async def create_mangel(
    body: MangelCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Mangel:
    if body.schweregrad not in MANGEL_SCHWEREGRADE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ungültiger Schweregrad")

    vorgang = await session.get(Vorgang, body.vorgang_id)
    if vorgang is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if body.anlage_id is not None and body.anlage_id != vorgang.anlage_id:
        # Kein Hard-Fail auf Anlagen-Existenz per FK reicht nicht: eine
        # fremde/nicht zum Vorgang passende Anlage waere ein stiller
        # Datenfehler, kein 404 -- also explizit geprueft.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anlage gehört nicht zum angegebenen Vorgang",
        )

    mangel = Mangel(
        mandant_id=auth.mandant_id,
        vorgang_id=body.vorgang_id,
        anlage_id=body.anlage_id,
        beschreibung=body.beschreibung,
        schweregrad=body.schweregrad,
        gemeldet_von=auth.user_id,
    )
    session.add(mangel)
    await session.flush()
    await session.refresh(mangel)

    session.add(
        VorgangEvent(
            mandant_id=auth.mandant_id,
            vorgang_id=body.vorgang_id,
            event_type="mangel",
            author_user_id=auth.user_id,
            body=f"Mangel erfasst ({mangel.schweregrad}): {mangel.beschreibung}",
            payload={"mangel_id": str(mangel.id), "schweregrad": mangel.schweregrad, "status": mangel.status},
        )
    )
    await session.flush()
    return mangel


@router.patch("/{mangel_id}", response_model=MangelRead)
async def update_mangel(
    mangel_id: UUID,
    body: MangelUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Mangel:
    mangel = await session.get(Mangel, mangel_id)
    if mangel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mangel nicht gefunden")

    changes = body.model_dump(exclude_unset=True)
    if "schweregrad" in changes and changes["schweregrad"] not in MANGEL_SCHWEREGRADE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ungültiger Schweregrad")

    neuer_status = changes.get("status")
    if neuer_status is not None:
        if mangel.status != "offen" or neuer_status not in _ERLAUBTE_DIREKTE_STATUS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dieser Statuswechsel ist nur direkt aus 'offen' nach 'behoben'/'abgelehnt' erlaubt "
                "-- über ein Angebot laufende Mängel werden dort verwaltet.",
            )

    for field, value in changes.items():
        setattr(mangel, field, value)
    if neuer_status == "behoben":
        mangel.behoben_am = datetime.now(timezone.utc)

    await session.flush()
    await session.refresh(mangel)

    if neuer_status is not None:
        session.add(
            VorgangEvent(
                mandant_id=mangel.mandant_id,
                vorgang_id=mangel.vorgang_id,
                event_type="mangel",
                author_user_id=auth.user_id,
                body=f"Mangel als '{neuer_status}' markiert: {mangel.beschreibung}",
                payload={"mangel_id": str(mangel.id), "status": neuer_status},
            )
        )
        await session.flush()

    return mangel
