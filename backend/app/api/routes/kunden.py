from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.core.security import hash_password
from app.models.anlage import Anlage
from app.models.kunde import Kunde
from app.models.kundenportal import KundenportalZugang
from app.models.tag import Tag, TagAssignment
from app.models.vorgang import Vorgang
from app.schemas.kunde import KundeCreate, KundeRead, KundeUpdate
from app.schemas.kundenportal import (
    KundenportalZugangCreate,
    KundenportalZugangRead,
    KundenportalZugangUpdate,
)
from app.schemas.profile import KundeProfil
from app.services.numbering_service import next_kundennummer

# super_admin is deliberately excluded: fachliche Daten sind immer
# mandantengebunden, und ein nicht-impersonierender super_admin hat kein
# mandant_id im Token. Zugriff läuft für die Plattform-Rolle ausschließlich
# über "Login als Mandant" (das Token trägt dann role=mandant_admin).
router = APIRouter(
    prefix="/api/kunden",
    tags=["kunden"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)


@router.get("", response_model=list[KundeRead])
async def list_kunden(
    q: str | None = Query(default=None, description="Suche in Name/Kundennummer"),
    session: AsyncSession = Depends(get_db),
) -> list[Kunde]:
    stmt = select(Kunde).order_by(Kunde.name)
    if q:
        stmt = stmt.where(Kunde.name.ilike(f"%{q}%"))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=KundeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_kunde(
    body: KundeCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Kunde:
    kundennummer = body.kundennummer or await next_kundennummer(session, auth.mandant_id)
    kunde = Kunde(
        mandant_id=auth.mandant_id,
        kundennummer=kundennummer,
        name=body.name,
        typ=body.typ,
        ansprechpartner=body.ansprechpartner,
        adresse=body.adresse,
        notiz=body.notiz,
    )
    session.add(kunde)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Kundennummer bereits vergeben"
        ) from exc
    return kunde


@router.get("/{kunde_id}", response_model=KundeRead)
async def get_kunde(kunde_id: UUID, session: AsyncSession = Depends(get_db)) -> Kunde:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
    return kunde


@router.get("/{kunde_id}/profil", response_model=KundeProfil)
async def get_kunde_profil(kunde_id: UUID, session: AsyncSession = Depends(get_db)) -> KundeProfil:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")

    anlagen_result = await session.execute(
        select(Anlage).where(Anlage.kunde_id == kunde_id).order_by(Anlage.bezeichnung)
    )
    vorgaenge_result = await session.execute(
        select(Vorgang)
        .where(Vorgang.kunde_id == kunde_id)
        .order_by(Vorgang.last_activity_at.desc())
        .limit(50)
    )
    tags_result = await session.execute(
        select(Tag)
        .join(TagAssignment, TagAssignment.tag_id == Tag.id)
        .where(TagAssignment.entity_type == "kunde", TagAssignment.entity_id == kunde_id)
    )

    return KundeProfil(
        **KundeRead.model_validate(kunde).model_dump(),
        anlagen=list(anlagen_result.scalars().all()),
        vorgaenge=list(vorgaenge_result.scalars().all()),
        tags=list(tags_result.scalars().all()),
    )


@router.patch(
    "/{kunde_id}",
    response_model=KundeRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_kunde(
    kunde_id: UUID, body: KundeUpdate, session: AsyncSession = Depends(get_db)
) -> Kunde:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(kunde, field, value)
    await session.flush()
    if changes:
        await session.refresh(kunde)
    return kunde


@router.get("/{kunde_id}/portal-zugaenge", response_model=list[KundenportalZugangRead])
async def list_portal_zugaenge(
    kunde_id: UUID, session: AsyncSession = Depends(get_db)
) -> list[KundenportalZugang]:
    if await session.get(Kunde, kunde_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
    result = await session.execute(
        select(KundenportalZugang).where(KundenportalZugang.kunde_id == kunde_id)
    )
    return list(result.scalars().all())


@router.post(
    "/{kunde_id}/portal-zugaenge",
    response_model=KundenportalZugangRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_portal_zugang(
    kunde_id: UUID,
    body: KundenportalZugangCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> KundenportalZugang:
    if await session.get(Kunde, kunde_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
    if len(body.password) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Passwort muss mindestens 10 Zeichen haben"
        )

    zugang = KundenportalZugang(
        mandant_id=auth.mandant_id,
        kunde_id=kunde_id,
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name,
    )
    session.add(zugang)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="E-Mail wird bereits verwendet"
        ) from exc
    return zugang


@router.patch(
    "/{kunde_id}/portal-zugaenge/{zugang_id}",
    response_model=KundenportalZugangRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_portal_zugang(
    kunde_id: UUID,
    zugang_id: UUID,
    body: KundenportalZugangUpdate,
    session: AsyncSession = Depends(get_db),
) -> KundenportalZugang:
    zugang = await session.get(KundenportalZugang, zugang_id)
    if zugang is None or zugang.kunde_id != kunde_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zugang nicht gefunden")

    changes = body.model_dump(exclude_unset=True, exclude={"password"})
    for field, value in changes.items():
        setattr(zugang, field, value)
    if body.password is not None:
        if len(body.password) < 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwort muss mindestens 10 Zeichen haben",
            )
        zugang.password_hash = hash_password(body.password)
        changes["password_hash"] = zugang.password_hash

    await session.flush()
    if changes:
        await session.refresh(zugang)
    return zugang
