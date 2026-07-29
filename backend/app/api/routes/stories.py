from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.core.config import get_settings
from app.models.anlage import Anlage
from app.models.material import Material
from app.models.pruefmittel import Pruefmittel
from app.models.pruefzyklus import Pruefzyklus
from app.models.termin import Termin
from app.models.vorgang import Vorgang
from app.schemas.story import Ampel, StoriesResponse, StoryItem

router = APIRouter(
    prefix="/api/stories",
    tags=["stories"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)

WARTET_KUNDE_SCHWELLE_TAGE = 3
FRIST_GELB_SCHWELLE_TAGE = 7


def _frist_ampel(faellig_am: date, heute: date) -> Ampel:
    if faellig_am < heute:
        return "rot"
    if faellig_am <= heute + timedelta(days=FRIST_GELB_SCHWELLE_TAGE):
        return "gelb"
    return "gruen"


@router.get("", response_model=StoriesResponse)
async def get_stories(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> StoriesResponse:
    settings = get_settings()
    jetzt = datetime.now(timezone.utc)
    heute_datum = jetzt.date()
    schwelle = jetzt - timedelta(days=WARTET_KUNDE_SCHWELLE_TAGE)

    # "heute": die eigene Tagesplanung des Aufrufers -- die Story-Leiste ist
    # eine persönliche Kurzübersicht, kein Dispo-Board für das ganze Team
    # (das liefert Phase 5 separat als eigene Desktop-Ansicht).
    tag_start = datetime.combine(heute_datum, time.min, tzinfo=timezone.utc)
    tag_ende = datetime.combine(heute_datum, time.max, tzinfo=timezone.utc)
    termine_result = await session.execute(
        select(Termin)
        .where(
            Termin.techniker_id == auth.user_id,
            Termin.status != "abgesagt",
            Termin.start_at <= tag_ende,
            Termin.ende_at >= tag_start,
        )
        .order_by(Termin.start_at.asc())
    )
    heute = [
        StoryItem(
            titel=t.titel,
            subtitel=f"{t.start_at:%H:%M}–{t.ende_at:%H:%M}",
            ziel_typ="vorgang",
            ziel_id=t.vorgang_id,
        )
        for t in termine_result.scalars().all()
    ]

    # "fristen": faellige/bald faellige Pruefzyklen (Anlagen) und
    # Pruefmittel-Kalibrierungen, mandantenweit -- Fristen betreffen die
    # ganze Disposition, nicht nur den eigenen Kalender.
    horizont = heute_datum + timedelta(days=settings.pruefzyklus_vorlauf_tage)
    fristen: list[StoryItem] = []

    pruefzyklen_result = await session.execute(
        select(Pruefzyklus, Anlage.bezeichnung)
        .join(Anlage, Anlage.id == Pruefzyklus.anlage_id)
        .where(Pruefzyklus.aktiv.is_(True), Pruefzyklus.naechste_pruefung_am <= horizont)
        .order_by(Pruefzyklus.naechste_pruefung_am.asc())
    )
    for zyklus, anlage_bezeichnung in pruefzyklen_result.all():
        fristen.append(
            StoryItem(
                titel=f"{zyklus.bezeichnung}: {anlage_bezeichnung}",
                subtitel=f"Fällig am {zyklus.naechste_pruefung_am:%d.%m.%Y}",
                ampel=_frist_ampel(zyklus.naechste_pruefung_am, heute_datum),
                ziel_typ="anlage",
                ziel_id=zyklus.anlage_id,
            )
        )

    pruefmittel_result = await session.execute(
        select(Pruefmittel)
        .where(Pruefmittel.status == "aktiv", Pruefmittel.naechste_kalibrierung_am <= horizont)
        .order_by(Pruefmittel.naechste_kalibrierung_am.asc())
    )
    for mittel in pruefmittel_result.scalars().all():
        fristen.append(
            StoryItem(
                titel=f"Kalibrierung: {mittel.bezeichnung}",
                subtitel=f"Fällig am {mittel.naechste_kalibrierung_am:%d.%m.%Y}",
                ampel=_frist_ampel(mittel.naechste_kalibrierung_am, heute_datum),
                ziel_typ="pruefmittel",
                ziel_id=mittel.id,
            )
        )

    result = await session.execute(
        select(Vorgang)
        .where(Vorgang.status == "wartet_kunde", Vorgang.last_activity_at < schwelle)
        .order_by(Vorgang.last_activity_at.asc())
    )
    wartet_kunde = [
        StoryItem(
            titel=f"{v.vorgangsnummer}: {v.titel}",
            subtitel=f"Seit {(jetzt - v.last_activity_at).days} Tagen ohne Rückmeldung",
            ampel="rot",
            ziel_typ="vorgang",
            ziel_id=v.id,
        )
        for v in result.scalars().all()
    ]

    # "material": Material, dessen Bestand die Mindestmenge erreicht oder
    # unterschritten hat -- rot, wenn bereits aufgebraucht, sonst gelb.
    material_result = await session.execute(
        select(Material).where(Material.bestand <= Material.mindestbestand).order_by(Material.bezeichnung)
    )
    material = [
        StoryItem(
            titel=m.bezeichnung,
            subtitel=f"Bestand: {m.bestand:g} {m.einheit} (Mindestbestand {m.mindestbestand:g})",
            ampel="rot" if m.bestand <= 0 else "gelb",
            ziel_typ="material",
            ziel_id=m.id,
        )
        for m in material_result.scalars().all()
    ]

    return StoriesResponse(
        heute=heute,
        fristen=fristen,
        wartet_kunde=wartet_kunde,
        material=material,
    )
