"""Kontakte vor Ort (Migration 0125): CRUD, Zuordnung, Vererbung, Rechte, Anonymisierung, Suche, Feed."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db.session import system_session
from app.models.audit_log import AuditLog
from app.models.vor_ort_kontakt import VorOrtKontakt
from app.services.vor_ort_kontakt_service import run_vor_ort_kontakte_anonymisierung
from tests.conftest import auth_headers, login

PW = "pw-123456"


async def _setup(make_mandant, make_user, make_kunde, client):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW)
    kunde = await make_kunde(mandant=mandant, name="Hausverwaltung Nord", typ="hausverwaltung")
    token = await login(client, admin.email, PW)
    return mandant, admin, kunde, auth_headers(token)


async def _standort(client, h, kunde, bezeichnung="Liegenschaft 1"):
    r = await client.post(
        "/api/standorte", headers=h, json={"kunde_id": str(kunde.id), "bezeichnung": bezeichnung, "adresse": {"ort": "Köln"}}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _kontakt(client, h, kunde, **kw):
    body = {"name": "Frau Becker", "rolle": "mieter", **kw}
    r = await client.post(f"/api/kunden/{kunde.id}/vor-ort-kontakte", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def _auftrag(client, h, kunde, **kw):
    r = await client.post("/api/auftraege", headers=h, json={"titel": "Heizung", "kunde_id": str(kunde.id), **kw})
    assert r.status_code == 201, r.text
    return r.json()


async def _vorgang(client, h, kunde, **kw):
    body = {
        "kunde_id": str(kunde.id), "titel": "Störung", "abrechnungsart": "aufwand", "leistungstyp": "stoerung", **kw,
    }
    r = await client.post("/api/vorgaenge", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def _projekt(client, h, kunde=None, **kw):
    body = {"name": "Neubau", **({"kunde_id": str(kunde.id)} if kunde else {}), **kw}
    r = await client.post("/api/projekte", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _zuordnen(client, h, pfad, ziel_id, **body):
    return client.post(f"/api/{pfad}/{ziel_id}/vor-ort-kontakte", headers=h, json=body)


@pytest.mark.asyncio
async def test_crud_und_name_oder_telefon_pflicht(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _setup(make_mandant, make_user, make_kunde, client)
    standort = await _standort(client, h, kunde)

    k = await _kontakt(
        client, h, kunde, standort_id=standort["id"], einheit="  Whg. 3  ", telefon="0171 123", email="  ", hinweis="Hund"
    )
    assert k["einheit"] == "Whg. 3" and k["email"] is None
    assert k["quelle"] == "buero" and k["standort_bezeichnung"] == "Liegenschaft 1"
    assert k["zuordnungen_anzahl"] == 0 and k["anonymisiert_am"] is None

    # Weder Name noch Telefon -> 422; leere Strings zaehlen als nicht gesetzt.
    r = await client.post(f"/api/kunden/{kunde.id}/vor-ort-kontakte", headers=h, json={"rolle": "mieter", "name": "  ", "telefon": ""})
    assert r.status_code == 422 and "Name oder Telefon" in r.text
    r = await client.post(f"/api/kunden/{kunde.id}/vor-ort-kontakte", headers=h, json={"rolle": "chef", "name": "X"})
    assert r.status_code == 422

    lst = await client.get(f"/api/kunden/{kunde.id}/vor-ort-kontakte", headers=h)
    assert [e["id"] for e in lst.json()] == [k["id"]]
    assert (await client.get(f"/api/kunden/{kunde.id}/vor-ort-kontakte?rolle=hausmeister", headers=h)).json() == []
    assert len((await client.get(f"/api/kunden/{kunde.id}/vor-ort-kontakte?q=0171", headers=h)).json()) == 1
    assert len((await client.get(f"/api/kunden/{kunde.id}/vor-ort-kontakte?q=Whg", headers=h)).json()) == 1

    r = await client.patch(f"/api/vor-ort-kontakte/{k['id']}", headers=h, json={"telefon2": "030 1", "rolle": "eigentuemer"})
    assert r.status_code == 200 and r.json()["rolle"] == "eigentuemer" and r.json()["telefon2"] == "030 1"
    # Ergebnis muss Name oder Telefon behalten.
    r = await client.patch(f"/api/vor-ort-kontakte/{k['id']}", headers=h, json={"name": None, "telefon": None})
    assert r.status_code == 422

    assert (await client.delete(f"/api/vor-ort-kontakte/{k['id']}", headers=h)).status_code == 204
    assert (await client.get(f"/api/kunden/{kunde.id}/vor-ort-kontakte", headers=h)).json() == []
    assert (await client.patch(f"/api/vor-ort-kontakte/{k['id']}", headers=h, json={"hinweis": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_standort_eines_anderen_kunden_wird_abgelehnt(client, make_mandant, make_user, make_kunde):
    mandant, _, kunde, h = await _setup(make_mandant, make_user, make_kunde, client)
    anderer = await make_kunde(mandant=mandant, name="Anderer")
    fremd = await _standort(client, h, anderer)
    r = await client.post(
        f"/api/kunden/{kunde.id}/vor-ort-kontakte", headers=h,
        json={"name": "X", "rolle": "mieter", "standort_id": fremd["id"]},
    )
    assert r.status_code == 422
    k = await _kontakt(client, h, kunde)
    r = await client.patch(f"/api/vor-ort-kontakte/{k['id']}", headers=h, json={"standort_id": fremd["id"]})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_zuordnung_kontakt_anderer_kunde_an_vorgang_422(client, make_mandant, make_user, make_kunde):
    mandant, _, kunde, h = await _setup(make_mandant, make_user, make_kunde, client)
    anderer = await make_kunde(mandant=mandant, name="Anderer")
    k = await _kontakt(client, h, kunde)
    vorgang = await _vorgang(client, h, anderer)
    r = await _zuordnen(client, h, "vorgaenge", vorgang["id"], kontakt_id=k["id"])
    assert r.status_code == 422
    # genau eines von kontakt_id/neu
    r = await _zuordnen(client, h, "vorgaenge", vorgang["id"])
    assert r.status_code == 422
    r = await _zuordnen(client, h, "vorgaenge", vorgang["id"], kontakt_id=k["id"], neu={"name": "X", "rolle": "mieter"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_auftrag_und_projekt_ohne_auftraggeber_422(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _setup(make_mandant, make_user, make_kunde, client)
    k = await _kontakt(client, h, kunde)
    auftrag = (await client.post("/api/auftraege", headers=h, json={"titel": "Ohne Kunde"})).json()
    r = await _zuordnen(client, h, "auftraege", auftrag["id"], kontakt_id=k["id"])
    assert r.status_code == 422 and "Auftraggeber" in r.text
    projekt = await _projekt(client, h)
    r = await _zuordnen(client, h, "projekte", projekt["id"], neu={"name": "X", "rolle": "bauherr"})
    assert r.status_code == 422 and "Auftraggeber" in r.text


@pytest.mark.asyncio
async def test_rls_anderer_mandant_sieht_und_aendert_nichts(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _setup(make_mandant, make_user, make_kunde, client)
    k = await _kontakt(client, h, kunde)
    mandant_b = await make_mandant("Betrieb B")
    admin_b = await make_user(mandant=mandant_b, role="mandant_admin", password=PW)
    hb = auth_headers(await login(client, admin_b.email, PW))
    assert (await client.get(f"/api/kunden/{kunde.id}/vor-ort-kontakte", headers=hb)).status_code == 404
    assert (await client.patch(f"/api/vor-ort-kontakte/{k['id']}", headers=hb, json={"hinweis": "x"})).status_code == 404
    assert (await client.delete(f"/api/vor-ort-kontakte/{k['id']}", headers=hb)).status_code == 404
    assert (await client.post(f"/api/vor-ort-kontakte/{k['id']}/anonymisieren", headers=hb)).status_code == 404
    # Auch das Zuordnen eines fremden Kontakts an ein eigenes Ziel scheitert.
    kunde_b = await make_kunde(mandant=mandant_b, name="B-Kunde")
    vorgang_b = await _vorgang(client, hb, kunde_b)
    assert (await _zuordnen(client, hb, "vorgaenge", vorgang_b["id"], kontakt_id=k["id"])).status_code == 404
    assert (await client.get(f"/api/kunden/{kunde.id}/vor-ort-kontakte", headers=h)).json()[0]["hinweis"] is None


@pytest.mark.asyncio
async def test_vererbung_dedupe_und_hauptkontakt_der_naechsten_ebene(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _setup(make_mandant, make_user, make_kunde, client)
    projekt = await _projekt(client, h, kunde)
    auftrag = await _auftrag(client, h, kunde, projekt_id=projekt["id"])
    vorgang = await _vorgang(client, h, kunde, auftrag_id=auftrag["id"])
    assert vorgang["projekt_id"] == projekt["id"]

    bauherr = await _kontakt(client, h, kunde, name="Bauherr Boss", rolle="bauherr")
    mieterin = await _kontakt(client, h, kunde, name="Frau Becker")
    bauleiter = await _kontakt(client, h, kunde, name="Bauleiter Bau", rolle="sonstige")

    r = await _zuordnen(client, h, "projekte", projekt["id"], kontakt_id=bauherr["id"], ist_hauptkontakt=True)
    assert r.status_code == 201 and r.json()["herkunft"] == "projekt" and r.json()["herkunft_titel"] == "Neubau"
    await _zuordnen(client, h, "auftraege", auftrag["id"], kontakt_id=mieterin["id"], ist_hauptkontakt=True)
    # Derselbe Kontakt auf zwei Ebenen; der Bauleiter nur am Vorgang.
    await _zuordnen(client, h, "auftraege", auftrag["id"], kontakt_id=bauherr["id"])
    await _zuordnen(client, h, "vorgaenge", vorgang["id"], kontakt_id=bauleiter["id"])

    liste = (await client.get(f"/api/vorgaenge/{vorgang['id']}/vor-ort-kontakte", headers=h)).json()
    namen = [(e["kontakt"]["name"], e["herkunft"], e["ist_hauptkontakt"]) for e in liste]
    # Hauptkontakt (Auftrag-Ebene schlaegt Projekt) zuerst, dann Vorgang, Auftrag, Projekt; Bauherr nur einmal (Auftrag gewinnt).
    assert namen == [
        ("Frau Becker", "auftrag", True),
        ("Bauleiter Bau", "vorgang", False),
        ("Bauherr Boss", "auftrag", False),
    ]
    assert liste[0]["herkunft_titel"] == "Heizung"

    assert [e["herkunft"] for e in (await client.get(f"/api/auftraege/{auftrag['id']}/vor-ort-kontakte", headers=h)).json()] == [
        "auftrag", "auftrag",
    ]
    projekt_liste = (await client.get(f"/api/projekte/{projekt['id']}/vor-ort-kontakte", headers=h)).json()
    assert [e["kontakt"]["name"] for e in projekt_liste] == ["Bauherr Boss"]

    detail = (await client.get(f"/api/vorgaenge/{vorgang['id']}", headers=h)).json()
    assert [e["kontakt"]["name"] for e in detail["vor_ort_kontakte"]] == ["Frau Becker", "Bauleiter Bau", "Bauherr Boss"]
    assert detail["hauptkontakt_vor_ort"]["name"] == "Frau Becker"

    # Hauptkontakt am Vorgang gewinnt gegenueber dem des Auftrags.
    z = (await _zuordnen(client, h, "vorgaenge", vorgang["id"], kontakt_id=mieterin["id"], ist_hauptkontakt=True)).json()
    assert z["ist_hauptkontakt"] is True
    detail = (await client.get(f"/api/vorgaenge/{vorgang['id']}", headers=h)).json()
    assert [(e["kontakt"]["name"], e["herkunft"]) for e in detail["vor_ort_kontakte"]][0] == ("Frau Becker", "vorgang")
    assert sum(e["ist_hauptkontakt"] for e in detail["vor_ort_kontakte"]) == 1


@pytest.mark.asyncio
async def test_hauptkontakt_wechsel_und_doppelte_zuordnung(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _setup(make_mandant, make_user, make_kunde, client)
    auftrag = await _auftrag(client, h, kunde)
    a = await _kontakt(client, h, kunde, name="A")
    b = await _kontakt(client, h, kunde, name="B")
    za = (await _zuordnen(client, h, "auftraege", auftrag["id"], kontakt_id=a["id"], ist_hauptkontakt=True)).json()
    zb = (await _zuordnen(client, h, "auftraege", auftrag["id"], kontakt_id=b["id"])).json()
    assert (await _zuordnen(client, h, "auftraege", auftrag["id"], kontakt_id=a["id"])).status_code == 409

    r = await client.patch(f"/api/vor-ort-kontakt-zuordnungen/{zb['zuordnung_id']}", headers=h, json={"ist_hauptkontakt": True})
    assert r.status_code == 200 and r.json()["ist_hauptkontakt"] is True
    liste = (await client.get(f"/api/auftraege/{auftrag['id']}/vor-ort-kontakte", headers=h)).json()
    assert {e["kontakt"]["name"]: e["ist_hauptkontakt"] for e in liste} == {"A": False, "B": True}
    # Neuen Kontakt direkt anlegen und zum Hauptkontakt machen.
    n = await _zuordnen(client, h, "auftraege", auftrag["id"], neu={"name": "C", "rolle": "hausmeister"}, ist_hauptkontakt=True)
    assert n.status_code == 201 and n.json()["kontakt"]["quelle"] == "buero"
    liste = (await client.get(f"/api/auftraege/{auftrag['id']}/vor-ort-kontakte", headers=h)).json()
    assert [e["kontakt"]["name"] for e in liste if e["ist_hauptkontakt"]] == ["C"]

    assert (await client.delete(f"/api/vor-ort-kontakt-zuordnungen/{za['zuordnung_id']}", headers=h)).status_code == 204
    assert (await client.delete(f"/api/vor-ort-kontakt-zuordnungen/{za['zuordnung_id']}", headers=h)).status_code == 404
    kontakte = (await client.get(f"/api/kunden/{kunde.id}/vor-ort-kontakte", headers=h)).json()
    assert {k["name"]: k["zuordnungen_anzahl"] for k in kontakte} == {"A": 0, "B": 1, "C": 1}
    assert {k["name"]: k["offene_zuordnungen_anzahl"] for k in kontakte}["B"] == 1


@pytest.mark.asyncio
async def test_neuer_kontakt_erbt_standort_des_ziels(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _setup(make_mandant, make_user, make_kunde, client)
    standort = await _standort(client, h, kunde)
    auftrag = await _auftrag(client, h, kunde, standort_id=standort["id"])
    r = await _zuordnen(client, h, "auftraege", auftrag["id"], neu={"name": "Neu", "rolle": "mieter"})
    assert r.json()["kontakt"]["standort_id"] == standort["id"]


@pytest.mark.asyncio
async def test_vorgang_im_auftrag_uebernimmt_standort_und_einheit(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _setup(make_mandant, make_user, make_kunde, client)
    standort = await _standort(client, h, kunde)
    auftrag = await _auftrag(client, h, kunde, standort_id=standort["id"], einheit="Whg. 3", kunden_referenz="HV-17")

    v = await _vorgang(client, h, kunde, auftrag_id=auftrag["id"], adresse={"ort": "Bonn"})
    assert (v["standort_id"], v["einheit"], v["adresse"]) == (standort["id"], "Whg. 3", {"ort": "Bonn"})
    # Explizit gesetzte Werte bleiben, ohne Auftrag keine Vorbelegung.
    anderer_standort = await _standort(client, h, kunde, "Liegenschaft 2")
    v2 = await _vorgang(client, h, kunde, auftrag_id=auftrag["id"], standort_id=anderer_standort["id"], einheit="Whg. 9")
    assert (v2["standort_id"], v2["einheit"]) == (anderer_standort["id"], "Whg. 9")
    v3 = await _vorgang(client, h, kunde)
    assert (v3["standort_id"], v3["einheit"]) == (None, None)

    detail = (await client.get(f"/api/vorgaenge/{v['id']}", headers=h)).json()
    assert detail["auftrag_kunden_referenz"] == "HV-17" and detail["auftraggeber_ansprechpartner"] is None
    # Einheit am Vorgang ist aenderbar.
    r = await client.patch(f"/api/vorgaenge/{v['id']}", headers=h, json={"einheit": "Whg. 4"})
    assert r.json()["einheit"] == "Whg. 4"


@pytest.mark.asyncio
async def test_auftrag_standort_ansprechpartner_und_kundenwechsel(client, make_mandant, make_user, make_kunde):
    mandant, _, kunde, h = await _setup(make_mandant, make_user, make_kunde, client)
    r = await client.post(
        "/api/kunden", headers=h,
        json={"name": "HV Süd", "ansprechpartner": [{"name": "Herr Meier", "position": "Sachbearbeitung", "telefon": "0221 1"}]},
    )
    hv = r.json()
    partner_id = hv["ansprechpartner"][0]["id"]
    standort = await _standort(client, h, kunde)
    fremd = await _standort(client, h, await make_kunde(mandant=mandant, name="Fremd"))

    auftrag = await _auftrag(client, h, kunde, standort_id=standort["id"])
    assert auftrag["standort"]["bezeichnung"] == "Liegenschaft 1" and auftrag["standort"]["adresse"] == {"ort": "Köln"}
    r = await client.patch(f"/api/auftraege/{auftrag['id']}", headers=h, json={"standort_id": fremd["id"]})
    assert r.status_code == 422
    r = await client.patch(f"/api/auftraege/{auftrag['id']}", headers=h, json={"ansprechpartner_id": partner_id})
    assert r.status_code == 422  # gehoert zu HV Süd, nicht zum Auftraggeber
    # Kundenwechsel mit nicht passendem Standort: 422 statt stilles Loeschen.
    r = await client.patch(f"/api/auftraege/{auftrag['id']}", headers=h, json={"kunde_id": hv["id"]})
    assert r.status_code == 422
    r = await client.patch(
        f"/api/auftraege/{auftrag['id']}", headers=h,
        json={"kunde_id": hv["id"], "standort_id": None, "ansprechpartner_id": partner_id, "kunden_referenz": " AZ-1 "},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ansprechpartner"]["name"] == "Herr Meier" and body["standort"] is None and body["kunden_referenz"] == "AZ-1"

    # Kontakte des alten Auftraggebers blockieren den Wechsel (409).
    a2 = await _auftrag(client, h, kunde)
    k = await _kontakt(client, h, kunde)
    await _zuordnen(client, h, "auftraege", a2["id"], kontakt_id=k["id"])
    r = await client.patch(f"/api/auftraege/{a2['id']}", headers=h, json={"kunde_id": hv["id"]})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_projekt_mit_auftraggeber_und_standort(client, make_mandant, make_user, make_kunde):
    mandant, _, kunde, h = await _setup(make_mandant, make_user, make_kunde, client)
    standort = await _standort(client, h, kunde)
    fremd = await _standort(client, h, await make_kunde(mandant=mandant, name="Fremd"))
    p = await _projekt(client, h, kunde, standort_id=standort["id"])
    assert p["kunde_name"] == "Hausverwaltung Nord" and p["standort_bezeichnung"] == "Liegenschaft 1"
    assert (await client.post("/api/projekte", headers=h, json={"name": "X", "kunde_id": str(kunde.id), "standort_id": fremd["id"]})).status_code == 422
    assert (await client.post("/api/projekte", headers=h, json={"name": "X", "standort_id": standort["id"]})).status_code == 422
    r = await client.patch(f"/api/projekte/{p['id']}", headers=h, json={"standort_id": fremd["id"]})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_techniker_ohne_betreuung_sieht_kontakte_des_kunden_nicht(
    client, make_mandant, make_user, make_kunde, make_kunde_zuweisung
):
    mandant, _, kunde, h = await _setup(make_mandant, make_user, make_kunde, client)
    k = await _kontakt(client, h, kunde)
    tech = await make_user(mandant=mandant, role="techniker", password=PW)
    ht = auth_headers(await login(client, tech.email, PW))
    assert (await client.get(f"/api/kunden/{kunde.id}/vor-ort-kontakte", headers=ht)).status_code == 404
    # Ohne Recht kunden.bearbeiten schon an der Route (403), nicht erst am Kundenscope.
    assert (await client.patch(f"/api/vor-ort-kontakte/{k['id']}", headers=ht, json={"hinweis": "x"})).status_code in (403, 404)

    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=tech)
    r = await client.get(f"/api/kunden/{kunde.id}/vor-ort-kontakte", headers=ht)
    assert r.status_code == 200 and len(r.json()) == 1


@pytest.mark.asyncio
async def test_abschluss_setzt_letzten_einsatz_und_job_anonymisiert_nur_alte_ohne_offene_zuordnung(
    client, make_mandant, make_user, make_kunde
):
    mandant, _, kunde, h = await _setup(make_mandant, make_user, make_kunde, client)
    auftrag = await _auftrag(client, h, kunde)
    vorgang = await _vorgang(client, h, kunde, auftrag_id=auftrag["id"])
    erledigt = await _kontakt(client, h, kunde, name="Erledigt", telefon="1")
    offen = await _kontakt(client, h, kunde, name="Offen")
    jung = await _kontakt(client, h, kunde, name="Jung")
    frei = await _kontakt(client, h, kunde, name="Frei")
    await _zuordnen(client, h, "vorgaenge", vorgang["id"], kontakt_id=erledigt["id"])
    await _zuordnen(client, h, "auftraege", auftrag["id"], kontakt_id=offen["id"])

    # Abschluss des Vorgangs vermerkt den Einsatz bei Kontakten des Vorgangs und seines Auftrags.
    r = await client.patch(f"/api/vorgaenge/{vorgang['id']}", headers=h, json={"status": "abgeschlossen"})
    assert r.status_code == 200, r.text
    kontakte = {k["name"]: k for k in (await client.get(f"/api/kunden/{kunde.id}/vor-ort-kontakte", headers=h)).json()}
    assert kontakte["Erledigt"]["letzter_einsatz_am"] is not None and kontakte["Offen"]["letzter_einsatz_am"] is not None
    assert kontakte["Jung"]["letzter_einsatz_am"] is None
    assert kontakte["Erledigt"]["offene_zuordnungen_anzahl"] == 0 and kontakte["Offen"]["offene_zuordnungen_anzahl"] == 1

    # Alle ausser "Jung" liegen 13 Monate zurueck; "Offen" hat noch einen offenen Auftrag.
    alt = datetime.now(timezone.utc) - timedelta(days=400)
    async with system_session(grund="test") as session:
        await session.execute(
            text("UPDATE vor_ort_kontakte SET letzter_einsatz_am = :alt, created_at = :alt WHERE name <> 'Jung'"), {"alt": alt}
        )
    ergebnis = await run_vor_ort_kontakte_anonymisierung([mandant.id])
    assert ergebnis == {"kontakte_anonymisiert": 2}  # Erledigt + Frei

    async with system_session(grund="test") as session:
        zeilen = {k.rolle + str(k.id): k for k in (await session.execute(select(VorOrtKontakt))).scalars()}
        anonym = [k for k in zeilen.values() if k.anonymisiert_am is not None]
        assert len(anonym) == 2
        for k in anonym:
            assert (k.name, k.telefon, k.email, k.hinweis) == (None, None, None, None) and k.rolle == "mieter"
        protokoll = (await session.execute(select(AuditLog).where(AuditLog.aktion == "vor_ort_kontakt_anonymisiert"))).scalars().all()
        assert len(protokoll) == 2 and all(p.payload == {"grund": "frist"} for p in protokoll)

    kontakte = {k["id"]: k for k in (await client.get(f"/api/kunden/{kunde.id}/vor-ort-kontakte", headers=h)).json()}
    assert kontakte[offen["id"]]["name"] == "Offen" and kontakte[jung["id"]]["name"] == "Jung"
    assert kontakte[frei["id"]]["name"] is None and kontakte[frei["id"]]["anonymisiert_am"] is not None
    # Zweiter Lauf: nichts mehr zu tun. Anonymisierte sind nicht mehr aenderbar oder zuordenbar.
    assert await run_vor_ort_kontakte_anonymisierung([mandant.id]) == {"kontakte_anonymisiert": 0}
    assert (await client.patch(f"/api/vor-ort-kontakte/{frei['id']}", headers=h, json={"hinweis": "x"})).status_code == 409
    auftrag2 = await _auftrag(client, h, kunde)
    assert (await _zuordnen(client, h, "auftraege", auftrag2["id"], kontakt_id=frei["id"])).status_code == 409
    # Anonymisierte bleiben an ihren Zielen sichtbar (ohne Namen) und sind filterbar.
    ziel = (await client.get(f"/api/vorgaenge/{vorgang['id']}/vor-ort-kontakte", headers=h)).json()
    assert {e["kontakt"]["name"] for e in ziel} == {None, "Offen"}
    assert len((await client.get(f"/api/kunden/{kunde.id}/vor-ort-kontakte?mit_anonymisierten=false", headers=h)).json()) == 2


@pytest.mark.asyncio
async def test_manuelles_anonymisieren_und_frist_aus_einstellungen(client, make_mandant, make_user, make_kunde):
    mandant, _, kunde, h = await _setup(make_mandant, make_user, make_kunde, client)
    k = await _kontakt(client, h, kunde, telefon="0171", einheit="Whg. 1", hinweis="Klingel defekt")
    r = await client.post(f"/api/vor-ort-kontakte/{k['id']}/anonymisieren", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["name"] is None and body["telefon"] is None and body["hinweis"] is None
    assert body["einheit"] == "Whg. 1" and body["rolle"] == "mieter" and body["anonymisiert_am"]
    async with system_session(grund="test") as session:
        eintrag = (await session.execute(select(AuditLog).where(AuditLog.aktion == "vor_ort_kontakt_anonymisiert"))).scalar_one()
        assert eintrag.payload == {"grund": "manuell"} and eintrag.actor_user_id is not None

    einst = (await client.get("/api/mandant/einstellungen", headers=h)).json()
    assert einst["vor_ort_kontakte_anonymisieren_monate"] == 12
    for ungueltig in (2, 61):
        assert (await client.patch("/api/mandant/einstellungen", headers=h, json={"vor_ort_kontakte_anonymisieren_monate": ungueltig})).status_code == 422
    r = await client.patch("/api/mandant/einstellungen", headers=h, json={"vor_ort_kontakte_anonymisieren_monate": 24})
    assert r.json()["vor_ort_kontakte_anonymisieren_monate"] == 24
    # Andere Felder lassen die Frist unberuehrt.
    r = await client.patch("/api/mandant/einstellungen", headers=h, json={"wiedervorlage_standard_tage": 3})
    assert r.json()["vor_ort_kontakte_anonymisieren_monate"] == 24

    # Mit 24 Monaten ist ein 13 Monate alter Kontakt noch nicht faellig.
    k2 = await _kontakt(client, h, kunde, name="Alt")
    alt = datetime.now(timezone.utc) - timedelta(days=400)
    async with system_session(grund="test") as session:
        await session.execute(text("UPDATE vor_ort_kontakte SET created_at = :alt WHERE id = :id"), {"alt": alt, "id": k2["id"]})
    assert await run_vor_ort_kontakte_anonymisierung([mandant.id]) == {"kontakte_anonymisiert": 0}


@pytest.mark.asyncio
async def test_constraint_name_oder_telefon_in_der_datenbank(client, make_mandant, make_user, make_kunde):
    mandant, _, kunde, _ = await _setup(make_mandant, make_user, make_kunde, client)
    with pytest.raises(IntegrityError):
        async with system_session(grund="test") as session:
            session.add(VorOrtKontakt(mandant_id=mandant.id, kunde_id=kunde.id, rolle="mieter"))
            await session.flush()


@pytest.mark.asyncio
async def test_feed_liefert_hauptkontakt_und_einheit(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _setup(make_mandant, make_user, make_kunde, client)
    auftrag = await _auftrag(client, h, kunde, einheit="Whg. 3")
    mit = await _vorgang(client, h, kunde, auftrag_id=auftrag["id"], titel="Mit Kontakt")
    ohne = await _vorgang(client, h, kunde, titel="Ohne Kontakt")
    k = await _kontakt(client, h, kunde, name="Frau Becker", telefon="0171 1", einheit="Whg. 3")
    await _zuordnen(client, h, "auftraege", auftrag["id"], kontakt_id=k["id"], ist_hauptkontakt=True)

    items = {i["titel"]: i for i in (await client.get("/api/feed", headers=h)).json()["items"]}
    assert items["Mit Kontakt"]["hauptkontakt_vor_ort"] == {
        "name": "Frau Becker", "rolle": "mieter", "telefon": "0171 1", "einheit": "Whg. 3",
    }
    assert items["Mit Kontakt"]["einheit"] == "Whg. 3"
    assert items["Ohne Kontakt"]["hauptkontakt_vor_ort"] is None
    liste = {v["id"]: v for v in (await client.get("/api/vorgaenge", headers=h)).json()}
    assert liste[mit["id"]]["hauptkontakt_vor_ort"]["name"] == "Frau Becker"
    assert liste[ohne["id"]]["hauptkontakt_vor_ort"] is None


@pytest.mark.asyncio
async def test_suche_findet_kontakt_mit_ziel_kunde(client, make_mandant, make_user, make_kunde, make_kunde_zuweisung):
    mandant, _, kunde, h = await _setup(make_mandant, make_user, make_kunde, client)
    k = await _kontakt(client, h, kunde, name="Familie Zimmermann", einheit="Dachgeschoss")
    treffer = (await client.get("/api/search?q=Zimmermann", headers=h)).json()
    hits = [t for t in treffer["treffer"] if t["kategorie"] == "vor_ort_kontakt"]
    assert [(t["id"], t["kunde_id"], t["kunde_name"]) for t in hits] == [(k["id"], str(kunde.id), "Hausverwaltung Nord")]
    assert treffer["anzahl"]["vor_ort_kontakt"] == 1
    assert len((await client.get("/api/search?q=Dachgeschoss&kategorie=vor_ort_kontakt", headers=h)).json()["treffer"]) == 1

    tech = await make_user(mandant=mandant, role="techniker", password=PW)
    ht = auth_headers(await login(client, tech.email, PW))
    assert [t for t in (await client.get("/api/search?q=Zimmermann", headers=ht)).json()["treffer"] if t["kategorie"] == "vor_ort_kontakt"] == []
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=tech)
    assert len([t for t in (await client.get("/api/search?q=Zimmermann", headers=ht)).json()["treffer"] if t["kategorie"] == "vor_ort_kontakt"]) == 1

    await client.delete(f"/api/vor-ort-kontakte/{k['id']}", headers=h)
    assert (await client.get("/api/search?q=Zimmermann", headers=h)).json()["anzahl"].get("vor_ort_kontakt") == 0
