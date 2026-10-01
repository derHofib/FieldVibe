"""Account-Typ-Schalter nur_zugewiesene_kunden muss auch bei Rechnungen,
Angeboten, Auswertung, Maengeln, Highlights und Stories greifen (nicht nur bei
Kunden/Vorgaengen)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.session import system_session
from app.models.account_typ import AccountTyp
from app.models.user import User
from app.models.vorgang_event import VorgangEvent
from tests.conftest import auth_headers, login


@pytest.fixture
async def szenario(client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    # "disponent" hat volle abrechnung-/vorgaenge-Rechte; der Schalter wird
    # fuer den Test gezielt eingeschaltet, damit auch Mutationen (nicht nur
    # Lesen wie beim Techniker) bis zur Zuweisungspruefung kommen.
    eingeschraenkt = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    async with system_session() as session:
        user = await session.get(User, eingeschraenkt.id)
        typ = await session.get(AccountTyp, user.account_typ_id)
        typ.nur_zugewiesene_kunden = True

    eigener = await make_kunde(mandant=mandant, name="Eigener Kunde")
    fremder = await make_kunde(mandant=mandant, name="Fremder Kunde")
    await make_kunde_zuweisung(mandant=mandant, kunde=eigener, techniker=eingeschraenkt)

    alt = datetime.now(timezone.utc) - timedelta(days=10)
    vorgang_eigen = await make_vorgang(
        mandant=mandant, kunde=eigener, status="wartet_kunde", last_activity_at=alt
    )
    vorgang_fremd = await make_vorgang(
        mandant=mandant, kunde=fremder, status="wartet_kunde", last_activity_at=alt
    )

    admin_token = await login(client, admin.email, "pw-123456")
    token = await login(client, eingeschraenkt.email, "pw-123456")
    return {
        "mandant": mandant,
        "admin": auth_headers(admin_token),
        "user": auth_headers(token),
        "eigener": eigener,
        "fremder": fremder,
        "vorgang_eigen": vorgang_eigen,
        "vorgang_fremd": vorgang_fremd,
    }


async def _rechnung(client, headers, kunde, netto, *, versenden=True) -> str:
    resp = await client.post(
        "/api/rechnungen",
        headers=headers,
        json={"kunde_id": str(kunde.id), "betrag_netto": netto, "mwst_satz": "19.00"},
    )
    assert resp.status_code == 201, resp.text
    rid = resp.json()["id"]
    if versenden:
        r = await client.patch(f"/api/rechnungen/{rid}", headers=headers, json={"status": "versendet"})
        assert r.status_code == 200, r.text
    return rid


async def _angebot(client, headers, kunde) -> str:
    resp = await client.post(
        "/api/angebote",
        headers=headers,
        json={
            "kunde_id": str(kunde.id),
            "positionen": [{"beschreibung": "Leistung", "menge": "1", "einzelpreis": "100"}],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_rechnungen_liste_detail_export_und_mutationen(client, szenario):
    s = szenario
    r_eigen = await _rechnung(client, s["admin"], s["eigener"], "1000.00")
    r_fremd = await _rechnung(client, s["admin"], s["fremder"], "500.00")

    liste = await client.get("/api/rechnungen", headers=s["user"])
    assert liste.status_code == 200
    assert [e["id"] for e in liste.json()["eintraege"]] == [r_eigen]
    # Summenzeile darf fremde Betraege nicht mitzaehlen
    assert liste.json()["gesamt_anzahl"] == 1
    assert liste.json()["summe_netto"] == "1000.00"

    # kunde_id-Filter auf fremden Kunden liefert nichts statt fremde Daten
    gefiltert = await client.get(
        "/api/rechnungen", headers=s["user"], params={"kunde_id": str(s["fremder"].id)}
    )
    assert gefiltert.json()["eintraege"] == []

    admin_liste = await client.get("/api/rechnungen", headers=s["admin"])
    assert {e["id"] for e in admin_liste.json()["eintraege"]} == {r_eigen, r_fremd}
    assert admin_liste.json()["summe_netto"] == "1500.00"

    assert (await client.get(f"/api/rechnungen/{r_eigen}", headers=s["user"])).status_code == 200
    for pfad in ("", "/pdf", "/xml", "/emails", "/positionsvorschlaege"):
        resp = await client.get(f"/api/rechnungen/{r_fremd}{pfad}", headers=s["user"])
        assert resp.status_code == 404, pfad
    assert (await client.get(f"/api/rechnungen/{r_fremd}", headers=s["admin"])).status_code == 200

    csv_user = await client.get("/api/rechnungen/export/csv", headers=s["user"])
    assert csv_user.status_code == 200
    assert "Fremder Kunde" not in csv_user.text
    assert "Eigener Kunde" in csv_user.text
    assert "Fremder Kunde" in (await client.get("/api/rechnungen/export/csv", headers=s["admin"])).text

    # Mutationen auf fremder Rechnung -> 404
    assert (
        await client.patch(f"/api/rechnungen/{r_fremd}", headers=s["user"], json={"status": "bezahlt"})
    ).status_code == 404
    assert (
        await client.post(
            f"/api/rechnungen/{r_fremd}/zahlungen",
            headers=s["user"],
            json={"betrag": "10.00", "zahlungsart": "ueberweisung"},
        )
    ).status_code == 404
    assert (await client.post(f"/api/rechnungen/{r_fremd}/storno", headers=s["user"], json={})).status_code == 404
    assert (await client.delete(f"/api/rechnungen/{r_fremd}", headers=s["user"])).status_code == 404
    assert (
        await client.post(
            f"/api/rechnungen/{r_fremd}/positionen",
            headers=s["user"],
            json={"beschreibung": "x", "menge": "1", "einzelpreis": "1"},
        )
    ).status_code == 404
    # Rechnung unveraendert
    assert (await client.get(f"/api/rechnungen/{r_fremd}", headers=s["admin"])).json()["status"] == "versendet"


@pytest.mark.asyncio
async def test_rechnung_anlegen_und_abrechenbare_vorgaenge_fuer_fremden_kunden(client, szenario):
    s = szenario
    resp = await client.post(
        "/api/rechnungen",
        headers=s["user"],
        json={"kunde_id": str(s["fremder"].id), "betrag_netto": "10.00", "mwst_satz": "19.00"},
    )
    assert resp.status_code == 403

    ok = await client.post(
        "/api/rechnungen",
        headers=s["user"],
        json={"kunde_id": str(s["eigener"].id), "betrag_netto": "10.00", "mwst_satz": "19.00"},
    )
    assert ok.status_code == 201

    assert (
        await client.get(
            "/api/rechnungen/abrechenbare-vorgaenge", headers=s["user"], params={"kunde_id": str(s["fremder"].id)}
        )
    ).status_code == 404
    assert (
        await client.get(
            "/api/rechnungen/abrechenbare-vorgaenge", headers=s["user"], params={"kunde_id": str(s["eigener"].id)}
        )
    ).status_code == 200
    assert (
        await client.get(
            "/api/rechnungen/abrechenbare-vorgaenge", headers=s["admin"], params={"kunde_id": str(s["fremder"].id)}
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_vorgang_vorschlaege_fremde_rechnung_404(client, szenario):
    s = szenario
    r_fremd = await _rechnung(client, s["admin"], s["fremder"], "500.00", versenden=False)
    resp = await client.get(
        f"/api/rechnungen/{r_fremd}/vorgaenge/{s['vorgang_fremd'].id}/vorschlaege", headers=s["user"]
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_angebote(client, szenario):
    s = szenario
    a_eigen = await _angebot(client, s["admin"], s["eigener"])
    a_fremd = await _angebot(client, s["admin"], s["fremder"])

    liste = await client.get("/api/angebote", headers=s["user"])
    assert [a["id"] for a in liste.json()] == [a_eigen]
    assert {a["id"] for a in (await client.get("/api/angebote", headers=s["admin"])).json()} == {a_eigen, a_fremd}
    assert (await client.get("/api/angebote", headers=s["user"], params={"kunde_id": str(s["fremder"].id)})).json() == []

    assert (await client.get(f"/api/angebote/{a_eigen}", headers=s["user"])).status_code == 200
    for pfad in ("", "/pdf", "/emails"):
        assert (await client.get(f"/api/angebote/{a_fremd}{pfad}", headers=s["user"])).status_code == 404, pfad
    assert (await client.get(f"/api/angebote/{a_fremd}", headers=s["admin"])).status_code == 200

    assert (
        await client.patch(f"/api/angebote/{a_fremd}", headers=s["user"], json={"status": "versendet"})
    ).status_code == 404
    assert (
        await client.post(
            f"/api/angebote/{a_fremd}/positionen",
            headers=s["user"],
            json={"beschreibung": "x", "menge": "1", "einzelpreis": "1"},
        )
    ).status_code == 404
    assert (await client.delete(f"/api/angebote/{a_fremd}", headers=s["user"])).status_code == 404

    neu = await client.post("/api/angebote", headers=s["user"], json={"kunde_id": str(s["fremder"].id)})
    assert neu.status_code == 403
    aus_vorgang = await client.post(
        "/api/angebote/from-vorgang", headers=s["user"], json={"vorgang_id": str(s["vorgang_fremd"].id)}
    )
    assert aus_vorgang.status_code == 403


@pytest.mark.asyncio
async def test_auswertung_nur_ueber_zugewiesene_kunden(client, szenario):
    s = szenario
    await _rechnung(client, s["admin"], s["eigener"], "1000.00")
    await _rechnung(client, s["admin"], s["fremder"], "500.00")
    await client.post(
        "/api/eingangsrechnungen",
        headers=s["admin"],
        json={
            "lieferant_name": "Sonepar",
            "rechnungsnummer_lieferant": "RE-1",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "200.00",
            "mwst_satz": "19.00",
        },
    )
    zeitraum = {"von": "2020-01-01", "bis": "2030-12-31"}

    admin_ust = (await client.get("/api/auswertung/ust-va", headers=s["admin"], params=zeitraum)).json()
    assert admin_ust["summe_umsatzsteuer"] == "285.00"
    assert admin_ust["summe_vorsteuer"] == "38.00"

    ust = (await client.get("/api/auswertung/ust-va", headers=s["user"], params=zeitraum)).json()
    assert ust["summe_umsatzsteuer"] == "190.00"
    assert ust["umsatzsteuer_saetze"][0]["netto"] == "1000.00"
    # Eingangsrechnungen haben keinen Kundenbezug
    assert ust["summe_vorsteuer"] == "0.00"

    op_admin = (await client.get("/api/auswertung/offene-posten", headers=s["admin"])).json()
    assert len(op_admin["debitoren"]) == 2
    assert len(op_admin["kreditoren"]) == 1
    op = (await client.get("/api/auswertung/offene-posten", headers=s["user"])).json()
    assert len(op["debitoren"]) == 1
    assert op["debitoren"][0]["partner_name"] == "Eigener Kunde"
    assert op["kreditoren"] == []
    assert op["summe_debitoren"] == "1190.00"

    datev = await client.get("/api/auswertung/datev-export", headers=s["user"], params=zeitraum)
    assert datev.status_code == 200
    assert "Fremder Kunde" not in datev.text
    assert "Eigener Kunde" in datev.text
    assert "Fremder Kunde" in (
        await client.get("/api/auswertung/datev-export", headers=s["admin"], params=zeitraum)
    ).text


@pytest.mark.asyncio
async def test_maengel(client, szenario):
    s = szenario
    ids = {}
    for name in ("eigen", "fremd"):
        resp = await client.post(
            "/api/maengel",
            headers=s["admin"],
            json={"vorgang_id": str(s[f"vorgang_{name}"].id), "beschreibung": f"Mangel {name}"},
        )
        assert resp.status_code == 201, resp.text
        ids[name] = resp.json()["id"]

    liste = await client.get("/api/maengel", headers=s["user"])
    assert [m["id"] for m in liste.json()] == [ids["eigen"]]
    assert len((await client.get("/api/maengel", headers=s["admin"])).json()) == 2

    assert (await client.get(f"/api/maengel/{ids['eigen']}", headers=s["user"])).status_code == 200
    assert (await client.get(f"/api/maengel/{ids['fremd']}", headers=s["user"])).status_code == 404
    assert (await client.get(f"/api/maengel/{ids['fremd']}", headers=s["admin"])).status_code == 200
    assert (
        await client.patch(f"/api/maengel/{ids['fremd']}", headers=s["user"], json={"status": "behoben"})
    ).status_code == 404
    assert (await client.delete(f"/api/maengel/{ids['fremd']}", headers=s["user"])).status_code == 404
    assert (
        await client.post(
            "/api/maengel",
            headers=s["user"],
            json={"vorgang_id": str(s["vorgang_fremd"].id), "beschreibung": "x"},
        )
    ).status_code == 404
    assert (
        await client.get(
            "/api/maengel/protokoll/pdf", headers=s["user"], params={"vorgang_id": str(s["vorgang_fremd"].id)}
        )
    ).status_code == 404
    assert (
        await client.get(
            "/api/maengel/protokoll/pdf", headers=s["user"], params={"vorgang_id": str(s["vorgang_eigen"].id)}
        )
    ).status_code == 200
    # Mangel fremd weiterhin offen
    assert (await client.get(f"/api/maengel/{ids['fremd']}", headers=s["admin"])).json()["status"] == "offen"


async def _foto_event(mandant, vorgang) -> int:
    async with system_session() as session:
        event = VorgangEvent(
            mandant_id=mandant.id,
            vorgang_id=vorgang.id,
            event_type="foto",
            payload={"key": "fotos/t.jpg", "thumbnail_key": "fotos/t_thumb.jpg"},
        )
        session.add(event)
        await session.flush()
        return event.id


@pytest.mark.asyncio
async def test_highlights(client, szenario):
    s = szenario
    ev_eigen = await _foto_event(s["mandant"], s["vorgang_eigen"])
    ev_fremd = await _foto_event(s["mandant"], s["vorgang_fremd"])

    assert (
        await client.post("/api/highlights", headers=s["user"], json={"vorgang_event_id": ev_fremd})
    ).status_code == 404
    assert (
        await client.post("/api/highlights", headers=s["user"], json={"vorgang_event_id": ev_eigen})
    ).status_code == 201
    fremd = await client.post("/api/highlights", headers=s["admin"], json={"vorgang_event_id": ev_fremd})
    assert fremd.status_code == 201
    fremd_id = fremd.json()["id"]

    liste = await client.get("/api/highlights", headers=s["user"])
    assert [h["vorgang_id"] for h in liste.json()] == [str(s["vorgang_eigen"].id)]
    assert len((await client.get("/api/highlights", headers=s["admin"])).json()) == 2

    assert (await client.delete(f"/api/highlights/{fremd_id}", headers=s["user"])).status_code == 404
    assert (await client.delete(f"/api/highlights/{fremd_id}", headers=s["admin"])).status_code == 204


@pytest.mark.asyncio
async def test_stories_wartet_kunde(client, szenario):
    s = szenario
    user = (await client.get("/api/stories", headers=s["user"])).json()
    assert [i["ziel_id"] for i in user["wartet_kunde"]] == [str(s["vorgang_eigen"].id)]
    admin = (await client.get("/api/stories", headers=s["admin"])).json()
    assert {i["ziel_id"] for i in admin["wartet_kunde"]} == {
        str(s["vorgang_eigen"].id),
        str(s["vorgang_fremd"].id),
    }
