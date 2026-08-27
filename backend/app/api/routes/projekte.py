from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AuthContext,
    get_current_user,
    get_db,
    require_recht,
    require_roles,
)
from app.models.kunde import Kunde
from app.models.projekt import Projekt, ProjektAufgabe, ProjektSpalte
from app.models.user import User
from app.models.vorgang import Vorgang
from app.schemas.projekt import (
    ProjektAufgabeCreate,
    ProjektAufgabeMitDetails,
    ProjektAufgabeRead,
    ProjektAufgabeUpdate,
    ProjektCreate,
    ProjektRead,
    ProjektSpalteCreate,
    ProjektSpalteRead,
    ProjektSpalteUpdate,
    ProjektUpdate,
)
from app.services import papierkorb_service

# Basisrechte fuer alles unter /api/projekte und /api/projekt-aufgaben.
# loesch_operativ hat dieselben Rechte wie mandant_admin (siehe
# app/api/deps.py:require_roles()).
router = APIRouter(
    prefix="/api/projekte",
    tags=["projekte"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("projekte", "sehen")),
    ],
)

aufgaben_router = APIRouter(
    prefix="/api/projekt-aufgaben",
    tags=["projekte"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("projekte", "sehen")),
    ],
)

# Ein neues Projekt startet nie ganz leer -- ohne mindestens eine Spalte
# koennte keine Aufgabe angelegt werden. Rein ein sinnvoller Vorschlag,
# jede Spalte ist danach frei umbenennbar/loeschbar wie jede andere auch.
STANDARD_SPALTEN = ("Offen", "In Arbeit", "Review", "Fertig")


async def _require_projekt(session: AsyncSession, projekt_id: UUID) -> Projekt:
    projekt = await session.get(Projekt, projekt_id)
    if projekt is None or projekt.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projekt nicht gefunden")
    return projekt


async def _require_spalte(session: AsyncSession, projekt_id: UUID, spalte_id: UUID) -> ProjektSpalte:
    spalte = await session.get(ProjektSpalte, spalte_id)
    if spalte is None or spalte.projekt_id != projekt_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spalte nicht gefunden")
    return spalte


async def _require_aufgabe(session: AsyncSession, aufgabe_id: UUID) -> ProjektAufgabe:
    aufgabe = await session.get(ProjektAufgabe, aufgabe_id)
    if aufgabe is None or aufgabe.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aufgabe nicht gefunden")
    return aufgabe


@router.get("", response_model=list[ProjektRead])
async def list_projekte(session: AsyncSession = Depends(get_db)) -> list[Projekt]:
    result = await session.execute(
        select(Projekt).where(Projekt.geloescht_am.is_(None)).order_by(Projekt.created_at)
    )
    return list(result.scalars().all())


@router.post(
    "",
    response_model=ProjektRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("projekte", "erstellen")),
    ],
)
async def create_projekt(
    body: ProjektCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Projekt:
    projekt = Projekt(
        mandant_id=auth.mandant_id,
        name=body.name,
        beschreibung=body.beschreibung,
        erstellt_von=auth.user_id,
    )
    session.add(projekt)
    await session.flush()

    for reihenfolge, name in enumerate(STANDARD_SPALTEN):
        session.add(
            ProjektSpalte(
                mandant_id=auth.mandant_id, projekt_id=projekt.id, name=name, reihenfolge=reihenfolge
            )
        )

    await session.flush()
    await session.refresh(projekt)
    return projekt


@router.get("/{projekt_id}", response_model=ProjektRead)
async def get_projekt(projekt_id: UUID, session: AsyncSession = Depends(get_db)) -> Projekt:
    return await _require_projekt(session, projekt_id)


@router.patch(
    "/{projekt_id}",
    response_model=ProjektRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("projekte", "bearbeiten")),
    ],
)
async def update_projekt(
    projekt_id: UUID,
    body: ProjektUpdate,
    session: AsyncSession = Depends(get_db),
) -> Projekt:
    projekt = await _require_projekt(session, projekt_id)
    for feld, wert in body.model_dump(exclude_unset=True).items():
        setattr(projekt, feld, wert)
    await session.flush()
    await session.refresh(projekt)
    return projekt


@router.delete(
    "/{projekt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("projekte", "loeschen")),
    ],
)
async def delete_projekt(
    projekt_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    projekt = await papierkorb_service.soft_delete(
        session, entity_typ="projekt", entity_id=projekt_id, actor_user_id=auth.user_id
    )
    if projekt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projekt nicht gefunden")


@router.get("/{projekt_id}/spalten", response_model=list[ProjektSpalteRead])
async def list_spalten(projekt_id: UUID, session: AsyncSession = Depends(get_db)) -> list[ProjektSpalte]:
    await _require_projekt(session, projekt_id)
    result = await session.execute(
        select(ProjektSpalte).where(ProjektSpalte.projekt_id == projekt_id).order_by(ProjektSpalte.reihenfolge)
    )
    return list(result.scalars().all())


@router.post(
    "/{projekt_id}/spalten",
    response_model=ProjektSpalteRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("projekte", "bearbeiten")),
    ],
)
async def create_spalte(
    projekt_id: UUID,
    body: ProjektSpalteCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ProjektSpalte:
    await _require_projekt(session, projekt_id)
    naechste_reihenfolge = (
        await session.execute(
            select(func.coalesce(func.max(ProjektSpalte.reihenfolge), -1) + 1).where(
                ProjektSpalte.projekt_id == projekt_id
            )
        )
    ).scalar_one()
    spalte = ProjektSpalte(
        mandant_id=auth.mandant_id, projekt_id=projekt_id, name=body.name, reihenfolge=naechste_reihenfolge
    )
    session.add(spalte)
    await session.flush()
    return spalte


@router.patch(
    "/{projekt_id}/spalten/{spalte_id}",
    response_model=ProjektSpalteRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("projekte", "bearbeiten")),
    ],
)
async def update_spalte(
    projekt_id: UUID,
    spalte_id: UUID,
    body: ProjektSpalteUpdate,
    session: AsyncSession = Depends(get_db),
) -> ProjektSpalte:
    spalte = await _require_spalte(session, projekt_id, spalte_id)
    for feld, wert in body.model_dump(exclude_unset=True).items():
        setattr(spalte, feld, wert)
    await session.flush()
    return spalte


@router.delete(
    "/{projekt_id}/spalten/{spalte_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("projekte", "bearbeiten")),
    ],
)
async def delete_spalte(
    projekt_id: UUID,
    spalte_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> None:
    spalte = await _require_spalte(session, projekt_id, spalte_id)
    anzahl_aufgaben = (
        await session.execute(
            select(func.count()).where(
                ProjektAufgabe.spalte_id == spalte_id, ProjektAufgabe.geloescht_am.is_(None)
            )
        )
    ).scalar_one()
    if anzahl_aufgaben > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Spalte enthält noch Aufgaben -- erst verschieben oder löschen",
        )
    await session.delete(spalte)
    await session.flush()


def _mit_details(zeilen) -> list[ProjektAufgabeMitDetails]:
    return [
        ProjektAufgabeMitDetails(
            **ProjektAufgabeRead.model_validate(aufgabe).model_dump(),
            zugewiesener_name=zugewiesener_name,
            vorgang_vorgangsnummer=vorgangsnummer,
            vorgang_kunde_name=kunde_name,
        )
        for aufgabe, zugewiesener_name, vorgangsnummer, kunde_name in zeilen
    ]


@aufgaben_router.get("", response_model=list[ProjektAufgabeMitDetails])
async def list_aufgaben(
    projekt_id: UUID | None = Query(default=None),
    vorgang_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> list[ProjektAufgabeMitDetails]:
    stmt = (
        select(ProjektAufgabe, User.name, Vorgang.vorgangsnummer, Kunde.name)
        .outerjoin(User, User.id == ProjektAufgabe.zugewiesen_an)
        .outerjoin(Vorgang, Vorgang.id == ProjektAufgabe.vorgang_id)
        .outerjoin(Kunde, Kunde.id == Vorgang.kunde_id)
        .where(ProjektAufgabe.geloescht_am.is_(None))
        .order_by(ProjektAufgabe.created_at)
    )
    if projekt_id is not None:
        stmt = stmt.where(ProjektAufgabe.projekt_id == projekt_id)
    if vorgang_id is not None:
        stmt = stmt.where(ProjektAufgabe.vorgang_id == vorgang_id)
    result = await session.execute(stmt)
    return _mit_details(result.all())


@aufgaben_router.post(
    "",
    response_model=ProjektAufgabeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("projekte", "erstellen")),
    ],
)
async def create_aufgabe(
    body: ProjektAufgabeCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ProjektAufgabe:
    await _require_projekt(session, body.projekt_id)
    await _require_spalte(session, body.projekt_id, body.spalte_id)
    if body.vorgang_id is not None and await session.get(Vorgang, body.vorgang_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )

    aufgabe = ProjektAufgabe(
        mandant_id=auth.mandant_id,
        projekt_id=body.projekt_id,
        spalte_id=body.spalte_id,
        titel=body.titel,
        beschreibung=body.beschreibung,
        faelligkeit_am=body.faelligkeit_am,
        prioritaet=body.prioritaet,
        zugewiesen_an=body.zugewiesen_an,
        vorgang_id=body.vorgang_id,
        checkliste=[punkt.model_dump() for punkt in body.checkliste],
        zusatzfelder=body.zusatzfelder,
        erstellt_von=auth.user_id,
    )
    session.add(aufgabe)
    await session.flush()
    return aufgabe


@aufgaben_router.get("/{aufgabe_id}", response_model=ProjektAufgabeRead)
async def get_aufgabe(aufgabe_id: UUID, session: AsyncSession = Depends(get_db)) -> ProjektAufgabe:
    return await _require_aufgabe(session, aufgabe_id)


@aufgaben_router.patch(
    "/{aufgabe_id}",
    response_model=ProjektAufgabeRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("projekte", "bearbeiten")),
    ],
)
async def update_aufgabe(
    aufgabe_id: UUID,
    body: ProjektAufgabeUpdate,
    session: AsyncSession = Depends(get_db),
) -> ProjektAufgabe:
    aufgabe = await _require_aufgabe(session, aufgabe_id)
    changes = body.model_dump(exclude_unset=True)

    if "spalte_id" in changes:
        await _require_spalte(session, aufgabe.projekt_id, changes["spalte_id"])
    if changes.get("vorgang_id") is not None and await session.get(Vorgang, changes["vorgang_id"]) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if "checkliste" in changes and changes["checkliste"] is not None:
        changes["checkliste"] = [punkt.model_dump() for punkt in body.checkliste]

    for feld, wert in changes.items():
        setattr(aufgabe, feld, wert)
    await session.flush()
    await session.refresh(aufgabe)
    return aufgabe


@aufgaben_router.delete(
    "/{aufgabe_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("projekte", "loeschen")),
    ],
)
async def delete_aufgabe(
    aufgabe_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    aufgabe = await papierkorb_service.soft_delete(
        session, entity_typ="projekt_aufgabe", entity_id=aufgabe_id, actor_user_id=auth.user_id
    )
    if aufgabe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aufgabe nicht gefunden")
