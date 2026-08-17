"""Geocodiert bestehende Standorte/Anlagen nach, die eine Adresse aber noch
keine Koordinaten haben -- fuer Mandanten, die das Modul "karten" bereits
aktiviert haben (nur diese hatten bislang ueberhaupt eine Chance auf
Auto-Geocoding, siehe app/services/geocoding_service.py). Ohne konfigurierten
MAPBOX_ACCESS_TOKEN bricht der Lauf sofort ab, statt fuer jede Zeile einzeln
zu scheitern.

`backfill_geocode_fuer_mandant()` ist die pro-Mandant-Kernlogik und wird auch
direkt beim Aktivieren des Moduls "karten" in app/api/routes/mandanten.py
aufgerufen (siehe update_mandant) -- Admins muessen nach dem Aktivieren also
nicht mehr wissen, dass es dieses Skript ueberhaupt gibt.

Idempotent: ueberspringt Zeilen, die schon Koordinaten haben. Sicher mehrfach
ausfuehrbar. Manueller Lauf ueber alle Mandanten (z.B. nach nachtraeglichem
Setzen von MAPBOX_ACCESS_TOKEN) mit:

    docker compose run --rm backend python -m app.backfill_geocode
"""
import asyncio
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import system_session
from app.models.anlage import Anlage
from app.models.mandant import Mandant
from app.models.standort import Standort
from app.services.geocoding_service import geocode_adresse


async def backfill_geocode_fuer_mandant(session: AsyncSession, mandant_id: UUID) -> tuple[int, int]:
    """Geocodiert Standorte/Anlagen eines einzelnen Mandanten nach. Setzt
    voraus, dass der Aufrufer bereits geprueft hat, dass ein
    MAPBOX_ACCESS_TOKEN konfiguriert ist. Gibt (anzahl_geocodiert,
    anzahl_ohne_treffer) zurueck, committet aber nicht selbst."""
    anzahl_geocodiert = 0
    anzahl_ohne_treffer = 0

    for model in (Standort, Anlage):
        result = await session.execute(
            select(model).where(
                model.mandant_id == mandant_id,
                model.geloescht_am.is_(None),
                model.geo_lat.is_(None),
                model.geo_lng.is_(None),
            )
        )
        for zeile in result.scalars().all():
            if not zeile.adresse:
                continue
            koordinaten = await geocode_adresse(zeile.adresse)
            if koordinaten is None:
                anzahl_ohne_treffer += 1
                continue
            zeile.geo_lat, zeile.geo_lng = koordinaten
            anzahl_geocodiert += 1

    return anzahl_geocodiert, anzahl_ohne_treffer


async def backfill_geocode() -> None:
    settings = get_settings()
    if not settings.mapbox_access_token:
        print("[backfill_geocode] Kein MAPBOX_ACCESS_TOKEN konfiguriert -- abgebrochen.")
        return

    async with system_session() as session:
        result = await session.execute(select(Mandant))
        mandant_ids = {
            m.id for m in result.scalars().all() if "karten" not in m.deaktivierte_module
        }
        if not mandant_ids:
            print("[backfill_geocode] Kein Mandant hat das Modul 'karten' aktiviert.")
            return

        anzahl_geocodiert = 0
        anzahl_ohne_treffer = 0
        for mandant_id in mandant_ids:
            geocodiert, ohne_treffer = await backfill_geocode_fuer_mandant(session, mandant_id)
            anzahl_geocodiert += geocodiert
            anzahl_ohne_treffer += ohne_treffer

        await session.flush()

    print(
        f"\n[backfill_geocode] Fertig: {anzahl_geocodiert} geocodiert, "
        f"{anzahl_ohne_treffer} ohne Treffer/Adresse übersprungen."
    )


if __name__ == "__main__":
    asyncio.run(backfill_geocode())
