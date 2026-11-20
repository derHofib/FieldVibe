"""Etappe B (Migration 0126): Kontakte vor Ort ueber Kundenportal-Anfragen, Portal-Vorgang-Detail und Partnerportal."""
import pytest
from sqlalchemy import select

from app.db.session import system_session
from app.models.vor_ort_kontakt import VorOrtKontakt
from app.models.vorgang_anfrage import VorgangAnfrage
from tests.conftest import auth_headers, login
from tests.test_kundenportal import _kunden_login, _make_zugang
from tests.test_partner import _make_zugang as _make_partner_zugang
from tests.test_partner import _partner_login

PW = "pw-123456"
KONTAKTE = [
    {"name": "Frau Becker", "rolle": "mieter", "telefon": "0171 111", "erreichbarkeit": "nachmittags", "hinweis": "Hund"},
    {"telefon": "0171 222", "rolle": "hausmeister"},
]


async def _portal(client, mandant, kunde, email="hv@example.de"):
    await _make_zugang(mandant, kunde, email=email)
    tokens = await _kunden_login(client, email, "kunden-pw-123")
    return auth_headers(tokens["access_token"])


async def _admin(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW)
    kunde = await make_kunde(mandant=mandant, name="Hausverwaltung Nord", typ="hausverwaltung")
    return mandant, kunde, auth_headers(await login(client, admin.email, PW))


async def _anfrage(client, portal_h, **kw):
    r = await client.post(
        "/api/kundenportal/anfragen",
        headers=portal_h,
        json={"titel": "Heizung kalt", "leistungstyp": "stoerung", **kw},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_anfrage_validierung(client, make_mandant, make_user, make_kunde):
    mandant, kunde, _ = await _admin(client, make_mandant, make_user, make_kunde)
    portal = await _portal(client, mandant, kunde)

    def post(kontakte):
        return client.post(
            "/api/kundenportal/anfragen", headers=portal,
            json={"titel": "X", "leistungstyp": "stoerung", "vor_ort_kontakte": kontakte},
        )

    assert (await post([{"rolle": "mieter"}])).status_code == 422  # weder Name noch Telefon
    assert (await post([{"name": "A", "rolle": "chef"}])).status_code == 422
    assert (await post([{"name": f"P{i}", "rolle": "mieter"} for i in range(6)])).status_code == 422
    assert (await post([{"name": f"P{i}", "rolle": "mieter"} for i in range(5)])).status_code == 201


@pytest.mark.asyncio
async def test_annahme_legt_kontakte_an_und_leert_jsonb(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    portal = await _portal(client, mandant, kunde)
    standort = (
        await client.post(
            "/api/standorte", headers=h,
            json={"kunde_id": str(kunde.id), "bezeichnung": "Rosenweg 5", "adresse": {"ort": "Köln"}},
        )
    ).json()
    anfrage = await _anfrage(
        client, portal, standort_id=standort["id"], einheit="Whg. 3", kunden_referenz="HV-17", vor_ort_kontakte=KONTAKTE
    )
    # Das Portal sieht seine Eingaben, Office sieht sie im Anfrage-Detail.
    assert anfrage["einheit"] == "Whg. 3" and len(anfrage["vor_ort_kontakte"]) == 2
    detail = (await client.get(f"/api/vorgang-anfragen/{anfrage['id']}", headers=h)).json()
    assert detail["einheit"] == "Whg. 3" and detail["kunden_referenz"] == "HV-17"
    assert [k["rolle"] for k in detail["vor_ort_kontakte"]] == ["mieter", "hausmeister"]

    angenommen = await client.post(
        f"/api/vorgang-anfragen/{anfrage['id']}/annehmen", headers=h, json={"abrechnungsart": "aufwand"}
    )
    assert angenommen.status_code == 200, angenommen.text
    assert angenommen.json()["vor_ort_kontakte"] == [] and angenommen.json()["kunden_referenz"] == "HV-17"
    vorgang_id = angenommen.json()["vorgang_id"]

    assert (await client.get(f"/api/vorgaenge/{vorgang_id}", headers=h)).json()["einheit"] == "Whg. 3"
    kontakte = (await client.get(f"/api/vorgaenge/{vorgang_id}/vor-ort-kontakte", headers=h)).json()
    assert [k["kontakt"]["name"] for k in kontakte] == ["Frau Becker", None]
    assert [k["ist_hauptkontakt"] for k in kontakte] == [True, False]
    assert all(k["herkunft"] == "vorgang" for k in kontakte)
    erster = kontakte[0]["kontakt"]
    assert erster["quelle"] == "kundenportal" and erster["kunde_id"] == str(kunde.id)
    assert erster["standort_id"] == standort["id"] and erster["einheit"] == "Whg. 3"
    async with system_session(grund="test") as s:
        k = (await s.execute(select(VorOrtKontakt).where(VorOrtKontakt.name == "Frau Becker"))).scalar_one()
        assert k.erstellt_von_kundenportal_zugang_id is not None
        gespeichert = await s.get(VorgangAnfrage, anfrage["id"])
        assert gespeichert.vor_ort_kontakte == []


@pytest.mark.asyncio
async def test_ablehnung_leert_kontaktdaten(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    portal = await _portal(client, mandant, kunde)
    anfrage = await _anfrage(client, portal, vor_ort_kontakte=KONTAKTE)
    r = await client.post(f"/api/vorgang-anfragen/{anfrage['id']}/ablehnen", headers=h, json={"ablehnungsgrund": "Nein"})
    assert r.status_code == 200 and r.json()["vor_ort_kontakte"] == []
    async with system_session(grund="test") as s:
        assert (await s.get(VorgangAnfrage, anfrage["id"])).vor_ort_kontakte == []
        assert (await s.execute(select(VorOrtKontakt))).scalars().all() == []


@pytest.mark.asyncio
async def test_portal_vorgang_zeigt_nur_eigene_kontakte_ohne_email(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    portal = await _portal(client, mandant, kunde)
    anderer = await make_kunde(mandant=mandant, name="Andere HV")
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    fremder_vorgang = await make_vorgang(mandant=mandant, kunde=anderer)
    r = await client.post(
        f"/api/vorgaenge/{vorgang.id}/vor-ort-kontakte", headers=h,
        json={"neu": {"name": "Herr Kurz", "rolle": "eigentuemer", "email": "kurz@example.de", "telefon": "0221 1", "hinweis": "Klingel 2"}, "ist_hauptkontakt": True},
    )
    assert r.status_code == 201, r.text

    detail = (await client.get(f"/api/kundenportal/vorgaenge/{vorgang.id}", headers=portal)).json()
    assert detail["vor_ort_kontakte"] == [
        {"name": "Herr Kurz", "rolle": "eigentuemer", "einheit": None, "telefon": "0221 1", "erreichbarkeit": None, "hinweis": "Klingel 2"}
    ]
    assert "kurz@example.de" not in str(detail)
    # In der Liste bleibt die Kontaktliste leer; der fremde Vorgang ist nicht erreichbar.
    liste = (await client.get("/api/kundenportal/vorgaenge", headers=portal)).json()
    assert liste[0]["vor_ort_kontakte"] == []
    assert (await client.get(f"/api/kundenportal/vorgaenge/{fremder_vorgang.id}", headers=portal)).status_code == 404


@pytest.mark.asyncio
async def test_partner_sieht_kontakte_erst_nach_annahme(client, make_mandant, make_user, make_kunde, make_vorgang, make_partner):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    partner = await make_partner(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, partner_id=partner.id, partner_freigabe_status="vorgeschlagen")
    r = await client.post(
        f"/api/vorgaenge/{vorgang.id}/vor-ort-kontakte", headers=h,
        json={"neu": {"name": "Frau Brandt", "rolle": "mieter", "einheit": "Whg. 2", "telefon": "0221 5", "telefon2": "0171 5", "email": "b@example.de", "erreichbarkeit": "abends", "hinweis": "Schlüssel beim Nachbarn"}},
    )
    assert r.status_code == 201, r.text
    await _make_partner_zugang(mandant, partner, email="p@partner.example.de")
    tokens = await _partner_login(client, "p@partner.example.de", "partner-pw-123")
    ph = auth_headers(tokens["access_token"])

    vorher = (await client.get(f"/api/partnerportal/auftraege/{vorgang.id}", headers=ph)).json()
    assert vorher["vor_ort_kontakte"] == []

    angenommen = await client.patch(
        f"/api/partnerportal/auftraege/{vorgang.id}/antwort", headers=ph, json={"status": "angenommen"}
    )
    assert angenommen.status_code == 200, angenommen.text
    nachher = (await client.get(f"/api/partnerportal/auftraege/{vorgang.id}", headers=ph)).json()
    assert nachher["vor_ort_kontakte"] == [
        {
            "name": "Frau Brandt", "rolle": "mieter", "einheit": "Whg. 2", "telefon": "0221 5", "telefon2": "0171 5",
            "erreichbarkeit": "abends", "hinweis": "Schlüssel beim Nachbarn",
        }
    ]
    assert "b@example.de" not in str(nachher)
