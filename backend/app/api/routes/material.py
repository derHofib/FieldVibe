from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.anlage import Anlage
from app.models.material import Material, MaterialBestand, MaterialBewegung, MaterialVerwendung
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.material import (
    MaterialBestandRead,
    MaterialBestandSetzen,
    MaterialBewegungRead,
    MaterialCreate,
    MaterialRead,
    MaterialUmlagernRequest,
    MaterialUpdate,
    MaterialVerwendungCreate,
    MaterialVerwendungRead,
)
from app.services.csv_service import csv_response

router = APIRouter(
    prefix="/api/material",
    tags=["material"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)

LAGERORT_OBJEKTTYPEN = ("fahrzeug", "lager", "baustelle")


async def _default_lager(session: AsyncSession, mandant_id: UUID) -> Anlage:
    result = await session.execute(
        select(Anlage)
        .where(Anlage.mandant_id == mandant_id, Anlage.objekttyp == "lager")
        .order_by(Anlage.created_at.asc())
    )
    lager = result.scalars().first()
    if lager is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kein Lagerort für diesen Mandanten vorhanden",
        )
    return lager


async def _require_lager(session: AsyncSession, lager_id: UUID) -> Anlage:
    # RLS scopt das SELECT bereits auf den eigenen Mandanten -- ein fremder
    # lager_id resolved hier zu None, siehe anlagen.py:_require_own_kunde.
    lager = await session.get(Anlage, lager_id)
    if lager is None or lager.objekttyp not in LAGERORT_OBJEKTTYPEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Lagerort nicht gefunden"
        )
    return lager


async def _get_or_create_bestand(
    session: AsyncSession, mandant_id: UUID, material_id: UUID, lager_id: UUID
) -> MaterialBestand:
    result = await session.execute(
        select(MaterialBestand).where(
            MaterialBestand.material_id == material_id, MaterialBestand.lager_id == lager_id
        )
    )
    bestand = result.scalar_one_or_none()
    if bestand is None:
        bestand = MaterialBestand(
            mandant_id=mandant_id, material_id=material_id, lager_id=lager_id, menge=Decimal("0")
        )
        session.add(bestand)
        await session.flush()
    return bestand


async def _material_read(session: AsyncSession, material: Material) -> MaterialRead:
    result = await session.execute(
        select(MaterialBestand, Anlage.bezeichnung)
        .join(Anlage, Anlage.id == MaterialBestand.lager_id)
        .where(MaterialBestand.material_id == material.id)
        .order_by(Anlage.bezeichnung)
    )
    # .quantize() vereinheitlicht die Nachkommastellen unabhaengig davon, ob
    # menge gerade frisch in Python berechnet wurde (z.B. Decimal("0") +
    # Decimal("4") = Decimal("4")) oder aus der DB geladen ist (NUMERIC(10,2)
    # liefert immer 2 Nachkommastellen) -- ohne das waeren Bestandswerte je
    # nach Code-Pfad inkonsistent formatiert (z.B. "4" vs. "4.00").
    bestaende = [
        MaterialBestandRead(
            lager_id=mb.lager_id, lager_bezeichnung=name, menge=mb.menge.quantize(Decimal("0.01"))
        )
        for mb, name in result.all()
    ]
    bestand_gesamt = sum((b.menge for b in bestaende), Decimal("0")).quantize(Decimal("0.01"))
    return MaterialRead(
        id=material.id,
        bezeichnung=material.bezeichnung,
        einheit=material.einheit,
        mindestbestand=material.mindestbestand,
        einzelpreis=material.einzelpreis,
        created_at=material.created_at,
        updated_at=material.updated_at,
        bestand_gesamt=bestand_gesamt,
        bestaende=bestaende,
    )


@router.get("", response_model=list[MaterialRead])
async def list_material(
    lager_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> list[MaterialRead]:
    stmt = select(Material).order_by(Material.bezeichnung)
    if lager_id is not None:
        # Nur Material, das an diesem Lagerort tatsaechlich vorhanden ist --
        # ein Bestand-Datensatz mit menge=0 ist nur ein Ueberbleibsel einer
        # frueheren Umlagerung, kein "ist hier"-Signal mehr.
        stmt = stmt.where(
            Material.id.in_(
                select(MaterialBestand.material_id).where(
                    MaterialBestand.lager_id == lager_id, MaterialBestand.menge > 0
                )
            )
        )
    result = await session.execute(stmt)
    return [await _material_read(session, m) for m in result.scalars().all()]


@router.get(
    "/export/csv", dependencies=[Depends(require_roles("mandant_admin", "disponent"))]
)
async def export_material_csv(session: AsyncSession = Depends(get_db)) -> Response:
    result = await session.execute(
        select(Material, MaterialBestand, Anlage.bezeichnung)
        .join(MaterialBestand, MaterialBestand.material_id == Material.id)
        .join(Anlage, Anlage.id == MaterialBestand.lager_id)
        .order_by(Material.bezeichnung, Anlage.bezeichnung)
    )
    rows = [
        [
            material.bezeichnung,
            material.einheit,
            lager_bezeichnung,
            f"{bestand.menge:g}".replace(".", ","),
            f"{material.mindestbestand:g}".replace(".", ","),
            f"{material.einzelpreis:g}".replace(".", ",") if material.einzelpreis is not None else "",
        ]
        for material, bestand, lager_bezeichnung in result.all()
    ]
    return csv_response(
        ["Material", "Einheit", "Lagerort", "Menge", "Mindestbestand", "Einzelpreis (EUR)"],
        rows,
        "Material-Bestand.csv",
    )


@router.post(
    "",
    response_model=MaterialRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_material(
    body: MaterialCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MaterialRead:
    material = Material(
        mandant_id=auth.mandant_id,
        bezeichnung=body.bezeichnung,
        einheit=body.einheit,
        mindestbestand=body.mindestbestand,
        einzelpreis=body.einzelpreis,
    )
    session.add(material)
    await session.flush()

    lager = (
        await _require_lager(session, body.lager_id)
        if body.lager_id is not None
        else await _default_lager(session, auth.mandant_id)
    )
    session.add(
        MaterialBestand(
            mandant_id=auth.mandant_id, material_id=material.id, lager_id=lager.id, menge=body.menge
        )
    )
    if body.menge > 0:
        session.add(
            MaterialBewegung(
                mandant_id=auth.mandant_id,
                material_id=material.id,
                typ="eingang",
                nach_lager_id=lager.id,
                menge=body.menge,
                erstellt_von=auth.user_id,
            )
        )
    await session.flush()
    await session.refresh(material)
    return await _material_read(session, material)


@router.patch(
    "/{material_id}",
    response_model=MaterialRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_material(
    material_id: UUID, body: MaterialUpdate, session: AsyncSession = Depends(get_db)
) -> MaterialRead:
    material = await session.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material nicht gefunden")

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(material, field, value)
    await session.flush()
    if changes:
        await session.refresh(material)
    return await _material_read(session, material)


@router.put(
    "/{material_id}/bestand/{lager_id}",
    response_model=MaterialRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def bestand_setzen(
    material_id: UUID,
    lager_id: UUID,
    body: MaterialBestandSetzen,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MaterialRead:
    """Bestand an einem Lagerort auf einen konkreten Wert setzen -- fuer
    Inventur/Korrekturen, nicht fuer normale Zu-/Abgaenge (dafuer gibt es
    Umlagerung/Verwendung, die je zwei Lagerorte bzw. einen Vorgang
    verknuepfen)."""
    material = await session.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material nicht gefunden")
    await _require_lager(session, lager_id)

    bestand = await _get_or_create_bestand(session, auth.mandant_id, material_id, lager_id)
    delta = body.menge - bestand.menge
    bestand.menge = body.menge
    if delta > 0:
        session.add(
            MaterialBewegung(
                mandant_id=auth.mandant_id,
                material_id=material_id,
                typ="korrektur",
                nach_lager_id=lager_id,
                menge=delta,
                erstellt_von=auth.user_id,
            )
        )
    elif delta < 0:
        session.add(
            MaterialBewegung(
                mandant_id=auth.mandant_id,
                material_id=material_id,
                typ="korrektur",
                von_lager_id=lager_id,
                menge=-delta,
                erstellt_von=auth.user_id,
            )
        )
    await session.flush()
    return await _material_read(session, material)


@router.post("/{material_id}/umlagern", response_model=MaterialRead)
async def umlagern(
    material_id: UUID,
    body: MaterialUmlagernRequest,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MaterialRead:
    material = await session.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material nicht gefunden")
    if body.von_lager_id == body.nach_lager_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Quelle und Ziel müssen unterschiedlich sein"
        )
    await _require_lager(session, body.von_lager_id)
    await _require_lager(session, body.nach_lager_id)

    von_bestand = await _get_or_create_bestand(session, auth.mandant_id, material_id, body.von_lager_id)
    if body.menge > von_bestand.menge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nicht genug Bestand am Quell-Lagerort: {von_bestand.menge} {material.einheit} verfügbar, {body.menge} angefragt",
        )
    nach_bestand = await _get_or_create_bestand(session, auth.mandant_id, material_id, body.nach_lager_id)

    von_bestand.menge -= body.menge
    nach_bestand.menge += body.menge
    session.add(
        MaterialBewegung(
            mandant_id=auth.mandant_id,
            material_id=material_id,
            typ="umlagerung",
            von_lager_id=body.von_lager_id,
            nach_lager_id=body.nach_lager_id,
            menge=body.menge,
            erstellt_von=auth.user_id,
        )
    )
    await session.flush()
    return await _material_read(session, material)


@router.get("/{material_id}/bewegungen", response_model=list[MaterialBewegungRead])
async def bewegungen(
    material_id: UUID, session: AsyncSession = Depends(get_db)
) -> list[MaterialBewegung]:
    result = await session.execute(
        select(MaterialBewegung)
        .where(MaterialBewegung.material_id == material_id)
        .order_by(MaterialBewegung.created_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/{material_id}/verwendung", response_model=MaterialVerwendungRead, status_code=status.HTTP_201_CREATED
)
async def verwendung_erfassen(
    material_id: UUID,
    body: MaterialVerwendungCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MaterialVerwendung:
    material = await session.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material nicht gefunden")
    vorgang = await session.get(Vorgang, body.vorgang_id)
    if vorgang is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    await _require_lager(session, body.lager_id)
    bestand = await _get_or_create_bestand(session, auth.mandant_id, material_id, body.lager_id)
    if body.menge > bestand.menge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nicht genug Bestand: {bestand.menge} {material.einheit} verfügbar, {body.menge} angefragt",
        )

    bestand.menge -= body.menge
    verwendung = MaterialVerwendung(
        mandant_id=auth.mandant_id,
        material_id=material_id,
        lager_id=body.lager_id,
        vorgang_id=body.vorgang_id,
        menge=body.menge,
        verwendet_von=auth.user_id,
    )
    session.add(verwendung)
    session.add(
        MaterialBewegung(
            mandant_id=auth.mandant_id,
            material_id=material_id,
            typ="verwendung",
            von_lager_id=body.lager_id,
            menge=body.menge,
            vorgang_id=body.vorgang_id,
            erstellt_von=auth.user_id,
        )
    )

    session.add(
        VorgangEvent(
            mandant_id=auth.mandant_id,
            vorgang_id=body.vorgang_id,
            event_type="material",
            author_user_id=auth.user_id,
            body=f"{body.menge:g} {material.einheit} {material.bezeichnung} verwendet",
            payload={"material_id": str(material_id), "menge": str(body.menge)},
        )
    )

    await session.flush()
    await session.refresh(verwendung)
    return verwendung
