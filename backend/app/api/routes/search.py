from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.models.anlage import Anlage
from app.models.kunde import Kunde
from app.models.tag import Tag
from app.models.vorgang import Vorgang
from app.schemas.search import SearchHit, SearchResponse

router = APIRouter(
    prefix="/api/search",
    tags=["search"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)

HITS_PER_KATEGORIE = 8


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=1), session: AsyncSession = Depends(get_db)
) -> SearchResponse:
    # Ein führendes '#' durchsucht ausschließlich Tags (Abschnitt 5.3).
    if q.startswith("#"):
        label = q[1:].strip().lower()
        result = await session.execute(
            select(Tag)
            .where(Tag.label.ilike(f"%{label}%"))
            .order_by(func.similarity(Tag.label, label).desc())
            .limit(HITS_PER_KATEGORIE)
        )
        return SearchResponse(
            treffer=[
                SearchHit(kategorie="tag", id=t.id, titel=f"#{t.label}") for t in result.scalars()
            ]
        )

    treffer: list[SearchHit] = []

    kunden_result = await session.execute(
        select(Kunde)
        .where(or_(Kunde.name.ilike(f"%{q}%"), Kunde.kundennummer.ilike(f"%{q}%")))
        .order_by(func.similarity(Kunde.name, q).desc())
        .limit(HITS_PER_KATEGORIE)
    )
    treffer += [
        SearchHit(kategorie="kunde", id=k.id, titel=k.name, subtitel=k.kundennummer)
        for k in kunden_result.scalars()
    ]

    anlagen_result = await session.execute(
        select(Anlage)
        .where(Anlage.bezeichnung.ilike(f"%{q}%"))
        .order_by(func.similarity(Anlage.bezeichnung, q).desc())
        .limit(HITS_PER_KATEGORIE)
    )
    treffer += [
        SearchHit(kategorie="anlage", id=a.id, titel=a.bezeichnung, subtitel=a.anlagentyp)
        for a in anlagen_result.scalars()
    ]

    # Vorgaenge: Volltextsuche (Titel/Beschreibung/Kommentare) ODER
    # Trigram-Treffer auf die Vorgangsnummer, damit "V-1002" genauso
    # funktioniert wie ein Stichwort aus dem Chat.
    vorgaenge_result = await session.execute(
        select(Vorgang)
        .where(
            or_(
                text("search_vector @@ websearch_to_tsquery('german', :q)"),
                Vorgang.vorgangsnummer.ilike(f"%{q}%"),
            )
        )
        .params(q=q)
        .limit(HITS_PER_KATEGORIE)
    )
    treffer += [
        SearchHit(kategorie="vorgang", id=v.id, titel=f"{v.vorgangsnummer}: {v.titel}", subtitel=v.status)
        for v in vorgaenge_result.scalars()
    ]

    tags_result = await session.execute(
        select(Tag)
        .where(Tag.label.ilike(f"%{q}%"))
        .order_by(func.similarity(Tag.label, q).desc())
        .limit(HITS_PER_KATEGORIE)
    )
    treffer += [
        SearchHit(kategorie="tag", id=t.id, titel=f"#{t.label}") for t in tags_result.scalars()
    ]

    return SearchResponse(treffer=treffer)
