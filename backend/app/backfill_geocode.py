"""Geocodiert bestehende Standorte/Anlagen nach, die eine Adresse aber noch
keine Koordinaten haben -- fuer Mandanten, die das Modul "karten" bereits
aktiviert haben (nur diese hatten bislang ueberhaupt eine Chance auf
Auto-Geocoding, siehe app/services/geocoding_service.py). Ohne konfigurierten
MAPBOX_ACCESS_TOKEN bricht der Lauf sofort ab, statt fuer jede Zeile einzeln
zu scheitern.

Idempotent: ueberspringt Zeilen, die schon Koordinaten haben. Sicher mehrfach
ausfuehrbar, z.B. nach dem erstmaligen Aktivieren des Moduls fuer einen
Mandanten. Run mit:

    docker compose run --rm backend python -m app.backfill_geocode
"""
import asyncio

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import system_session
from app.models.anlage import Anlage
from app.models.mandant import Mandant
from app.models.standort import Standort
from app.services.geocoding_service import geocode_adresse


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

        for model, label in ((Standort, "Standort"), (Anlage, "Anlage")):
            result = await session.execute(
                select(model).where(
                    model.mandant_id.in_(mandant_ids),
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
                print(f"[backfill_geocode] {label} {zeile.id}: {koordinaten}")

        await session.flush()

    print(
        f"\n[backfill_geocode] Fertig: {anzahl_geocodiert} geocodiert, "
        f"{anzahl_ohne_treffer} ohne Treffer/Adresse übersprungen."
    )


if __name__ == "__main__":
    asyncio.run(backfill_geocode())
