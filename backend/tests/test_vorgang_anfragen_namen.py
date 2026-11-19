import pytest

from tests.conftest import auth_headers, login
from tests.test_standorte_anfragen_rechte import _kunden_login, _make_zugang


async def _anfrage_stellen(client, mandant, kunde, *, email, zugang_name="Frau Portal", **body):
    await _make_zugang(mandant, kunde, email=email, name=zugang_name)
    tokens = await _kunden_login(client, email, "kunden-pw-123")
    resp = await client.post(
        "/api/kundenportal/anfragen",
        headers=auth_headers(tokens["access_token"]),
        json={"titel": "Anfrage", "leistungstyp": "stoerung", **body},
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_liste_liefert_namen(client, make_mandant, make_user, make_kunde, make_anlage):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Bäckerei Krause")
    anlage = await make_anlage(mandant=mandant, kunde=kunde, bezeichnung="Backofen 2")
    token = await login(client, admin.email, "pw-123456")
    standort = await client.post(
        "/api/standorte",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "bezeichnung": "Filiale Nord"},
    )
    await _anfrage_stellen(
        client, mandant, kunde, email="portal@example.de",
        standort_id=standort.json()["id"], anlage_id=str(anlage.id),
    )

    liste = await client.get("/api/vorgang-anfragen", headers=auth_headers(token))
    assert liste.status_code == 200
    eintrag = liste.json()[0]
    assert eintrag["kunde_name"] == "Bäckerei Krause"
    assert eintrag["standort_bezeichnung"] == "Filiale Nord"
    assert eintrag["anlage_bezeichnung"] == "Backofen 2"
    assert eintrag["gestellt_von_name"] == "Frau Portal"
    assert eintrag["gestellt_von_email"] == "portal@example.de"
    assert eintrag["vorgang_nummer"] is None
    assert eintrag["bearbeitet_von_name"] is None


@pytest.mark.asyncio
async def test_ohne_standort_und_anlage_sind_felder_null(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Kunde X")
    anfrage = await _anfrage_stellen(client, mandant, kunde, email="p2@example.de")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get(f"/api/vorgang-anfragen/{anfrage['id']}", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["kunde_name"] == "Kunde X"
    assert body["standort_bezeichnung"] is None
    assert body["anlage_bezeichnung"] is None


@pytest.mark.asyncio
async def test_annehmen_setzt_prioritaet_und_liefert_nummer_und_bearbeiter(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456", name="Dora Dispo")
    kunde = await make_kunde(mandant=mandant)
    anfrage = await _anfrage_stellen(client, mandant, kunde, email="p3@example.de")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        f"/api/vorgang-anfragen/{anfrage['id']}/annehmen",
        headers=auth_headers(token),
        json={"abrechnungsart": "aufwand", "prioritaet": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["vorgang_nummer"]
    assert body["bearbeitet_von_name"] == "Dora Dispo"
    assert body["gestellt_von_name"] == "Frau Portal"

    vorgang = await client.get(f"/api/vorgaenge/{body['vorgang_id']}", headers=auth_headers(token))
    assert vorgang.json()["prioritaet"] == 1
    assert vorgang.json()["vorgangsnummer"] == body["vorgang_nummer"]


@pytest.mark.asyncio
async def test_ablehnen_liefert_bearbeiter_name(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456", name="Dora Dispo")
    kunde = await make_kunde(mandant=mandant)
    anfrage = await _anfrage_stellen(client, mandant, kunde, email="p4@example.de")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        f"/api/vorgang-anfragen/{anfrage['id']}/ablehnen",
        headers=auth_headers(token),
        json={"ablehnungsgrund": "Nein"},
    )
    assert resp.status_code == 200
    assert resp.json()["bearbeitet_von_name"] == "Dora Dispo"
    assert resp.json()["vorgang_nummer"] is None


@pytest.mark.asyncio
async def test_anderer_mandant_sieht_anfrage_nicht(client, make_mandant, make_user, make_kunde):
    mandant_a = await make_mandant(name="A")
    mandant_b = await make_mandant(name="B")
    kunde = await make_kunde(mandant=mandant_a)
    anfrage = await _anfrage_stellen(client, mandant_a, kunde, email="p5@example.de")
    admin_b = await make_user(mandant=mandant_b, role="mandant_admin", password="pw-123456")
    token_b = await login(client, admin_b.email, "pw-123456")

    liste = await client.get("/api/vorgang-anfragen", headers=auth_headers(token_b))
    assert liste.status_code == 200
    assert liste.json() == []
    einzeln = await client.get(f"/api/vorgang-anfragen/{anfrage['id']}", headers=auth_headers(token_b))
    assert einzeln.status_code == 404
