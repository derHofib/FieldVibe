import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.mandant import Mandant

logger = logging.getLogger(__name__)


def _adresse_als_zeile(adresse: dict) -> str:
    strasse = (adresse.get("strasse") or "").strip()
    plz = (adresse.get("plz") or "").strip()
    ort = (adresse.get("ort") or "").strip()
    return ", ".join(teil for teil in (strasse, f"{plz} {ort}".strip()) if teil)


async def geocode_adresse(adresse: dict) -> tuple[float, float] | None:
    """Wandelt eine Adresse (dict mit strasse/plz/ort) per Mapbox-Geocoding-
    API in (geo_lat, geo_lng) um. Liefert None statt eines Fehlers, wenn kein
    Token konfiguriert ist, die Adresse leer ist oder Mapbox nicht erreichbar
    ist -- Geocoding ist immer ein Best-Effort-Zusatz, nie eine Voraussetzung
    fuers Speichern von Anlage/Standort. Mapbox liefert Koordinaten als
    [lng, lat] ("center") -- hier bewusst auf unsere (lat, lng)-Konvention
    gedreht, damit Aufrufer nicht selbst vertauschen muessen."""
    settings = get_settings()
    if not settings.mapbox_access_token:
        return None

    zeile = _adresse_als_zeile(adresse)
    if not zeile:
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"https://api.mapbox.com/geocoding/v5/mapbox.places/{zeile}.json",
                params={"access_token": settings.mapbox_access_token, "limit": 1},
            )
            resp.raise_for_status()
            data = resp.json()

        features = data.get("features") or []
        if not features:
            return None
        lng, lat = features[0]["center"]
        return (lat, lng)
    except Exception:
        logger.warning("Geocoding fehlgeschlagen für Adresse %r", zeile, exc_info=True)
        return None


async def geocode_falls_modul_aktiv(
    session: AsyncSession, mandant_id, adresse: dict
) -> tuple[float, float] | None:
    """Wie geocode_adresse, ruft Mapbox aber nur auf, wenn der Mandant das
    Modul 'karten' aktiv hat -- verhindert, dass Mandanten ohne Kartenansicht
    unbemerkt Mapbox-Kosten verursachen (siehe MANDANT_MODULE)."""
    mandant = await session.get(Mandant, mandant_id)
    if mandant is None or "karten" in mandant.deaktivierte_module:
        return None
    return await geocode_adresse(adresse)
