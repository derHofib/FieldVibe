"""Meine Aufgaben: Auftragsbezug, Pfad-Ableitung, Erledigt-Filter (Konzept meine-aufgaben, Etappe B/C)."""
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.db.session import system_session
from app.models.auftrag import Auftrag
from app.models.projekt import Projekt, ProjektAufgabe
from tests.conftest import auth_headers, login

PW = "pw-123456"


async def _admin(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW)
    token = await login(client, admin.email, PW)
    return mandant, admin, auth_headers(token)


async def _projekt(mandant, admin, name="Projekt A") -> Projekt:
    async with system_session(grund="test") as session:
        p = Projekt(mandant_id=mandant.id, name=name, erstellt_von=admin.id)
        session.add(p)
        await session.flush()
        await session.refresh(p)
        return p


async def _auftrag(mandant, admin, *, projekt=None, titel="Auftrag 1") -> Auftrag:
    async with system_session(grund="test") as session:
        a = Auftrag(
            mandant_id=mandant.id, titel=titel, erstellt_von=admin.id, projekt_id=projekt.id if projekt else None
        )
        session.add(a)
        await session.flush()
        await session.refresh(a)
        return a


async def _liste(client, headers, **params):
    resp = await client.get("/api/projekt-aufgaben", headers=headers, params={"mir_zugewiesen": True, **params})
    assert resp.status_code == 200, resp.text
    return {a["titel"]: a for a in resp.json()}


@pytest.mark.asyncio
async def test_pfad_privat_mit_vorgang_auftrag_projekt(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    projekt = await _projekt(mandant, admin)
    auftrag = await _auftrag(mandant, admin, projekt=projekt)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, titel="Vorgangstitel", auftrag_id=auftrag.id)
    resp = await client.post(
        "/api/projekt-aufgaben", headers=h, json={"titel": "Privat-V", "vorgang_id": str(vorgang.id)}
    )
    assert resp.status_code == 201, resp.text

    a = (await _liste(client, h))["Privat-V"]
    assert a["vorgang_titel"] == "Vorgangstitel"
    assert a["vorgang_status"] == vorgang.status
    assert a["pfad_auftrag_id"] == str(auftrag.id)
    assert a["auftrag_titel"] == "Auftrag 1"
    assert a["pfad_projekt_id"] == str(projekt.id)
    assert a["pfad_projekt_name"] == "Projekt A"
    assert a["projekt_name"] is None
    assert a["pfad_abweichung_projekt_name"] is None


@pytest.mark.asyncio
async def test_pfad_privat_mit_direktem_auftrag(client, make_mandant, make_user):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    projekt = await _projekt(mandant, admin)
    auftrag = await _auftrag(mandant, admin, projekt=projekt)
    resp = await client.post(
        "/api/projekt-aufgaben", headers=h, json={"titel": "Privat-A", "auftrag_id": str(auftrag.id)}
    )
    assert resp.status_code == 201
    assert resp.json()["auftrag_id"] == str(auftrag.id)

    a = (await _liste(client, h))["Privat-A"]
    assert a["pfad_auftrag_id"] == str(auftrag.id)
    assert a["auftrag_status"] == auftrag.status
    assert a["pfad_projekt_name"] == "Projekt A"
    assert a["vorgang_titel"] is None


@pytest.mark.asyncio
async def test_pfad_abweichung_bei_karte_mit_vorgang_anderen_projekts(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    karten_projekt = await _projekt(mandant, admin, "Karten-Projekt")
    anderes = await _projekt(mandant, admin, "Anderes Projekt")
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, projekt_id=anderes.id)
    spalten = (await client.get(f"/api/projekte/{karten_projekt.id}/spalten", headers=h)).json()
    # Projekt wurde ohne API angelegt -> Spalte selbst anlegen.
    if not spalten:
        r = await client.post(
            f"/api/projekte/{karten_projekt.id}/spalten", headers=h, json={"name": "Offen", "reihenfolge": 0}
        )
        assert r.status_code == 201, r.text
        spalten = [r.json()]
    resp = await client.post(
        "/api/projekt-aufgaben",
        headers=h,
        json={
            "titel": "Karte",
            "projekt_id": str(karten_projekt.id),
            "spalte_id": spalten[0]["id"],
            "vorgang_id": str(vorgang.id),
            "zugewiesen_an": str(admin.id),
        },
    )
    assert resp.status_code == 201, resp.text

    a = (await _liste(client, h))["Karte"]
    assert a["projekt_name"] == "Karten-Projekt"
    assert a["spalte_name"] == spalten[0]["name"]
    assert a["pfad_projekt_id"] == str(karten_projekt.id)
    assert a["pfad_projekt_name"] == "Karten-Projekt"
    assert a["pfad_abweichung_projekt_name"] == "Anderes Projekt"


@pytest.mark.asyncio
async def test_auftrag_und_vorgang_zusammen_ist_422(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    auftrag = await _auftrag(mandant, admin)
    resp = await client.post(
        "/api/projekt-aufgaben",
        headers=h,
        json={"titel": "X", "vorgang_id": str(vorgang.id), "auftrag_id": str(auftrag.id)},
    )
    assert resp.status_code == 422

    ok = await client.post("/api/projekt-aufgaben", headers=h, json={"titel": "Y"})
    resp = await client.patch(
        f"/api/projekt-aufgaben/{ok.json()['id']}",
        headers=h,
        json={"vorgang_id": str(vorgang.id), "auftrag_id": str(auftrag.id)},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_vorgang_setzen_leert_auftrag_und_auftrag_bei_vorgang_ist_422(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    auftrag = await _auftrag(mandant, admin)
    erstellt = await client.post(
        "/api/projekt-aufgaben", headers=h, json={"titel": "Z", "auftrag_id": str(auftrag.id)}
    )
    aid = erstellt.json()["id"]

    resp = await client.patch(f"/api/projekt-aufgaben/{aid}", headers=h, json={"vorgang_id": str(vorgang.id)})
    assert resp.status_code == 200, resp.text
    assert resp.json()["auftrag_id"] is None
    assert resp.json()["vorgang_id"] == str(vorgang.id)

    resp = await client.patch(f"/api/projekt-aufgaben/{aid}", headers=h, json={"auftrag_id": str(auftrag.id)})
    assert resp.status_code == 422
    assert "Vorgang" in resp.json()["detail"]

    # Vorgang explizit loesen und Auftrag setzen ist erlaubt.
    resp = await client.patch(
        f"/api/projekt-aufgaben/{aid}", headers=h, json={"vorgang_id": None, "auftrag_id": str(auftrag.id)}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["auftrag_id"] == str(auftrag.id)
    assert resp.json()["vorgang_id"] is None


@pytest.mark.asyncio
async def test_auftrag_fremder_mandant_abgelehnt(client, make_mandant, make_user):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    fremd = await make_mandant()
    fremder_admin = await make_user(mandant=fremd, role="mandant_admin", password=PW)
    fremder_auftrag = await _auftrag(fremd, fremder_admin)
    resp = await client.post(
        "/api/projekt-aufgaben", headers=h, json={"titel": "X", "auftrag_id": str(fremder_auftrag.id)}
    )
    assert resp.status_code == 400
    assert "Auftrag" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_erledigt_und_erledigt_seit_filter(client, make_mandant, make_user):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    ids = {}
    for titel in ("offen", "neu-erledigt", "alt-erledigt"):
        r = await client.post("/api/projekt-aufgaben", headers=h, json={"titel": titel})
        ids[titel] = r.json()["id"]
    for titel in ("neu-erledigt", "alt-erledigt"):
        r = await client.patch(f"/api/projekt-aufgaben/{ids[titel]}", headers=h, json={"erledigt": True})
        assert r.status_code == 200
    async with system_session(grund="test") as session:
        aufgabe = await session.get(ProjektAufgabe, uuid.UUID(ids["alt-erledigt"]))
        aufgabe.erledigt_am = datetime.now(UTC) - timedelta(days=30)

    assert set(await _liste(client, h)) == {"offen", "neu-erledigt", "alt-erledigt"}
    assert set(await _liste(client, h, erledigt="offen")) == {"offen"}
    assert set(await _liste(client, h, erledigt="erledigt")) == {"neu-erledigt", "alt-erledigt"}
    seit = (datetime.now(UTC) - timedelta(days=7)).date().isoformat()
    assert set(await _liste(client, h, erledigt_seit=seit)) == {"offen", "neu-erledigt"}
    assert set(await _liste(client, h, erledigt="erledigt", erledigt_seit=seit)) == {"neu-erledigt"}


@pytest.mark.asyncio
async def test_auftrag_id_filter_direkt_und_ueber_vorgang(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    auftrag = await _auftrag(mandant, admin)
    anderer = await _auftrag(mandant, admin, titel="Anderer")
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, auftrag_id=auftrag.id)
    for body in (
        {"titel": "direkt", "auftrag_id": str(auftrag.id)},
        {"titel": "via-vorgang", "vorgang_id": str(vorgang.id)},
        {"titel": "anderer", "auftrag_id": str(anderer.id)},
        {"titel": "ohne"},
    ):
        assert (await client.post("/api/projekt-aufgaben", headers=h, json=body)).status_code == 201
    resp = await client.get("/api/projekt-aufgaben", headers=h, params={"auftrag_id": str(auftrag.id)})
    assert resp.status_code == 200
    assert {a["titel"] for a in resp.json()} == {"direkt", "via-vorgang"}


@pytest.mark.asyncio
async def test_gespeicherter_filter_entitaet_aufgaben(client, make_mandant, make_user):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    resp = await client.post(
        "/api/gespeicherte-filter",
        headers=h,
        json={"entitaet": "aufgaben", "name": "Offene", "filter_json": {"erledigt": "offen"}},
    )
    assert resp.status_code == 201, resp.text
    liste = await client.get("/api/gespeicherte-filter?entitaet=aufgaben", headers=h)
    assert [f["name"] for f in liste.json()] == ["Offene"]


@pytest.mark.asyncio
async def test_einzelabruf_post_patch_liefern_details(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    projekt = await _projekt(mandant, admin)
    auftrag = await _auftrag(mandant, admin, projekt=projekt)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, titel="Vorgangstitel", auftrag_id=auftrag.id)
    erstellt = await client.post("/api/projekt-aufgaben", headers=h, json={"titel": "E", "vorgang_id": str(vorgang.id)})
    assert erstellt.status_code == 201
    assert erstellt.json()["pfad_projekt_name"] == "Projekt A"
    aid = erstellt.json()["id"]

    einzeln = await client.get(f"/api/projekt-aufgaben/{aid}", headers=h)
    assert einzeln.status_code == 200
    assert einzeln.json()["vorgang_titel"] == "Vorgangstitel"
    assert einzeln.json()["pfad_auftrag_id"] == str(auftrag.id)
    assert einzeln.json()["auftrag_titel"] == "Auftrag 1"

    patch = await client.patch(f"/api/projekt-aufgaben/{aid}", headers=h, json={"titel": "E2"})
    assert patch.status_code == 200
    assert patch.json()["titel"] == "E2"
    assert patch.json()["pfad_projekt_id"] == str(projekt.id)
