from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_module, require_recht, require_roles
from app.models.kunde import Kunde
from app.models.material import Material
from app.models.material_bedarf import MaterialBedarf
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.material_bedarf import (
    MaterialBedarfCreate,
    MaterialBedarfMitDetails,
    MaterialBedarfRead,
)
from app.services import papierkorb_service
from app.services.vorgang_completion_service import VORGANG_STATUS_GESCHLOSSEN

router = APIRouter(
    prefix="/api/material-bedarfe",
    tags=["material-bedarfe"],
    dependencies=[
        Depends(
            require_roles(
                "mandant_admin", "disponent", "techniker", "controller", "mitarbeiter",
                "loesch_operativ",
            )
        ),
        Depends(require_module("material")),
    ],
)


@router.get(
    "", response_model=list[MaterialBedarfMitDetails], dependencies=[Depends(require_recht("material", "sehen"))]
)
async def list_material_bedarfe(
    vorgang_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    zweck: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> list[MaterialBedarfMitDetails]:
    stmt = (
        select(MaterialBedarf)
        .where(MaterialBedarf.geloescht_am.is_(None))
        .order_by(MaterialBedarf.created_at.desc())
    )
    if vorgang_id:
        stmt = stmt.where(MaterialBedarf.vorgang_id == vorgang_id)
    if status_filter:
        stmt = stmt.where(MaterialBedarf.status == status_filter)
    if zweck:
        stmt = stmt.where(MaterialBedarf.zweck == zweck)
    bedarfe = list((await session.execute(stmt)).scalars().all())
    if not bedarfe:
        return []

    material_ids = {b.material_id for b in bedarfe}
    vorgang_ids = {b.vorgang_id for b in bedarfe}
    materialien = {
        m.id: m for m in (await session.execute(select(Material).where(Material.id.in_(material_ids)))).scalars().all()
    }
    vorgaenge = {
        v.id: v for v in (await session.execute(select(Vorgang).where(Vorgang.id.in_(vorgang_ids)))).scalars().all()
    }
    kunde_ids = {v.kunde_id for v in vorgaenge.values()}
    kunden = {
        k.id: k for k in (await session.execute(select(Kunde).where(Kunde.id.in_(kunde_ids)))).scalars().all()
    }

    ergebnis = []
    for b in bedarfe:
        material = materialien.get(b.material_id)
        vorgang = vorgaenge.get(b.vorgang_id)
        kunde = kunden.get(vorgang.kunde_id) if vorgang else None
        ergebnis.append(
            MaterialBedarfMitDetails(
                **MaterialBedarfRead.model_validate(b).model_dump(),
                material_bezeichnung=material.bezeichnung if material else "?",
                material_einheit=material.einheit if material else "Stk",
                vorgang_titel=vorgang.titel if vorgang else "?",
                vorgang_vorgangsnummer=vorgang.vorgangsnummer if vorgang else "?",
                kunde_name=kunde.name if kunde else "",
            )
        )
    return ergebnis


@router.post(
    "",
    response_model=MaterialBedarfRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            require_roles(
                "mandant_admin", "disponent", "techniker", "controller", "mitarbeiter"
            )
        ),
        Depends(require_recht("material", "bearbeiten")),
    ],
)
async def create_material_bedarf(
    body: MaterialBedarfCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MaterialBedarf:
    material = await session.get(Material, body.material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material nicht gefunden")
    vorgang = await session.get(Vorgang, body.vorgang_id)
    if vorgang is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if vorgang.status in VORGANG_STATUS_GESCHLOSSEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vorgang ist abgeschlossen und kann nicht mehr bebucht werden",
        )

    bedarf = MaterialBedarf(
        mandant_id=auth.mandant_id,
        material_id=body.material_id,
        vorgang_id=body.vorgang_id,
        menge=body.menge,
        notiz=body.notiz,
        zweck=body.zweck,
        erstellt_von=auth.user_id,
    )
    session.add(bedarf)

    ziel_text = "zur Bestellung vorgemerkt" if body.zweck == "bestellung" else "für Angebot vorgemerkt"
    session.add(
        VorgangEvent(
            mandant_id=auth.mandant_id,
            vorgang_id=body.vorgang_id,
            event_type="material",
            author_user_id=auth.user_id,
            body=f"{body.menge:g} {material.einheit} {material.bezeichnung} {ziel_text}",
            payload={"material_id": str(body.material_id), "menge": str(body.menge), "zweck": body.zweck},
        )
    )

    await session.flush()
    await session.refresh(bedarf)
    return bedarf


@router.delete(
    "/{bedarf_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_recht("material", "bearbeiten"))],
)
async def delete_material_bedarf(
    bedarf_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    bedarf = await session.get(MaterialBedarf, bedarf_id)
    if bedarf is None or bedarf.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Materialbedarf nicht gefunden")
    if bedarf.status != "offen":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nur offene Materialbedarfe können entfernt werden",
        )
    await papierkorb_service.soft_delete(
        session, entity_typ="material_bedarf", entity_id=bedarf_id, actor_user_id=auth.user_id
    )
