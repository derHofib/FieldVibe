"""Telefonate (Konzept telefonate): Anlegen am Vorgang/Kunden, Validierung, Idempotenz, Arbeitszeit-Buchung,
Loeschen, Rechte, Mandantentrennung, Kontaktverlauf, Portale, Scheduler und automatisches Erledigen."""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.db.session import system_session, tenant_session
from app.models.email_log import EmailLog
from app.models.notification import Notification
from app.models.telefonat import Telefonat
from app.models.vorgang_event import VorgangEvent
from app.models.zeiterfassung import Zeiterfassung
from app.services.scheduler_service import run_rueckruf_scheduler
from tests.conftest import auth_headers, login
from tests.test_kundenportal import _kunden_login, _make_zugang


def _body(**kw) -> dict:
    basis = {
        "partner_name": "Frau Brandt",
        "partner_nummer": "+49 221 5550123",
        "richtung": "ausgehend",
        "ergebnis": "erreicht",
        "beginn": (datetime.now(UTC) - timedelta(minutes=30)).isoformat(),
        "dauer_sekunden": 600,
        "notiz": "Termin abgestimmt",
    }
    basis.update(kw)
    return basis


async def _kopf(client, user) -> dict:
    return auth_headers(await login(client, user.email, user._plaintext_password))


@pytest.fixture
async def szenario(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", name="Sabine Admin")
    kunde = await make_kunde(mandant=mandant, name="Café Sonnenschein")
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, titel="Beleuchtung", vorgangsnummer="V-00048")
    return {
        "mandant": mandant, "admin": admin, "kunde": kunde, "vorgang": vorgang,
        "h": await _kopf(client, admin),
    }


async def _events(vorgang_id, typ="telefonat") -> list[VorgangEvent]:
    async with system_session(grund="test") as s:
        return list(
            (await s.execute(select(VorgangEvent).where(VorgangEvent.vorgang_id == vorgang_id, VorgangEvent.event_type == typ))).scalars()
        )


async def _zeiten(vorgang_id, nur_aktive=True) -> list[Zeiterfassung]:
    async with system_session(grund="test") as s:
        stmt = select(Zeiterfassung).where(Zeiterfassung.vorgang_id == vorgang_id)
        if nur_aktive:
            stmt = stmt.where(Zeiterfassung.geloescht_am.is_(None))
        return list((await s.execute(stmt)).scalars())


# --- Anlegen ---------------------------------------------------------------------------------


async def test_anlegen_am_vorgang_erzeugt_verlauf_event(client, szenario):
    s = szenario
    resp = await client.post(
        "/api/telefonate", headers=s["h"], json=_body(vorgang_id=str(s["vorgang"].id), rueckruf_am="2030-01-01T09:00:00Z")
    )
    assert resp.status_code == 201, resp.text
    t = resp.json()
    assert t["kunde_id"] == str(s["kunde"].id) and t["kunde_name"] == "Café Sonnenschein"
    assert t["vorgang_nummer"] == "V-00048" and t["vorgang_titel"] == "Beleuchtung"
    assert t["erfasst_von"] == str(s["admin"].id) and t["erfasst_von_name"] == "Sabine Admin"
    assert t["erstellt_via"] == "app" and t["zeiterfassung_id"] is None and t["rueckruf_erledigt_am"] is None

    (event,) = await _events(s["vorgang"].id)
    assert event.ref_entity_type == "telefonat" and event.ref_entity_id == uuid.UUID(t["id"])
    assert event.body == "Termin abgestimmt" and event.kundensichtbar is False
    assert event.author_user_id == s["admin"].id
    p = event.payload
    assert p["telefonat_id"] == t["id"] and p["richtung"] == "ausgehend" and p["ergebnis"] == "erreicht"
    assert p["dauer_sekunden"] == 600 and p["partner_name"] == "Frau Brandt" and p["partner_nummer"] == "+49 221 5550123"
    assert p["rueckruf_am"].startswith("2030-01-01") and p["rueckruf_erledigt_am"] is None
    assert p["zeit_gebucht"] is False and "via" not in p

    verlauf = (await client.get(f"/api/vorgaenge/{s['vorgang'].id}/events", headers=s["h"])).json()
    assert [e["event_type"] for e in verlauf if e["event_type"] == "telefonat"] == ["telefonat"]


async def test_anlegen_nur_am_kunden_ohne_event(client, szenario):
    s = szenario
    resp = await client.post(
        "/api/telefonate", headers=s["h"], json=_body(kunde_id=str(s["kunde"].id), ergebnis="mailbox", notiz=None, dauer_sekunden=45)
    )
    assert resp.status_code == 201, resp.text
    t = resp.json()
    assert t["vorgang_id"] is None and t["vorgang_nummer"] is None
    # Mailbox hat keine Gespraechsdauer.
    assert t["dauer_sekunden"] is None
    async with system_session(grund="test") as db:
        assert (await db.execute(select(func.count()).select_from(VorgangEvent).where(VorgangEvent.event_type == "telefonat"))).scalar_one() == 0


async def test_telefonat_ist_kein_setzbarer_event_typ(client, szenario):
    s = szenario
    resp = await client.post(
        f"/api/vorgaenge/{s['vorgang'].id}/events", headers=s["h"], json={"event_type": "telefonat", "body": "x"}
    )
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "aenderung, text_teil",
    [
        ({"ergebnis": "erreicht", "notiz": "  "}, "Notiz"),
        ({"ergebnis": "erreicht", "notiz": None}, "Notiz"),
        ({"als_arbeitszeit_buchen": True, "dauer_sekunden": 0}, "Dauer"),
        ({"als_arbeitszeit_buchen": True, "dauer_sekunden": None}, "Dauer"),
        ({"als_arbeitszeit_buchen": True, "ergebnis": "mailbox", "notiz": None}, "erreichtes"),
        ({"dauer_sekunden": -1}, ""),
        ({"dauer_sekunden": 86401}, ""),
        ({"partner_name": ""}, ""),
        ({"richtung": "quer"}, ""),
    ],
)
async def test_validierungen_am_vorgang(client, szenario, aenderung, text_teil):
    s = szenario
    resp = await client.post("/api/telefonate", headers=s["h"], json=_body(vorgang_id=str(s["vorgang"].id), **aenderung))
    assert resp.status_code == 422, resp.text
    assert text_teil in resp.text


async def test_validierung_weder_kunde_noch_vorgang(client, szenario):
    resp = await client.post("/api/telefonate", headers=szenario["h"], json=_body())
    assert resp.status_code == 422 and "Vorgang oder einen Kunden" in resp.text


async def test_arbeitszeit_nur_mit_vorgang(client, szenario):
    resp = await client.post(
        "/api/telefonate", headers=szenario["h"], json=_body(kunde_id=str(szenario["kunde"].id), als_arbeitszeit_buchen=True)
    )
    assert resp.status_code == 422 and "Vorgang" in resp.text


async def test_abweichende_kunde_id_zum_vorgang_ist_422(client, szenario, make_kunde):
    anderer = await make_kunde(mandant=szenario["mandant"], name="Anderer")
    resp = await client.post(
        "/api/telefonate", headers=szenario["h"],
        json=_body(vorgang_id=str(szenario["vorgang"].id), kunde_id=str(anderer.id)),
    )
    assert resp.status_code == 422


async def test_idempotenz_client_uuid(client, szenario):
    s = szenario
    body = _body(vorgang_id=str(s["vorgang"].id), client_uuid=str(uuid.uuid4()))
    erste = await client.post("/api/telefonate", headers=s["h"], json=body)
    zweite = await client.post("/api/telefonate", headers=s["h"], json=body)
    assert erste.status_code == 201 and zweite.status_code == 200
    assert erste.json()["id"] == zweite.json()["id"]
    assert len(await _events(s["vorgang"].id)) == 1
    async with system_session(grund="test") as db:
        assert (await db.execute(select(func.count()).select_from(Telefonat))).scalar_one() == 1


# --- Arbeitszeit -----------------------------------------------------------------------------


async def test_arbeitszeit_buchen_legt_zeiteintrag_an(client, szenario):
    s = szenario
    beginn = datetime.now(UTC) - timedelta(hours=1)
    resp = await client.post(
        "/api/telefonate", headers=s["h"],
        json=_body(vorgang_id=str(s["vorgang"].id), beginn=beginn.isoformat(), dauer_sekunden=900, als_arbeitszeit_buchen=True),
    )
    assert resp.status_code == 201, resp.text
    t = resp.json()
    (z,) = await _zeiten(s["vorgang"].id)
    assert t["zeiterfassung_id"] == str(z.id)
    assert z.kategorie == "auftrag" and z.quelle == "manuell" and z.techniker_id == s["admin"].id
    assert z.taetigkeit == "Telefonat mit Frau Brandt" and z.abrechenbar is True
    assert z.start_at == beginn and z.ende_at == beginn + timedelta(seconds=900)
    assert z.buchungsstatus == "vermerkt"
    assert (await _events(s["vorgang"].id))[0].payload["zeit_gebucht"] is True


async def test_patch_zieht_gebuchte_arbeitszeit_mit(client, szenario):
    s = szenario
    t = (
        await client.post(
            "/api/telefonate", headers=s["h"],
            json=_body(vorgang_id=str(s["vorgang"].id), dauer_sekunden=900, als_arbeitszeit_buchen=True),
        )
    ).json()
    resp = await client.patch(f"/api/telefonate/{t['id']}", headers=s["h"], json={"dauer_sekunden": 1800, "notiz": "Länger als gedacht"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["dauer_sekunden"] == 1800
    (z,) = await _zeiten(s["vorgang"].id)
    assert z.ende_at - z.start_at == timedelta(seconds=1800)
    event = (await _events(s["vorgang"].id))[0]
    assert event.body == "Länger als gedacht" and event.payload["dauer_sekunden"] == 1800


async def test_patch_409_wenn_arbeitszeit_bereits_gebucht(client, szenario):
    s = szenario
    t = (
        await client.post(
            "/api/telefonate", headers=s["h"],
            json=_body(vorgang_id=str(s["vorgang"].id), dauer_sekunden=900, als_arbeitszeit_buchen=True),
        )
    ).json()
    async with system_session(grund="test") as db:
        z = await db.get(Zeiterfassung, uuid.UUID(t["zeiterfassung_id"]))
        z.buchungsstatus = "gebucht"
    resp = await client.patch(f"/api/telefonate/{t['id']}", headers=s["h"], json={"dauer_sekunden": 60})
    assert resp.status_code == 409 and "Arbeitszeit" in resp.json()["detail"]
    # Das Telefonat selbst bleibt unveraendert; reine Notiz-Aenderungen gehen weiterhin.
    assert (await client.get(f"/api/telefonate/{t['id']}", headers=s["h"])).json()["dauer_sekunden"] == 900
    assert (await client.patch(f"/api/telefonate/{t['id']}", headers=s["h"], json={"notiz": "nur Text"})).status_code == 200


# --- Aendern / Loeschen ----------------------------------------------------------------------


async def test_patch_erreicht_braucht_notiz_und_leert_dauer_bei_mailbox(client, szenario):
    s = szenario
    t = (await client.post("/api/telefonate", headers=s["h"], json=_body(vorgang_id=str(s["vorgang"].id)))).json()
    assert (await client.patch(f"/api/telefonate/{t['id']}", headers=s["h"], json={"notiz": ""})).status_code == 422
    resp = await client.patch(f"/api/telefonate/{t['id']}", headers=s["h"], json={"ergebnis": "mailbox"})
    assert resp.status_code == 200 and resp.json()["dauer_sekunden"] is None
    assert (await _events(s["vorgang"].id))[0].payload["ergebnis"] == "mailbox"


async def test_rueckruf_erledigt_per_patch(client, szenario):
    s = szenario
    t = (await client.post("/api/telefonate", headers=s["h"], json=_body(vorgang_id=str(s["vorgang"].id), rueckruf_am="2030-01-01T09:00:00Z"))).json()
    erledigt = (await client.patch(f"/api/telefonate/{t['id']}", headers=s["h"], json={"rueckruf_erledigt": True})).json()
    assert erledigt["rueckruf_erledigt_am"] is not None
    assert (await _events(s["vorgang"].id))[0].payload["rueckruf_erledigt_am"] is not None
    offen = (await client.patch(f"/api/telefonate/{t['id']}", headers=s["h"], json={"rueckruf_erledigt": False})).json()
    assert offen["rueckruf_erledigt_am"] is None


async def test_loeschen_entfernt_event_und_zeiteintrag(client, szenario):
    s = szenario
    t = (
        await client.post(
            "/api/telefonate", headers=s["h"],
            json=_body(vorgang_id=str(s["vorgang"].id), dauer_sekunden=900, als_arbeitszeit_buchen=True),
        )
    ).json()
    assert (await client.delete(f"/api/telefonate/{t['id']}", headers=s["h"])).status_code == 204
    assert await _events(s["vorgang"].id) == []
    assert await _zeiten(s["vorgang"].id) == []
    assert (await client.get(f"/api/telefonate/{t['id']}", headers=s["h"])).status_code == 404
    assert (await client.get("/api/telefonate", headers=s["h"])).json() == []


async def test_loeschen_409_wenn_zeit_gebucht(client, szenario):
    s = szenario
    t = (
        await client.post(
            "/api/telefonate", headers=s["h"],
            json=_body(vorgang_id=str(s["vorgang"].id), dauer_sekunden=900, als_arbeitszeit_buchen=True),
        )
    ).json()
    async with system_session(grund="test") as db:
        (await db.get(Zeiterfassung, uuid.UUID(t["zeiterfassung_id"]))).buchungsstatus = "gebucht"
    resp = await client.delete(f"/api/telefonate/{t['id']}", headers=s["h"])
    assert resp.status_code == 409
    assert (await client.get(f"/api/telefonate/{t['id']}", headers=s["h"])).status_code == 200
    assert len(await _events(s["vorgang"].id)) == 1


# --- Rechte ----------------------------------------------------------------------------------


async def test_techniker_ohne_vorgangszugriff(client, szenario, make_user):
    s = szenario
    techniker = await make_user(mandant=s["mandant"], role="techniker")
    h = await _kopf(client, techniker)
    # Kunde ist dem Techniker nicht zugewiesen: Vorgang und Kunde bleiben unsichtbar.
    assert (await client.post("/api/telefonate", headers=h, json=_body(vorgang_id=str(s["vorgang"].id)))).status_code in (403, 404)
    assert (await client.post("/api/telefonate", headers=h, json=_body(kunde_id=str(s["kunde"].id)))).status_code in (403, 404)
    t = (await client.post("/api/telefonate", headers=s["h"], json=_body(vorgang_id=str(s["vorgang"].id)))).json()
    assert (await client.get(f"/api/telefonate/{t['id']}", headers=h)).status_code == 404
    assert (await client.get("/api/telefonate", headers=h)).json() == []
    assert (await client.get(f"/api/kunden/{s['kunde'].id}/kontaktverlauf", headers=h)).status_code == 404


async def test_zugewiesener_techniker_darf_erfassen(client, szenario, make_user, make_kunde_zuweisung):
    s = szenario
    techniker = await make_user(mandant=s["mandant"], role="techniker")
    await make_kunde_zuweisung(mandant=s["mandant"], kunde=s["kunde"], techniker=techniker)
    h = await _kopf(client, techniker)
    assert (await client.post("/api/telefonate", headers=h, json=_body(vorgang_id=str(s["vorgang"].id)))).status_code == 201
    assert (await client.post("/api/telefonate", headers=h, json=_body(kunde_id=str(s["kunde"].id)))).status_code == 201


async def test_fremder_erfasser_darf_nicht_aendern_admin_schon(client, szenario, make_user, make_kunde_zuweisung):
    s = szenario
    techniker = await make_user(mandant=s["mandant"], role="techniker")
    await make_kunde_zuweisung(mandant=s["mandant"], kunde=s["kunde"], techniker=techniker)
    kollege = await make_user(mandant=s["mandant"], role="techniker")
    await make_kunde_zuweisung(mandant=s["mandant"], kunde=s["kunde"], techniker=kollege)
    h_tech, h_kollege = await _kopf(client, techniker), await _kopf(client, kollege)

    t = (await client.post("/api/telefonate", headers=h_tech, json=_body(vorgang_id=str(s["vorgang"].id)))).json()
    # Sehen darf der Kollege es, aendern/loeschen nicht.
    assert (await client.get(f"/api/telefonate/{t['id']}", headers=h_kollege)).status_code == 200
    assert (await client.patch(f"/api/telefonate/{t['id']}", headers=h_kollege, json={"notiz": "x"})).status_code == 403
    assert (await client.delete(f"/api/telefonate/{t['id']}", headers=h_kollege)).status_code == 403
    assert (await client.patch(f"/api/telefonate/{t['id']}", headers=h_tech, json={"notiz": "eigene"})).status_code == 200
    assert (await client.patch(f"/api/telefonate/{t['id']}", headers=s["h"], json={"notiz": "Admin"})).status_code == 200
    assert (await client.delete(f"/api/telefonate/{t['id']}", headers=s["h"])).status_code == 204


# --- Mandantentrennung -----------------------------------------------------------------------


async def test_mandant_b_sieht_telefonat_von_a_nicht(client, szenario, make_mandant, make_user):
    s = szenario
    t = (await client.post("/api/telefonate", headers=s["h"], json=_body(vorgang_id=str(s["vorgang"].id)))).json()
    mandant_b = await make_mandant(name="Betrieb B")
    admin_b = await make_user(mandant=mandant_b, role="mandant_admin")
    h_b = await _kopf(client, admin_b)

    assert (await client.get(f"/api/telefonate/{t['id']}", headers=h_b)).status_code == 404
    assert (await client.patch(f"/api/telefonate/{t['id']}", headers=h_b, json={"notiz": "x"})).status_code == 404
    assert (await client.delete(f"/api/telefonate/{t['id']}", headers=h_b)).status_code == 404
    assert (await client.get("/api/telefonate", headers=h_b)).json() == []
    assert (await client.get(f"/api/kunden/{s['kunde'].id}/kontaktverlauf", headers=h_b)).status_code == 404
    # Auch auf Datenbankebene (RLS) unsichtbar.
    async with tenant_session(mandant_id=mandant_b.id) as db:
        assert (await db.execute(select(func.count()).select_from(Telefonat))).scalar_one() == 0
    async with tenant_session(mandant_id=s["mandant"].id) as db:
        assert (await db.execute(select(func.count()).select_from(Telefonat))).scalar_one() == 1


# --- Liste, Rueckrufe ------------------------------------------------------------------------


async def test_liste_filter_und_sortierung(client, szenario):
    s = szenario
    jetzt = datetime.now(UTC)
    a = (await client.post("/api/telefonate", headers=s["h"], json=_body(vorgang_id=str(s["vorgang"].id), beginn=(jetzt - timedelta(hours=3)).isoformat(), rueckruf_am=(jetzt + timedelta(days=5)).isoformat()))).json()
    b = (await client.post("/api/telefonate", headers=s["h"], json=_body(kunde_id=str(s["kunde"].id), beginn=(jetzt - timedelta(hours=1)).isoformat(), partner_nummer=None, partner_name="Herr Roth", rueckruf_am=(jetzt + timedelta(days=1)).isoformat()))).json()
    c = (await client.post("/api/telefonate", headers=s["h"], json=_body(kunde_id=str(s["kunde"].id), beginn=(jetzt - timedelta(hours=2)).isoformat(), partner_nummer=None, partner_name="Frau Mailbox", ergebnis="mailbox", notiz=None))).json()

    ids = lambda r: [x["id"] for x in r.json()]  # noqa: E731
    assert ids(await client.get("/api/telefonate", headers=s["h"])) == [b["id"], c["id"], a["id"]]
    assert ids(await client.get("/api/telefonate?rueckruf_offen=true", headers=s["h"])) == [b["id"], a["id"]]
    assert ids(await client.get(f"/api/telefonate?vorgang_id={s['vorgang'].id}", headers=s["h"])) == [a["id"]]
    assert ids(await client.get("/api/telefonate?ergebnis=mailbox", headers=s["h"])) == [c["id"]]
    assert ids(await client.get("/api/telefonate?von_mir=true&limit=1&seite=2", headers=s["h"])) == [c["id"]]
    assert (await client.get("/api/telefonate/anzahl-offene-rueckrufe", headers=s["h"])).json() == {"anzahl": 2}
    await client.patch(f"/api/telefonate/{b['id']}", headers=s["h"], json={"rueckruf_erledigt": True})
    assert (await client.get("/api/telefonate/anzahl-offene-rueckrufe", headers=s["h"])).json() == {"anzahl": 1}


async def test_erreicht_erledigt_offene_rueckrufe_desselben_partners(client, szenario):
    s = szenario
    ap = str(uuid.uuid4())
    morgen = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    offen_ap = (await client.post("/api/telefonate", headers=s["h"], json=_body(vorgang_id=str(s["vorgang"].id), ergebnis="nicht_erreicht", notiz=None, ansprechpartner_id=ap, partner_nummer=None, rueckruf_am=morgen))).json()
    offen_nr = (await client.post("/api/telefonate", headers=s["h"], json=_body(kunde_id=str(s["kunde"].id), ergebnis="mailbox", notiz=None, partner_name="Frau B", partner_nummer="0221 555 0123", rueckruf_am=morgen))).json()
    anderer = (await client.post("/api/telefonate", headers=s["h"], json=_body(kunde_id=str(s["kunde"].id), ergebnis="mailbox", notiz=None, partner_name="Herr C", partner_nummer="0221 999", rueckruf_am=morgen))).json()
    erreicht_nicht = (await client.post("/api/telefonate", headers=s["h"], json=_body(kunde_id=str(s["kunde"].id), ergebnis="nicht_erreicht", notiz=None, ansprechpartner_id=ap, partner_nummer="0221555 0123"))).json()
    assert (await client.get("/api/telefonate/anzahl-offene-rueckrufe", headers=s["h"])).json() == {"anzahl": 3}, erreicht_nicht

    # Gleicher Ansprechpartner, anderer Kunde: bleibt offen (Kunde ist Teil des Schluessels).
    resp = await client.post("/api/telefonate", headers=s["h"], json=_body(kunde_id=str(s["kunde"].id), ansprechpartner_id=ap, partner_nummer="02215550123"))
    assert resp.status_code == 201

    def _rr(tid):
        return client.get(f"/api/telefonate/{tid}", headers=s["h"])

    assert (await _rr(offen_ap["id"])).json()["rueckruf_erledigt_am"] is not None
    assert (await _rr(offen_nr["id"])).json()["rueckruf_erledigt_am"] is not None
    assert (await _rr(anderer["id"])).json()["rueckruf_erledigt_am"] is None
    # Das Verlauf-Event des erledigten Rueckrufs zieht mit.
    (event,) = await _events(s["vorgang"].id)
    assert event.payload["rueckruf_erledigt_am"] is not None


async def test_nicht_erreicht_erledigt_rueckruf_nicht(client, szenario):
    s = szenario
    morgen = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    offen = (await client.post("/api/telefonate", headers=s["h"], json=_body(kunde_id=str(s["kunde"].id), ergebnis="mailbox", notiz=None, rueckruf_am=morgen))).json()
    await client.post("/api/telefonate", headers=s["h"], json=_body(kunde_id=str(s["kunde"].id), ergebnis="nicht_erreicht", notiz=None))
    assert (await client.get(f"/api/telefonate/{offen['id']}", headers=s["h"])).json()["rueckruf_erledigt_am"] is None


# --- Kontaktverlauf --------------------------------------------------------------------------


async def test_kontaktverlauf_mischt_telefonate_und_emails(client, szenario):
    s = szenario
    jetzt = datetime.now(UTC)
    await client.post("/api/telefonate", headers=s["h"], json=_body(vorgang_id=str(s["vorgang"].id), beginn=(jetzt - timedelta(days=3)).isoformat()))
    await client.post("/api/telefonate", headers=s["h"], json=_body(kunde_id=str(s["kunde"].id), beginn=(jetzt - timedelta(days=1)).isoformat()))
    async with system_session(grund="test") as db:
        for entity_type, entity_id, alter, betreff in (
            ("kunde", s["kunde"].id, 2, "Direkt an Kunde"),
            ("vorgang", s["vorgang"].id, 4, "Zum Vorgang"),
        ):
            m = EmailLog(
                mandant_id=s["mandant"].id, entity_type=entity_type, entity_id=entity_id, empfaenger="a@b.de",
                betreff=betreff, inhalt="x", status="gesendet",
            )
            m.created_at = (jetzt - timedelta(days=alter)).replace(tzinfo=None)
            db.add(m)
        fremd = EmailLog(mandant_id=s["mandant"].id, entity_type="kunde", entity_id=uuid.uuid4(), empfaenger="x@y.de", betreff="fremd", inhalt="x", status="gesendet")
        db.add(fremd)

    resp = await client.get(f"/api/kunden/{s['kunde'].id}/kontaktverlauf", headers=s["h"])
    assert resp.status_code == 200, resp.text
    eintraege = resp.json()
    assert [e["art"] for e in eintraege] == ["telefonat", "email", "telefonat", "email"]
    assert eintraege[1]["email"]["betreff"] == "Direkt an Kunde" and eintraege[1]["email"]["vorgang_id"] is None
    assert eintraege[3]["email"]["vorgang_nummer"] == "V-00048" and eintraege[3]["email"]["status"] == "gesendet"
    assert eintraege[0]["telefonat"]["vorgang_id"] is None and eintraege[2]["telefonat"]["vorgang_nummer"] == "V-00048"
    zeiten = [e["zeit"] for e in eintraege]
    assert zeiten == sorted(zeiten, reverse=True)
    assert len((await client.get(f"/api/kunden/{s['kunde'].id}/kontaktverlauf?limit=2", headers=s["h"])).json()) == 2


# --- Portale ---------------------------------------------------------------------------------


async def test_kundenportal_liefert_kein_telefonat_event(client, szenario):
    s = szenario
    await client.post("/api/telefonate", headers=s["h"], json=_body(vorgang_id=str(s["vorgang"].id)))
    # Selbst ein faelschlich als kundensichtbar markiertes Event darf nicht im Portal landen.
    async with system_session(grund="test") as db:
        for e in (await db.execute(select(VorgangEvent).where(VorgangEvent.event_type == "telefonat"))).scalars():
            e.kundensichtbar = True
    zugang = await _make_zugang(s["mandant"], s["kunde"], email="portal-tel@example.de")
    tokens = await _kunden_login(client, "portal-tel@example.de", "kunden-pw-123")
    resp = await client.get(f"/api/kundenportal/vorgaenge/{s['vorgang'].id}/events", headers=auth_headers(tokens["access_token"]))
    assert resp.status_code == 200, zugang
    assert all(e["event_type"] != "telefonat" for e in resp.json())
    assert "Termin abgestimmt" not in resp.text


# --- Scheduler -------------------------------------------------------------------------------


async def test_scheduler_benachrichtigt_genau_einmal(client, szenario):
    s = szenario
    t = (await client.post("/api/telefonate", headers=s["h"], json=_body(vorgang_id=str(s["vorgang"].id), partner_name="Frau Brandt", rueckruf_am=(datetime.now(UTC) + timedelta(hours=1)).isoformat()))).json()
    async with system_session(grund="test") as db:
        (await db.get(Telefonat, uuid.UUID(t["id"]))).rueckruf_am = datetime.now(UTC) - timedelta(minutes=1)
    zukunft = (await client.post("/api/telefonate", headers=s["h"], json=_body(kunde_id=str(s["kunde"].id), ergebnis="mailbox", notiz=None, rueckruf_am=(datetime.now(UTC) + timedelta(days=2)).isoformat()))).json()
    erledigt = (await client.post("/api/telefonate", headers=s["h"], json=_body(kunde_id=str(s["kunde"].id), ergebnis="mailbox", notiz=None, rueckruf_am="2020-01-01T09:00:00Z"))).json()
    await client.patch(f"/api/telefonate/{erledigt['id']}", headers=s["h"], json={"rueckruf_erledigt": True})

    assert (await run_rueckruf_scheduler([s["mandant"].id]))["rueckrufe_benachrichtigt"] == 1
    assert (await run_rueckruf_scheduler([s["mandant"].id]))["rueckrufe_benachrichtigt"] == 0

    async with system_session(grund="test") as db:
        notis = (await db.execute(select(Notification).where(Notification.typ == "rueckruf"))).scalars().all()
        assert len(notis) == 1
        n = notis[0]
        assert n.user_id == s["admin"].id and n.titel == "Rückruf: Frau Brandt"
        assert n.ref_entity_type == "vorgang" and n.ref_entity_id == s["vorgang"].id
        assert (await db.get(Telefonat, uuid.UUID(t["id"]))).rueckruf_benachrichtigt_am is not None
        assert (await db.get(Telefonat, uuid.UUID(zukunft["id"]))).rueckruf_benachrichtigt_am is None

    # Die Benachrichtigung ist ueber die normale Notification-API lesbar.
    liste = (await client.get("/api/notifications", headers=s["h"])).json()
    assert any(x["typ"] == "rueckruf" for x in liste)


async def test_scheduler_verweist_bei_telefonat_ohne_vorgang_auf_den_kunden(client, szenario):
    s = szenario
    await client.post("/api/telefonate", headers=s["h"], json=_body(kunde_id=str(s["kunde"].id), rueckruf_am="2020-01-01T09:00:00Z"))
    await run_rueckruf_scheduler([s["mandant"].id])
    async with system_session(grund="test") as db:
        n = (await db.execute(select(Notification).where(Notification.typ == "rueckruf"))).scalar_one()
        assert n.ref_entity_type == "kunde" and n.ref_entity_id == s["kunde"].id


async def test_geaenderter_rueckruf_loest_neue_erinnerung_aus(client, szenario):
    s = szenario
    t = (await client.post("/api/telefonate", headers=s["h"], json=_body(kunde_id=str(s["kunde"].id), rueckruf_am="2020-01-01T09:00:00Z"))).json()
    await run_rueckruf_scheduler([s["mandant"].id])
    await client.patch(f"/api/telefonate/{t['id']}", headers=s["h"], json={"rueckruf_am": "2020-02-01T09:00:00Z"})
    assert (await run_rueckruf_scheduler([s["mandant"].id]))["rueckrufe_benachrichtigt"] == 1


# --- Auswertung ------------------------------------------------------------------------------


async def test_auswertung_telefonate_und_telefonzeit(client, szenario):
    s = szenario
    await client.post("/api/telefonate", headers=s["h"], json=_body(vorgang_id=str(s["vorgang"].id), dauer_sekunden=600))
    await client.post("/api/telefonate", headers=s["h"], json=_body(kunde_id=str(s["kunde"].id), dauer_sekunden=1200))
    await client.post("/api/telefonate", headers=s["h"], json=_body(kunde_id=str(s["kunde"].id), ergebnis="mailbox", notiz=None))
    heute = datetime.now(UTC).date()
    params = {"bereich": "telefonate", "gruppierung": "kunde", "von": str(heute - timedelta(days=7)), "bis": str(heute + timedelta(days=1))}
    anzahl = (await client.get("/api/statistik/aggregat", headers=s["h"], params={**params, "kennzahl": "anzahl"})).json()
    assert anzahl["gesamt"] == 3 and anzahl["zeilen"][0]["label"] == "Café Sonnenschein"
    zeit = (await client.get("/api/statistik/aggregat", headers=s["h"], params={**params, "kennzahl": "telefonzeit_minuten"})).json()
    assert zeit["gesamt"] == 30.0
    ungueltig = await client.get("/api/statistik/aggregat", headers=s["h"], params={**params, "kennzahl": "anzahl", "gruppierung": "status"})
    assert ungueltig.status_code == 422


# --- Schema-Ebene ----------------------------------------------------------------------------


async def test_db_checks_greifen(szenario):
    s = szenario
    async with system_session(grund="test") as db:
        user_id = s["admin"].id
        with pytest.raises(Exception, match="ck_telefonate_kunde_oder_vorgang"):
            async with db.begin_nested():
                db.add(Telefonat(mandant_id=s["mandant"].id, partner_name="x", richtung="ausgehend", ergebnis="mailbox", beginn=datetime.now(UTC), erfasst_von=user_id))
                await db.flush()
        with pytest.raises(Exception, match="ck_telefonate_richtung_valid"):
            async with db.begin_nested():
                db.add(Telefonat(mandant_id=s["mandant"].id, kunde_id=s["kunde"].id, partner_name="x", richtung="quer", ergebnis="mailbox", beginn=datetime.now(UTC), erfasst_von=user_id))
                await db.flush()
        with pytest.raises(Exception, match="ck_telefonate_dauer_nicht_negativ"):
            async with db.begin_nested():
                db.add(Telefonat(mandant_id=s["mandant"].id, kunde_id=s["kunde"].id, partner_name="x", richtung="ausgehend", ergebnis="erreicht", dauer_sekunden=-5, beginn=datetime.now(UTC), erfasst_von=user_id))
                await db.flush()
