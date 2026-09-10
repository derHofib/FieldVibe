from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AuthContext,
    get_current_user,
    get_db,
    require_recht,
    require_roles,
)
from app.models.kunde import Kunde
from app.models.leistungsverzeichnis import (
    Leistungsverzeichnis,
    LeistungsverzeichnisKunde,
    LeistungsverzeichnisPosition,
)
from app.schemas.leistungsverzeichnis import (
    LeistungsverzeichnisCreate,
    LeistungsverzeichnisRead,
    LeistungsverzeichnisUpdate,
)
from app.services import papierkorb_service

# Gleiche Rollen-/Rechte-Basis wie leistungsverzeichnis.py/kunden.py: das
# Leistungsverzeichnis haengt fachlich am Kunden, daher dieselbe
# "kunden"-Rechtematrix statt eines eigenen Rechts.
router = APIRouter(
    prefix="/api/leistungsverzeichnisse",
    tags=["leistungsverzeichnisse"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("kunden", "sehen")),
    ],
)


async def _require_lv(session: AsyncSession, lv_id: UUID) -> Leistungsverzeichnis:
    lv = await session.get(Leistungsverzeichnis, lv_id)
    if lv is None or lv.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leistungsverzeichnis nicht gefunden")
    return lv


async def _kunden_ids_lesen(session: AsyncSession, lv_ids: list[UUID]) -> dict[UUID, list[UUID]]:
    if not lv_ids:
        return {}
    result = await session.execute(
        select(LeistungsverzeichnisKunde.leistungsverzeichnis_id, LeistungsverzeichnisKunde.kunde_id).where(
            LeistungsverzeichnisKunde.leistungsverzeichnis_id.in_(lv_ids)
        )
    )
    zuordnung: dict[UUID, list[UUID]] = {}
    for lv_id, kunde_id in result.all():
        zuordnung.setdefault(lv_id, []).append(kunde_id)
    return zuordnung


async def _annotiere_kunden_ids(session: AsyncSession, lvs: list[Leistungsverzeichnis]) -> None:
    """Haengt kunden_ids als transientes (nicht in der DB gespeichertes)
    Attribut an -- LeistungsverzeichnisRead.model_validate() liest es per
    from_attributes wie jedes andere Feld."""
    zuordnung = await _kunden_ids_lesen(session, [lv.id for lv in lvs])
    for lv in lvs:
        lv.kunden_ids = zuordnung.get(lv.id, [])  # type: ignore[attr-defined]


async def _kunden_setzen(session: AsyncSession, auth: AuthContext, lv_id: UUID, kunden_ids: list[UUID]) -> None:
    neue = set(kunden_ids)
    for kunde_id in neue:
        kunde = await session.get(Kunde, kunde_id)
        if kunde is None or kunde.geloescht_am is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Kunde nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )

    bestehende_result = await session.execute(
        select(LeistungsverzeichnisKunde).where(LeistungsverzeichnisKunde.leistungsverzeichnis_id == lv_id)
    )
    bestehende = {z.kunde_id: z for z in bestehende_result.scalars().all()}

    for kunde_id, zuweisung in bestehende.items():
        if kunde_id not in neue:
            await session.delete(zuweisung)
    for kunde_id in neue - bestehende.keys():
        session.add(
            LeistungsverzeichnisKunde(mandant_id=auth.mandant_id, leistungsverzeichnis_id=lv_id, kunde_id=kunde_id)
        )
    await session.flush()


@router.get("", response_model=list[LeistungsverzeichnisRead])
async def list_leistungsverzeichnisse(session: AsyncSession = Depends(get_db)) -> list[Leistungsverzeichnis]:
    stmt = select(Leistungsverzeichnis).where(Leistungsverzeichnis.geloescht_am.is_(None)).order_by(
        Leistungsverzeichnis.name
    )
    lvs = list((await session.execute(stmt)).scalars().all())
    await _annotiere_kunden_ids(session, lvs)
    return lvs


@router.post(
    "",
    response_model=LeistungsverzeichnisRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("kunden", "bearbeiten")),
    ],
)
async def create_leistungsverzeichnis(
    body: LeistungsverzeichnisCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Leistungsverzeichnis:
    lv = Leistungsverzeichnis(mandant_id=auth.mandant_id, name=body.name, beschreibung=body.beschreibung)
    session.add(lv)
    await session.flush()
    if body.kunden_ids:
        await _kunden_setzen(session, auth, lv.id, body.kunden_ids)
    await session.refresh(lv)
    await _annotiere_kunden_ids(session, [lv])
    return lv


@router.get("/{lv_id}", response_model=LeistungsverzeichnisRead)
async def get_leistungsverzeichnis(lv_id: UUID, session: AsyncSession = Depends(get_db)) -> Leistungsverzeichnis:
    lv = await _require_lv(session, lv_id)
    await _annotiere_kunden_ids(session, [lv])
    return lv


@router.patch(
    "/{lv_id}",
    response_model=LeistungsverzeichnisRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("kunden", "bearbeiten")),
    ],
)
async def update_leistungsverzeichnis(
    lv_id: UUID,
    body: LeistungsverzeichnisUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Leistungsverzeichnis:
    lv = await _require_lv(session, lv_id)
    changes = body.model_dump(exclude_unset=True)
    kunden_ids = changes.pop("kunden_ids", None)
    for feld, wert in changes.items():
        setattr(lv, feld, wert)
    await session.flush()
    if kunden_ids is not None:
        await _kunden_setzen(session, auth, lv.id, kunden_ids)
    await session.refresh(lv)
    await _annotiere_kunden_ids(session, [lv])
    return lv


@router.delete(
    "/{lv_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("kunden", "loeschen")),
    ],
)
async def delete_leistungsverzeichnis(
    lv_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    geloescht = await papierkorb_service.soft_delete(
        session, entity_typ="leistungsverzeichnis", entity_id=lv_id, actor_user_id=auth.user_id
    )
    if geloescht is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leistungsverzeichnis nicht gefunden")


@router.post(
    "/{lv_id}/duplizieren",
    response_model=LeistungsverzeichnisRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("kunden", "bearbeiten")),
    ],
)
async def duplizieren(
    lv_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Leistungsverzeichnis:
    """Kopiert ein Leistungsverzeichnis samt aller aktiven Positionen
    (Haupt- und Unterpunkte). Die Kopie bekommt bewusst KEINE Kunden-
    Zuweisung -- ein dupliziertes LV muss dem Zielkunden immer explizit neu
    zugewiesen werden, es "erbt" die Zuordnung des Originals nicht (siehe
    Absprache: eine Position/ein LV bekommt einen Kunden nur durch
    ausdrueckliche Zuweisung, auch wenn es dupliziert wurde)."""
    original = await _require_lv(session, lv_id)

    kopie = Leistungsverzeichnis(
        mandant_id=auth.mandant_id, name=f"{original.name} (Kopie)", beschreibung=original.beschreibung
    )
    session.add(kopie)
    await session.flush()

    positionen = list(
        (
            await session.execute(
                select(LeistungsverzeichnisPosition).where(
                    LeistungsverzeichnisPosition.leistungsverzeichnis_id == lv_id,
                    LeistungsverzeichnisPosition.geloescht_am.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    def _kopiere(p: LeistungsverzeichnisPosition, eltern_id: UUID | None) -> LeistungsverzeichnisPosition:
        neu = LeistungsverzeichnisPosition(
            mandant_id=auth.mandant_id,
            leistungsverzeichnis_id=kopie.id,
            eltern_position_id=eltern_id,
            bezeichnung=p.bezeichnung,
            einheit=p.einheit,
            einzelpreis=p.einzelpreis,
            ist_stundensatz=p.ist_stundensatz,
            notiz=p.notiz,
            kalkulationsmodus=p.kalkulationsmodus,
            lohn_minuten=p.lohn_minuten,
            lohn_stundensatz=p.lohn_stundensatz,
            lohn_gemeinkosten_prozent=p.lohn_gemeinkosten_prozent,
            material_posten=list(p.material_posten),
            material_aufschlag_prozent=p.material_aufschlag_prozent,
            gewinn_wagnis_prozent=p.gewinn_wagnis_prozent,
            lohn_gesamt=p.lohn_gesamt,
            material_gesamt=p.material_gesamt,
        )
        session.add(neu)
        return neu

    id_zuordnung: dict[UUID, UUID] = {}
    for p in [x for x in positionen if x.eltern_position_id is None]:
        neu = _kopiere(p, None)
        await session.flush()
        id_zuordnung[p.id] = neu.id
    for p in [x for x in positionen if x.eltern_position_id is not None]:
        eltern_neu_id = id_zuordnung.get(p.eltern_position_id)
        if eltern_neu_id is not None:
            _kopiere(p, eltern_neu_id)
    await session.flush()

    await session.refresh(kopie)
    await _annotiere_kunden_ids(session, [kopie])
    return kopie
