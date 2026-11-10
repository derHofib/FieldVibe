"""Scopes in Datenabfragen (zuweisung_service: erlaubte_kunde_ids/erlaubte_user_ids,
vorgang_scope_filter) -- Vorgaenge, Kunden, Termine, Projektaufgaben, Schreibzugriffe."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.core.security import hash_password
from app.db.session import system_session
from app.models.account_typ import AccountTyp, AccountTypRecht
from app.models.kunde_zuweisung import KundeZuweisung
from app.models.organigramm import OrgEinheit, Position, PositionBesetzung, PositionRecht
from app.models.projekt import Projekt, ProjektAufgabe
from app.models.termin import Termin
from app.models.user import User
from app.services import zuweisung_service as zs
from tests.conftest import auth_headers, login

PW = "pw-123456"
BEREICHE = ("vorgaenge", "kunden", "dispo", "projekte")
AKTIONEN = ("sehen", "bearbeiten", "loeschen")


async def _typ(session, mandant, name, scope):
    typ = AccountTyp(mandant_id=mandant.id, name=name)
    session.add(typ)
    await session.flush()
    for bereich in BEREICHE + ("mitarbeiterverwaltung",):
        for aktion in AKTIONEN:
            session.add(
                AccountTypRecht(
                    mandant_id=mandant.id,
                    account_typ_id=typ.id,
                    bereich=bereich,
                    aktion=aktion,
                    erlaubt=True,
                    scope=scope,
                )
            )
    await session.flush()
    return typ


async def _person(session, mandant, name, scope, *, parent=None, einheit=None, typ="linie"):
    """Position + Nutzer + Besetzung; scope=None -> Typ mit Scope eigene."""
    account_typ = await _typ(session, mandant, f"Typ {name}", scope or "eigene")
    position = Position(
        mandant_id=mandant.id,
        titel=name,
        parent_id=parent.id if parent else None,
        org_einheit_id=einheit.id if einheit else None,
        account_typ_id=account_typ.id,
        typ=typ,
    )
    session.add(position)
    user = User(
        mandant_id=mandant.id,
        email=f"{name.lower().replace(' ', '')}-{uuid.uuid4().hex[:6]}@example.de",
        password_hash=hash_password(PW),
        role="custom",
        name=name,
    )
    session.add(user)
    await session.flush()
    session.add(
        PositionBesetzung(
            mandant_id=mandant.id,
            position_id=position.id,
            user_id=user.id,
            gueltig_von=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )
    await session.flush()
    return position, user


@pytest.fixture
async def org(make_mandant, make_kunde, make_vorgang, client):
    mandant = await make_mandant()
    daten: dict = {"mandant": mandant}
    async with system_session() as session:
        service = OrgEinheit(mandant_id=mandant.id, name="Service", typ="bereich")
        session.add(service)
        await session.flush()
        team_a = OrgEinheit(mandant_id=mandant.id, name="Team A", typ="team", parent_id=service.id)
        team_b = OrgEinheit(mandant_id=mandant.id, name="Team B", typ="team", parent_id=service.id)
        session.add_all([team_a, team_b])
        await session.flush()

        gf_pos, gf = await _person(session, mandant, "GF", "mandant")
        bl_pos, bl = await _person(session, mandant, "Bereichsleiter", "bereich", parent=gf_pos, einheit=service)
        tla_pos, tla = await _person(session, mandant, "Teamleiter A", "teilbaum", parent=bl_pos, einheit=team_a)
        tlb_pos, tlb = await _person(session, mandant, "Teamleiter B", "teilbaum", parent=bl_pos, einheit=team_b)
        a1_pos, a1 = await _person(session, mandant, "Techniker A1", "eigene", parent=tla_pos, einheit=team_a)
        a2_pos, a2 = await _person(session, mandant, "Techniker A2", "eigene", parent=tla_pos, einheit=team_a)
        b1_pos, b1 = await _person(session, mandant, "Techniker B1", "eigene", parent=tlb_pos, einheit=team_b)
        # Teamkollege A: Scope team (Positionen derselben Einheit Team A)
        tk_pos, tk = await _person(session, mandant, "Teamkraft A", "team", parent=tla_pos, einheit=team_a)
        # Stabsstelle QM an der GF: Typ eigene, per Override mandantweit bzw. teilbaum.
        qm_pos, qm = await _person(session, mandant, "QM", "eigene", parent=gf_pos, typ="stabsstelle")
        qm2_pos, qm2 = await _person(session, mandant, "QM Teilbaum", "teilbaum", parent=gf_pos, typ="stabsstelle")
        for bereich in BEREICHE:
            for aktion in AKTIONEN:
                session.add(
                    PositionRecht(
                        mandant_id=mandant.id,
                        position_id=qm_pos.id,
                        bereich=bereich,
                        aktion=aktion,
                        wirkung="erlauben",
                        scope="mandant",
                    )
                )
        daten["nutzer"] = {
            "gf": gf, "bl": bl, "tla": tla, "tlb": tlb, "a1": a1, "a2": a2, "b1": b1,
            "tk": tk, "qm": qm, "qm2": qm2,
        }
        mandant_id = mandant.id
        user_ids = {k: u.id for k, u in daten["nutzer"].items()}

    daten["kunden"], daten["vorgaenge"], daten["termine"], daten["aufgaben"] = {}, {}, {}, {}
    daten["ids"] = user_ids
    async with system_session() as session:
        projekt = Projekt(mandant_id=mandant_id, name="Projekt", erstellt_von=user_ids["gf"])
        session.add(projekt)
        await session.flush()
        daten["projekt_id"] = projekt.id
    for key in ("a1", "a2", "b1"):
        kunde = await make_kunde(mandant=mandant, name=f"Kunde {key}")
        vorgang = await make_vorgang(
            mandant=mandant, kunde=kunde, titel=f"Vorgang {key}", zugewiesener_user_id=user_ids[key]
        )
        async with system_session() as session:
            session.add(KundeZuweisung(mandant_id=mandant_id, kunde_id=kunde.id, user_id=user_ids[key]))
            termin = Termin(
                mandant_id=mandant_id,
                vorgang_id=vorgang.id,
                techniker_id=user_ids[key],
                erstellt_von=user_ids["gf"],
                titel=f"Termin {key}",
                start_at=datetime.now(timezone.utc),
                ende_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
            aufgabe = ProjektAufgabe(
                mandant_id=mandant_id,
                projekt_id=projekt.id,
                titel=f"Aufgabe {key}",
                zugewiesen_an=user_ids[key],
                erstellt_von=user_ids["gf"],
            )
            session.add_all([termin, aufgabe])
            await session.flush()
            daten["termine"][key] = termin.id
            daten["aufgaben"][key] = aufgabe.id
        daten["kunden"][key] = kunde.id
        daten["vorgaenge"][key] = vorgang.id
    daten["headers"] = {}
    for key, user in daten["nutzer"].items():
        token = await login(client, user.email, PW)
        daten["headers"][key] = auth_headers(token)
    return daten


async def _titel(client: AsyncClient, org, key: str, pfad: str, feld: str, **params) -> set[str]:
    resp = await client.get(pfad, headers=org["headers"][key], params=params)
    assert resp.status_code == 200, resp.text
    daten = resp.json()
    if isinstance(daten, dict):
        daten = daten.get("items", daten.get("eintraege", []))
    return {e[feld] for e in daten}


def _namen(*keys):
    return {f"Vorgang {k}" for k in keys}


async def test_vorgaenge_liste_je_scope(client, org):
    liste = lambda key: _titel(client, org, key, "/api/vorgaenge", "titel")  # noqa: E731
    assert await liste("a1") == _namen("a1")  # eigene
    assert await liste("tla") == _namen("a1", "a2")  # teilbaum
    assert await liste("tk") == _namen("a1", "a2")  # team (Einheit Team A)
    assert await liste("bl") == _namen("a1", "a2", "b1")  # bereich
    assert await liste("gf") == _namen("a1", "a2", "b1")  # mandant
    assert await liste("qm") == _namen("a1", "a2", "b1")  # mandant-Override
    assert await liste("qm2") == set()  # Stabsstelle: Teilbaum ohne Linie


async def test_vorgaenge_zugewiesen_ohne_kundenzuweisung_sichtbar(client, org, make_kunde, make_vorgang):
    kunde = await make_kunde(mandant=org["mandant"], name="Ohne Zuweisung")
    await make_vorgang(
        mandant=org["mandant"], kunde=kunde, titel="Direkt an A1", zugewiesener_user_id=org["ids"]["a1"]
    )
    assert "Direkt an A1" in await _titel(client, org, "a1", "/api/vorgaenge", "titel")
    assert "Direkt an A1" in await _titel(client, org, "tla", "/api/vorgaenge", "titel")
    assert "Direkt an A1" not in await _titel(client, org, "b1", "/api/vorgaenge", "titel")


async def test_vorgang_detail_und_bearbeiten_ausserhalb_404(client, org):
    fremd = org["vorgaenge"]["b1"]
    eigen = org["vorgaenge"]["a1"]
    h = org["headers"]
    assert (await client.get(f"/api/vorgaenge/{fremd}", headers=h["a1"])).status_code == 404
    assert (await client.get(f"/api/vorgaenge/{eigen}", headers=h["a1"])).status_code == 200
    assert (await client.get(f"/api/vorgaenge/{fremd}", headers=h["tla"])).status_code == 404
    assert (await client.get(f"/api/vorgaenge/{org['vorgaenge']['a2']}", headers=h["tla"])).status_code == 200
    antwort = await client.patch(f"/api/vorgaenge/{fremd}", headers=h["tla"], json={"titel": "x"})
    assert antwort.status_code == 404
    antwort = await client.patch(f"/api/vorgaenge/{org['vorgaenge']['a2']}", headers=h["tla"], json={"titel": "ok"})
    assert antwort.status_code == 200, antwort.text
    assert (await client.patch(f"/api/vorgaenge/{fremd}", headers=h["qm"], json={"titel": "qm"})).status_code == 200
    assert (await client.get(f"/api/vorgaenge/{fremd}", headers=h["qm2"])).status_code == 404
    assert (await client.delete(f"/api/vorgaenge/{fremd}", headers=h["tla"])).status_code == 404


async def test_feed_und_suche(client, org):
    for key, erwartet in (("a1", {"a1"}), ("tla", {"a1", "a2"}), ("bl", {"a1", "a2", "b1"}), ("qm2", set())):
        resp = await client.get("/api/feed", headers=org["headers"][key])
        assert resp.status_code == 200, resp.text
        titel = {e["titel"] for e in resp.json()["items"]} if isinstance(resp.json(), dict) else set()
        assert titel == _namen(*erwartet), key
    resp = await client.get("/api/search", params={"q": "Vorgang"}, headers=org["headers"]["tla"])
    assert resp.status_code == 200
    treffer = {t["titel"] for t in resp.json()["treffer"] if t["kategorie"] == "vorgang"}
    assert {t.split(": ", 1)[-1] for t in treffer} == {"Vorgang a1", "Vorgang a2"}


async def test_kunden_liste_detail_bearbeiten(client, org):
    h = org["headers"]
    namen = lambda *k: {f"Kunde {x}" for x in k}  # noqa: E731
    assert await _titel(client, org, "a1", "/api/kunden", "name") == namen("a1")
    assert await _titel(client, org, "tla", "/api/kunden", "name") == namen("a1", "a2")
    assert await _titel(client, org, "tk", "/api/kunden", "name") == namen("a1", "a2")
    assert await _titel(client, org, "bl", "/api/kunden", "name") == namen("a1", "a2", "b1")
    assert await _titel(client, org, "qm", "/api/kunden", "name") == namen("a1", "a2", "b1")
    assert await _titel(client, org, "qm2", "/api/kunden", "name") == set()
    fremd = org["kunden"]["b1"]
    assert (await client.get(f"/api/kunden/{fremd}", headers=h["tla"])).status_code == 404
    assert (await client.get(f"/api/kunden/{org['kunden']['a2']}", headers=h["tla"])).status_code == 200
    assert (await client.patch(f"/api/kunden/{fremd}", headers=h["tla"], json={"name": "x"})).status_code == 404
    assert (await client.patch(f"/api/kunden/{fremd}", headers=h["qm"], json={"name": "Kunde b1"})).status_code == 200
    assert (await client.delete(f"/api/kunden/{fremd}", headers=h["tla"])).status_code == 404


async def test_termine_liste_detail_bearbeiten(client, org):
    h = org["headers"]
    assert await _titel(client, org, "a1", "/api/termine", "titel") == {"Termin a1"}
    assert await _titel(client, org, "tla", "/api/termine", "titel") == {"Termin a1", "Termin a2"}
    assert await _titel(client, org, "tk", "/api/termine", "titel") == {"Termin a1", "Termin a2"}
    assert await _titel(client, org, "bl", "/api/termine", "titel") == {"Termin a1", "Termin a2", "Termin b1"}
    assert await _titel(client, org, "qm", "/api/termine", "titel") == {"Termin a1", "Termin a2", "Termin b1"}
    assert await _titel(client, org, "qm2", "/api/termine", "titel") == set()
    fremd = org["termine"]["b1"]
    assert (await client.get(f"/api/termine/{fremd}", headers=h["tla"])).status_code == 404
    assert (await client.get(f"/api/termine/{org['termine']['a1']}", headers=h["tla"])).status_code == 200
    assert (await client.patch(f"/api/termine/{fremd}", headers=h["tla"], json={"titel": "x"})).status_code == 404
    assert (await client.delete(f"/api/termine/{fremd}", headers=h["tla"])).status_code == 404
    assert (await client.patch(f"/api/termine/{fremd}", headers=h["qm"], json={"titel": "qm"})).status_code == 200


async def test_projektaufgaben_liste_detail_bearbeiten(client, org):
    h = org["headers"]
    pfad = "/api/projekt-aufgaben"
    p = {"projekt_id": str(org["projekt_id"])}
    aufg = lambda *k: {f"Aufgabe {x}" for x in k}  # noqa: E731
    assert await _titel(client, org, "a1", pfad, "titel", **p) == aufg("a1")
    assert await _titel(client, org, "tla", pfad, "titel", **p) == aufg("a1", "a2")
    assert await _titel(client, org, "bl", pfad, "titel", **p) == aufg("a1", "a2", "b1")
    assert await _titel(client, org, "qm", pfad, "titel", **p) == aufg("a1", "a2", "b1")
    assert await _titel(client, org, "qm2", pfad, "titel", **p) == set()
    fremd = org["aufgaben"]["b1"]
    assert (await client.get(f"{pfad}/{fremd}", headers=h["tla"])).status_code == 404
    assert (await client.get(f"{pfad}/{org['aufgaben']['a2']}", headers=h["tla"])).status_code == 200
    assert (await client.patch(f"{pfad}/{fremd}", headers=h["tla"], json={"titel": "x"})).status_code == 404
    assert (await client.delete(f"{pfad}/{fremd}", headers=h["tla"])).status_code == 404


async def test_erlaubte_ids_und_cache(org):
    def auth(key):
        return SimpleNamespace(user_id=org["ids"][key], role="custom", account_typ_id=None)

    ids = org["ids"]
    async with system_session() as session:
        assert await zs.erlaubte_user_ids(session, auth("a1"), "vorgaenge") == {ids["a1"]}
        got = await zs.erlaubte_user_ids(session, auth("tla"), "vorgaenge")
        assert got >= {ids["a1"], ids["a2"]}
        assert ids["b1"] not in await zs.erlaubte_user_ids(session, auth("tla"), "vorgaenge")
        assert await zs.erlaubte_user_ids(session, auth("gf"), "vorgaenge") is None
        assert await zs.erlaubte_kunde_ids(session, auth("gf")) is None
        assert await zs.erlaubte_kunde_ids(session, auth("a1")) == {org["kunden"]["a1"]}
        # Eigene == bisheriges Verhalten (assigned_kunde_ids)
        assert await zs.erlaubte_kunde_ids(session, auth("a1")) == await zs.assigned_kunde_ids(session, ids["a1"])
        assert await zs.erlaubte_kunde_ids(session, auth("tla")) == {org["kunden"]["a1"], org["kunden"]["a2"]}
        # Mitarbeiterdaten (Hilfsfunktion fuer die Zeiterfassung)
        assert await zs.darf_mitarbeiterdaten_einsehen(session, auth("tla"), ids["a2"])
        assert not await zs.darf_mitarbeiterdaten_einsehen(session, auth("tla"), ids["b1"])
        assert await zs.darf_mitarbeiterdaten_einsehen(session, auth("a1"), ids["a1"])
        assert not await zs.darf_mitarbeiterdaten_einsehen(session, auth("a1"), ids["a2"])
        assert await zs.darf_mitarbeiterdaten_einsehen(session, auth("gf"), ids["b1"])
