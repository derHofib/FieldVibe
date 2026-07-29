from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.anlage import Anlage
from app.models.termin import Termin
from app.models.vorgang import Vorgang
from app.schemas.termin import TerminWarnung

_ERDRADIUS_KM = 6371.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lng2 - lng1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * _ERDRADIUS_KM * asin(sqrt(a))


async def _anlage_geo(session: AsyncSession, anlage_id: UUID | None) -> tuple[float, float] | None:
    if anlage_id is None:
        return None
    anlage = await session.get(Anlage, anlage_id)
    if anlage is None or anlage.geo_lat is None or anlage.geo_lng is None:
        return None
    return (anlage.geo_lat, anlage.geo_lng)


async def compute_warnungen(
    session: AsyncSession,
    *,
    techniker_id: UUID,
    start_at: datetime,
    ende_at: datetime,
    anlage_id: UUID | None,
    exclude_termin_id: UUID | None = None,
) -> list[TerminWarnung]:
    """Ueberschneidungs- und Fahrzeit-Warnungen fuer einen (geplanten) Termin.

    Beides sind Warnungen, kein Hard-Block (Abschnitt 12): der Disponent
    kann trotzdem speichern, soll die Kollision aber sehen. Die
    Fahrzeit-Schaetzung ist eine grobe Luftlinien-Heuristik (Haversine
    durch eine angenommene Durchschnittsgeschwindigkeit plus Puffer), kein
    echter Routendienst -- fuer die Handwerker-Praxis reicht das, um
    offensichtlich zu enge Planungen ("zwei Termine am anderen Ende der
    Stadt in 15 Minuten") zu erkennen.
    """
    settings = get_settings()
    warnungen: list[TerminWarnung] = []

    base_stmt = select(Termin).where(
        Termin.techniker_id == techniker_id, Termin.status != "abgesagt"
    )
    if exclude_termin_id is not None:
        base_stmt = base_stmt.where(Termin.id != exclude_termin_id)

    overlap_stmt = base_stmt.where(Termin.start_at < ende_at, Termin.ende_at > start_at)
    overlaps = (await session.execute(overlap_stmt)).scalars().all()
    for t in overlaps:
        warnungen.append(
            TerminWarnung(
                typ="ueberschneidung",
                meldung=(
                    f'Überschneidung mit Termin "{t.titel}" '
                    f"({t.start_at:%d.%m. %H:%M}–{t.ende_at:%H:%M})"
                ),
                anderer_termin_id=t.id,
            )
        )

    neue_geo = await _anlage_geo(session, anlage_id)
    if neue_geo is not None:
        required_minuten = (
            lambda distanz_km: distanz_km / settings.dispo_geschwindigkeit_kmh * 60
            + settings.dispo_puffer_minuten
        )

        prev_termin = (
            await session.execute(
                base_stmt.where(Termin.ende_at <= start_at)
                .order_by(Termin.ende_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if prev_termin is not None:
            prev_vorgang = await session.get(Vorgang, prev_termin.vorgang_id)
            prev_geo = await _anlage_geo(session, prev_vorgang.anlage_id if prev_vorgang else None)
            if prev_geo is not None:
                distanz = haversine_km(*prev_geo, *neue_geo)
                benoetigt = required_minuten(distanz)
                verfuegbar = (start_at - prev_termin.ende_at).total_seconds() / 60
                if verfuegbar < benoetigt:
                    warnungen.append(
                        TerminWarnung(
                            typ="fahrzeit",
                            meldung=(
                                f"Fahrzeit zu knapp: nur {verfuegbar:.0f} Min. Pause nach "
                                f'"{prev_termin.titel}", ca. {benoetigt:.0f} Min. nötig '
                                f"({distanz:.1f} km Luftlinie)"
                            ),
                            anderer_termin_id=prev_termin.id,
                        )
                    )

        next_termin = (
            await session.execute(
                base_stmt.where(Termin.start_at >= ende_at)
                .order_by(Termin.start_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if next_termin is not None:
            next_vorgang = await session.get(Vorgang, next_termin.vorgang_id)
            next_geo = await _anlage_geo(session, next_vorgang.anlage_id if next_vorgang else None)
            if next_geo is not None:
                distanz = haversine_km(*neue_geo, *next_geo)
                benoetigt = required_minuten(distanz)
                verfuegbar = (next_termin.start_at - ende_at).total_seconds() / 60
                if verfuegbar < benoetigt:
                    warnungen.append(
                        TerminWarnung(
                            typ="fahrzeit",
                            meldung=(
                                f"Fahrzeit zu knapp: nur {verfuegbar:.0f} Min. Pause vor "
                                f'"{next_termin.titel}", ca. {benoetigt:.0f} Min. nötig '
                                f"({distanz:.1f} km Luftlinie)"
                            ),
                            anderer_termin_id=next_termin.id,
                        )
                    )

    return warnungen
