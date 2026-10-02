"""Account-Typ-Schalter nur_zugewiesene_kunden muss auch bei Rechnungen,
Angeboten, Auswertung, Maengeln, Highlights und Stories greifen (nicht nur bei
Kunden/Vorgaengen)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.db.session import system_session
from app.models.account_typ import AccountTyp, AccountTypRecht
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
        # Der Legacy-Disponent hat kein projekte-Recht (Auftraege/Aufgaben/Zeitplan).
        await session.execute(
            delete(AccountTypRecht).where(
                AccountTypRecht.account_typ_id == typ.id, AccountTypRecht.bereich == "projekte"
            )
        )
        for aktion in ("sehen", "erstellen", "bearbeiten", "loeschen"):
            session.add(
                AccountTypRecht(account_typ_id=typ.id, bereich="projekte", aktion=aktion, erlaubt=True)
            )

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
        "eingeschraenkt": eingeschraenkt,
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
async def test_auswertung_fuer_eingeschraenkte_gesperrt(client, szenario):
    s = szenario
    zeitraum = {"von": "2020-01-01", "bis": "2030-12-31"}
    for pfad, params in (
        ("/api/auswertung/ust-va", zeitraum),
        ("/api/auswertung/offene-posten", None),
        ("/api/auswertung/datev-export", zeitraum),
    ):
        user = await client.get(pfad, headers=s["user"], params=params)
        assert user.status_code == 403, pfad
        assert "Kundeneinschränkung" in user.json()["detail"]
        assert (await client.get(pfad, headers=s["admin"], params=params)).status_code == 200, pfad


@pytest.mark.asyncio
async def test_me_liefert_nur_zugewiesene_kunden_flag(client, szenario):
    s = szenario
    assert (await client.get("/api/auth/me", headers=s["user"])).json()["nur_zugewiesene_kunden"] is True
    assert (await client.get("/api/auth/me", headers=s["admin"])).json()["nur_zugewiesene_kunden"] is False


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


# --- Anfragen, Auftraege, Material, Pruefzyklen, Aufgaben, Statistik, Zeitplan ---


async def _anfrage(mandant, kunde, titel) -> str:
    from app.models.kundenportal import KundenportalZugang
    from app.models.vorgang_anfrage import VorgangAnfrage

    async with system_session() as session:
        zugang = KundenportalZugang(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            email=f"p-{kunde.id}@example.de",
            password_hash="x",
            name="Portal",
        )
        session.add(zugang)
        await session.flush()
        anfrage = VorgangAnfrage(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            kundenportal_zugang_id=zugang.id,
            titel=titel,
            leistungstyp="stoerung",
        )
        session.add(anfrage)
        await session.flush()
        return str(anfrage.id)


@pytest.mark.asyncio
async def test_vorgang_anfragen(client, szenario):
    s = szenario
    a_eigen = await _anfrage(s["mandant"], s["eigener"], "Eigene Anfrage")
    a_fremd = await _anfrage(s["mandant"], s["fremder"], "Fremde Anfrage")

    assert [a["id"] for a in (await client.get("/api/vorgang-anfragen", headers=s["user"])).json()] == [a_eigen]
    assert len((await client.get("/api/vorgang-anfragen", headers=s["admin"])).json()) == 2
    assert (await client.get(f"/api/vorgang-anfragen/{a_eigen}", headers=s["user"])).status_code == 200
    assert (await client.get(f"/api/vorgang-anfragen/{a_fremd}", headers=s["user"])).status_code == 404
    assert (await client.get(f"/api/vorgang-anfragen/{a_fremd}", headers=s["admin"])).status_code == 200

    assert (
        await client.post(
            f"/api/vorgang-anfragen/{a_fremd}/annehmen", headers=s["user"], json={"abrechnungsart": "aufwand"}
        )
    ).status_code == 404
    assert (
        await client.post(f"/api/vorgang-anfragen/{a_fremd}/ablehnen", headers=s["user"], json={})
    ).status_code == 404
    assert (await client.get(f"/api/vorgang-anfragen/{a_fremd}", headers=s["admin"])).json()["status"] == "offen"
    assert (
        await client.post(
            f"/api/vorgang-anfragen/{a_eigen}/annehmen", headers=s["user"], json={"abrechnungsart": "aufwand"}
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_auftraege(client, szenario):
    s = szenario
    ids = {}
    for name, kunde_id in (
        ("eigen", str(s["eigener"].id)),
        ("fremd", str(s["fremder"].id)),
        ("ohne", None),
    ):
        resp = await client.post(
            "/api/auftraege", headers=s["admin"], json={"titel": f"Auftrag {name}", "kunde_id": kunde_id}
        )
        assert resp.status_code == 201, resp.text
        ids[name] = resp.json()["id"]

    # Auftraege ohne Kunde bleiben sichtbar (kein Kundenbezug)
    assert {a["id"] for a in (await client.get("/api/auftraege", headers=s["user"])).json()} == {
        ids["eigen"],
        ids["ohne"],
    }
    assert len((await client.get("/api/auftraege", headers=s["admin"])).json()) == 3
    assert (await client.get(f"/api/auftraege/{ids['ohne']}", headers=s["user"])).status_code == 200
    assert (await client.get(f"/api/auftraege/{ids['fremd']}", headers=s["user"])).status_code == 404
    assert (await client.get(f"/api/auftraege/{ids['fremd']}", headers=s["admin"])).status_code == 200
    assert (
        await client.patch(f"/api/auftraege/{ids['fremd']}", headers=s["user"], json={"titel": "x"})
    ).status_code == 404
    assert (await client.delete(f"/api/auftraege/{ids['fremd']}", headers=s["user"])).status_code == 404
    assert (await client.get(f"/api/auftraege/{ids['fremd']}", headers=s["admin"])).json()["titel"] == "Auftrag fremd"
    assert (
        await client.post(
            "/api/auftraege", headers=s["user"], json={"titel": "neu", "kunde_id": str(s["fremder"].id)}
        )
    ).status_code == 403
    # eigenen Auftrag nicht auf fremden Kunden umhaengen
    assert (
        await client.patch(
            f"/api/auftraege/{ids['eigen']}", headers=s["user"], json={"kunde_id": str(s["fremder"].id)}
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_material_bedarfe(client, szenario):
    from app.models.material import Material
    from app.models.material_bedarf import MaterialBedarf

    s = szenario
    async with system_session() as session:
        material = Material(mandant_id=s["mandant"].id, bezeichnung="Kabel", einheit="m")
        session.add(material)
        await session.flush()
        material_id = str(material.id)
    ids = {}
    for name in ("eigen", "fremd"):
        resp = await client.post(
            "/api/material-bedarfe",
            headers=s["admin"],
            json={"material_id": material_id, "vorgang_id": str(s[f"vorgang_{name}"].id), "menge": "3"},
        )
        assert resp.status_code == 201, resp.text
        ids[name] = resp.json()["id"]

    assert [b["id"] for b in (await client.get("/api/material-bedarfe", headers=s["user"])).json()] == [ids["eigen"]]
    assert len((await client.get("/api/material-bedarfe", headers=s["admin"])).json()) == 2
    assert (
        await client.post(
            "/api/material-bedarfe",
            headers=s["user"],
            json={"material_id": material_id, "vorgang_id": str(s["vorgang_fremd"].id), "menge": "1"},
        )
    ).status_code == 403
    assert (await client.delete(f"/api/material-bedarfe/{ids['fremd']}", headers=s["user"])).status_code == 404
    async with system_session() as session:
        assert (await session.get(MaterialBedarf, ids["fremd"])).geloescht_am is None
    assert (await client.delete(f"/api/material-bedarfe/{ids['eigen']}", headers=s["user"])).status_code == 204


@pytest.mark.asyncio
async def test_pruefzyklen(client, szenario, make_anlage):
    s = szenario
    anlagen = {
        "eigen": await make_anlage(mandant=s["mandant"], kunde=s["eigener"]),
        "fremd": await make_anlage(mandant=s["mandant"], kunde=s["fremder"]),
        # Pruefmittel/Fahrzeug ohne Kunde bleiben sichtbar
        "fahrzeug": await make_anlage(mandant=s["mandant"], objekttyp="fahrzeug", bezeichnung="Transporter"),
    }
    ids = {}
    for name, anlage in anlagen.items():
        resp = await client.post(
            "/api/pruefzyklen",
            headers=s["admin"],
            json={"anlage_id": str(anlage.id), "bezeichnung": name, "intervall_wert": 12, "intervall_einheit": "monat"},
        )
        assert resp.status_code == 201, resp.text
        ids[name] = resp.json()["id"]

    assert {z["id"] for z in (await client.get("/api/pruefzyklen", headers=s["user"])).json()} == {
        ids["eigen"],
        ids["fahrzeug"],
    }
    assert len((await client.get("/api/pruefzyklen", headers=s["admin"])).json()) == 3
    assert (await client.get(f"/api/pruefzyklen/{ids['fahrzeug']}", headers=s["user"])).status_code == 200
    assert (await client.get(f"/api/pruefzyklen/{ids['fremd']}", headers=s["user"])).status_code == 404
    assert (await client.get(f"/api/pruefzyklen/{ids['fremd']}", headers=s["admin"])).status_code == 200
    assert (
        await client.patch(f"/api/pruefzyklen/{ids['fremd']}", headers=s["user"], json={"bezeichnung": "x"})
    ).status_code == 404
    assert (await client.delete(f"/api/pruefzyklen/{ids['fremd']}", headers=s["user"])).status_code == 404
    assert (
        await client.post(
            "/api/pruefzyklen",
            headers=s["user"],
            json={"anlage_id": str(anlagen["fremd"].id), "bezeichnung": "x", "intervall_wert": 1},
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_aufgaben_ansicht_blendet_fremde_kunden_aus(client, szenario):
    s = szenario
    user_id = str(s["eingeschraenkt"].id)
    for titel, extra in (
        ("Aufgabe eigen", {"vorgang_id": str(s["vorgang_eigen"].id)}),
        ("Aufgabe fremd", {"vorgang_id": str(s["vorgang_fremd"].id)}),
        ("Aufgabe fremder Kunde", {"kunde_id": str(s["fremder"].id)}),
        ("Aufgabe ohne Bezug", {}),
    ):
        resp = await client.post(
            "/api/projekt-aufgaben", headers=s["admin"], json={"titel": titel, "zugewiesen_an": user_id, **extra}
        )
        assert resp.status_code == 201, resp.text

    user = await client.get("/api/projekt-aufgaben", headers=s["user"], params={"mir_zugewiesen": "true"})
    assert {a["titel"] for a in user.json()} == {"Aufgabe eigen", "Aufgabe ohne Bezug"}
    admin = await client.get("/api/projekt-aufgaben", headers=s["admin"], params={"mir_zugewiesen": "true"})
    # Admin hat sie angelegt (erstellt_von) und sieht daher alle vier
    assert len(admin.json()) == 4
    # Vorgang-Ansicht: fremder Vorgang liefert keine Aufgaben
    fremd = await client.get(
        "/api/projekt-aufgaben", headers=s["user"], params={"vorgang_id": str(s["vorgang_fremd"].id)}
    )
    assert fremd.json() == []


@pytest.mark.asyncio
async def test_statistik_nur_erlaubte_kunden(client, szenario):
    s = szenario
    admin = (await client.get("/api/statistik/vorgang-kennzahlen", headers=s["admin"])).json()
    user = (await client.get("/api/statistik/vorgang-kennzahlen", headers=s["user"])).json()
    assert admin["offene_vorgaenge_gesamt"] == 2
    assert user["offene_vorgaenge_gesamt"] == 1


@pytest.mark.asyncio
async def test_zeitplan_read_ohne_fremden_vorgang(client, szenario):
    from app.models.termin import Termin

    s = szenario
    async with system_session() as session:
        admin_user = (
            await session.execute(select(User).where(User.mandant_id == s["mandant"].id, User.role == "mandant_admin"))
        ).scalars().one()
        for v in (s["vorgang_eigen"], s["vorgang_fremd"]):
            session.add(
                Termin(
                    mandant_id=s["mandant"].id,
                    vorgang_id=v.id,
                    techniker_id=admin_user.id,
                    erstellt_von=admin_user.id,
                    titel="Termin",
                    start_at=datetime.now(timezone.utc),
                    ende_at=datetime.now(timezone.utc) + timedelta(hours=1),
                )
            )
    pid = (await client.post("/api/projekte", headers=s["admin"], json={"name": "Neubau"})).json()["id"]
    for titel, v in (("Eigen", s["vorgang_eigen"]), ("Fremd", s["vorgang_fremd"])):
        resp = await client.post(
            f"/api/projekte/{pid}/zeitplan/elemente",
            headers=s["admin"],
            json={"typ": "schritt", "titel": titel, "start_am": "2026-06-01", "vorgang_id": str(v.id)},
        )
        assert resp.status_code == 200, resp.text

    def _el(zp, titel):
        return next(e for e in zp["elemente"] if e["titel"] == titel)

    admin_zp = (await client.get(f"/api/projekte/{pid}/zeitplan", headers=s["admin"])).json()
    assert _el(admin_zp, "Fremd")["vorgang"] is not None and len(_el(admin_zp, "Fremd")["termine"]) == 1

    user_resp = await client.get(f"/api/projekte/{pid}/zeitplan", headers=s["user"])
    assert user_resp.status_code == 200, user_resp.text
    user_zp = user_resp.json()
    assert _el(user_zp, "Eigen")["vorgang"] is not None and len(_el(user_zp, "Eigen")["termine"]) == 1
    fremd = _el(user_zp, "Fremd")
    # Element selbst bleibt sichtbar, Vorgang/Termine nicht
    assert fremd["vorgang"] is None and fremd["termine"] == []


# --- Kleinkram ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_kundenportal_standorte_ohne_interne_felder(client, make_mandant, make_kunde):
    from tests.test_kundenportal import _kunden_login, _make_zugang

    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    await _make_zugang(mandant, kunde, email="standort@example.de")
    tokens = await _kunden_login(client, "standort@example.de", "kunden-pw-123")
    headers = auth_headers(tokens["access_token"])

    erlaubt = {"id", "bezeichnung", "adresse", "aktiv", "created_at"}
    neu = await client.post("/api/kundenportal/standorte", headers=headers, json={"bezeichnung": "Filiale"})
    assert neu.status_code == 201, neu.text
    assert set(neu.json()) == erlaubt
    liste = await client.get("/api/kundenportal/standorte", headers=headers)
    assert [set(e) for e in liste.json()] == [erlaubt]


@pytest.mark.asyncio
async def test_zuweisung_anonymisierter_oder_deaktivierter_nutzer_400(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    h = auth_headers(await login(client, admin.email, "pw-123456"))
    kunde = await make_kunde(mandant=mandant)
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    anonym = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    deaktiviert = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    aktiv = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    async with system_session() as session:
        u = await session.get(User, anonym.id)
        u.aktiv = False
        u.email = f"geloescht-{uuid.uuid4()}@invalid.fieldvibe"
        (await session.get(User, deaktiviert.id)).aktiv = False

    for user in (anonym, deaktiviert):
        r = await client.put(f"/api/kunden/{kunde.id}/techniker", headers=h, json={"user_ids": [str(user.id)]})
        assert r.status_code == 400, r.text
        r = await client.put(
            f"/api/fahrzeug-zuweisungen/{user.id}", headers=h, json={"anlage_id": str(fahrzeug.id)}
        )
        assert r.status_code == 400, r.text

    ok = await client.put(f"/api/kunden/{kunde.id}/techniker", headers=h, json={"user_ids": [str(aktiv.id)]})
    assert ok.status_code == 200, ok.text
    ok = await client.put(f"/api/fahrzeug-zuweisungen/{aktiv.id}", headers=h, json={"anlage_id": str(fahrzeug.id)})
    assert ok.status_code == 200, ok.text

    # Vorgang-Zuweisung (PATCH)
    vorgang = await client.post(
        "/api/vorgaenge",
        headers=h,
        json={"kunde_id": str(kunde.id), "titel": "V", "abrechnungsart": "aufwand", "leistungstyp": "stoerung"},
    )
    assert vorgang.status_code == 201, vorgang.text
    r = await client.patch(
        f"/api/vorgaenge/{vorgang.json()['id']}", headers=h, json={"zugewiesener_user_id": str(deaktiviert.id)}
    )
    assert r.status_code == 400, r.text
