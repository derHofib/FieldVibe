from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import (
    AuthContext,
    get_current_user,
    get_db,
    require_recht,
    require_roles,
)
from app.models.anlage import Anlage
from app.models.kunde import Kunde
from app.models.projekt import Projekt, ProjektAufgabe, ProjektSpalte
from app.models.standort import Standort
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
from app.services.rechte_service import hat_recht

# Basisrechte fuer alles unter /api/projekte (Projekte + Spalten -- reine
# Kanban-Konfiguration, es gibt hier keine private Variante).
router = APIRouter(
    prefix="/api/projekte",
    tags=["projekte"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("projekte", "sehen")),
    ],
)

# Nur das Rollen-Gate hier -- ob zusaetzlich der Rechte-Bereich "projekte"
# noetig ist, haengt pro Aufgabe davon ab, ob sie zu einem Projekt gehoert
# (Kanban, Recht-gepflichtig) oder privat ist (projekt_id NULL, jeder
# authentifizierte Nutzer darf seine eigenen sehen/bearbeiten/loeschen,
# siehe _pruefe_zugriff_auf_aufgabe() unten).
aufgaben_router = APIRouter(
    prefix="/api/projekt-aufgaben",
    tags=["projekte"],
    dependencies=[Depends(require_roles("mandant_admin", "custom", "loesch_operativ"))],
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


async def _hat_projekte_recht(session: AsyncSession, auth: AuthContext, aktion: str) -> bool:
    """Gleiche Logik wie require_recht(), aber als Bool statt als Dependency
    -- gebraucht, weil sich hier erst zur Laufzeit (anhand der Aufgabe)
    entscheidet, ob das Recht ueberhaupt gefragt ist."""
    if auth.role != "custom":
        return True
    return await hat_recht(session, account_typ_id=auth.account_typ_id, bereich="projekte", aktion=aktion)


async def _pruefe_zugriff_auf_aufgabe(
    session: AsyncSession, auth: AuthContext, aufgabe: ProjektAufgabe, aktion: str
) -> None:
    """Private Aufgabe (projekt_id NULL): nur Ersteller/Zugewiesener duerfen
    ran, unabhaengig von jedem Rechte-Bereich. Kanban-Aufgabe: wie bisher
    ueber den Rechte-Bereich "projekte" geregelt."""
    if aufgabe.projekt_id is None:
        if auth.user_id not in (aufgabe.zugewiesen_an, aufgabe.erstellt_von):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Keine Berechtigung für diese Aktion")
        return
    if not await _hat_projekte_recht(session, auth, aktion):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Keine Berechtigung für diese Aktion")


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
            vorgang_kunde_name=vorgang_kunde_name,
            anlage_name=anlage_name,
            kunde_name=kunde_name,
            standort_name=standort_name,
            unteraufgaben_gesamt=unteraufgaben_gesamt or 0,
            unteraufgaben_erledigt=unteraufgaben_erledigt or 0,
        )
        for (
            aufgabe,
            zugewiesener_name,
            vorgangsnummer,
            vorgang_kunde_name,
            anlage_name,
            kunde_name,
            standort_name,
            unteraufgaben_gesamt,
            unteraufgaben_erledigt,
        ) in zeilen
    ]


@aufgaben_router.get("", response_model=list[ProjektAufgabeMitDetails])
async def list_aufgaben(
    projekt_id: UUID | None = Query(default=None),
    vorgang_id: UUID | None = Query(default=None),
    eltern_aufgabe_id: UUID | None = Query(default=None),
    mir_zugewiesen: bool = Query(default=False),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[ProjektAufgabeMitDetails]:
    darf_kanban_sehen = await _hat_projekte_recht(session, auth, "sehen")
    eigene_privaten = and_(
        ProjektAufgabe.projekt_id.is_(None),
        or_(ProjektAufgabe.zugewiesen_an == auth.user_id, ProjektAufgabe.erstellt_von == auth.user_id),
    )

    if eltern_aufgabe_id is not None:
        eltern = await _require_aufgabe(session, eltern_aufgabe_id)
        await _pruefe_zugriff_auf_aufgabe(session, auth, eltern, "sehen")
        bedingung = ProjektAufgabe.eltern_aufgabe_id == eltern_aufgabe_id
    elif mir_zugewiesen:
        # "Meine Aufgaben": eigene private Aufgaben, plus -- sofern das
        # Kanban-Recht besteht -- alle einem zugewiesenen Projekt-Aufgaben,
        # projektuebergreifend.
        bedingung = (
            or_(
                eigene_privaten,
                and_(ProjektAufgabe.projekt_id.isnot(None), ProjektAufgabe.zugewiesen_an == auth.user_id),
            )
            if darf_kanban_sehen
            else eigene_privaten
        )
    elif projekt_id is not None:
        if not darf_kanban_sehen:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Keine Berechtigung für diese Aktion")
        # Unteraufgaben erscheinen nicht als eigene Karte auf dem Board.
        bedingung = and_(ProjektAufgabe.projekt_id == projekt_id, ProjektAufgabe.eltern_aufgabe_id.is_(None))
    elif vorgang_id is not None:
        # Verknuepfte-Aufgaben-Ansicht am Vorgang: Kanban-Aufgaben nur mit
        # Recht, eigene private Aufgaben immer -- siehe "nur ich sehe diese
        # Verbindungen, wenn es meine Aufgaben sind".
        bedingung = and_(
            ProjektAufgabe.vorgang_id == vorgang_id,
            eigene_privaten if not darf_kanban_sehen else or_(ProjektAufgabe.projekt_id.isnot(None), eigene_privaten),
        )
    else:
        if not darf_kanban_sehen:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Keine Berechtigung für diese Aktion")
        bedingung = ProjektAufgabe.projekt_id.isnot(None)

    Kind = aliased(ProjektAufgabe)
    VorgangKunde = aliased(Kunde)
    unteraufgaben_gesamt_sq = (
        select(func.count())
        .select_from(Kind)
        .where(Kind.eltern_aufgabe_id == ProjektAufgabe.id, Kind.geloescht_am.is_(None))
        .correlate(ProjektAufgabe)
        .scalar_subquery()
    )
    unteraufgaben_erledigt_sq = (
        select(func.count())
        .select_from(Kind)
        .where(
            Kind.eltern_aufgabe_id == ProjektAufgabe.id,
            Kind.geloescht_am.is_(None),
            Kind.erledigt_am.isnot(None),
        )
        .correlate(ProjektAufgabe)
        .scalar_subquery()
    )

    stmt = (
        select(
            ProjektAufgabe,
            User.name,
            Vorgang.vorgangsnummer,
            VorgangKunde.name,
            Anlage.bezeichnung,
            Kunde.name,
            Standort.bezeichnung,
            unteraufgaben_gesamt_sq,
            unteraufgaben_erledigt_sq,
        )
        .outerjoin(User, User.id == ProjektAufgabe.zugewiesen_an)
        .outerjoin(Vorgang, Vorgang.id == ProjektAufgabe.vorgang_id)
        .outerjoin(VorgangKunde, VorgangKunde.id == Vorgang.kunde_id)
        .outerjoin(Anlage, Anlage.id == ProjektAufgabe.anlage_id)
        .outerjoin(Kunde, Kunde.id == ProjektAufgabe.kunde_id)
        .outerjoin(Standort, Standort.id == ProjektAufgabe.standort_id)
        .where(ProjektAufgabe.geloescht_am.is_(None), bedingung)
        .order_by(ProjektAufgabe.created_at)
    )
    result = await session.execute(stmt)
    return _mit_details(result.all())


async def _pruefe_verknuepfungen(
    session: AsyncSession,
    *,
    vorgang_id: UUID | None,
    anlage_id: UUID | None,
    kunde_id: UUID | None,
    standort_id: UUID | None,
) -> None:
    if vorgang_id is not None and await session.get(Vorgang, vorgang_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if anlage_id is not None and await session.get(Anlage, anlage_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anlage nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if kunde_id is not None and await session.get(Kunde, kunde_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kunde nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if standort_id is not None and await session.get(Standort, standort_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Standort nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )


@aufgaben_router.post("", response_model=ProjektAufgabeRead, status_code=status.HTTP_201_CREATED)
async def create_aufgabe(
    body: ProjektAufgabeCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ProjektAufgabe:
    if body.eltern_aufgabe_id is not None:
        eltern = await _require_aufgabe(session, body.eltern_aufgabe_id)
        await _pruefe_zugriff_auf_aufgabe(session, auth, eltern, "sehen")
        if eltern.eltern_aufgabe_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Unteraufgaben können nicht verschachtelt werden"
            )
        if eltern.projekt_id != body.projekt_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unteraufgabe muss zur selben Aufgabenebene wie die Elternaufgabe gehören",
            )

    if body.projekt_id is not None:
        if not await _hat_projekte_recht(session, auth, "erstellen"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Keine Berechtigung für diese Aktion")
        await _require_projekt(session, body.projekt_id)
        # Unteraufgaben brauchen keine eigene Spalte -- sie erscheinen nicht
        # als eigene Karte auf dem Board (siehe list_aufgaben()).
        if body.eltern_aufgabe_id is None and body.spalte_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Spalte ist für Projekt-Aufgaben erforderlich"
            )
        if body.spalte_id is not None:
            await _require_spalte(session, body.projekt_id, body.spalte_id)

    await _pruefe_verknuepfungen(
        session,
        vorgang_id=body.vorgang_id,
        anlage_id=body.anlage_id,
        kunde_id=body.kunde_id,
        standort_id=body.standort_id,
    )

    aufgabe = ProjektAufgabe(
        mandant_id=auth.mandant_id,
        projekt_id=body.projekt_id,
        spalte_id=body.spalte_id,
        eltern_aufgabe_id=body.eltern_aufgabe_id,
        titel=body.titel,
        beschreibung=body.beschreibung,
        faelligkeit_am=body.faelligkeit_am,
        prioritaet=body.prioritaet,
        zugewiesen_an=body.zugewiesen_an,
        vorgang_id=body.vorgang_id,
        anlage_id=body.anlage_id,
        kunde_id=body.kunde_id,
        standort_id=body.standort_id,
        checkliste=[punkt.model_dump() for punkt in body.checkliste],
        zusatzfelder=body.zusatzfelder,
        erstellt_von=auth.user_id,
    )
    session.add(aufgabe)
    await session.flush()
    return aufgabe


@aufgaben_router.get("/{aufgabe_id}", response_model=ProjektAufgabeRead)
async def get_aufgabe(
    aufgabe_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ProjektAufgabe:
    aufgabe = await _require_aufgabe(session, aufgabe_id)
    await _pruefe_zugriff_auf_aufgabe(session, auth, aufgabe, "sehen")
    return aufgabe


@aufgaben_router.patch("/{aufgabe_id}", response_model=ProjektAufgabeRead)
async def update_aufgabe(
    aufgabe_id: UUID,
    body: ProjektAufgabeUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ProjektAufgabe:
    aufgabe = await _require_aufgabe(session, aufgabe_id)
    await _pruefe_zugriff_auf_aufgabe(session, auth, aufgabe, "bearbeiten")
    changes = body.model_dump(exclude_unset=True)

    if "spalte_id" in changes and changes["spalte_id"] is not None:
        if aufgabe.projekt_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Private Aufgaben haben keine Spalte")
        await _require_spalte(session, aufgabe.projekt_id, changes["spalte_id"])

    if "eltern_aufgabe_id" in changes and changes["eltern_aufgabe_id"] is not None:
        neue_eltern_id = changes["eltern_aufgabe_id"]
        if neue_eltern_id == aufgabe.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Eine Aufgabe kann nicht ihre eigene Elternaufgabe sein"
            )
        eltern = await _require_aufgabe(session, neue_eltern_id)
        await _pruefe_zugriff_auf_aufgabe(session, auth, eltern, "sehen")
        if eltern.eltern_aufgabe_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Unteraufgaben können nicht verschachtelt werden"
            )
        if eltern.projekt_id != aufgabe.projekt_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unteraufgabe muss zur selben Aufgabenebene wie die Elternaufgabe gehören",
            )

    await _pruefe_verknuepfungen(
        session,
        vorgang_id=changes.get("vorgang_id"),
        anlage_id=changes.get("anlage_id"),
        kunde_id=changes.get("kunde_id"),
        standort_id=changes.get("standort_id"),
    )

    if "checkliste" in changes and changes["checkliste"] is not None:
        changes["checkliste"] = [punkt.model_dump() for punkt in body.checkliste]
    if "erledigt" in changes:
        erledigt = changes.pop("erledigt")
        changes["erledigt_am"] = datetime.now(UTC) if erledigt else None

    for feld, wert in changes.items():
        setattr(aufgabe, feld, wert)
    await session.flush()
    await session.refresh(aufgabe)
    return aufgabe


@aufgaben_router.delete("/{aufgabe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_aufgabe(
    aufgabe_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    aufgabe = await _require_aufgabe(session, aufgabe_id)
    await _pruefe_zugriff_auf_aufgabe(session, auth, aufgabe, "loeschen")
    geloescht = await papierkorb_service.soft_delete(
        session, entity_typ="projekt_aufgabe", entity_id=aufgabe_id, actor_user_id=auth.user_id
    )
    if geloescht is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aufgabe nicht gefunden")
