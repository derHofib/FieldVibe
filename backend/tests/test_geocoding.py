from unittest.mock import patch

import pytest

from app.core.config import get_settings
from app.db.session import system_session
from app.services.geocoding_service import geocode_adresse, geocode_falls_modul_aktiv
from tests.conftest import auth_headers, login


class _FakeResponse:
    def __init__(self, data: dict):
        self._data = data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._data


class _FakeAsyncClient:
    """Simuliert eine erfolgreiche Mapbox-Geocoding-Antwort fuer Berlin."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, *args, **kwargs) -> _FakeResponse:
        # Mapbox liefert "center" als [lng, lat], nicht [lat, lng].
        return _FakeResponse({"features": [{"center": [13.405, 52.52]}]})


class _EmptyAsyncClient(_FakeAsyncClient):
    async def get(self, *args, **kwargs) -> _FakeResponse:
        return _FakeResponse({"features": []})


class _FailingAsyncClient(_FakeAsyncClient):
    async def get(self, *args, **kwargs):
        raise ConnectionError("kein Netz")


class _AbortIfCalledAsyncClient(_FakeAsyncClient):
    """Faellt den Test durch, falls Mapbox ueberhaupt aufgerufen wird --
    fuer Faelle, in denen genau das nicht passieren darf (Modul aus, leere
    Adresse, explizit gesetzte Koordinaten)."""

    async def get(self, *args, **kwargs):
        raise AssertionError("Mapbox haette hier nicht aufgerufen werden duerfen")


async def _deaktiviere_module(client, super_admin_token, mandant_id, module: list[str]) -> None:
    resp = await client.patch(
        f"/api/admin/mandanten/{mandant_id}",
        headers=auth_headers(super_admin_token),
        json={"deaktivierte_module": module},
    )
    assert resp.status_code == 200


# --- geocode_adresse (reine Service-Funktion) ------------------------------


@pytest.mark.asyncio
async def test_geocode_adresse_ohne_token_liefert_none():
    with patch.object(get_settings(), "mapbox_access_token", None):
        with patch("app.services.geocoding_service.httpx.AsyncClient", _AbortIfCalledAsyncClient):
            koordinaten = await geocode_adresse({"strasse": "Teststr. 1", "plz": "10117", "ort": "Berlin"})
    assert koordinaten is None


@pytest.mark.asyncio
async def test_geocode_adresse_bei_leerer_adresse_liefert_none():
    with patch.object(get_settings(), "mapbox_access_token", "pk.test-token"):
        with patch("app.services.geocoding_service.httpx.AsyncClient", _AbortIfCalledAsyncClient):
            koordinaten = await geocode_adresse({})
    assert koordinaten is None


@pytest.mark.asyncio
async def test_geocode_adresse_parst_mapbox_response_lat_lng_richtig():
    with patch.object(get_settings(), "mapbox_access_token", "pk.test-token"):
        with patch("app.services.geocoding_service.httpx.AsyncClient", _FakeAsyncClient):
            koordinaten = await geocode_adresse({"strasse": "Teststr. 1", "plz": "10117", "ort": "Berlin"})
    assert koordinaten == (52.52, 13.405)


@pytest.mark.asyncio
async def test_geocode_adresse_ohne_treffer_liefert_none():
    with patch.object(get_settings(), "mapbox_access_token", "pk.test-token"):
        with patch("app.services.geocoding_service.httpx.AsyncClient", _EmptyAsyncClient):
            koordinaten = await geocode_adresse({"strasse": "Nirgendwostr. 1", "ort": "Nirgendwo"})
    assert koordinaten is None


@pytest.mark.asyncio
async def test_geocode_adresse_bei_netzwerkfehler_liefert_none_statt_crash():
    with patch.object(get_settings(), "mapbox_access_token", "pk.test-token"):
        with patch("app.services.geocoding_service.httpx.AsyncClient", _FailingAsyncClient):
            koordinaten = await geocode_adresse({"strasse": "Teststr. 1", "ort": "Berlin"})
    assert koordinaten is None


# --- geocode_falls_modul_aktiv (Modul-Gate) --------------------------------


@pytest.mark.asyncio
async def test_geocode_falls_modul_aktiv_ueberspringt_wenn_karten_deaktiviert(make_mandant):
    mandant = await make_mandant()  # "karten" ist per Default deaktiviert
    with patch.object(get_settings(), "mapbox_access_token", "pk.test-token"):
        with patch("app.services.geocoding_service.httpx.AsyncClient", _AbortIfCalledAsyncClient):
            async with system_session() as session:
                koordinaten = await geocode_falls_modul_aktiv(
                    session, mandant.id, {"strasse": "Teststr. 1", "ort": "Berlin"}
                )
    assert koordinaten is None


# --- Auto-Geocoding beim Anlegen/Aendern von Standort/Anlage ---------------


@pytest.mark.asyncio
async def test_standort_ohne_karten_modul_bleibt_ohne_koordinaten(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    with patch.object(get_settings(), "mapbox_access_token", "pk.test-token"):
        with patch("app.services.geocoding_service.httpx.AsyncClient", _AbortIfCalledAsyncClient):
            resp = await client.post(
                "/api/standorte",
                headers=auth_headers(token),
                json={
                    "kunde_id": str(kunde.id),
                    "bezeichnung": "Filiale Nord",
                    "adresse": {"strasse": "Teststr. 1", "plz": "10117", "ort": "Berlin"},
                },
            )
    assert resp.status_code == 201
    assert resp.json()["geo_lat"] is None
    assert resp.json()["geo_lng"] is None


@pytest.mark.asyncio
async def test_standort_mit_karten_modul_wird_automatisch_geocodiert(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    super_admin = await make_user(mandant=None, role="super_admin", password="admin-pass-1")
    super_admin_token = await login(client, super_admin.email, "admin-pass-1")
    await _deaktiviere_module(client, super_admin_token, mandant.id, [])  # "karten" aktivieren

    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    with patch.object(get_settings(), "mapbox_access_token", "pk.test-token"):
        with patch("app.services.geocoding_service.httpx.AsyncClient", _FakeAsyncClient):
            resp = await client.post(
                "/api/standorte",
                headers=auth_headers(token),
                json={
                    "kunde_id": str(kunde.id),
                    "bezeichnung": "Filiale Nord",
                    "adresse": {"strasse": "Teststr. 1", "plz": "10117", "ort": "Berlin"},
                },
            )
    assert resp.status_code == 201
    assert resp.json()["geo_lat"] == pytest.approx(52.52)
    assert resp.json()["geo_lng"] == pytest.approx(13.405)


@pytest.mark.asyncio
async def test_standort_mit_expliziten_koordinaten_ueberspringt_geocoding(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    super_admin = await make_user(mandant=None, role="super_admin", password="admin-pass-2")
    super_admin_token = await login(client, super_admin.email, "admin-pass-2")
    await _deaktiviere_module(client, super_admin_token, mandant.id, [])  # "karten" aktivieren

    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    with patch.object(get_settings(), "mapbox_access_token", "pk.test-token"):
        with patch("app.services.geocoding_service.httpx.AsyncClient", _AbortIfCalledAsyncClient):
            resp = await client.post(
                "/api/standorte",
                headers=auth_headers(token),
                json={
                    "kunde_id": str(kunde.id),
                    "bezeichnung": "Filiale Nord",
                    "adresse": {"strasse": "Teststr. 1", "ort": "Berlin"},
                    "geo_lat": 1.23,
                    "geo_lng": 4.56,
                },
            )
    assert resp.status_code == 201
    assert resp.json()["geo_lat"] == pytest.approx(1.23)
    assert resp.json()["geo_lng"] == pytest.approx(4.56)


@pytest.mark.asyncio
async def test_standort_update_adresse_geocodiert_neu(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    super_admin = await make_user(mandant=None, role="super_admin", password="admin-pass-3")
    super_admin_token = await login(client, super_admin.email, "admin-pass-3")
    await _deaktiviere_module(client, super_admin_token, mandant.id, [])  # "karten" aktivieren

    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    create = await client.post(
        "/api/standorte",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "bezeichnung": "Filiale Nord"},
    )
    assert create.status_code == 201
    assert create.json()["geo_lat"] is None
    standort_id = create.json()["id"]

    with patch.object(get_settings(), "mapbox_access_token", "pk.test-token"):
        with patch("app.services.geocoding_service.httpx.AsyncClient", _FakeAsyncClient):
            update = await client.patch(
                f"/api/standorte/{standort_id}",
                headers=auth_headers(token),
                json={"adresse": {"strasse": "Teststr. 1", "plz": "10117", "ort": "Berlin"}},
            )
    assert update.status_code == 200
    assert update.json()["geo_lat"] == pytest.approx(52.52)
    assert update.json()["geo_lng"] == pytest.approx(13.405)


@pytest.mark.asyncio
async def test_anlage_mit_karten_modul_wird_automatisch_geocodiert(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    super_admin = await make_user(mandant=None, role="super_admin", password="admin-pass-4")
    super_admin_token = await login(client, super_admin.email, "admin-pass-4")
    await _deaktiviere_module(client, super_admin_token, mandant.id, [])  # "karten" aktivieren

    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    with patch.object(get_settings(), "mapbox_access_token", "pk.test-token"):
        with patch("app.services.geocoding_service.httpx.AsyncClient", _FakeAsyncClient):
            resp = await client.post(
                "/api/anlagen",
                headers=auth_headers(token),
                json={
                    "kunde_id": str(kunde.id),
                    "bezeichnung": "Hauptverteilung",
                    "adresse": {"strasse": "Teststr. 1", "plz": "10117", "ort": "Berlin"},
                },
            )
    assert resp.status_code == 201
    assert resp.json()["geo_lat"] == pytest.approx(52.52)
    assert resp.json()["geo_lng"] == pytest.approx(13.405)


# --- Automatischer Backfill beim Aktivieren des Moduls "karten" ------------


@pytest.mark.asyncio
async def test_karten_modul_aktivieren_geocodiert_bestehenden_standort_nach(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()  # "karten" ist per Default deaktiviert
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    create = await client.post(
        "/api/standorte",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "bezeichnung": "Filiale Nord",
            "adresse": {"strasse": "Teststr. 1", "plz": "10117", "ort": "Berlin"},
        },
    )
    assert create.status_code == 201
    assert create.json()["geo_lat"] is None
    standort_id = create.json()["id"]

    super_admin = await make_user(mandant=None, role="super_admin", password="admin-pass-5")
    super_admin_token = await login(client, super_admin.email, "admin-pass-5")
    with patch.object(get_settings(), "mapbox_access_token", "pk.test-token"):
        with patch("app.services.geocoding_service.httpx.AsyncClient", _FakeAsyncClient):
            await _deaktiviere_module(client, super_admin_token, mandant.id, [])

    nachher = await client.get(f"/api/standorte/{standort_id}", headers=auth_headers(token))
    assert nachher.status_code == 200
    assert nachher.json()["geo_lat"] == pytest.approx(52.52)
    assert nachher.json()["geo_lng"] == pytest.approx(13.405)


@pytest.mark.asyncio
async def test_karten_modul_aktivieren_ohne_token_bricht_backfill_folgenlos_ab(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    create = await client.post(
        "/api/standorte",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "bezeichnung": "Filiale Nord",
            "adresse": {"strasse": "Teststr. 1", "plz": "10117", "ort": "Berlin"},
        },
    )
    standort_id = create.json()["id"]

    super_admin = await make_user(mandant=None, role="super_admin", password="admin-pass-6")
    super_admin_token = await login(client, super_admin.email, "admin-pass-6")
    with patch.object(get_settings(), "mapbox_access_token", None):
        await _deaktiviere_module(client, super_admin_token, mandant.id, [])

    nachher = await client.get(f"/api/standorte/{standort_id}", headers=auth_headers(token))
    assert nachher.json()["geo_lat"] is None
