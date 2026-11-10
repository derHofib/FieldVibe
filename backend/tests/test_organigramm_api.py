"""Organigramm-API (routes/organigramm.py): Lesen/Scope/DSGVO, Zyklen, Archiv/Loeschen,
Platzhalter-Ablauf, Audit, RLS."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import system_session
from app.models.account_typ import AccountTyp, AccountTypRecht
from app.models.audit_log import AuditLog
from app.models.organigramm import Position, PositionBesetzung
from app.models.user import User
from tests.conftest import auth_headers, login

PW = "pw-123456"
GESCHUETZT = "/api/fehlerberichte"  # require_recht("fehlerberichte", "sehen"); Techniker-Typ hat es nicht


async def kopf(client, user) -> dict:
    return auth_headers(await login(client, user.email, PW))


async def wurzel_id(client, k) -> str:
    liste = (await client.get("/api/organigramm/positionen", headers=k)).json()
    return next(p["id"] for p in liste if p["parent_id"] is None)


async def neue_position(client, k, parent_id, titel, **felder) -> dict:
    antwort = await client.post(
        "/api/organigramm/positionen", headers=k, json={"parent_id": parent_id, "titel": titel, **felder}
    )
    assert antwort.status_code == 201, antwort.text
    return antwort.json()


async def admin_mit_kopf(client, make_mandant, make_user, name="Admin"):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW, name=name)
    return mandant, admin, await kopf(client, admin)


async def audit(aktion: str) -> list[AuditLog]:
    async with system_session() as session:
        return list((await session.execute(select(AuditLog).where(AuditLog.aktion == aktion))).scalars())


async def typ_mit_rechten(mandant, name, rechte) -> uuid.UUID:
    """rechte: (bereich, aktion, scope)"""
    async with system_session() as session:
        typ = AccountTyp(mandant_id=mandant.id, name=name)
        session.add(typ)
        await session.flush()
        for bereich, aktion, scope in rechte:
            session.add(
                AccountTypRecht(
                    mandant_id=mandant.id, account_typ_id=typ.id, bereich=bereich, aktion=aktion, erlaubt=True, scope=scope
                )
            )
        return typ.id


async def custom_user(mandant, name) -> User:
    async with system_session() as session:
        user = User(
            mandant_id=mandant.id,
            email=f"{name.lower().replace(' ', '')}-{uuid.uuid4().hex[:6]}@example.de",
            password_hash=hash_password(PW),
            role="custom",
            name=name,
        )
        session.add(user)
        await session.flush()
        return user


async def besetzen(mandant, position_id, user) -> None:
    async with system_session() as session:
        session.add(
            PositionBesetzung(
                mandant_id=mandant.id,
                position_id=uuid.UUID(str(position_id)),
                user_id=user.id,
                gueltig_von=datetime.now(timezone.utc) - timedelta(days=1),
            )
        )


# --- RLS / Mandantentrennung ---------------------------------------------------------


async def test_mandant_b_sieht_und_aendert_nichts_von_a(client, make_mandant, make_user):
    _, _, ka = await admin_mit_kopf(client, make_mandant, make_user, "A")
    _, _, kb = await admin_mit_kopf(client, make_mandant, make_user, "B")
    wa = await wurzel_id(client, ka)
    pos = await neue_position(client, ka, wa, "Nur A")
    benutzer_a = await custom_user(await _mandant_von(pos["id"]), "UserA")

    assert (await client.get(f"/api/organigramm/positionen/{pos['id']}", headers=kb)).status_code == 404
    assert (await client.patch(f"/api/organigramm/positionen/{pos['id']}", headers=kb, json={"titel": "x"})).status_code == 404
    assert (await client.delete(f"/api/organigramm/positionen/{pos['id']}", headers=kb)).status_code == 404
    assert (await client.post(f"/api/organigramm/positionen/{pos['id']}/archivieren", headers=kb)).status_code == 404
    assert (await client.put(f"/api/organigramm/positionen/{pos['id']}/rechte", headers=kb, json=[])).status_code == 404
    assert (
        await client.post(
            f"/api/organigramm/positionen/{pos['id']}/besetzungen", headers=kb, json={"user_id": str(benutzer_a.id)}
        )
    ).status_code == 404
    assert (await client.put(f"/api/organigramm/users/{benutzer_a.id}/rechte", headers=kb, json=[])).status_code == 404
    assert (await client.get(f"/api/organigramm/effektiv?position_id={pos['id']}", headers=kb)).status_code == 404

    # B legt eine Position unter einer Position von A an -> 404 (kein Fremdbezug)
    r = await client.post("/api/organigramm/positionen", headers=kb, json={"parent_id": pos["id"], "titel": "x"})
    assert r.status_code == 404
    liste_b = (await client.get("/api/organigramm/positionen", headers=kb)).json()
    assert pos["id"] not in {p["id"] for p in liste_b}


async def _mandant_von(position_id):
    async with system_session() as session:
        position = await session.get(Position, uuid.UUID(position_id))
        from app.models.mandant import Mandant

        return await session.get(Mandant, position.mandant_id)


# --- Zyklen / Wurzel -------------------------------------------------------------------


async def test_zyklus_und_wurzel_schutz(client, make_mandant, make_user):
    _, _, k = await admin_mit_kopf(client, make_mandant, make_user)
    wurzel = await wurzel_id(client, k)
    p1 = await neue_position(client, k, wurzel, "P1")
    p2 = await neue_position(client, k, p1["id"], "P2")
    p3 = await neue_position(client, k, p2["id"], "P3")
    url = "/api/organigramm/positionen/"

    assert (await client.patch(url + p1["id"], headers=k, json={"parent_id": p3["id"]})).status_code == 409
    assert (await client.patch(url + p1["id"], headers=k, json={"parent_id": p2["id"]})).status_code == 409
    assert (await client.patch(url + p1["id"], headers=k, json={"parent_id": p1["id"]})).status_code == 409
    # Umhaengen an eine zulaessige Stelle klappt
    r = await client.patch(url + p3["id"], headers=k, json={"parent_id": p1["id"]})
    assert r.status_code == 200 and r.json()["parent_id"] == p1["id"]

    assert (await client.patch(url + wurzel, headers=k, json={"parent_id": p3["id"]})).status_code == 409
    assert (await client.patch(url + wurzel, headers=k, json={"typ": "stabsstelle"})).status_code == 409
    assert (await client.post(url + wurzel + "/archivieren", headers=k)).status_code == 409
    assert (await client.delete(url + wurzel, headers=k)).status_code == 409
    assert (await client.post(url + wurzel + "/duplizieren", headers=k)).status_code == 409
    # Titel der Wurzel bleibt aenderbar
    assert (await client.patch(url + wurzel, headers=k, json={"titel": "Chef"})).status_code == 200


async def test_org_einheiten_crud_und_zyklus(client, make_mandant, make_user):
    _, _, k = await admin_mit_kopf(client, make_mandant, make_user)
    b = (await client.post("/api/organigramm/org-einheiten", headers=k, json={"name": "Service", "typ": "bereich"})).json()
    t = (
        await client.post(
            "/api/organigramm/org-einheiten", headers=k, json={"name": "Team Nord", "typ": "team", "parent_id": b["id"]}
        )
    ).json()
    url = "/api/organigramm/org-einheiten/"
    assert (await client.patch(url + b["id"], headers=k, json={"parent_id": t["id"]})).status_code == 409
    assert (await client.patch(url + b["id"], headers=k, json={"parent_id": b["id"]})).status_code == 409
    assert (await client.post(url + b["id"] + "/archivieren", headers=k)).status_code == 409  # hat Untereinheit
    assert (await client.delete(url + b["id"], headers=k)).status_code == 409

    wurzel = await wurzel_id(client, k)
    pos = await neue_position(client, k, wurzel, "Teamleiter", org_einheit_id=t["id"])
    assert pos["org_einheit"]["name"] == "Team Nord"
    assert (await client.post(url + t["id"] + "/archivieren", headers=k)).status_code == 409  # Position zugeordnet
    assert (await client.delete(url + t["id"], headers=k)).status_code == 409

    await client.delete(f"/api/organigramm/positionen/{pos['id']}", headers=k)
    assert (await client.delete(url + t["id"], headers=k)).status_code == 204
    assert (await client.post(url + b["id"] + "/archivieren", headers=k)).status_code == 200
    assert (await client.get(url[:-1], headers=k)).json() == []
    assert len((await client.get(url[:-1] + "?archivierte=true", headers=k)).json()) == 1
    assert len(await audit("org_einheit_erstellt")) == 2


# --- Archivieren / Loeschen -------------------------------------------------------------


async def test_archivieren_und_loeschen_regeln(client, make_mandant, make_user):
    mandant, admin, k = await admin_mit_kopf(client, make_mandant, make_user)
    wurzel = await wurzel_id(client, k)
    eltern = await neue_position(client, k, wurzel, "Eltern")
    kind = await neue_position(client, k, eltern["id"], "Kind")
    url = "/api/organigramm/positionen/"

    r = await client.post(url + eltern["id"] + "/archivieren", headers=k)
    assert r.status_code == 409 and "Unterposition" in r.json()["detail"]
    assert (await client.delete(url + eltern["id"], headers=k)).status_code == 409

    nutzer = await custom_user(mandant, "Besetzter")
    b = await client.post(url + kind["id"] + "/besetzungen", headers=k, json={"user_id": str(nutzer.id)})
    assert b.status_code == 201, b.text
    r = await client.post(url + kind["id"] + "/archivieren", headers=k)
    assert r.status_code == 409 and "besetzt" in r.json()["detail"]
    assert (await client.delete(url + kind["id"], headers=k)).status_code == 409

    # Besetzung beenden -> archivierbar; Loeschen bleibt wegen Historie verboten
    assert (await client.patch(f"/api/organigramm/besetzungen/{b.json()['besetzung']['id']}", headers=k, json={})).status_code == 200
    assert (await client.delete(url + kind["id"], headers=k)).status_code == 409
    r = await client.post(url + kind["id"] + "/archivieren", headers=k)
    assert r.status_code == 200 and r.json()["archiviert_am"]
    # jetzt hat Eltern kein aktives Kind mehr
    assert (await client.post(url + eltern["id"] + "/archivieren", headers=k)).status_code == 200

    # Nie besetzte Position ohne Kinder ist loeschbar
    leer = await neue_position(client, k, wurzel, "Leer")
    assert (await client.delete(url + leer["id"], headers=k)).status_code == 204
    assert (await client.get(url + leer["id"], headers=k)).status_code == 404

    aktiv = {p["id"] for p in (await client.get("/api/organigramm/positionen", headers=k)).json()}
    assert eltern["id"] not in aktiv
    mit = {p["id"] for p in (await client.get("/api/organigramm/positionen?archivierte=true", headers=k)).json()}
    assert eltern["id"] in mit


# --- Platzhalter-Ablauf (E2E) -------------------------------------------------------------


async def test_platzhalter_ablauf_zuweisen_und_freistellen(client, make_mandant, make_user):
    mandant, admin, k = await admin_mit_kopf(client, make_mandant, make_user)
    techniker = await make_user(mandant=mandant, role="techniker", password=PW, name="Tina Techniker")
    kt = await kopf(client, techniker)
    assert (await client.get(GESCHUETZT, headers=kt)).status_code == 403

    wurzel = await wurzel_id(client, k)
    ph = await neue_position(client, k, wurzel, "Bereichsleiter Service", geplant=True)
    assert ph["status"] == "geplant"
    r = await client.put(
        f"/api/organigramm/positionen/{ph['id']}/rechte",
        headers=k,
        json=[
            {"bereich": "fehlerberichte", "aktion": "sehen", "wirkung": "erlauben"},
            {"bereich": "vorgaenge", "aktion": "sehen", "wirkung": "erlauben", "scope": "teilbaum"},
        ],
    )
    assert r.status_code == 200, r.text

    eff = (await client.get(f"/api/organigramm/effektiv?position_id={ph['id']}", headers=k)).json()
    schluessel = {(e["bereich"], e["aktion"]): e["scope"] for e in eff["rechte"]}
    assert schluessel == {("fehlerberichte", "sehen"): "mandant", ("vorgaenge", "sehen"): "teilbaum"}
    assert all(e["herkunft"][0]["art"] == "position_override" for e in eff["rechte"])
    # Der Techniker hat davon noch nichts
    eff_user = (await client.get(f"/api/organigramm/effektiv?user_id={techniker.id}", headers=k)).json()
    assert ("fehlerberichte", "sehen") not in {(e["bereich"], e["aktion"]) for e in eff_user["rechte"]}
    assert (await client.get(GESCHUETZT, headers=kt)).status_code == 403

    # Zuweisen: sofort wirksam
    z = await client.post(
        f"/api/organigramm/positionen/{ph['id']}/besetzungen", headers=k, json={"user_id": str(techniker.id)}
    )
    assert z.status_code == 201, z.text
    assert z.json()["warnung"] is None
    assert (await client.get(GESCHUETZT, headers=kt)).status_code == 200
    detail = (await client.get(f"/api/organigramm/positionen/{ph['id']}", headers=k)).json()
    assert detail["status"] == "besetzt" and detail["ist_besetzung"] == 1
    assert detail["besetzungen"][0]["name"] == "Tina Techniker"
    assert {(d["bereich"], d["aktion"], d["art"]) for d in detail["diff_zur_vorlage"]} == {
        ("fehlerberichte", "sehen", "hinzugefuegt"),
        ("vorgaenge", "sehen", "hinzugefuegt"),
    }

    # Freistellung: wieder verweigert
    f = await client.patch(f"/api/organigramm/besetzungen/{z.json()['besetzung']['id']}", headers=k, json={})
    assert f.status_code == 200 and f.json()["besetzung"]["gueltig_bis"]
    assert (await client.get(GESCHUETZT, headers=kt)).status_code == 403
    detail = (await client.get(f"/api/organigramm/positionen/{ph['id']}", headers=k)).json()
    assert detail["status"] == "geplant" and len(detail["alle_besetzungen"]) == 1
    # zweites Ende -> 409
    assert (await client.patch(f"/api/organigramm/besetzungen/{z.json()['besetzung']['id']}", headers=k, json={})).status_code == 409

    # Audit mit vorher/nachher
    erstellt = (await audit("position_erstellt"))[-1].payload
    assert erstellt["vorher"] is None and erstellt["nachher"]["titel"] == "Bereichsleiter Service"
    rechte = (await audit("position_rechte_geaendert"))[-1].payload
    assert rechte["vorher"]["overrides"] == [] and len(rechte["nachher"]["overrides"]) == 2
    angelegt = [a for a in await audit("besetzung_angelegt") if a.payload["nachher"].get("position_id") == ph["id"]]
    assert angelegt and angelegt[0].actor_user_id == admin.id
    beendet = [a for a in await audit("besetzung_beendet") if a.entity_id == uuid.UUID(z.json()["besetzung"]["id"])]
    assert beendet and beendet[0].payload["vorher"]["gueltig_bis"] is None and beendet[0].payload["nachher"]["gueltig_bis"]


async def test_besetzung_regeln_warnung_vertretung_duplikat_inaktiv(client, make_mandant, make_user):
    mandant, admin, k = await admin_mit_kopf(client, make_mandant, make_user)
    wurzel = await wurzel_id(client, k)
    pos = await neue_position(client, k, wurzel, "Einzelstelle", soll_besetzung=1)
    u1, u2 = await custom_user(mandant, "Eins"), await custom_user(mandant, "Zwei")
    url = f"/api/organigramm/positionen/{pos['id']}/besetzungen"

    assert (await client.post(url, headers=k, json={"user_id": str(u1.id)})).status_code == 201
    assert (await client.post(url, headers=k, json={"user_id": str(u1.id)})).status_code == 409  # schon aktiv
    zweite = await client.post(url, headers=k, json={"user_id": str(u2.id)})
    assert zweite.status_code == 201 and "Soll-Besetzung" in zweite.json()["warnung"]
    # Vertretung braucht gueltig_bis
    u3 = await custom_user(mandant, "Drei")
    assert (await client.post(url, headers=k, json={"user_id": str(u3.id), "art": "vertretung"})).status_code == 422
    bis = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    v = await client.post(url, headers=k, json={"user_id": str(u3.id), "art": "vertretung", "gueltig_bis": bis})
    assert v.status_code == 201 and v.json()["warnung"] is None
    # Deaktivierter Nutzer / Fremdmandant
    async with system_session() as session:
        (await session.get(User, u2.id)).aktiv = False
    u4 = await custom_user(mandant, "Vier")
    async with system_session() as session:
        (await session.get(User, u4.id)).aktiv = False
    assert (await client.post(url, headers=k, json={"user_id": str(u4.id)})).status_code == 409
    anderer = await make_mandant("Andere")
    fremd = await custom_user(anderer, "Fremd")
    assert (await client.post(url, headers=k, json={"user_id": str(fremd.id)})).status_code == 404


async def test_duplizieren_kopiert_overrides_ohne_besetzungen(client, make_mandant, make_user):
    mandant, _, k = await admin_mit_kopf(client, make_mandant, make_user)
    wurzel = await wurzel_id(client, k)
    pos = await neue_position(client, k, wurzel, "Vorlage", geplant=True, soll_besetzung=2)
    await client.put(
        f"/api/organigramm/positionen/{pos['id']}/rechte",
        headers=k,
        json=[{"bereich": "material", "aktion": "sehen", "wirkung": "erlauben"}],
    )
    await client.post(
        f"/api/organigramm/positionen/{pos['id']}/besetzungen", headers=k, json={"user_id": str((await custom_user(mandant, "X")).id)}
    )
    kopie = await client.post(f"/api/organigramm/positionen/{pos['id']}/duplizieren", headers=k)
    assert kopie.status_code == 201
    kopie = kopie.json()
    assert kopie["titel"] == "Vorlage (Kopie)" and kopie["besetzungen"] == [] and kopie["soll_besetzung"] == 2
    detail = (await client.get(f"/api/organigramm/positionen/{kopie['id']}", headers=k)).json()
    assert [(o["bereich"], o["aktion"]) for o in detail["overrides"]] == [("material", "sehen")]


async def test_override_validierung_gegen_registry(client, make_mandant, make_user):
    _, _, k = await admin_mit_kopf(client, make_mandant, make_user)
    pos = await neue_position(client, k, await wurzel_id(client, k), "P")
    url = f"/api/organigramm/positionen/{pos['id']}/rechte"
    # statistik kennt nur Scope mandant
    r = await client.put(url, headers=k, json=[{"bereich": "statistik", "aktion": "sehen", "wirkung": "erlauben", "scope": "teilbaum"}])
    assert r.status_code == 422
    assert (await client.put(url, headers=k, json=[{"bereich": "gibtsnicht", "aktion": "sehen", "wirkung": "erlauben"}])).status_code == 422
    assert (await client.put(url, headers=k, json=[{"bereich": "material", "aktion": "freigeben", "wirkung": "erlauben"}])).status_code == 422
    doppelt = [{"bereich": "material", "aktion": "sehen", "wirkung": "erlauben"}] * 2
    assert (await client.put(url, headers=k, json=doppelt)).status_code == 422
    assert (await client.put(url, headers=k, json=[{"bereich": "vorgaenge", "aktion": "sehen", "wirkung": "erlauben", "scope": "foo"}])).status_code == 422


# --- Lesen: Scope und DSGVO -----------------------------------------------------------------


async def test_lesen_scope_kontextknoten_und_dsgvo(client, make_mandant, make_user):
    mandant, admin, ka = await admin_mit_kopf(client, make_mandant, make_user)
    wurzel = await wurzel_id(client, ka)
    # Eigene Einheit, sonst gelten die Geschwister unter der Wurzel als "Team" des Leiters.
    einheit = (await client.post("/api/organigramm/org-einheiten", headers=ka, json={"name": "T", "typ": "team"})).json()
    leiter = await neue_position(client, ka, wurzel, "Teamleiter", org_einheit_id=einheit["id"])
    mitarbeiter_pos = await neue_position(client, ka, leiter["id"], "Techniker")
    fremd = await neue_position(client, ka, wurzel, "Buchhaltung")

    sehen_nur = await typ_mit_rechten(mandant, "NurOrg", [("organigramm", "sehen", "teilbaum")])
    mit_namen = await typ_mit_rechten(
        mandant, "MitNamen", [("organigramm", "sehen", "teilbaum"), ("mitarbeiterverwaltung", "sehen", "teilbaum")]
    )
    async with system_session() as session:
        for pid, tid in ((leiter["id"], sehen_nur),):
            (await session.get(Position, uuid.UUID(pid))).account_typ_id = tid

    u_leiter = await custom_user(mandant, "Lena Leiter")
    u_tech = await custom_user(mandant, "Tom Tech")
    u_fremd = await custom_user(mandant, "Berta Buch")
    await besetzen(mandant, leiter["id"], u_leiter)
    await besetzen(mandant, mitarbeiter_pos["id"], u_tech)
    await besetzen(mandant, fremd["id"], u_fremd)

    # Ohne mitarbeiterverwaltung.sehen: nur Teilbaum + Kontext, keine Namen/user_ids
    kl = await kopf(client, u_leiter)
    liste = (await client.get("/api/organigramm/positionen", headers=kl)).json()
    nach_id = {p["id"]: p for p in liste}
    assert set(nach_id) == {wurzel, leiter["id"], mitarbeiter_pos["id"]}
    assert nach_id[wurzel]["kontext"] is True and "status" not in nach_id[wurzel] and "besetzungen" not in nach_id[wurzel]
    assert nach_id[mitarbeiter_pos["id"]]["status"] == "besetzt"
    b = nach_id[mitarbeiter_pos["id"]]["besetzungen"][0]
    assert b["name"] is None and "user_id" not in b
    assert (await client.get(f"/api/organigramm/positionen/{fremd['id']}", headers=kl)).status_code == 403
    assert (await client.get(f"/api/organigramm/effektiv?user_id={u_tech.id}", headers=kl)).status_code == 403
    assert (await client.get(f"/api/organigramm/effektiv?position_id={fremd['id']}", headers=kl)).status_code == 403

    # Mit mitarbeiterverwaltung.sehen: Namen im Scope
    async with system_session() as session:
        (await session.get(Position, uuid.UUID(leiter["id"]))).account_typ_id = mit_namen
    kl = await kopf(client, u_leiter)
    liste = (await client.get("/api/organigramm/positionen", headers=kl)).json()
    nach_id = {p["id"]: p for p in liste}
    b = nach_id[mitarbeiter_pos["id"]]["besetzungen"][0]
    assert b["name"] == "Tom Tech" and b["user_id"] == str(u_tech.id)
    # Effektive Rechte des Kollegen im Scope sichtbar
    assert (await client.get(f"/api/organigramm/effektiv?user_id={u_tech.id}", headers=kl)).status_code == 200
    assert (await client.get(f"/api/organigramm/effektiv?user_id={u_fremd.id}", headers=kl)).status_code == 403

    # Admin sieht alles
    liste_admin = (await client.get("/api/organigramm/positionen", headers=ka)).json()
    assert {p["id"] for p in liste_admin} >= {wurzel, leiter["id"], mitarbeiter_pos["id"], fremd["id"]}
    # effektiv: genau ein Parameter
    assert (await client.get("/api/organigramm/effektiv", headers=ka)).status_code == 422


async def test_ohne_organigramm_sehen_kein_zugriff(client, make_mandant, make_user):
    mandant, _, _ = await admin_mit_kopf(client, make_mandant, make_user)
    techniker = await make_user(mandant=mandant, role="techniker", password=PW)
    kt = await kopf(client, techniker)
    assert (await client.get("/api/organigramm/positionen", headers=kt)).status_code == 403
    assert (await client.get("/api/organigramm/org-einheiten", headers=kt)).status_code == 403
    assert (await client.post("/api/organigramm/positionen", headers=kt, json={"parent_id": str(uuid.uuid4()), "titel": "x"})).status_code == 403
