"""Eskalationsschutz, letzter Admin und Audit der Rechte-Schreibpfade
(app/services/eskalation_service.py)."""
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.db.session import system_session
from app.models.audit_log import AuditLog
from app.models.organigramm import Position, PositionBesetzung
from app.models.user import User
from app.services import eskalation_service as esk
from tests.test_organigramm_api import (
    GESCHUETZT,
    PW,
    admin_mit_kopf,
    audit,
    besetzen,
    custom_user,
    kopf,
    neue_position,
    typ_mit_rechten,
    wurzel_id,
)

ORG = "/api/organigramm"
TEAMLEITER_RECHTE = [
    ("organigramm", "sehen", "teilbaum"),
    ("organigramm", "erstellen", "teilbaum"),
    ("organigramm", "bearbeiten", "teilbaum"),
    ("organigramm", "rechte_verwalten", "teilbaum"),
    ("mitarbeiterverwaltung", "sehen", "teilbaum"),
    ("vorgaenge", "sehen", "teilbaum"),
]


async def _setze_typ(position_id: str, typ_id) -> None:
    async with system_session() as session:
        (await session.get(Position, uuid.UUID(position_id))).account_typ_id = typ_id


@pytest.fixture
async def umfeld(client, make_mandant, make_user):
    mandant, admin, ka = await admin_mit_kopf(client, make_mandant, make_user)
    wurzel = await wurzel_id(client, ka)
    einheit = (await client.post(f"{ORG}/org-einheiten", headers=ka, json={"name": "Team A", "typ": "team"})).json()
    tl_pos = await neue_position(client, ka, wurzel, "Teamleiter", org_einheit_id=einheit["id"])
    tech_a = await neue_position(client, ka, tl_pos["id"], "Techniker A")
    tech_b = await neue_position(client, ka, tl_pos["id"], "Techniker B")
    buch = await neue_position(client, ka, wurzel, "Buchhaltung")
    await _setze_typ(tl_pos["id"], await typ_mit_rechten(mandant, "TeamleiterTyp", TEAMLEITER_RECHTE))
    tl_user = await custom_user(mandant, "Teamleiter")
    tech_user = await custom_user(mandant, "Techniker")
    frei_user = await custom_user(mandant, "Frei")
    await besetzen(mandant, tl_pos["id"], tl_user)
    await besetzen(mandant, tech_a["id"], tech_user)
    return {
        "mandant": mandant,
        "admin": admin,
        "ka": ka,
        "kt": await kopf(client, tl_user),
        "tl_user": tl_user,
        "tech_user": tech_user,
        "frei_user": frei_user,
        "wurzel": wurzel,
        "tl": tl_pos,
        "tech_a": tech_a,
        "tech_b": tech_b,
        "buch": buch,
        "typ_abrechnung": await typ_mit_rechten(mandant, "Abrechnung", [("abrechnung", "sehen", "mandant")]),
        "typ_klein": await typ_mit_rechten(mandant, "Klein", [("vorgaenge", "sehen", "team")]),
    }


def _ov(bereich, aktion, wirkung="erlauben", scope=None):
    eintrag = {"bereich": bereich, "aktion": aktion, "wirkung": wirkung}
    if scope:
        eintrag["scope"] = scope
    return eintrag


async def test_teamleiter_kann_nicht_eskalieren(client, umfeld):
    u, kt = umfeld, umfeld["kt"]
    # Scope auf mandant heben: fuer andere Position, eigene Position und Nutzer (auch sich selbst)
    mandant_scope = [_ov("vorgaenge", "sehen", scope="mandant")]
    for ziel in (u["tech_a"]["id"], u["tl"]["id"]):
        r = await client.put(f"{ORG}/positionen/{ziel}/rechte", headers=kt, json=mandant_scope)
        assert r.status_code == 403, r.text
    for uid in (u["tl_user"].id, u["tech_user"].id):
        assert (await client.put(f"{ORG}/users/{uid}/rechte", headers=kt, json=mandant_scope)).status_code == 403
    # Recht, das er selbst nicht hat
    r = await client.put(
        f"{ORG}/positionen/{u['tech_a']['id']}/rechte", headers=kt, json=[_ov("abrechnung", "sehen", scope="mandant")]
    )
    assert r.status_code == 403 and "abrechnung.sehen" in r.json()["detail"]
    assert (
        await client.put(f"{ORG}/positionen/{u['tech_a']['id']}/rechte", headers=kt, json=[_ov("abrechnung", "sehen")])
    ).status_code == 403
    # Hoeherer Scope als der eigene
    assert (
        await client.put(f"{ORG}/positionen/{u['tech_a']['id']}/rechte", headers=kt, json=[_ov("vorgaenge", "sehen", scope="bereich")])
    ).status_code == 403
    # Positionen ausserhalb des Teilbaums
    assert (await client.patch(f"{ORG}/positionen/{u['buch']['id']}", headers=kt, json={"titel": "x"})).status_code == 403
    assert (
        await client.put(f"{ORG}/positionen/{u['buch']['id']}/rechte", headers=kt, json=[_ov("vorgaenge", "sehen", "verweigern")])
    ).status_code == 403
    assert (
        await client.post(f"{ORG}/positionen", headers=kt, json={"parent_id": u["buch"]["id"], "titel": "x"})
    ).status_code == 403
    assert (
        await client.patch(f"{ORG}/positionen/{u['tech_a']['id']}", headers=kt, json={"parent_id": u["buch"]["id"]})
    ).status_code == 403
    assert (await client.post(f"{ORG}/positionen/{u['buch']['id']}/archivieren", headers=kt)).status_code == 403
    assert (
        await client.post(f"{ORG}/positionen/{u['buch']['id']}/besetzungen", headers=kt, json={"user_id": str(u["frei_user"].id)})
    ).status_code == 403
    # Position mit maechtigerem Account-Typ: Typ setzen und Nutzer zuweisen
    r = await client.patch(f"{ORG}/positionen/{u['tech_b']['id']}", headers=kt, json={"account_typ_id": str(u["typ_abrechnung"])})
    assert r.status_code == 403
    await _setze_typ(u["tech_b"]["id"], u["typ_abrechnung"])
    r = await client.post(
        f"{ORG}/positionen/{u['tech_b']['id']}/besetzungen", headers=kt, json={"user_id": str(u["frei_user"].id)}
    )
    assert r.status_code == 403
    # Nichts davon hat etwas veraendert
    async with system_session() as session:
        assert (await session.execute(select(PositionBesetzung).where(PositionBesetzung.user_id == u["frei_user"].id))).first() is None
    # Users-PATCH: Account-Typ mit mehr Rechten, Rolle, Deaktivieren
    url = f"/api/users/{u['tech_user'].id}"
    assert (await client.patch(url, headers=kt, json={"account_typ_id": str(u["typ_abrechnung"])})).status_code == 403
    assert (await client.patch(url, headers=kt, json={"role": "mandant_admin"})).status_code == 403
    assert (await client.patch(url, headers=kt, json={"aktiv": False})).status_code == 403
    assert (await client.patch(f"/api/users/{u['frei_user'].id}", headers=kt, json={"account_typ_id": str(u["typ_klein"])})).status_code == 403  # nicht im Scope


async def test_teamleiter_kann_innerhalb_seines_scopes_vergeben(client, umfeld):
    u, kt, ka = umfeld, umfeld["kt"], umfeld["ka"]
    pos_url = f"{ORG}/positionen/{u['tech_a']['id']}/rechte"
    # verweigern ist immer erlaubt (im Scope)
    assert (await client.put(pos_url, headers=kt, json=[_ov("abrechnung", "sehen", "verweigern")])).status_code == 200
    # Rechte <= eigene
    r = await client.put(
        pos_url,
        headers=kt,
        json=[_ov("vorgaenge", "sehen", scope="team")],
    )
    assert r.status_code == 200
    assert (await client.put(pos_url, headers=kt, json=[_ov("vorgaenge", "sehen", scope="teilbaum")])).status_code == 200
    # Neue Position im Teilbaum mit kleinerem Typ, Nutzer zuweisen
    neu = await client.post(f"{ORG}/positionen", headers=kt, json={"parent_id": u["tl"]["id"], "titel": "Azubi"})
    assert neu.status_code == 201
    r = await client.patch(f"{ORG}/positionen/{neu.json()['id']}", headers=kt, json={"account_typ_id": str(u["typ_klein"])})
    assert r.status_code == 200, r.text
    r = await client.post(
        f"{ORG}/positionen/{neu.json()['id']}/besetzungen", headers=kt, json={"user_id": str(u["frei_user"].id)}
    )
    assert r.status_code == 201, r.text
    # Nutzer-Override im Scope
    assert (
        await client.put(f"{ORG}/users/{u['tech_user'].id}/rechte", headers=kt, json=[_ov("vorgaenge", "sehen", "verweigern")])
    ).status_code == 200
    # Account-Typ des Nutzers im Scope auf kleineren Typ setzen
    assert (
        await client.patch(f"/api/users/{u['tech_user'].id}", headers=kt, json={"account_typ_id": str(u["typ_klein"])})
    ).status_code == 200
    # Positionen duplizieren/umhaengen im Teilbaum
    assert (await client.post(f"{ORG}/positionen/{u['tech_b']['id']}/duplizieren", headers=kt)).status_code == 201
    assert (await client.patch(f"{ORG}/positionen/{u['tech_b']['id']}", headers=kt, json={"parent_id": u["tech_a"]["id"]})).status_code == 200

    # Account-Typen-Matrix: nur mit Scope <= eigener (Typ mit nur_zugewiesene_kunden gibt "eigene")
    eigene = (await client.post("/api/account-typen", headers=ka, json={"name": "Nur Eigene", "nur_zugewiesene_kunden": True})).json()
    normal = (await client.post("/api/account-typen", headers=ka, json={"name": "Normal"})).json()
    put = lambda typ_id, bereich: client.put(  # noqa: E731
        f"/api/account-typen/{typ_id}/rechte", headers=kt, json={"bereich": bereich, "aktion": "sehen", "erlaubt": True}
    )
    assert (await put(eigene["id"], "vorgaenge")).status_code == 200
    assert (await put(normal["id"], "vorgaenge")).status_code == 403  # mandant > teilbaum
    assert (await put(eigene["id"], "abrechnung")).status_code == 403  # nicht vorhanden
    assert (await client.get("/api/account-typen", headers=kt)).status_code == 200
    # typ_klein wird durch die Nutzerverwaltung (Typ-Position unter der Wurzel) auch
    # ausserhalb des Teilbaums genutzt -> Aenderung am Typ gesperrt
    r = await client.put(
        f"/api/account-typen/{u['typ_klein']}/rechte", headers=kt, json={"bereich": "vorgaenge", "aktion": "sehen", "erlaubt": False}
    )
    assert r.status_code == 403 and "außerhalb" in r.json()["detail"]
    assert (await client.patch(f"/api/account-typen/{u['typ_klein']}", headers=kt, json={"name": "Umbenannt"})).status_code == 403
    assert (await client.delete(f"/api/account-typen/{u['typ_klein']}", headers=kt)).status_code == 403
    assert (await client.patch(f"/api/account-typen/{eigene['id']}", headers=kt, json={"name": "Eigene2"})).status_code == 200


async def test_verweigerung_aufheben_zaehlt_als_vergabe(client, umfeld):
    u, kt, ka = umfeld, umfeld["kt"], umfeld["ka"]
    await _setze_typ(u["tech_b"]["id"], u["typ_abrechnung"])
    url = f"{ORG}/positionen/{u['tech_b']['id']}/rechte"
    assert (await client.put(url, headers=ka, json=[_ov("abrechnung", "sehen", "verweigern")])).status_code == 200
    assert (await client.put(url, headers=kt, json=[])).status_code == 403
    assert (await client.put(url, headers=ka, json=[])).status_code == 200


async def test_ohne_rechte_verwalten_und_account_typen_zugriff(client, make_mandant, make_user):
    mandant, _, ka = await admin_mit_kopf(client, make_mandant, make_user)
    techniker = await make_user(mandant=mandant, role="techniker", password=PW)
    kt = await kopf(client, techniker)
    assert (await client.get("/api/account-typen", headers=kt)).status_code == 403
    assert (await client.post("/api/account-typen", headers=kt, json={"name": "X"})).status_code == 403
    assert (await client.get("/api/account-typen", headers=ka)).status_code == 200


async def test_account_typen_routen_schreiben_audit(client, make_mandant, make_user):
    mandant, admin, ka = await admin_mit_kopf(client, make_mandant, make_user)
    typ = (await client.post("/api/account-typen", headers=ka, json={"name": "Neu"})).json()
    await client.patch(f"/api/account-typen/{typ['id']}", headers=ka, json={"name": "Neuer"})
    await client.put(
        f"/api/account-typen/{typ['id']}/rechte", headers=ka, json={"bereich": "material", "aktion": "sehen", "erlaubt": True}
    )
    await client.delete(f"/api/account-typen/{typ['id']}", headers=ka)
    erstellt = (await audit("account_typ_erstellt"))[0]
    assert erstellt.payload["vorher"] is None and erstellt.payload["nachher"]["name"] == "Neu"
    assert erstellt.actor_user_id == admin.id
    geaendert = (await audit("account_typ_geaendert"))[0].payload
    assert geaendert["vorher"] == {"name": "Neu"} and geaendert["nachher"] == {"name": "Neuer"}
    recht = (await audit("account_typ_recht_geaendert"))[0].payload
    assert recht["vorher"]["erlaubt"] is False and recht["nachher"]["erlaubt"] is True
    assert (await audit("account_typ_geloescht"))[0].payload["nachher"] is None


# --- Letzter Admin ---------------------------------------------------------------------------


async def test_letzter_admin_nicht_deaktivierbar_herabstufbar_loeschbar(client, make_mandant, make_user):
    mandant, admin, ka = await admin_mit_kopf(client, make_mandant, make_user)
    typ = (await client.post("/api/account-typen", headers=ka, json={"name": "T"})).json()
    url = f"/api/users/{admin.id}"
    r = await client.patch(url, headers=ka, json={"aktiv": False})
    assert r.status_code == 409 and "letzte" in r.json()["detail"]
    assert (await client.patch(url, headers=ka, json={"role": "custom", "account_typ_id": typ["id"]})).status_code == 409
    assert (await client.delete(url, headers=ka)).status_code == 400  # eigener Account (bestehende Regel)

    zweiter = await make_user(mandant=mandant, role="mandant_admin", password=PW, name="Zweiter")
    # mit zweitem Admin geht Herabstufen
    r = await client.patch(f"/api/users/{zweiter.id}", headers=ka, json={"role": "custom", "account_typ_id": typ["id"]})
    assert r.status_code == 200, r.text
    # jetzt ist admin wieder der letzte
    assert (await client.patch(url, headers=ka, json={"aktiv": False})).status_code == 409
    # Loeschen des letzten Admins durch einen anderen Admin (Fremd-Admin im selben Mandanten ist nicht moeglich:
    # ein zweiter Admin waere ja nicht der letzte) -> Stand bleibt unveraendert
    async with system_session() as session:
        assert (await session.get(User, admin.id)).aktiv is True

    dritter = await make_user(mandant=mandant, role="mandant_admin", password=PW, name="Dritter")
    kd = await kopf(client, dritter)
    assert (await client.patch(url, headers=kd, json={"aktiv": False})).status_code == 200  # admin war nicht der letzte


async def test_letzter_admin_loeschen_bleibt_400(client, make_mandant, make_user):
    mandant, admin, ka = await admin_mit_kopf(client, make_mandant, make_user)
    # loesch_operativ darf wie mandant_admin loeschen (require_roles-Alias), ist aber nicht der Admin selbst
    op = await make_user(mandant=mandant, role="loesch_operativ", password=PW)
    # Bestehender Vertrag des Loeschpfads (tests/test_user_loeschen.py): 400 statt 409.
    r = await client.delete(f"/api/users/{admin.id}", headers=await kopf(client, op))
    assert r.status_code == 400 and "letzte" in r.json()["detail"]


async def test_verwaltung_bleibt_erhalten_ohne_admin(make_mandant):
    """Ohne mandant_admin muss ein Nutzer mit mandantweitem rechte_verwalten uebrig bleiben."""
    mandant = await make_mandant()
    typ = await typ_mit_rechten(mandant, "Verwalter", [("organigramm", "rechte_verwalten", "mandant")])
    async with system_session() as session:
        wurzel = (await session.execute(select(Position).where(Position.mandant_id == mandant.id))).scalars().first()
        wurzel.account_typ_id = typ
    verwalter = await custom_user(mandant, "Verwalter")
    await besetzen(mandant, str(wurzel.id), verwalter)

    async with system_session() as session:
        assert await esk.verwaltung_vorhanden(session, mandant.id)
        with pytest.raises(HTTPException) as fehler:
            async with esk.verwaltung_bleibt_erhalten(session, mandant.id):
                await session.execute(
                    PositionBesetzung.__table__.delete().where(PositionBesetzung.user_id == verwalter.id)
                )
        assert fehler.value.status_code == 409


async def test_sync_schreibt_besetzungs_audit_mit_akteur(client, make_mandant, make_user):
    mandant, admin, ka = await admin_mit_kopf(client, make_mandant, make_user)
    typ = (await client.post("/api/account-typen", headers=ka, json={"name": "Dispo"})).json()
    neu = await client.post(
        "/api/users",
        headers=ka,
        json={"mandant_id": str(mandant.id), "email": "n@x.de", "password": "supersecret1", "role": "custom",
              "account_typ_id": typ["id"], "name": "N"},
    )
    assert neu.status_code == 201
    angelegt = [a for a in await audit("besetzung_angelegt") if a.payload["nachher"]["user_id"] == neu.json()["id"]]
    assert len(angelegt) == 1 and angelegt[0].actor_user_id == admin.id
    await client.patch(f"/api/users/{neu.json()['id']}", headers=ka, json={"aktiv": False})
    beendet = [a for a in await audit("besetzung_beendet") if a.payload["vorher"]["user_id"] == neu.json()["id"]]
    assert len(beendet) == 1 and beendet[0].actor_user_id == admin.id
    assert beendet[0].payload["vorher"]["gueltig_bis"] is None and beendet[0].payload["nachher"]["gueltig_bis"]
    rolle = (await audit("user_rolle_geaendert"))[0].payload
    assert rolle["vorher"]["aktiv"] is True and rolle["nachher"]["aktiv"] is False
