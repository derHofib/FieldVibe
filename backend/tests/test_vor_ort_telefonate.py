"""Etappe C (Migration 0127): Telefonate mit Kontakt vor Ort, Rufnummer-Erkennung, Anonymisierung der Telefonate,
und (Nachtrag Etappe A) Korrektur eines Kontakts durch Nutzer mit vorgaenge.bearbeiten."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.session import system_session
from app.models.telefonat import Telefonat
from app.models.vorgang_event import VorgangEvent
from tests.conftest import auth_headers, login
from tests.mcp_helfer import PASSWORT, custom_nutzer

PW = "pw-123456"


def _body(**kw) -> dict:
    basis = {
        "partner_name": "Frau Becker",
        "partner_nummer": "0171 123456",
        "richtung": "eingehend",
        "ergebnis": "erreicht",
        "beginn": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
        "dauer_sekunden": 120,
        "notiz": "Termin abgestimmt",
    }
    basis.update(kw)
    return basis


@pytest.fixture
async def s(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW)
    kunde = await make_kunde(
        mandant=mandant,
        name="Hausverwaltung Nord",
        ansprechpartner=[{"id": str(uuid4()), "name": "Herr Sach", "telefon": "+49 221 9990-0"}],
    )
    anderer = await make_kunde(mandant=mandant, name="Andere HV")
    h = auth_headers(await login(client, admin.email, PW))
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, titel="Heizung kalt", vorgangsnummer="V-00099")
    kontakt = (
        await client.post(
            f"/api/kunden/{kunde.id}/vor-ort-kontakte", headers=h,
            json={"name": "Frau Becker", "rolle": "mieter", "telefon": "0171 123456", "telefon2": "(0221) 555-77", "einheit": "Whg. 3"},
        )
    ).json()
    zuordnung = await client.post(
        f"/api/vorgaenge/{vorgang.id}/vor-ort-kontakte", headers=h, json={"kontakt_id": kontakt["id"], "ist_hauptkontakt": True}
    )
    assert zuordnung.status_code == 201, zuordnung.text
    return {"mandant": mandant, "admin": admin, "kunde": kunde, "anderer": anderer, "h": h, "vorgang": vorgang, "kontakt": kontakt}


@pytest.mark.asyncio
async def test_telefonat_mit_kontakt_vor_ort(client, s):
    h, kunde, kontakt = s["h"], s["kunde"], s["kontakt"]
    r = await client.post("/api/telefonate", headers=h, json=_body(kunde_id=str(kunde.id), vor_ort_kontakt_id=kontakt["id"]))
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["vor_ort_kontakt_id"] == kontakt["id"]
    assert t["vor_ort_kontakt"] == {"id": kontakt["id"], "name": "Frau Becker", "rolle": "mieter"}

    # Kontakt eines anderen Kunden bzw. beides gleichzeitig -> 422.
    falscher = await client.post("/api/telefonate", headers=h, json=_body(kunde_id=str(s["anderer"].id), vor_ort_kontakt_id=kontakt["id"]))
    assert falscher.status_code == 422
    beides = await client.post(
        "/api/telefonate", headers=h,
        json=_body(kunde_id=str(kunde.id), vor_ort_kontakt_id=kontakt["id"], ansprechpartner_id=str(uuid4())),
    )
    assert beides.status_code == 422

    # Ueber den Vorgang (Kunde wird daraus gesetzt) und per PATCH aenderbar.
    am_vorgang = await client.post(
        "/api/telefonate", headers=h, json=_body(vorgang_id=str(s["vorgang"].id), vor_ort_kontakt_id=kontakt["id"])
    )
    assert am_vorgang.status_code == 201 and am_vorgang.json()["kunde_id"] == str(kunde.id)
    ohne = await client.post("/api/telefonate", headers=h, json=_body(kunde_id=str(kunde.id)))
    gesetzt = await client.patch(f"/api/telefonate/{ohne.json()['id']}", headers=h, json={"vor_ort_kontakt_id": kontakt["id"]})
    assert gesetzt.status_code == 200 and gesetzt.json()["vor_ort_kontakt"]["name"] == "Frau Becker"
    falsch = await client.patch(f"/api/telefonate/{t['id']}", headers=h, json={"vor_ort_kontakt_id": str(uuid4())})
    assert falsch.status_code == 422
    geloest = await client.patch(f"/api/telefonate/{t['id']}", headers=h, json={"vor_ort_kontakt_id": None})
    assert geloest.json()["vor_ort_kontakt_id"] is None and geloest.json()["vor_ort_kontakt"] is None


@pytest.mark.asyncio
async def test_nummer_zuordnen_erkennt_kontakt_ansprechpartner_und_offene_vorgaenge(client, s, make_vorgang):
    h = s["h"]
    # Zweiter, abgeschlossener Vorgang desselben Kontakts erscheint nicht.
    geschlossen = await make_vorgang(mandant=s["mandant"], kunde=s["kunde"], titel="Alt", status="abgeschlossen")
    await client.post(f"/api/vorgaenge/{geschlossen.id}/vor-ort-kontakte", headers=h, json={"kontakt_id": s["kontakt"]["id"]})
    # Ueber den Auftrag zugeordneter Vorgang.
    auftrag = (await client.post("/api/auftraege", headers=h, json={"titel": "Auftrag", "kunde_id": str(s["kunde"].id)})).json()
    ueber_auftrag = (
        await client.post(
            "/api/vorgaenge", headers=h,
            json={"kunde_id": str(s["kunde"].id), "titel": "Über Auftrag", "abrechnungsart": "aufwand", "leistungstyp": "stoerung", "auftrag_id": auftrag["id"]},
        )
    ).json()
    await client.post(f"/api/auftraege/{auftrag['id']}/vor-ort-kontakte", headers=h, json={"kontakt_id": s["kontakt"]["id"]})

    # Verschiedene Schreibweisen derselben Nummer (national, international, mit Zeichen), auch telefon2.
    for nummer in ("0171 123456", "+49 171 123456", "0049-171-123456", "(0221) 555 77"):
        r = await client.get("/api/telefonate/nummer-zuordnen", headers=h, params={"nummer": nummer})
        assert r.status_code == 200, r.text
        treffer = r.json()
        assert treffer["kunde_id"] == str(s["kunde"].id) and treffer["kunde_name"] == "Hausverwaltung Nord"
        assert treffer["vor_ort_kontakt_id"] == s["kontakt"]["id"] and treffer["ansprechpartner_id"] is None
        assert treffer["partner_name"] == "Frau Becker"
        assert {v["vorgangsnummer"] for v in treffer["offene_vorgaenge"]} == {"V-00099", ueber_auftrag["vorgangsnummer"]}

    ansprechpartner = (await client.get("/api/telefonate/nummer-zuordnen", headers=h, params={"nummer": "0221 99900"})).json()
    assert ansprechpartner["ansprechpartner_id"] == s["kunde"].ansprechpartner[0]["id"]
    assert ansprechpartner["vor_ort_kontakt_id"] is None and ansprechpartner["offene_vorgaenge"] == []

    unbekannt = await client.get("/api/telefonate/nummer-zuordnen", headers=h, params={"nummer": "030 99887766"})
    assert unbekannt.status_code == 200 and unbekannt.json() is None
    # Anonymisierte Kontakte werden nicht mehr erkannt.
    await client.post(f"/api/vor-ort-kontakte/{s['kontakt']['id']}/anonymisieren", headers=h)
    assert (await client.get("/api/telefonate/nummer-zuordnen", headers=h, params={"nummer": "0171 123456"})).json() is None


@pytest.mark.asyncio
async def test_nummer_zuordnen_respektiert_kundenscope(client, s, make_user, make_kunde_zuweisung):
    techniker = await make_user(mandant=s["mandant"], role="techniker", password=PW)
    th = auth_headers(await login(client, techniker.email, PW))
    ohne = await client.get("/api/telefonate/nummer-zuordnen", headers=th, params={"nummer": "0171 123456"})
    assert ohne.status_code == 200 and ohne.json() is None  # Kunde ist dem Techniker nicht zugewiesen
    await make_kunde_zuweisung(mandant=s["mandant"], kunde=s["kunde"], techniker=techniker)
    mit = await client.get("/api/telefonate/nummer-zuordnen", headers=th, params={"nummer": "0171 123456"})
    assert mit.json()["vor_ort_kontakt_id"] == s["kontakt"]["id"]


@pytest.mark.asyncio
async def test_anonymisieren_leert_telefonate_des_kontakts(client, s):
    h = s["h"]
    t = (
        await client.post(
            "/api/telefonate", headers=h,
            json=_body(vorgang_id=str(s["vorgang"].id), vor_ort_kontakt_id=s["kontakt"]["id"]),
        )
    ).json()
    anderes = (await client.post("/api/telefonate", headers=h, json=_body(kunde_id=str(s["kunde"].id)))).json()

    r = await client.post(f"/api/vor-ort-kontakte/{s['kontakt']['id']}/anonymisieren", headers=h)
    assert r.status_code == 200
    gelesen = (await client.get(f"/api/telefonate/{t['id']}", headers=h)).json()
    assert gelesen["partner_name"] == "Kontakt anonymisiert" and gelesen["partner_nummer"] is None
    assert gelesen["vor_ort_kontakt"]["name"] is None and gelesen["vor_ort_kontakt"]["rolle"] == "mieter"
    assert (await client.get(f"/api/telefonate/{anderes['id']}", headers=h)).json()["partner_name"] == "Frau Becker"
    async with system_session(grund="test") as session:
        event = (await session.execute(select(VorgangEvent).where(VorgangEvent.ref_entity_id == t["id"]))).scalar_one()
        assert event.payload["partner_name"] == "Kontakt anonymisiert" and event.payload["partner_nummer"] is None


@pytest.mark.asyncio
async def test_anonymisierungs_job_leert_telefonate(client, s):
    from app.services.vor_ort_kontakt_service import run_vor_ort_kontakte_anonymisierung

    h = s["h"]
    t = (await client.post("/api/telefonate", headers=h, json=_body(kunde_id=str(s["kunde"].id), vor_ort_kontakt_id=s["kontakt"]["id"]))).json()
    # Vorgang abgeschlossen und Einsatz lange her -> faellig.
    await client.patch(f"/api/vorgaenge/{s['vorgang'].id}", headers=h, json={"status": "abgeschlossen"})
    async with system_session(grund="test") as session:
        from app.models.vor_ort_kontakt import VorOrtKontakt

        kontakt = await session.get(VorOrtKontakt, s["kontakt"]["id"])
        kontakt.letzter_einsatz_am = datetime.now(UTC) - timedelta(days=800)
    await run_vor_ort_kontakte_anonymisierung([s["mandant"].id])
    async with system_session(grund="test") as session:
        telefonat = await session.get(Telefonat, t["id"])
        assert telefonat.partner_name == "Kontakt anonymisiert" and telefonat.partner_nummer is None


# --- Nachtrag Etappe A: Techniker korrigiert einen Kontakt ------------------------------------------------


@pytest.mark.asyncio
async def test_techniker_darf_kontakt_am_sichtbaren_vorgang_korrigieren(client, s, make_user, make_kunde_zuweisung, make_vorgang):
    techniker = await make_user(mandant=s["mandant"], role="techniker", password=PW)
    th = auth_headers(await login(client, techniker.email, PW))
    url = f"/api/vor-ort-kontakte/{s['kontakt']['id']}"

    # Kunde nicht zugewiesen: der Vorgang ist fuer ihn unsichtbar -> 404.
    assert (await client.patch(url, headers=th, json={"telefon": "0171 999"})).status_code == 404
    await make_kunde_zuweisung(mandant=s["mandant"], kunde=s["kunde"], techniker=techniker)
    r = await client.patch(url, headers=th, json={"telefon": "0171 999"})
    assert r.status_code == 200, r.text
    assert r.json()["telefon"] == "0171 999"

    # Loeschen und Anonymisieren bleiben bei kunden.bearbeiten.
    assert (await client.delete(url, headers=th)).status_code == 403
    assert (await client.post(f"{url}/anonymisieren", headers=th)).status_code == 403

    # Ein Kontakt ohne Zuordnung zu einem sichtbaren Vorgang bleibt tabu.
    lose = (
        await client.post(
            f"/api/kunden/{s['kunde'].id}/vor-ort-kontakte", headers=s["h"], json={"name": "Frei", "rolle": "sonstige"}
        )
    ).json()
    assert (await client.patch(f"/api/vor-ort-kontakte/{lose['id']}", headers=th, json={"telefon": "1"})).status_code == 404
    # Auch ueber den Auftrag zugeordnet gilt der Vorgang dieses Auftrags.
    auftrag = (await client.post("/api/auftraege", headers=s["h"], json={"titel": "A", "kunde_id": str(s["kunde"].id)})).json()
    await client.post(f"/api/auftraege/{auftrag['id']}/vor-ort-kontakte", headers=s["h"], json={"kontakt_id": lose["id"]})
    assert (await client.patch(f"/api/vor-ort-kontakte/{lose['id']}", headers=th, json={"telefon": "1"})).status_code == 404
    await client.post(
        "/api/vorgaenge", headers=s["h"],
        json={"kunde_id": str(s["kunde"].id), "titel": "V", "abrechnungsart": "aufwand", "leistungstyp": "stoerung", "auftrag_id": auftrag["id"]},
    )
    assert (await client.patch(f"/api/vor-ort-kontakte/{lose['id']}", headers=th, json={"telefon": "12345"})).status_code == 200


@pytest.mark.asyncio
async def test_nutzer_ohne_vorgang_bearbeiten_darf_kontakt_nicht_aendern(client, s, make_kunde_zuweisung):
    nur_sehen = await custom_nutzer(s["mandant"], "Nur Sehen", {"vorgaenge": ("sehen",), "kunden": ("sehen",)})
    await make_kunde_zuweisung(mandant=s["mandant"], kunde=s["kunde"], techniker=nur_sehen)
    th = auth_headers(await login(client, nur_sehen.email, PASSWORT))
    r = await client.patch(f"/api/vor-ort-kontakte/{s['kontakt']['id']}", headers=th, json={"telefon": "1"})
    assert r.status_code == 404  # kein kunden.bearbeiten und kein vorgaenge.bearbeiten
