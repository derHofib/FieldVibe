from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.models.vorgang import Vorgang
from app.schemas.story import StoriesResponse, StoryItem

router = APIRouter(
    prefix="/api/stories",
    tags=["stories"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)

WARTET_KUNDE_SCHWELLE_TAGE = 3


@router.get("", response_model=StoriesResponse)
async def get_stories(session: AsyncSession = Depends(get_db)) -> StoriesResponse:
    schwelle = datetime.now(timezone.utc) - timedelta(days=WARTET_KUNDE_SCHWELLE_TAGE)
    result = await session.execute(
        select(Vorgang)
        .where(Vorgang.status == "wartet_kunde", Vorgang.last_activity_at < schwelle)
        .order_by(Vorgang.last_activity_at.asc())
    )
    wartet_kunde = [
        StoryItem(
            titel=f"{v.vorgangsnummer}: {v.titel}",
            subtitel=f"Seit {(datetime.now(timezone.utc) - v.last_activity_at).days} Tagen ohne Rückmeldung",
            ampel="rot",
            ziel_typ="vorgang",
            ziel_id=v.id,
        )
        for v in result.scalars().all()
    ]

    return StoriesResponse(
        # "heute" (Termine) und "fristen" (Pruefzyklen/Pruefmittel) brauchen
        # Datenmodelle aus Phase 5, "material" aus Phase 7 -- bis dahin
        # liefert die Story-Leiste hier bewusst leere, aber typisierte Arrays
        # statt erfundener Platzhalterdaten.
        heute=[],
        fristen=[],
        wartet_kunde=wartet_kunde,
        material=[],
    )
