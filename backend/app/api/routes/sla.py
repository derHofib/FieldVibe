"""SLA-Richtlinien (docs/konzepte/SLA.md, Phase 2): Verwaltung. Fristberechnung,
Vorgangsintegration und Eskalation folgen in den Phasen 3 und 4."""
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_recht, require_roles
from app.models.sla import SlaEskalationsstufe, SlaRichtlinie
from app.models.vertrag import Vertrag
from app.schemas.sla import SlaRichtlinieCreate, SlaRichtlinieRead, SlaRichtlinieUpdate, SlaStufe

router = APIRouter(prefix="/api/sla/richtlinien", tags=["sla"])

_LESEN = [
    Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
    Depends(require_recht("sla", "sehen")),
]


def _verwalten(aktion: str):
    # Techniker sehen die Frist am Vorgang, aendern aber nie die Richtlinie.
    return [Depends(require_roles("mandant_admin", "custom")), Depends(require_recht("sla", aktion))]


async def _stufen(session: AsyncSession, richtlinie_ids: list[UUID]) -> dict[UUID, list[SlaEskalationsstufe]]:
    zeilen = (
        await session.execute(
            select(SlaEskalationsstufe)
            .where(SlaEskalationsstufe.richtlinie_id.in_(richtlinie_ids))
            .order_by(SlaEskalationsstufe.frist_art, SlaEskalationsstufe.position)
        )
    ).scalars()
    nach_richtlinie: dict[UUID, list[SlaEskalationsstufe]] = {i: [] for i in richtlinie_ids}
    for z in zeilen:
        nach_richtlinie[z.richtlinie_id].append(z)
    return nach_richtlinie


async def _read(session: AsyncSession, richtlinien: list[SlaRichtlinie]) -> list[SlaRichtlinieRead]:
    stufen = await _stufen(session, [r.id for r in richtlinien])
    ergebnis = []
    for r in richtlinien:
        modell = SlaRichtlinieRead.model_validate(r)
        modell.stufen = [s for s in stufen[r.id]]  # type: ignore[misc]
        ergebnis.append(modell)
    return ergebnis


async def _laden(session: AsyncSession, richtlinie_id: UUID) -> SlaRichtlinie:
    richtlinie = await session.get(SlaRichtlinie, richtlinie_id)
    if richtlinie is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SLA-Richtlinie nicht gefunden")
    return richtlinie


async def _stufen_ersetzen(session: AsyncSession, richtlinie: SlaRichtlinie, stufen: list[SlaStufe]) -> None:
    for alt in (await _stufen(session, [richtlinie.id]))[richtlinie.id]:
        await session.delete(alt)
    await session.flush()
    for position, stufe in enumerate(stufen):
        session.add(
            SlaEskalationsstufe(
                mandant_id=richtlinie.mandant_id,
                richtlinie_id=richtlinie.id,
                position=position,
                **stufe.model_dump(),
            )
        )
    await session.flush()


async def _standard_exklusiv(session: AsyncSession, richtlinie: SlaRichtlinie) -> None:
    if richtlinie.ist_standard:
        # Vor dem Flush der neuen Zeile, sonst greift der Unique-Index auf ist_standard.
        with session.no_autoflush:
            await session.execute(
                update(SlaRichtlinie)
                .where(SlaRichtlinie.mandant_id == richtlinie.mandant_id, SlaRichtlinie.id != richtlinie.id)
                .values(ist_standard=False)
            )


def _namenskonflikt() -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Eine SLA-Richtlinie mit diesem Namen existiert bereits")


@router.get("", response_model=list[SlaRichtlinieRead], dependencies=_LESEN)
async def list_richtlinien(session: AsyncSession = Depends(get_db)) -> list[SlaRichtlinieRead]:
    richtlinien = list((await session.execute(select(SlaRichtlinie).order_by(SlaRichtlinie.name))).scalars())
    return await _read(session, richtlinien)


@router.get("/{richtlinie_id}", response_model=SlaRichtlinieRead, dependencies=_LESEN)
async def get_richtlinie(richtlinie_id: UUID, session: AsyncSession = Depends(get_db)) -> SlaRichtlinieRead:
    return (await _read(session, [await _laden(session, richtlinie_id)]))[0]


@router.post(
    "", response_model=SlaRichtlinieRead, status_code=status.HTTP_201_CREATED, dependencies=_verwalten("erstellen")
)
async def create_richtlinie(
    body: SlaRichtlinieCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SlaRichtlinieRead:
    felder = body.model_dump(exclude={"stufen"})
    richtlinie = SlaRichtlinie(id=uuid4(), mandant_id=auth.mandant_id, **felder)
    await _standard_exklusiv(session, richtlinie)
    session.add(richtlinie)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _namenskonflikt() from exc
    await _stufen_ersetzen(session, richtlinie, body.stufen)
    await session.refresh(richtlinie)
    return (await _read(session, [richtlinie]))[0]


@router.patch("/{richtlinie_id}", response_model=SlaRichtlinieRead, dependencies=_verwalten("bearbeiten"))
async def update_richtlinie(
    richtlinie_id: UUID, body: SlaRichtlinieUpdate, session: AsyncSession = Depends(get_db)
) -> SlaRichtlinieRead:
    richtlinie = await _laden(session, richtlinie_id)
    aenderungen = body.model_dump(exclude_unset=True, exclude={"stufen"})
    for feld, wert in aenderungen.items():
        if wert is None and feld not in ("beschreibung",):
            continue
        setattr(richtlinie, feld, wert)
    if richtlinie.kalender == "geschaeftszeiten" and not any(richtlinie.geschaeftszeiten.values()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Für den Kalender „Geschäftszeiten“ ist mindestens ein Zeitfenster nötig",
        )
    await _standard_exklusiv(session, richtlinie)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _namenskonflikt() from exc
    if body.stufen is not None:
        await _stufen_ersetzen(session, richtlinie, body.stufen)
    await session.refresh(richtlinie)
    return (await _read(session, [richtlinie]))[0]


@router.delete("/{richtlinie_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=_verwalten("loeschen"))
async def delete_richtlinie(richtlinie_id: UUID, session: AsyncSession = Depends(get_db)) -> None:
    richtlinie = await _laden(session, richtlinie_id)
    verwendet = await session.scalar(
        select(func.count()).select_from(Vertrag).where(Vertrag.sla_richtlinie_id == richtlinie.id)
    )
    if verwendet:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Die Richtlinie ist Verträgen zugeordnet – bitte deaktivieren statt löschen",
        )
    await session.delete(richtlinie)
