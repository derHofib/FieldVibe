from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_recht, require_roles
from app.models.auftrag import Auftrag
from app.models.kunde import Kunde
from app.models.projekt import Projekt
from app.models.standort import Standort
from app.models.vorgang import Vorgang
from app.schemas.auftrag import AuftragCreate, AuftragRead, AuftragStandortKurz, AuftragUpdate
from app.services import leistungsort_service, papierkorb_service, vor_ort_kontakt_service, vorgang_verknuepfung_service
from app.services.vorgang_completion_service import VORGANG_STATUS_GESCHLOSSEN
from app.services.zuweisung_service import erlaubte_kunde_ids, require_kunde_zugewiesen

# Nutzt bewusst den bestehenden Rechte-Bereich "projekte" (siehe
# app/models/auftrag.py) -- kein eigener Bereich noetig.
router = APIRouter(
    prefix="/api/auftraege",
    tags=["auftraege"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("projekte", "sehen")),
    ],
)


async def _require_auftrag(session: AsyncSession, auth: AuthContext, auftrag_id: UUID) -> Auftrag:
    auftrag = await session.get(Auftrag, auftrag_id)
    if auftrag is None or auftrag.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auftrag nicht gefunden")
    # Auftraege ohne Kunde bleiben fuer Eingeschraenkte sichtbar (kein
    # Kundenbezug, den man schuetzen muesste) -- anders als
    # require_kunde_zugriff, das kunde_id=None sperrt.
    if auftrag.kunde_id is not None:
        erlaubt = await erlaubte_kunde_ids(session, auth)
        if erlaubt is not None and auftrag.kunde_id not in erlaubt:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auftrag nicht gefunden")
    return auftrag


def _ansprechpartner_liste(kunde: Kunde) -> list[dict]:
    return [a for a in (kunde.ansprechpartner or []) if isinstance(a, dict)]


async def _pruefe_leistungsort(
    session: AsyncSession, kunde_id: UUID | None, standort_id: UUID | None, ansprechpartner_id: UUID | None
) -> None:
    """Standort und Sachbearbeitung gehoeren zum Auftraggeber. Bei einem Kundenwechsel wird nichts still
    geleert, sondern abgelehnt (422): der Nutzer soll bewusst neu waehlen."""
    if standort_id is None and ansprechpartner_id is None:
        return
    if kunde_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Erst einen Auftraggeber setzen")
    if standort_id is not None:
        await vor_ort_kontakt_service.standort_pruefen(session, standort_id, kunde_id)
    if ansprechpartner_id is not None:
        kunde = await session.get(Kunde, kunde_id)
        if kunde is None or str(ansprechpartner_id) not in {str(a.get("id")) for a in _ansprechpartner_liste(kunde)}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Ansprechpartner gehört nicht zum Auftraggeber",
            )


async def _anreichern(session: AsyncSession, auftraege: list[Auftrag]) -> list[AuftragRead]:
    """Kunde-Name + Vorgaenge-Anzahl transient anreichern (gleiches Muster
    wie VorgangRead.zugewiesener_name) -- erspart dem Frontend zusaetzliche
    Abfragen fuer die Tabellen-Ansicht."""
    if not auftraege:
        return []
    rechnung_an = await leistungsort_service.kunden_kurz(
        session, {a.rechnung_an_kunde_id for a in auftraege if a.rechnung_an_kunde_id is not None}
    )
    kunde_ids = {a.kunde_id for a in auftraege if a.kunde_id is not None}
    kunden_namen: dict[UUID, str] = {}
    kunden_ansprechpartner: dict[UUID, list] = {}
    if kunde_ids:
        result = await session.execute(select(Kunde.id, Kunde.name, Kunde.ansprechpartner).where(Kunde.id.in_(kunde_ids)))
        zeilen = result.all()
        kunden_namen = {row.id: row.name for row in zeilen}
        kunden_ansprechpartner = {row.id: row.ansprechpartner or [] for row in zeilen}

    standort_ids = {a.standort_id for a in auftraege if a.standort_id is not None}
    standorte: dict[UUID, Standort] = {}
    if standort_ids:
        standorte = {
            s.id: s for s in (await session.execute(select(Standort).where(Standort.id.in_(standort_ids)))).scalars()
        }

    vorgaenge_counts: dict[UUID, int] = {}
    auftrag_ids = [a.id for a in auftraege]
    count_result = await session.execute(
        select(Vorgang.auftrag_id, func.count(Vorgang.id))
        .where(Vorgang.auftrag_id.in_(auftrag_ids), Vorgang.geloescht_am.is_(None))
        .group_by(Vorgang.auftrag_id)
    )
    vorgaenge_counts = {row[0]: row[1] for row in count_result}
    erledigt_result = await session.execute(
        select(Vorgang.auftrag_id, func.count(Vorgang.id))
        .where(
            Vorgang.auftrag_id.in_(auftrag_ids),
            Vorgang.geloescht_am.is_(None),
            Vorgang.status.in_(sorted(VORGANG_STATUS_GESCHLOSSEN)),
        )
        .group_by(Vorgang.auftrag_id)
    )
    vorgaenge_erledigt = {row[0]: row[1] for row in erledigt_result}

    projekt_ids = {a.projekt_id for a in auftraege if a.projekt_id is not None}
    projekt_namen: dict[UUID, str] = {}
    if projekt_ids:
        projekt_result = await session.execute(select(Projekt.id, Projekt.name).where(Projekt.id.in_(projekt_ids)))
        projekt_namen = {row.id: row.name for row in projekt_result}

    gelesen = []
    for auftrag in auftraege:
        read = AuftragRead.model_validate(auftrag)
        if auftrag.kunde_id is not None:
            read.kunde_name = kunden_namen.get(auftrag.kunde_id)
        standort = standorte.get(auftrag.standort_id) if auftrag.standort_id else None
        if standort is not None:
            read.standort = AuftragStandortKurz(id=standort.id, bezeichnung=standort.bezeichnung, adresse=standort.adresse)
        if auftrag.kunde_id is not None:
            read.ansprechpartner = vor_ort_kontakt_service.ansprechpartner_aufloesen(
                kunden_ansprechpartner.get(auftrag.kunde_id), auftrag.ansprechpartner_id
            )
        if auftrag.rechnung_an_kunde_id is not None:
            read.rechnung_an = rechnung_an.get(auftrag.rechnung_an_kunde_id)
        read.vorgaenge_gesamt = vorgaenge_counts.get(auftrag.id, 0)
        read.vorgaenge_erledigt = vorgaenge_erledigt.get(auftrag.id, 0)
        if auftrag.projekt_id is not None:
            read.projekt_name = projekt_namen.get(auftrag.projekt_id)
        gelesen.append(read)
    return gelesen


@router.get("", response_model=list[AuftragRead])
async def list_auftraege(
    projekt_id: UUID | None = Query(default=None),
    kunde_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[AuftragRead]:
    stmt = select(Auftrag).where(Auftrag.geloescht_am.is_(None)).order_by(Auftrag.created_at.desc())
    if projekt_id:
        stmt = stmt.where(Auftrag.projekt_id == projekt_id)
    if kunde_id:
        stmt = stmt.where(Auftrag.kunde_id == kunde_id)
    if status_filter:
        stmt = stmt.where(Auftrag.status == status_filter)
    erlaubte_kunden = await erlaubte_kunde_ids(session, auth)
    if erlaubte_kunden is not None:
        stmt = stmt.where(or_(Auftrag.kunde_id.is_(None), Auftrag.kunde_id.in_(erlaubte_kunden)))
    result = await session.execute(stmt)
    return await _anreichern(session, list(result.scalars().all()))


@router.post(
    "",
    response_model=AuftragRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recht("projekte", "erstellen"))],
)
async def create_auftrag(
    body: AuftragCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AuftragRead:
    if body.projekt_id is not None and await session.get(Projekt, body.projekt_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Projekt nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if body.kunde_id is not None:
        await require_kunde_zugewiesen(session, auth, body.kunde_id)
        if await session.get(Kunde, body.kunde_id) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Kunde nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
    await _pruefe_leistungsort(session, body.kunde_id, body.standort_id, body.ansprechpartner_id)
    rechnung_an_kunde_id = await leistungsort_service.rechnung_an_pruefen(
        session, body.rechnung_an_kunde_id, body.kunde_id
    )
    auftrag = Auftrag(
        mandant_id=auth.mandant_id,
        projekt_id=body.projekt_id,
        kunde_id=body.kunde_id,
        standort_id=body.standort_id,
        einheit=body.einheit,
        ansprechpartner_id=body.ansprechpartner_id,
        kunden_referenz=body.kunden_referenz,
        rechnung_an_kunde_id=rechnung_an_kunde_id,
        titel=body.titel,
        beschreibung=body.beschreibung,
        erstellt_von=auth.user_id,
    )
    session.add(auftrag)
    await session.flush()
    await session.refresh(auftrag)
    [gelesen] = await _anreichern(session, [auftrag])
    return gelesen


@router.get("/{auftrag_id}", response_model=AuftragRead)
async def get_auftrag(
    auftrag_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AuftragRead:
    auftrag = await _require_auftrag(session, auth, auftrag_id)
    [gelesen] = await _anreichern(session, [auftrag])
    return gelesen


@router.patch(
    "/{auftrag_id}",
    response_model=AuftragRead,
    dependencies=[Depends(require_recht("projekte", "bearbeiten"))],
)
async def update_auftrag(
    auftrag_id: UUID,
    body: AuftragUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AuftragRead:
    auftrag = await _require_auftrag(session, auth, auftrag_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("projekt_id") is not None and await session.get(Projekt, changes["projekt_id"]) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Projekt nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if changes.get("kunde_id") is not None:
        await require_kunde_zugewiesen(session, auth, changes["kunde_id"])
        if await session.get(Kunde, changes["kunde_id"]) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Kunde nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
    if changes.keys() & {"kunde_id", "standort_id", "ansprechpartner_id"}:
        kunde_neu = changes.get("kunde_id", auftrag.kunde_id)
        await _pruefe_leistungsort(
            session,
            kunde_neu,
            changes.get("standort_id", auftrag.standort_id),
            changes.get("ansprechpartner_id", auftrag.ansprechpartner_id),
        )
        if "kunde_id" in changes and kunde_neu != auftrag.kunde_id:
            await vor_ort_kontakt_service.kundenwechsel_pruefen(session, "auftrag_id", auftrag.id, kunde_neu)
    altes_projekt_id = auftrag.projekt_id
    for feld, wert in changes.items():
        setattr(auftrag, feld, wert)
    if changes.keys() & {"kunde_id", "rechnung_an_kunde_id"}:
        auftrag.rechnung_an_kunde_id = await leistungsort_service.rechnung_an_pruefen(
            session, auftrag.rechnung_an_kunde_id, auftrag.kunde_id
        )
    if "projekt_id" in changes and changes["projekt_id"] != altes_projekt_id:
        await vorgang_verknuepfung_service.vorgaenge_des_auftrags_mitziehen(
            session, auftrag, changes["projekt_id"], author_user_id=auth.user_id
        )
    await session.flush()
    await session.refresh(auftrag)
    [gelesen] = await _anreichern(session, [auftrag])
    return gelesen


@router.delete(
    "/{auftrag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_recht("projekte", "loeschen"))],
)
async def delete_auftrag(
    auftrag_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await _require_auftrag(session, auth, auftrag_id)
    auftrag = await papierkorb_service.soft_delete(
        session, entity_typ="auftrag", entity_id=auftrag_id, actor_user_id=auth.user_id
    )
    if auftrag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auftrag nicht gefunden")
