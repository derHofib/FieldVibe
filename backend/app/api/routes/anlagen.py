from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.anlage import Anlage
from app.models.kunde import Kunde
from app.models.tag import Tag, TagAssignment
from app.models.vorgang import Vorgang
from app.models.zeiterfassung import Zeiterfassung
from app.schemas.anlage import AnlageCreate, AnlageRead, AnlageUpdate
from app.schemas.kunde import KundeRead
from app.schemas.profile import AnlageProfil
from app.services.zuweisung_service import assigned_kunde_ids

router = APIRouter(
    prefix="/api/anlagen",
    tags=["anlagen"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)


async def _require_own_kunde(session: AsyncSession, kunde_id: UUID) -> Kunde:
    # RLS already hides other tenants' rows from this SELECT, so a foreign
    # kunde_id resolves to None here -- this is what actually stops an
    # Anlage from being linked to another mandant's Kunde (the FK
    # constraint alone would not catch it: FK existence checks run with the
    # table owner's privileges and ignore RLS).
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kunde nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    return kunde


@router.get("", response_model=list[AnlageRead])
async def list_anlagen(
    kunde_id: UUID | None = Query(default=None),
    objekttyp: str | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Anlage]:
    stmt = select(Anlage).order_by(Anlage.bezeichnung)
    if kunde_id:
        stmt = stmt.where(Anlage.kunde_id == kunde_id)
    if objekttyp:
        stmt = stmt.where(Anlage.objekttyp == objekttyp)
    if auth.role == "techniker":
        # Interne Objekte (Fahrzeuge/Lager/Baustellen, kunde_id NULL) sind
        # keine Kundendaten und daher unabhaengig von der Kunde-Zuweisung
        # immer sichtbar -- nur echte Kundenanlagen werden eingeschraenkt.
        zugewiesene = await assigned_kunde_ids(session, auth.user_id)
        stmt = stmt.where(or_(Anlage.kunde_id.is_(None), Anlage.kunde_id.in_(zugewiesene)))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=AnlageRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_anlage(
    body: AnlageCreate,
    auth=Depends(require_roles("mandant_admin", "disponent")),
    session: AsyncSession = Depends(get_db),
) -> Anlage:
    if body.kunde_id is not None:
        await _require_own_kunde(session, body.kunde_id)

    anlage = Anlage(
        mandant_id=auth.mandant_id,
        kunde_id=body.kunde_id,
        objekttyp=body.objekttyp,
        bezeichnung=body.bezeichnung,
        adresse=body.adresse,
        anlagentyp=body.anlagentyp,
        qr_code=body.qr_code,
        stammdaten=body.stammdaten,
        geo_lat=body.geo_lat,
        geo_lng=body.geo_lng,
    )
    session.add(anlage)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="QR-Code bereits vergeben"
        ) from exc
    return anlage


async def _require_anlage_zugriff(session: AsyncSession, auth: AuthContext, anlage: Anlage) -> None:
    if (
        auth.role == "techniker"
        and anlage.kunde_id is not None
        and anlage.kunde_id not in await assigned_kunde_ids(session, auth.user_id)
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anlage nicht gefunden")


@router.get("/by-qr/{qr_code}", response_model=AnlageRead)
async def get_anlage_by_qr(
    qr_code: str,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Anlage:
    # Registered before "/{anlage_id}" so "by-qr" isn't swallowed as a UUID
    # path param. qr_code is globally unique (Abschnitt 4.2), but RLS still
    # scopes this SELECT to the caller's own mandant -- scanning a QR code
    # that happens to belong to another tenant's Anlage resolves to 404,
    # not a cross-tenant leak.
    result = await session.execute(select(Anlage).where(Anlage.qr_code == qr_code))
    anlage = result.scalar_one_or_none()
    if anlage is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Keine Anlage mit diesem QR-Code gefunden"
        )
    if (
        auth.role == "techniker"
        and anlage.kunde_id is not None
        and anlage.kunde_id not in await assigned_kunde_ids(session, auth.user_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Keine Anlage mit diesem QR-Code gefunden"
        )
    return anlage


@router.get("/{anlage_id}", response_model=AnlageRead)
async def get_anlage(
    anlage_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Anlage:
    anlage = await session.get(Anlage, anlage_id)
    if anlage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anlage nicht gefunden")
    await _require_anlage_zugriff(session, auth, anlage)
    return anlage


@router.get("/{anlage_id}/profil", response_model=AnlageProfil)
async def get_anlage_profil(
    anlage_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AnlageProfil:
    anlage = await session.get(Anlage, anlage_id)
    if anlage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anlage nicht gefunden")
    await _require_anlage_zugriff(session, auth, anlage)
    kunde = await session.get(Kunde, anlage.kunde_id) if anlage.kunde_id is not None else None

    vorgaenge_result = await session.execute(
        select(Vorgang)
        .where(Vorgang.anlage_id == anlage_id)
        .order_by(Vorgang.last_activity_at.desc())
        .limit(50)
    )
    tags_result = await session.execute(
        select(Tag)
        .join(TagAssignment, TagAssignment.tag_id == Tag.id)
        .where(TagAssignment.entity_type == "anlage", TagAssignment.entity_id == anlage_id)
    )

    # Auswertung ueber ALLE Vorgaenge dieser Anlage, nicht nur die oben auf
    # 50 begrenzte Liste -- sonst waeren Status-Zaehlung und Stundensumme
    # bei einer langlebigen Anlage falsch.
    status_result = await session.execute(
        select(Vorgang.status, func.count())
        .where(Vorgang.anlage_id == anlage_id)
        .group_by(Vorgang.status)
    )
    vorgaenge_nach_status = {status: count for status, count in status_result.all()}

    sekunden_gesamt = await session.scalar(
        select(func.coalesce(func.sum(func.extract("epoch", Zeiterfassung.ende_at - Zeiterfassung.start_at)), 0))
        .select_from(Zeiterfassung)
        .join(Vorgang, Vorgang.id == Zeiterfassung.vorgang_id)
        .where(Vorgang.anlage_id == anlage_id, Zeiterfassung.ende_at.isnot(None))
    )
    stunden_gesamt = (Decimal(sekunden_gesamt or 0) / Decimal(3600)).quantize(Decimal("0.1"))

    return AnlageProfil(
        **AnlageRead.model_validate(anlage).model_dump(),
        kunde=KundeRead.model_validate(kunde) if kunde is not None else None,
        vorgaenge=list(vorgaenge_result.scalars().all()),
        tags=list(tags_result.scalars().all()),
        vorgaenge_nach_status=vorgaenge_nach_status,
        zeiterfassung_stunden_gesamt=stunden_gesamt,
    )


@router.patch(
    "/{anlage_id}",
    response_model=AnlageRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_anlage(
    anlage_id: UUID, body: AnlageUpdate, session: AsyncSession = Depends(get_db)
) -> Anlage:
    anlage = await session.get(Anlage, anlage_id)
    if anlage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anlage nicht gefunden")

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(anlage, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="QR-Code bereits vergeben"
        ) from exc
    if changes:
        await session.refresh(anlage)
    return anlage
