import os
import uuid
from datetime import date, timedelta

import pytest
import sqlalchemy
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import system_session
from app.models.notification import Notification
from tests.conftest import _BACKEND_DIR, auth_headers, login
from tests.test_projekte import _make_custom_mit_projekte_recht, _make_custom_user

PW = "pw-123456"
HEUTE = date.today()


def _d(tage: int) -> str:
    return (HEUTE + timedelta(days=tage)).isoformat()


def _url(pid, suffix=""):
    return f"/api/projekte/{pid}/zeitplan{suffix}"


async def _admin(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW, name="Chefin")
    return mandant, admin, auth_headers(await login(client, admin.email, PW))


async def _techniker(client, make_user, mandant, name="Tom Techniker"):
    user = await make_user(mandant=mandant, role="techniker", password=PW, name=name)
    return user, auth_headers(await login(client, user.email, PW))


async def _mitarbeit(client, h, pid, user) -> None:
    """Macht user zum Zustaendigen eines eigenen Elements -> Mitarbeit im Projekt."""
    await _element(client, h, pid, titel=f"Einsatz {user.id}", zugewiesen_an=str(user.id))


async def _projekt(client, h, name="Neubau") -> str:
    return (await client.post("/api/projekte", headers=h, json={"name": name})).json()["id"]


async def _element(client, h, pid, typ="schritt", titel="Rohbau", **kw) -> dict:
    resp = await client.post(_url(pid, "/elemente"), headers=h, json={"typ": typ, "titel": titel, **kw})
    assert resp.status_code == 200, resp.text
    return next(e for e in resp.json()["elemente"] if e["titel"] == titel)


async def _antrag(client, h, pid, element_id, art="verschieben", **kw):
    body = {"element_id": element_id, "art": art, "begruendung": "Material fehlt", **kw}
    return await client.post(_url(pid, "/antraege"), headers=h, json=body)


@pytest.mark.asyncio
async def test_techniker_sieht_zeitplan_aendert_aber_nicht_und_beantragt(client, make_mandant, make_user):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    el = await _element(client, h, pid, start_am=_d(0), ende_am=_d(4))
    u_th, th = await _techniker(client, make_user, mandant)
    await _mitarbeit(client, h, pid, u_th)

    assert (await client.get(_url(pid), headers=th)).status_code == 200
    assert (await client.get(_url(pid, "/basisplaene"), headers=th)).status_code == 200
    assert (await client.get(_url(pid, "/pdf"), headers=th)).status_code == 200
    # Editor-Hilfsliste und alle Mutationen bleiben gesperrt.
    assert (await client.get(_url(pid, "/auswahl/vorgaenge"), headers=th)).status_code == 403
    assert (await client.patch(_url(pid, f"/elemente/{el['id']}"), headers=th, json={"titel": "X"})).status_code == 403
    assert (await client.post(_url(pid, "/elemente"), headers=th, json={"typ": "schritt", "titel": "N"})).status_code == 403
    assert (await client.delete(_url(pid, f"/elemente/{el['id']}"), headers=th)).status_code == 403
    assert (await client.get("/api/projekte", headers=th)).status_code == 403

    resp = await _antrag(client, th, pid, el["id"], gewuenschter_start_am=_d(3))
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "offen"


@pytest.mark.asyncio
async def test_nutzer_ohne_rechte_sieht_nichts(client, make_mandant, make_user):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    el = await _element(client, h, pid, start_am=_d(0), ende_am=_d(4))
    typ = await _make_custom_mit_projekte_recht(mandant, aktionen=set())
    user = await _make_custom_user(mandant, typ)
    uh = auth_headers(await login(client, user.email, "hunter2!!"))

    assert (await client.get(_url(pid), headers=uh)).status_code == 403
    assert (await client.get(_url(pid, "/antraege"), headers=uh)).status_code == 403
    assert (await client.get("/api/projekte/meine-zeitplaene", headers=uh)).status_code == 403
    assert (await _antrag(client, uh, pid, el["id"], art="problem")).status_code == 403


@pytest.mark.asyncio
async def test_nur_zeitplan_sehen_darf_nicht_beantragen(client, make_mandant, make_user):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    el = await _element(client, h, pid, start_am=_d(0), ende_am=_d(4))
    typ = await _make_custom_mit_projekte_recht(mandant, aktionen={"zeitplan_sehen"})
    user = await _make_custom_user(mandant, typ)
    uh = auth_headers(await login(client, user.email, "hunter2!!"))

    await _mitarbeit(client, h, pid, user)
    assert (await client.get(_url(pid), headers=uh)).status_code == 200
    assert (await _antrag(client, uh, pid, el["id"], art="problem")).status_code == 403


@pytest.mark.asyncio
async def test_me_liefert_neue_rechte_und_matrix_kennt_sie(client, make_mandant, make_user):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    _, th = await _techniker(client, make_user, mandant)
    me = (await client.get("/api/auth/me", headers=th)).json()
    assert set(me["rechte"]["projekte"]) == {"zeitplan_sehen", "zeitplan_beantragen"}
    assert "zeitplan_sehen" in (await client.get("/api/auth/me", headers=h)).json()["rechte"]["projekte"]

    typen = (await client.get("/api/account-typen", headers=h)).json()
    tid = typen[0]["id"]
    matrix = (await client.get(f"/api/account-typen/{tid}/rechte", headers=h)).json()
    assert {(e["bereich"], e["aktion"]) for e in matrix if e["aktion"].startswith("zeitplan")} == {
        ("projekte", "zeitplan_sehen"),
        ("projekte", "zeitplan_beantragen"),
    }
    ok = await client.put(
        f"/api/account-typen/{tid}/rechte",
        headers=h,
        json={"bereich": "projekte", "aktion": "zeitplan_sehen", "erlaubt": True},
    )
    assert ok.status_code == 200
    falsch = await client.put(
        f"/api/account-typen/{tid}/rechte",
        headers=h,
        json={"bereich": "kunden", "aktion": "zeitplan_sehen", "erlaubt": True},
    )
    assert falsch.status_code == 422


@pytest.mark.asyncio
async def test_antrag_validierungen(client, make_mandant, make_user):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    schritt = await _element(client, h, pid, titel="Schritt", start_am=_d(0), ende_am=_d(4))
    meilenstein = await _element(client, h, pid, typ="meilenstein", titel="MS", start_am=_d(2))
    phase = await _element(client, h, pid, typ="phase", titel="Phase")
    u_th, th = await _techniker(client, make_user, mandant)
    await _mitarbeit(client, h, pid, u_th)

    # verschieben braucht Start; Ende = Start + bisherige Dauer (5 Tage inkl.)
    assert (await _antrag(client, th, pid, schritt["id"])).status_code == 400
    ok = await _antrag(client, th, pid, schritt["id"], gewuenschter_start_am=_d(10))
    assert ok.status_code == 201, ok.text
    assert ok.json()["gewuenschtes_ende_am"] == _d(14)
    assert ok.json()["aktueller_start_am"] == _d(0)
    assert ok.json()["element_titel"] == "Schritt"
    # Begruendung Pflicht
    leer = await client.post(
        _url(pid, "/antraege"), headers=th, json={"element_id": meilenstein["id"], "art": "problem", "begruendung": " "}
    )
    assert leer.status_code == 422
    # dauer_aendern braucht Ende, nicht vor Start, nicht fuer Meilensteine
    assert (await _antrag(client, th, pid, meilenstein["id"], art="dauer_aendern", gewuenschtes_ende_am=_d(5))).status_code == 400
    assert (await _antrag(client, th, pid, schritt["id"], art="dauer_aendern")).status_code == 400
    assert (
        await _antrag(client, th, pid, schritt["id"], art="dauer_aendern", gewuenschtes_ende_am=_d(-1))
    ).status_code == 400
    # problem ohne Datum
    assert (await _antrag(client, th, pid, meilenstein["id"], art="problem", gewuenschter_start_am=_d(1))).status_code == 400
    assert (await _antrag(client, th, pid, meilenstein["id"], art="problem")).status_code == 201
    # Phasen und fremde Elemente
    assert (await _antrag(client, th, pid, phase["id"], art="problem")).status_code == 400
    assert (await _antrag(client, th, pid, str(uuid.uuid4()), art="problem")).status_code == 404


@pytest.mark.asyncio
async def test_doppelantrag_409_aber_anderer_nutzer_ok(client, make_mandant, make_user):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    el = await _element(client, h, pid, start_am=_d(0), ende_am=_d(4))
    u_th, th = await _techniker(client, make_user, mandant)
    await _mitarbeit(client, h, pid, u_th)
    u_th2, th2 = await _techniker(client, make_user, mandant, name="Zweite")
    await _mitarbeit(client, h, pid, u_th2)

    assert (await _antrag(client, th, pid, el["id"], art="problem")).status_code == 201
    assert (await _antrag(client, th, pid, el["id"], art="problem")).status_code == 409
    assert (await _antrag(client, th2, pid, el["id"], art="problem")).status_code == 201


@pytest.mark.asyncio
async def test_liefer_meilenstein_nur_problem(client, make_mandant, make_user):
    from app.db.session import system_session as ss
    from app.models.bestellung import Bestellung

    mandant, admin, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    async with ss() as session:
        b = Bestellung(mandant_id=mandant.id, bestellnummer=f"B-{uuid.uuid4().hex[:6]}", status="bestellt", liefertermin=HEUTE + timedelta(days=5), erstellt_von=admin.id)
        session.add(b)
        await session.flush()
        bid = str(b.id)
    ms = await _element(client, h, pid, typ="meilenstein", titel="Lieferung", bestellung_id=bid)
    u_th, th = await _techniker(client, make_user, mandant)
    await _mitarbeit(client, h, pid, u_th)

    assert (await _antrag(client, th, pid, ms["id"], gewuenschter_start_am=_d(9))).status_code == 400
    assert (await _antrag(client, th, pid, ms["id"], art="problem")).status_code == 201


@pytest.mark.asyncio
async def test_annehmen_verschiebt_inkl_nachfolger_und_offene_antraege(client, make_mandant, make_user):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    a = await _element(client, h, pid, titel="A", start_am=_d(0), ende_am=_d(2))
    b = await _element(client, h, pid, titel="B", start_am=_d(3), ende_am=_d(5))
    assert (
        await client.post(
            _url(pid, "/abhaengigkeiten"), headers=h, json={"vorgaenger_id": a["id"], "nachfolger_id": b["id"]}
        )
    ).status_code == 200
    u_th, th = await _techniker(client, make_user, mandant)
    await _mitarbeit(client, h, pid, u_th)

    antrag = (await _antrag(client, th, pid, a["id"], gewuenschter_start_am=_d(5))).json()
    zp = (await client.get(_url(pid), headers=h)).json()
    assert next(e for e in zp["elemente"] if e["titel"] == "A")["offene_antraege"] == 1
    assert next(e for e in zp["elemente"] if e["titel"] == "B")["offene_antraege"] == 0

    # Techniker darf nicht entscheiden
    assert (await client.post(_url(pid, f"/antraege/{antrag['id']}/annehmen"), headers=th, json={})).status_code == 403

    resp = await client.post(
        _url(pid, f"/antraege/{antrag['id']}/annehmen"), headers=h, json={"antwort": "Passt"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["antrag"]["status"] == "angenommen"
    assert data["antrag"]["antwort"] == "Passt"
    assert data["antrag"]["bearbeitet_von_name"] == "Chefin"
    els = {e["titel"]: e for e in data["zeitplan"]["elemente"]}
    assert els["A"]["start_am"] == _d(5) and els["A"]["ende_am"] == _d(7)
    assert els["B"]["start_am"] == _d(8)  # Nachfolger zieht nach
    assert els["A"]["offene_antraege"] == 0
    # nicht erneut entscheidbar
    assert (await client.post(_url(pid, f"/antraege/{antrag['id']}/annehmen"), headers=h, json={})).status_code == 409

    # dauer_aendern + problem
    antrag2 = (await _antrag(client, th, pid, a["id"], art="dauer_aendern", gewuenschtes_ende_am=_d(9))).json()
    r2 = (await client.post(_url(pid, f"/antraege/{antrag2['id']}/annehmen"), headers=h, json={})).json()
    a2 = next(e for e in r2["zeitplan"]["elemente"] if e["titel"] == "A")
    assert (a2["start_am"], a2["ende_am"]) == (_d(5), _d(9))
    antrag3 = (await _antrag(client, th, pid, a["id"], art="problem")).json()
    r3 = (await client.post(_url(pid, f"/antraege/{antrag3['id']}/annehmen"), headers=h, json={})).json()
    a3 = next(e for e in r3["zeitplan"]["elemente"] if e["titel"] == "A")
    assert (a3["start_am"], a3["ende_am"]) == (_d(5), _d(9))
    assert r3["antrag"]["status"] == "angenommen"


@pytest.mark.asyncio
async def test_annehmen_geloeschtes_element_409(client, make_mandant, make_user):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    el = await _element(client, h, pid, start_am=_d(0), ende_am=_d(2))
    u_th, th = await _techniker(client, make_user, mandant)
    await _mitarbeit(client, h, pid, u_th)
    antrag = (await _antrag(client, th, pid, el["id"], gewuenschter_start_am=_d(3))).json()
    assert (await client.delete(_url(pid, f"/elemente/{el['id']}"), headers=h)).status_code == 200
    resp = await client.post(_url(pid, f"/antraege/{antrag['id']}/annehmen"), headers=h, json={})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_ablehnen_braucht_antwort_und_zurueckziehen_nur_ersteller(client, make_mandant, make_user):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    el = await _element(client, h, pid, start_am=_d(0), ende_am=_d(2))
    u_th, th = await _techniker(client, make_user, mandant)
    await _mitarbeit(client, h, pid, u_th)
    u_th2, th2 = await _techniker(client, make_user, mandant, name="Zweite")
    await _mitarbeit(client, h, pid, u_th2)
    antrag = (await _antrag(client, th, pid, el["id"], art="problem")).json()
    base = _url(pid, f"/antraege/{antrag['id']}")

    assert (await client.post(base + "/ablehnen", headers=h, json={})).status_code == 422
    assert (await client.post(base + "/ablehnen", headers=h, json={"antwort": "  "})).status_code == 422
    assert (await client.post(base + "/ablehnen", headers=th, json={"antwort": "Nein"})).status_code == 403

    # fremder Techniker darf nicht zurueckziehen, Ersteller schon
    assert (await client.post(base + "/zurueckziehen", headers=th2)).status_code == 403
    zr = await client.post(base + "/zurueckziehen", headers=th)
    assert zr.status_code == 200
    assert zr.json()["antrag"]["status"] == "zurueckgezogen"
    assert (await client.post(base + "/zurueckziehen", headers=th)).status_code == 409
    # nach Zurueckziehen kann derselbe Nutzer erneut beantragen
    assert (await _antrag(client, th, pid, el["id"], art="problem")).status_code == 201

    neu = (await _antrag(client, th2, pid, el["id"], art="problem")).json()
    abl = await client.post(
        _url(pid, f"/antraege/{neu['id']}/ablehnen"), headers=h, json={"antwort": "Geht nicht"}
    )
    assert abl.status_code == 200
    assert abl.json()["antrag"]["status"] == "abgelehnt"
    assert abl.json()["antrag"]["antwort"] == "Geht nicht"
    # abgelehnter Antrag kann nicht mehr zurueckgezogen werden
    assert (await client.post(_url(pid, f"/antraege/{neu['id']}/zurueckziehen"), headers=th2)).status_code == 409


@pytest.mark.asyncio
async def test_listen_sichtbarkeit_und_statusfilter(client, make_mandant, make_user):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    el = await _element(client, h, pid, start_am=_d(0), ende_am=_d(2))
    u_th, th = await _techniker(client, make_user, mandant)
    await _mitarbeit(client, h, pid, u_th)
    u_th2, th2 = await _techniker(client, make_user, mandant, name="Zweite")
    await _mitarbeit(client, h, pid, u_th2)
    a1 = (await _antrag(client, th, pid, el["id"], art="problem")).json()
    await _antrag(client, th2, pid, el["id"], art="problem")

    assert len((await client.get(_url(pid, "/antraege"), headers=h)).json()) == 2
    eigene = (await client.get(_url(pid, "/antraege"), headers=th)).json()
    assert [a["id"] for a in eigene] == [a1["id"]]
    assert eigene[0]["erstellt_von_name"] == "Tom Techniker"

    await client.post(_url(pid, f"/antraege/{a1['id']}/ablehnen"), headers=h, json={"antwort": "Nein"})
    assert len((await client.get(_url(pid, "/antraege?status=offen"), headers=h)).json()) == 1
    assert len((await client.get(_url(pid, "/antraege?status=abgelehnt"), headers=h)).json()) == 1
    assert (await client.get(_url(pid, "/antraege?status=quatsch"), headers=h)).status_code == 422


@pytest.mark.asyncio
async def test_mandantentrennung(client, make_mandant, make_user):
    m1, _, h1 = await _admin(client, make_mandant, make_user)
    m2, _, h2 = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h1)
    el = await _element(client, h1, pid, start_am=_d(0), ende_am=_d(2))
    u_th, th = await _techniker(client, make_user, m1)
    await _mitarbeit(client, h1, pid, u_th)
    antrag = (await _antrag(client, th, pid, el["id"], art="problem")).json()

    assert (await client.get(_url(pid, "/antraege"), headers=h2)).status_code == 404
    assert (await client.post(_url(pid, f"/antraege/{antrag['id']}/annehmen"), headers=h2, json={})).status_code == 404
    _, th_fremd = await _techniker(client, make_user, m2)
    assert (await _antrag(client, th_fremd, pid, el["id"], art="problem")).status_code == 404
    assert (await client.get("/api/projekte/meine-zeitplaene", headers=h2)).json() == []


@pytest.mark.asyncio
async def test_notifications(client, make_mandant, make_user):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)  # Ersteller = admin
    el = await _element(client, h, pid, start_am=_d(0), ende_am=_d(2))
    techniker, th = await _techniker(client, make_user, mandant)
    await _mitarbeit(client, h, pid, techniker)
    antrag = (await _antrag(client, th, pid, el["id"], art="problem")).json()

    async with system_session() as session:
        rows = (await session.execute(select(Notification).where(Notification.typ == "zeitplan_antrag"))).scalars().all()
        assert [(n.user_id, n.ref_entity_type, str(n.ref_entity_id)) for n in rows] == [(admin.id, "projekt", pid)]
    # ueber die API lesbar (Schema-Literal)
    liste = (await client.get("/api/notifications", headers=h)).json()
    assert any(n["typ"] == "zeitplan_antrag" for n in liste)

    await client.post(_url(pid, f"/antraege/{antrag['id']}/ablehnen"), headers=h, json={"antwort": "Nein"})
    liste = (await client.get("/api/notifications", headers=th)).json()
    assert [n["typ"] for n in liste] == ["zeitplan_antrag"]
    assert "abgelehnt" in liste[0]["titel"]


@pytest.mark.asyncio
async def test_notification_zustaendiger_office_nutzer(client, make_mandant, make_user):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    dispo = await make_user(mandant=mandant, role="mandant_admin", password=PW, name="Zweiter Admin")
    pid = await _projekt(client, h)
    el = await _element(client, h, pid, start_am=_d(0), ende_am=_d(2), zugewiesen_an=str(dispo.id))
    u_th, th = await _techniker(client, make_user, mandant)
    await _mitarbeit(client, h, pid, u_th)
    await _antrag(client, th, pid, el["id"], art="problem")
    async with system_session() as session:
        ids = {
            n.user_id
            for n in (await session.execute(select(Notification).where(Notification.typ == "zeitplan_antrag"))).scalars()
        }
    assert ids == {admin.id, dispo.id}


async def _alle_lese_endpunkte(client, th, pid, element_id) -> dict[str, int]:
    """Status aller Lese-/Antrags-Endpunkte fuer die Mitarbeits-Tests."""
    antrag = await _antrag(client, th, pid, element_id, art="problem")
    antrag_id = antrag.json().get("id", str(uuid.uuid4()))
    return {
        "zeitplan": (await client.get(_url(pid), headers=th)).status_code,
        "pdf": (await client.get(_url(pid, "/pdf"), headers=th)).status_code,
        "basisplaene": (await client.get(_url(pid, "/basisplaene"), headers=th)).status_code,
        "antraege": (await client.get(_url(pid, "/antraege"), headers=th)).status_code,
        "antrag_anlegen": antrag.status_code,
        "zurueckziehen": (await client.post(_url(pid, f"/antraege/{antrag_id}/zurueckziehen"), headers=th)).status_code,
    }


@pytest.mark.asyncio
async def test_lesen_ohne_mitarbeit_404(client, make_mandant, make_user):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    el = await _element(client, h, pid, start_am=_d(0), ende_am=_d(4))
    _, th = await _techniker(client, make_user, mandant)

    assert set((await _alle_lese_endpunkte(client, th, pid, el["id"])).values()) == {404}
    # Antrag, den ein Mitarbeiter stellt, ist fuer Fremde ebenfalls nicht erreichbar
    u2, th2 = await _techniker(client, make_user, mandant, name="Zweite")
    await _mitarbeit(client, h, pid, u2)
    antrag = (await _antrag(client, th2, pid, el["id"], art="problem")).json()
    assert (await client.post(_url(pid, f"/antraege/{antrag['id']}/zurueckziehen"), headers=th)).status_code == 404
    # unbekanntes Projekt: gleiche Antwort wie ohne Mitarbeit
    assert (await client.get(_url(uuid.uuid4()), headers=th)).status_code == 404
    assert (await client.get("/api/projekte/meine-zeitplaene", headers=th)).json() == []


@pytest.mark.asyncio
async def test_lesen_mit_mitarbeit_als_element_zustaendiger(client, make_mandant, make_user):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    el = await _element(client, h, pid, start_am=_d(0), ende_am=_d(4))
    user, th = await _techniker(client, make_user, mandant)
    await _mitarbeit(client, h, pid, user)
    assert await _alle_lese_endpunkte(client, th, pid, el["id"]) == {
        "zeitplan": 200, "pdf": 200, "basisplaene": 200, "antraege": 200, "antrag_anlegen": 201, "zurueckziehen": 200,
    }


@pytest.mark.asyncio
async def test_lesen_mit_mitarbeit_als_vorgang_techniker_und_termin(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    from datetime import datetime, timezone

    from app.models.termin import Termin

    mandant, admin, h = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    p_vorgang = await _projekt(client, h, "Per Vorgang")
    p_termin = await _projekt(client, h, "Per Termin")
    user, th = await _techniker(client, make_user, mandant)
    v1 = await make_vorgang(mandant=mandant, kunde=kunde, zugewiesener_user_id=user.id)
    v2 = await make_vorgang(mandant=mandant, kunde=kunde)
    async with system_session() as session:
        start = datetime.now(timezone.utc)
        session.add(
            Termin(
                mandant_id=mandant.id, vorgang_id=v2.id, techniker_id=user.id, erstellt_von=admin.id,
                titel="Einsatz", start_at=start, ende_at=start + timedelta(hours=2),
            )
        )
    e1 = await _element(client, h, p_vorgang, start_am=_d(0), ende_am=_d(2), vorgang_id=str(v1.id))
    e2 = await _element(client, h, p_termin, start_am=_d(0), ende_am=_d(2), vorgang_id=str(v2.id))

    assert (await client.get(_url(p_vorgang), headers=th)).status_code == 200
    assert (await _antrag(client, th, p_vorgang, e1["id"], art="problem")).status_code == 201
    assert (await client.get(_url(p_termin), headers=th)).status_code == 200
    assert (await _antrag(client, th, p_termin, e2["id"], art="problem")).status_code == 201


@pytest.mark.asyncio
async def test_lesen_mit_mitarbeit_als_zugewiesener_kunde(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_vertrag, make_kunde_zuweisung
):
    from app.models.auftrag import Auftrag

    mandant, admin, h = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    fremder_kunde = await make_kunde(mandant=mandant)
    user, th = await _techniker(client, make_user, mandant)
    p_auftrag = await _projekt(client, h, "Per Auftrag")
    p_vorgang = await _projekt(client, h, "Per Kunden-Vorgang")
    p_vertrag = await _projekt(client, h, "Per Vertrag")
    p_fremd = await _projekt(client, h, "Fremder Kunde")

    # Vor der Zuweisung: kein Zugriff, auch wenn die Projekte schon am Kunden haengen.
    async with system_session() as session:
        session.add(
            Auftrag(mandant_id=mandant.id, projekt_id=uuid.UUID(p_auftrag), kunde_id=kunde.id, titel="A", erstellt_von=admin.id)
        )
        session.add(
            Auftrag(mandant_id=mandant.id, projekt_id=uuid.UUID(p_fremd), kunde_id=fremder_kunde.id, titel="F", erstellt_von=admin.id)
        )
    await make_vorgang(mandant=mandant, kunde=kunde, projekt_id=uuid.UUID(p_vorgang))
    vertrag = await make_vertrag(mandant=mandant, kunde=kunde)
    assert (await client.patch(f"/api/projekte/{p_vertrag}", headers=h, json={"vertrag_id": str(vertrag.id)})).status_code == 200
    assert (await client.get(_url(p_auftrag), headers=th)).status_code == 404

    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=user)
    for pid in (p_auftrag, p_vorgang, p_vertrag):
        assert (await client.get(_url(pid), headers=th)).status_code == 200, pid
    assert (await client.get(_url(p_fremd), headers=th)).status_code == 404


@pytest.mark.asyncio
async def test_projekte_sehen_liest_ohne_mitarbeit(client, make_mandant, make_user):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    el = await _element(client, h, pid, start_am=_d(0), ende_am=_d(4))
    typ = await _make_custom_mit_projekte_recht(mandant, aktionen={"sehen", "zeitplan_beantragen"})
    user = await _make_custom_user(mandant, typ)
    uh = auth_headers(await login(client, user.email, "hunter2!!"))

    assert await _alle_lese_endpunkte(client, uh, pid, el["id"]) == {
        "zeitplan": 200, "pdf": 200, "basisplaene": 200, "antraege": 200, "antrag_anlegen": 201, "zurueckziehen": 200,
    }


@pytest.mark.asyncio
async def test_meine_zeitplaene_filter(client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    techniker, th = await _techniker(client, make_user, mandant)
    p_zust = await _projekt(client, h, "Zustaendig")
    p_vorgang = await _projekt(client, h, "Per Vorgang")
    p_kunde = await _projekt(client, h, "Per Kunde")
    p_fremd = await _projekt(client, h, "Fremd")
    p_archiv = await _projekt(client, h, "Archiv")

    await _element(client, h, p_zust, titel="Heute", start_am=_d(-5), ende_am=_d(-3), zugewiesen_an=str(techniker.id))
    await _element(client, h, p_zust, titel="Spaeter", start_am=_d(7), ende_am=_d(9))
    await _element(client, h, p_zust, titel="Bald", start_am=_d(2), ende_am=_d(3))

    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, zugewiesener_user_id=techniker.id)
    await _element(client, h, p_vorgang, titel="V", start_am=_d(1), ende_am=_d(2), vorgang_id=str(vorgang.id))

    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    vorgang_kunde = await make_vorgang(mandant=mandant, kunde=kunde, projekt_id=uuid.UUID(p_kunde))
    assert vorgang_kunde.projekt_id is not None
    await _element(client, h, p_fremd, titel="Fremd", start_am=_d(1), ende_am=_d(2))
    await _element(client, h, p_archiv, titel="Arch", start_am=_d(1), ende_am=_d(2), zugewiesen_an=str(techniker.id))
    await client.patch(f"/api/projekte/{p_archiv}", headers=h, json={"archiviert": True})

    liste = (await client.get("/api/projekte/meine-zeitplaene", headers=th)).json()
    namen = {p["name"]: p for p in liste}
    assert set(namen) == {"Zustaendig", "Per Vorgang", "Per Kunde"}
    assert namen["Zustaendig"]["naechster_schritt_titel"] == "Bald"
    assert namen["Zustaendig"]["naechster_schritt_start"] == _d(2)
    assert namen["Per Kunde"]["naechster_schritt_titel"] is None

    # Admin sieht alle aktiven Projekte
    alle = (await client.get("/api/projekte/meine-zeitplaene", headers=h)).json()
    assert {p["name"] for p in alle} == {"Zustaendig", "Per Vorgang", "Per Kunde", "Fremd"}


def _alembic_cfg() -> Config:
    cfg = Config(os.path.join(_BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND_DIR, "alembic"))
    return cfg


@pytest.mark.asyncio
async def test_migration_0095_up_down_up_mit_rechte_backfill(make_mandant):
    mandant = await make_mandant()
    cfg = _alembic_cfg()
    engine = sqlalchemy.create_engine(get_settings().database_url_sync)
    command.downgrade(cfg, "0094")
    try:
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("SELECT set_config('app.is_super_admin', 'true', true)"))
            ids = {}
            for name in ("Techniker", "Leser", "Nichts"):
                ids[name] = conn.execute(
                    sqlalchemy.text(
                        "INSERT INTO account_typen (id, mandant_id, name) VALUES (gen_random_uuid(), :m, :n) RETURNING id"
                    ),
                    {"m": mandant.id, "n": name},
                ).scalar_one()
            conn.execute(
                sqlalchemy.text(
                    "INSERT INTO account_typ_rechte (id, account_typ_id, bereich, aktion, erlaubt) "
                    "VALUES (gen_random_uuid(), :t, 'projekte', 'sehen', true)"
                ),
                {"t": ids["Leser"]},
            )
        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("SELECT set_config('app.is_super_admin', 'true', true)"))
            rows = conn.execute(
                sqlalchemy.text(
                    "SELECT account_typ_id, aktion, erlaubt FROM account_typ_rechte "
                    "WHERE aktion LIKE 'zeitplan_%' AND account_typ_id = ANY(:ids)"
                ),
                {"ids": list(ids.values())},
            ).all()
        assert {(r[0], r[1], r[2]) for r in rows} == {
            (ids[n], a, True) for n in ("Techniker", "Leser") for a in ("zeitplan_sehen", "zeitplan_beantragen")
        }
        # zweiter Lauf (down/up) ist idempotent
        command.downgrade(cfg, "0094")
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("SELECT set_config('app.is_super_admin', 'true', true)"))
            assert conn.execute(
                sqlalchemy.text("SELECT count(*) FROM account_typ_rechte WHERE aktion LIKE 'zeitplan_%'")
            ).scalar_one() == 0
            assert conn.execute(sqlalchemy.text("SELECT to_regclass('zeitplan_aenderungsantraege')")).scalar_one() is None
    finally:
        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("SELECT set_config('app.is_super_admin', 'true', true)"))
            conn.execute(
                sqlalchemy.text(
                    "DELETE FROM account_typ_rechte WHERE account_typ_id IN (SELECT id FROM account_typen WHERE mandant_id = :m)"
                ),
                {"m": mandant.id},
            )
            conn.execute(sqlalchemy.text("DELETE FROM account_typen WHERE mandant_id = :m"), {"m": mandant.id})
        engine.dispose()
