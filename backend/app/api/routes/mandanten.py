from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_db, require_roles
from app.backfill_geocode import backfill_geocode_fuer_mandant
from app.core.config import get_settings
from app.models.anlage import Anlage
from app.models.mandant import Mandant
from app.schemas.mandant import MandantCreate, MandantRead, MandantUpdate
from app.services.audit_service import log_action

router = APIRouter(
    prefix="/api/admin/mandanten",
    tags=["super-admin: mandanten"],
    dependencies=[Depends(require_roles("super_admin"))],
)


@router.get("", response_model=list[MandantRead])
async def list_mandanten(session: AsyncSession = Depends(get_db)) -> list[Mandant]:
    result = await session.execute(select(Mandant).order_by(Mandant.name))
    return list(result.scalars().all())


@router.post("", response_model=MandantRead, status_code=status.HTTP_201_CREATED)
async def create_mandant(
    body: MandantCreate,
    auth: AuthContext = Depends(require_roles("super_admin")),
    session: AsyncSession = Depends(get_db),
) -> Mandant:
    mandant = Mandant(
        name=body.name,
        slug=body.slug,
        branche=body.branche,
        branding=body.branding,
    )
    session.add(mandant)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Slug bereits vergeben",
        ) from exc

    # Jeder Mandant bekommt sofort einen nutzbaren Lagerort fuer die
    # Materialwirtschaft (siehe app/models/anlage.py: Lagerorte sind Anlagen
    # mit objekttyp="lager", kein eigenes Onboarding-Formular noetig).
    session.add(
        Anlage(
            mandant_id=mandant.id,
            kunde_id=None,
            objekttyp="lager",
            bezeichnung="Zentrallager",
            adresse={},
            stammdaten={},
        )
    )
    await session.flush()

    await log_action(
        session,
        aktion="mandant_erstellt",
        actor_user_id=auth.user_id,
        entity_type="mandant",
        entity_id=mandant.id,
        payload={"name": mandant.name, "slug": mandant.slug},
    )
    return mandant


@router.get("/{mandant_id}", response_model=MandantRead)
async def get_mandant(
    mandant_id: UUID, session: AsyncSession = Depends(get_db)
) -> Mandant:
    mandant = await session.get(Mandant, mandant_id)
    if mandant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden"
        )
    return mandant


@router.patch("/{mandant_id}", response_model=MandantRead)
async def update_mandant(
    mandant_id: UUID,
    body: MandantUpdate,
    auth: AuthContext = Depends(require_roles("super_admin")),
    session: AsyncSession = Depends(get_db),
) -> Mandant:
    mandant = await session.get(Mandant, mandant_id)
    if mandant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden"
        )

    karten_war_deaktiviert = "karten" in mandant.deaktivierte_module

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(mandant, field, value)
    await session.flush()
    if changes:
        # UPDATE doesn't RETURNING server-computed columns like updated_at
        # the way INSERT does, so without this the field stays expired and
        # a later lazy-load during response serialization fails outside the
        # session's async context.
        await session.refresh(mandant)

    # Wird "karten" frisch aktiviert, hatten bestehende Standorte/Anlagen
    # bislang nie eine Chance auf Auto-Geocoding (das Modul war ja aus) --
    # ohne diesen Nachzieh-Schritt muesste ein Admin sonst wissen, dass es
    # dafuer ein separates CLI-Skript (app/backfill_geocode.py) gibt.
    karten_frisch_aktiviert = karten_war_deaktiviert and "karten" not in mandant.deaktivierte_module
    if karten_frisch_aktiviert and get_settings().mapbox_access_token:
        anzahl_geocodiert, anzahl_ohne_treffer = await backfill_geocode_fuer_mandant(
            session, mandant.id
        )
        await session.flush()
        await log_action(
            session,
            aktion="mandant_karten_modul_backfill",
            actor_user_id=auth.user_id,
            entity_type="mandant",
            entity_id=mandant.id,
            payload={"geocodiert": anzahl_geocodiert, "ohne_treffer": anzahl_ohne_treffer},
        )

    if changes:
        await log_action(
            session,
            aktion="mandant_geaendert",
            actor_user_id=auth.user_id,
            entity_type="mandant",
            entity_id=mandant.id,
            payload=changes,
        )
    return mandant
