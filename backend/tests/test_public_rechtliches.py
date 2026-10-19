import pytest

from app.db.session import system_session
from app.models.mandant import Mandant
from tests.conftest import auth_headers, login

_FIRMENDATEN = {
    "adresse": {"strasse": "Werkstr. 5", "plz": "12345", "ort": "Musterstadt", "land": "DE"},
    "telefon": "0123 456",
    "email": "info@mueller.de",
    "website": "https://mueller.de",
    "geschaeftsfuehrung": "Max Mueller",
    "handelsregister": "HRB 1 Musterstadt",
    "ust_idnr": "DE123456789",
    "steuernummer": "12/345/67890",
    "iban": "DE00123456780000000000",
    "bic": "TESTDEFF",
    "bank_name": "Testbank",
    "impressum_url": "https://mueller.de/impressum",
    "datenschutz_url": "https://mueller.de/datenschutz",
}


async def _firmendaten_setzen(mandant, firmendaten: dict) -> None:
    async with system_session() as session:
        m = await session.get(Mandant, mandant.id)
        m.firmendaten = firmendaten


@pytest.mark.asyncio
async def test_ein_aktiver_mandant_liefert_firmenangaben_und_urls(client, make_mandant):
    mandant = await make_mandant(name="Mueller Elektro")
    await _firmendaten_setzen(mandant, _FIRMENDATEN)

    resp = await client.get("/api/public/rechtliches")

    assert resp.status_code == 200
    body = resp.json()
    assert body["impressum_url"] == "https://mueller.de/impressum"
    assert body["datenschutz_url"] == "https://mueller.de/datenschutz"
    anbieter = body["anbieter"]
    assert anbieter["name"] == "Mueller Elektro"
    assert anbieter["strasse"] == "Werkstr. 5"
    assert anbieter["plz"] == "12345"
    assert anbieter["ort"] == "Musterstadt"
    assert anbieter["telefon"] == "0123 456"
    assert anbieter["geschaeftsfuehrung"] == "Max Mueller"
    assert anbieter["handelsregister"] == "HRB 1 Musterstadt"
    assert anbieter["ust_idnr"] == "DE123456789"


@pytest.mark.asyncio
async def test_antwort_enthaelt_nie_sensible_felder(client, make_mandant):
    mandant = await make_mandant()
    await _firmendaten_setzen(mandant, _FIRMENDATEN)

    resp = await client.get("/api/public/rechtliches")

    text = resp.text.lower()
    for sensibel in ("iban", "bic", "steuernummer", "bank", "12/345/67890", "de0012345678"):
        assert sensibel not in text


@pytest.mark.asyncio
async def test_inaktive_mandanten_zaehlen_nicht(client, make_mandant):
    aktiv = await make_mandant(name="Aktiv")
    await make_mandant(name="Pausiert", status="pausiert")

    resp = await client.get("/api/public/rechtliches")

    assert resp.json()["anbieter"]["name"] == aktiv.name


@pytest.mark.asyncio
async def test_mehrere_mandanten_ohne_slug_liefern_keine_firmenangaben(client, make_mandant):
    m1 = await make_mandant(name="Betrieb A")
    m2 = await make_mandant(name="Betrieb B")
    await _firmendaten_setzen(m1, _FIRMENDATEN)
    await _firmendaten_setzen(m2, _FIRMENDATEN)

    resp = await client.get("/api/public/rechtliches")

    assert resp.status_code == 200
    assert resp.json() == {"impressum_url": None, "datenschutz_url": None, "anbieter": None}


@pytest.mark.asyncio
async def test_kein_mandant_liefert_keine_firmenangaben(client):
    resp = await client.get("/api/public/rechtliches")

    assert resp.status_code == 200
    assert resp.json()["anbieter"] is None


@pytest.mark.asyncio
async def test_gueltiger_slug_liefert_richtigen_mandanten(client, make_mandant, make_kunde):
    m1 = await make_mandant(name="Betrieb A")
    m2 = await make_mandant(name="Betrieb B")
    await _firmendaten_setzen(m2, {"telefon": "999", "impressum_url": "https://b.de/impressum"})
    kunde = await make_kunde(mandant=m2, portal_slug="slug-b")
    await make_kunde(mandant=m1, portal_slug="slug-a")

    resp = await client.get("/api/public/rechtliches", params={"portal_slug": kunde.portal_slug})

    assert resp.status_code == 200
    body = resp.json()
    assert body["anbieter"]["name"] == "Betrieb B"
    assert body["anbieter"]["telefon"] == "999"
    assert body["impressum_url"] == "https://b.de/impressum"
    assert body["datenschutz_url"] is None


@pytest.mark.asyncio
async def test_ungueltiger_slug_ist_404_auch_bei_einem_mandanten(client, make_mandant):
    await make_mandant(name="Einziger")

    resp = await client.get("/api/public/rechtliches", params={"portal_slug": "gibt-es-nicht"})

    assert resp.status_code == 404
    assert "Einziger" not in resp.text


@pytest.mark.asyncio
async def test_slug_eines_pausierten_mandanten_ist_404(client, make_mandant, make_kunde):
    mandant = await make_mandant(name="Pausiert", status="pausiert")
    kunde = await make_kunde(mandant=mandant, portal_slug="slug-pausiert")

    resp = await client.get("/api/public/rechtliches", params={"portal_slug": kunde.portal_slug})

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_nicht_http_urls_werden_verworfen(client, make_mandant):
    mandant = await make_mandant()
    await _firmendaten_setzen(
        mandant,
        {"impressum_url": "javascript:alert(1)", "datenschutz_url": "ftp://example.de/dsgvo"},
    )

    resp = await client.get("/api/public/rechtliches")

    body = resp.json()
    assert body["impressum_url"] is None
    assert body["datenschutz_url"] is None
    assert body["anbieter"]["name"] == mandant.name


@pytest.mark.asyncio
async def test_leere_und_falsch_typisierte_firmendaten_werden_toleriert(client, make_mandant):
    mandant = await make_mandant()
    await _firmendaten_setzen(
        mandant, {"adresse": "kaputt", "telefon": 123, "email": "  ", "impressum_url": ""}
    )

    resp = await client.get("/api/public/rechtliches")

    assert resp.status_code == 200
    anbieter = resp.json()["anbieter"]
    assert anbieter["telefon"] is None
    assert anbieter["email"] is None
    assert anbieter["strasse"] is None


@pytest.mark.asyncio
async def test_patch_lehnt_javascript_url_ab_und_behaelt_firmendaten(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    await _firmendaten_setzen(mandant, {"telefon": "0123", "impressum_url": "https://a.de/i"})
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        "/api/mandant/einstellungen",
        headers=auth_headers(token),
        json={"firmendaten": {"datenschutz_url": "javascript:alert(1)"}},
    )
    assert resp.status_code == 422

    resp = await client.patch(
        "/api/mandant/einstellungen",
        headers=auth_headers(token),
        json={"firmendaten": {"impressum_url": "//evil.example/x"}},
    )
    assert resp.status_code == 422

    get_resp = await client.get("/api/mandant/einstellungen", headers=auth_headers(token))
    fd = get_resp.json()["firmendaten"]
    assert fd == {"telefon": "0123", "impressum_url": "https://a.de/i"}


@pytest.mark.asyncio
async def test_patch_speichert_urls_und_behaelt_bestehende_keys(client, make_mandant, make_user):
    mandant = await make_mandant()
    await _firmendaten_setzen(mandant, {"telefon": "0123", "iban": "DE00"})
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        "/api/mandant/einstellungen",
        headers=auth_headers(token),
        json={
            "firmendaten": {
                "impressum_url": "  https://example.de/impressum  ",
                "datenschutz_url": "",
            }
        },
    )
    assert resp.status_code == 200
    fd = resp.json()["firmendaten"]
    assert fd["impressum_url"] == "https://example.de/impressum"
    assert fd["datenschutz_url"] == ""
    assert fd["telefon"] == "0123"
    assert fd["iban"] == "DE00"

    # Ein spaeteres Speichern anderer Felder darf die URLs nicht verlieren.
    resp = await client.patch(
        "/api/mandant/einstellungen",
        headers=auth_headers(token),
        json={"firmendaten": {"telefon": "999"}},
    )
    assert resp.status_code == 200
    fd = resp.json()["firmendaten"]
    assert fd["telefon"] == "999"
    assert fd["impressum_url"] == "https://example.de/impressum"

    pub = await client.get("/api/public/rechtliches")
    assert pub.json()["impressum_url"] == "https://example.de/impressum"
    assert pub.json()["datenschutz_url"] is None
