"""Kette Projekt > Auftrag > Vorgang, "Eigenstaendig fuehren", /verknuepfung,
Zaehler an Auftrag/Projekt (Konzept auftrag-projekt)."""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import system_session
from app.models.account_typ import AccountTyp, AccountTypRecht
from app.models.mangel import Mangel
from app.models.user import User
from app.models.zeiterfassung import Zeiterfassung
from app.services.organigramm_sync_service import besetzung_pflegen
from tests.conftest import auth_headers, login

PW = "pw-123456"
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def _user_mit_rechten(mandant, rechte: dict[str, set[str]], name: str = "Tester") -> User:
    async with system_session(grund="test") as session:
        typ = AccountTyp(mandant_id=mandant.id, name=f"Typ-{uuid.uuid4().hex[:6]}")
        session.add(typ)
        await session.flush()
        for bereich, aktionen in rechte.items():
            for aktion in aktionen:
                session.add(AccountTypRecht(account_typ_id=typ.id, bereich=bereich, aktion=aktion, erlaubt=True))
        await session.flush()
        user = User(
            mandant_id=mandant.id,
            email=f"{uuid.uuid4().hex[:10]}@example.de",
            password_hash=hash_password(PW),
            role="custom",
            account_typ_id=typ.id,
            name=name,
        )
        session.add(user)
        await session.flush()
        await besetzung_pflegen(session, user, neu=True)
        await session.refresh(user)
        return user


VORGANG_RECHTE = {
    "vorgaenge": {"sehen", "erstellen", "bearbeiten"},
    "projekte": {"sehen"},
}


@pytest.fixture
async def umgebung(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW, name="Chefin")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, PW)
    h = auth_headers(token)

    async def post(pfad, **json):
        r = await client.post(pfad, headers=h, json=json)
        assert r.status_code in (200, 201), r.text
        return r.json()

    projekt_a = await post("/api/projekte", name="Projekt A")
    projekt_b = await post("/api/projekte", name="Projekt B")
    auftrag_a = await post("/api/auftraege", titel="Auftrag A", projekt_id=projekt_a["id"])
    auftrag_b = await post("/api/auftraege", titel="Auftrag B", projekt_id=projekt_b["id"])
    auftrag_frei = await post("/api/auftraege", titel="Auftrag ohne Projekt")

    async def vorgang(**extra):
        return await post(
            "/api/vorgaenge",
            kunde_id=str(kunde.id), titel=extra.pop("titel", "V"), abrechnungsart="aufwand",
            leistungstyp="stoerung", **extra,
        )

    class U:
        pass

    u = U()
    u.mandant, u.admin, u.kunde, u.h, u.client = mandant, admin, kunde, h, client
    u.projekt_a, u.projekt_b, u.auftrag_a, u.auftrag_b, u.auftrag_frei = (
        projekt_a, projekt_b, auftrag_a, auftrag_b, auftrag_frei,
    )
    u.vorgang = vorgang
    return u


async def _get(u, pfad, h=None):
    return await u.client.get(pfad, headers=h or u.h)


async def _patch(u, pfad, h=None, **json):
    return await u.client.patch(pfad, headers=h or u.h, json=json)


@pytest.mark.asyncio
async def test_anlegen_mit_auftrag_uebernimmt_projekt(umgebung):
    u = umgebung
    v = await u.vorgang(auftrag_id=u.auftrag_a["id"])
    assert v["projekt_id"] == u.projekt_a["id"]
    assert v["projekt_name"] == "Projekt A"
    assert v["auftrag_titel"] == "Auftrag A"
    assert v["verknuepfung_eigenstaendig"] is False
    assert v["darf_eigenstaendig_setzen"] is True

    # Auftrag ohne Projekt -> Vorgang ohne Projekt (auch None).
    v2 = await u.vorgang(auftrag_id=u.auftrag_frei["id"])
    assert v2["projekt_id"] is None and v2["auftrag_id"] == u.auftrag_frei["id"]


@pytest.mark.asyncio
async def test_anlegen_widerspruch_projekt_auftrag_400(umgebung):
    u = umgebung
    r = await u.client.post(
        "/api/vorgaenge", headers=u.h,
        json={"kunde_id": str(u.kunde.id), "titel": "X", "abrechnungsart": "aufwand", "leistungstyp": "stoerung",
              "auftrag_id": u.auftrag_a["id"], "projekt_id": u.projekt_b["id"]},
    )
    assert r.status_code == 400 and "passt nicht zum Auftrag" in r.json()["detail"]
    # Gleiches Projekt wie der Auftrag ist kein Widerspruch.
    v = await u.vorgang(auftrag_id=u.auftrag_a["id"], projekt_id=u.projekt_a["id"])
    assert v["projekt_id"] == u.projekt_a["id"]


@pytest.mark.asyncio
async def test_patch_auftrag_zieht_projekt_nach_und_schreibt_event(umgebung):
    u = umgebung
    v = await u.vorgang(projekt_id=u.projekt_b["id"])
    r = await _patch(u, f"/api/vorgaenge/{v['id']}", auftrag_id=u.auftrag_a["id"])
    assert r.status_code == 200
    assert r.json()["projekt_id"] == u.projekt_a["id"] and r.json()["auftrag_id"] == u.auftrag_a["id"]

    events = (await _get(u, f"/api/vorgaenge/{v['id']}/events")).json()
    ereignis = next(e for e in events if e["event_type"] == "zuordnung_geaendert")
    assert ereignis["payload"]["alt"]["projekt_name"] == "Projekt B"
    assert ereignis["payload"]["neu"]["auftrag_titel"] == "Auftrag A"
    assert ereignis["payload"]["neu"]["projekt_id"] == u.projekt_a["id"]


@pytest.mark.asyncio
async def test_patch_widerspruch_und_projektwechsel_bei_bleibendem_auftrag_400(umgebung):
    u = umgebung
    v = await u.vorgang(auftrag_id=u.auftrag_a["id"])
    r = await _patch(u, f"/api/vorgaenge/{v['id']}", auftrag_id=u.auftrag_b["id"], projekt_id=u.projekt_a["id"])
    assert r.status_code == 400
    r = await _patch(u, f"/api/vorgaenge/{v['id']}", projekt_id=u.projekt_b["id"])
    assert r.status_code == 400
    # Unveraenderte Werte (PATCH mit vollem Formular) sind erlaubt und erzeugen kein Event.
    r = await _patch(u, f"/api/vorgaenge/{v['id']}", auftrag_id=u.auftrag_a["id"], projekt_id=u.projekt_a["id"])
    assert r.status_code == 200
    events = (await _get(u, f"/api/vorgaenge/{v['id']}/events")).json()
    assert not [e for e in events if e["event_type"] == "zuordnung_geaendert"]


@pytest.mark.asyncio
async def test_auftrag_entfernen_behaelt_projekt(umgebung):
    u = umgebung
    v = await u.vorgang(auftrag_id=u.auftrag_a["id"])
    r = await _patch(u, f"/api/vorgaenge/{v['id']}", auftrag_id=None)
    assert r.status_code == 200
    assert r.json()["auftrag_id"] is None and r.json()["projekt_id"] == u.projekt_a["id"]


@pytest.mark.asyncio
async def test_auftrag_projektwechsel_zieht_vorgaenge_mit_eigenstaendige_bleiben(umgebung):
    u = umgebung
    normal = await u.vorgang(auftrag_id=u.auftrag_a["id"], titel="normal")
    fest = await u.vorgang(auftrag_id=u.auftrag_a["id"], titel="fest")
    assert (await u.client.post(f"/api/vorgaenge/{fest['id']}/eigenstaendig", headers=u.h, json={"eigenstaendig": True})).status_code == 200

    r = await _patch(u, f"/api/auftraege/{u.auftrag_a['id']}", projekt_id=u.projekt_b["id"])
    assert r.status_code == 200 and r.json()["projekt_name"] == "Projekt B"

    assert (await _get(u, f"/api/vorgaenge/{normal['id']}")).json()["projekt_id"] == u.projekt_b["id"]
    assert (await _get(u, f"/api/vorgaenge/{fest['id']}")).json()["projekt_id"] == u.projekt_a["id"]
    events = (await _get(u, f"/api/vorgaenge/{normal['id']}/events")).json()
    assert [e for e in events if e["event_type"] == "zuordnung_geaendert"]

    # Projekt entfernen: auch None wird mitgezogen.
    r = await _patch(u, f"/api/auftraege/{u.auftrag_a['id']}", projekt_id=None)
    assert r.status_code == 200
    assert (await _get(u, f"/api/vorgaenge/{normal['id']}")).json()["projekt_id"] is None


@pytest.mark.asyncio
async def test_zuordnungswechsel_an_eigenstaendigem_vorgang_409(umgebung):
    u = umgebung
    v = await u.vorgang(auftrag_id=u.auftrag_a["id"])
    await u.client.post(f"/api/vorgaenge/{v['id']}/eigenstaendig", headers=u.h, json={"eigenstaendig": True})
    r = await _patch(u, f"/api/vorgaenge/{v['id']}", auftrag_id=u.auftrag_b["id"])
    assert r.status_code == 409 and "eigenständig" in r.json()["detail"]
    r = await _patch(u, f"/api/vorgaenge/{v['id']}", auftrag_id=None)
    assert r.status_code == 409
    # Nicht-Zuordnungsfelder bleiben aenderbar, unveraenderte Zuordnung ebenfalls.
    r = await _patch(u, f"/api/vorgaenge/{v['id']}", titel="neu", auftrag_id=u.auftrag_a["id"])
    assert r.status_code == 200 and r.json()["titel"] == "neu"
    # Nach dem Aufheben geht der Wechsel wieder.
    await u.client.post(f"/api/vorgaenge/{v['id']}/eigenstaendig", headers=u.h, json={"eigenstaendig": False})
    r = await _patch(u, f"/api/vorgaenge/{v['id']}", auftrag_id=u.auftrag_b["id"])
    assert r.status_code == 200 and r.json()["projekt_id"] == u.projekt_b["id"]


@pytest.mark.asyncio
async def test_eigenstaendig_endpoint_felder_events_und_400(umgebung):
    u = umgebung
    ohne = await u.vorgang()
    r = await u.client.post(f"/api/vorgaenge/{ohne['id']}/eigenstaendig", headers=u.h, json={"eigenstaendig": True})
    assert r.status_code == 400

    v = await u.vorgang(auftrag_id=u.auftrag_a["id"])
    r = await u.client.post(f"/api/vorgaenge/{v['id']}/eigenstaendig", headers=u.h, json={"eigenstaendig": True})
    assert r.status_code == 200
    body = r.json()
    assert body["verknuepfung_eigenstaendig"] is True
    assert body["verknuepfung_eigenstaendig_am"] is not None
    assert body["verknuepfung_eigenstaendig_von_name"] == "Chefin"
    assert body["projekt_name"] == "Projekt A"

    # Idempotent: zweites Setzen schreibt kein weiteres Event.
    await u.client.post(f"/api/vorgaenge/{v['id']}/eigenstaendig", headers=u.h, json={"eigenstaendig": True})
    r = await u.client.post(f"/api/vorgaenge/{v['id']}/eigenstaendig", headers=u.h, json={"eigenstaendig": False})
    assert r.json()["verknuepfung_eigenstaendig"] is False
    assert r.json()["verknuepfung_eigenstaendig_am"] is None
    typen = [e["event_type"] for e in (await _get(u, f"/api/vorgaenge/{v['id']}/events")).json()]
    assert typen.count("eigenstaendig_gesetzt") == 1 and typen.count("eigenstaendig_aufgehoben") == 1


@pytest.mark.asyncio
async def test_rechte_403_ausblendung_und_filter(umgebung, make_kunde_zuweisung):
    u = umgebung
    v = await u.vorgang(auftrag_id=u.auftrag_a["id"], titel="geheim")
    sichtbar = await u.vorgang(auftrag_id=u.auftrag_a["id"], titel="normal")
    await u.client.post(f"/api/vorgaenge/{v['id']}/eigenstaendig", headers=u.h, json={"eigenstaendig": True})

    monteur = await _user_mit_rechten(u.mandant, VORGANG_RECHTE, "Monteur")
    hm = auth_headers(await login(u.client, monteur.email, PW))
    dispo = await _user_mit_rechten(u.mandant, {**VORGANG_RECHTE, "vorgaenge": {"sehen", "bearbeiten", "eigenstaendig_setzen"}}, "Dispo")
    hd = auth_headers(await login(u.client, dispo.email, PW))

    # Ohne Recht: 403 am Endpoint.
    r = await u.client.post(f"/api/vorgaenge/{sichtbar['id']}/eigenstaendig", headers=hm, json={"eigenstaendig": True})
    assert r.status_code == 403

    # Ohne Recht: Zuordnung des eigenstaendigen Vorgangs ist serverseitig leer ...
    r = await _get(u, f"/api/vorgaenge/{v['id']}", hm)
    gelesen = r.json()
    assert gelesen["projekt_id"] is None and gelesen["auftrag_id"] is None
    assert gelesen["projekt_name"] is None and gelesen["auftrag_titel"] is None
    assert gelesen["darf_eigenstaendig_setzen"] is False
    # ... beim normalen Vorgang sichtbar.
    r = await _get(u, f"/api/vorgaenge/{sichtbar['id']}", hm)
    assert r.json()["projekt_name"] == "Projekt A" and r.json()["auftrag_titel"] == "Auftrag A"

    # Liste und Filter: eigenstaendiger Vorgang erscheint nicht ueber projekt_id/auftrag_id.
    liste = (await _get(u, f"/api/vorgaenge?auftrag_id={u.auftrag_a['id']}", hm)).json()
    assert [x["id"] for x in liste] == [sichtbar["id"]]
    alle = {x["id"]: x for x in (await _get(u, "/api/vorgaenge", hm)).json()}
    assert alle[v["id"]]["projekt_id"] is None

    # /verknuepfung: 404 ausgeblendet, 200 beim normalen Vorgang (ohne den eigenstaendigen Geschwister).
    assert (await _get(u, f"/api/vorgaenge/{v['id']}/verknuepfung", hm)).status_code == 404
    r = await _get(u, f"/api/vorgaenge/{sichtbar['id']}/verknuepfung", hm)
    assert r.status_code == 200
    assert [g["id"] for g in r.json()["geschwister"]] == [sichtbar["id"]]

    # Verlauf: Eigenstaendig-Ereignis fuer Monteur unsichtbar, fuer Dispo sichtbar.
    typen_monteur = [e["event_type"] for e in (await _get(u, f"/api/vorgaenge/{v['id']}/events", hm)).json()]
    assert "eigenstaendig_gesetzt" not in typen_monteur
    typen_dispo = [e["event_type"] for e in (await _get(u, f"/api/vorgaenge/{v['id']}/events", hd)).json()]
    assert "eigenstaendig_gesetzt" in typen_dispo

    # Feed: Karte ohne Namen fuer Monteur, mit Namen fuer Dispo und beim normalen Vorgang.
    feed_m = {c["id"]: c for c in (await _get(u, "/api/feed", hm)).json()["items"]}
    assert feed_m[v["id"]]["projekt_name"] is None and feed_m[v["id"]]["auftrag_titel"] is None
    assert feed_m[sichtbar["id"]]["auftrag_titel"] == "Auftrag A"
    feed_d = {c["id"]: c for c in (await _get(u, "/api/feed", hd)).json()["items"]}
    assert feed_d[v["id"]]["projekt_name"] == "Projekt A"

    # Feed-Filter auftrag_id/projekt_id; eigenstaendiger Vorgang ohne Recht nicht darueber auffindbar.
    for filt in (f"auftrag_id={u.auftrag_a['id']}", f"projekt_id={u.projekt_a['id']}"):
        ids_m = {c["id"] for c in (await _get(u, f"/api/feed?{filt}", hm)).json()["items"]}
        ids_d = {c["id"] for c in (await _get(u, f"/api/feed?{filt}", hd)).json()["items"]}
        assert ids_m == {sichtbar["id"]} and ids_d == {sichtbar["id"], v["id"]}
    assert not (await _get(u, f"/api/feed?auftrag_id={u.auftrag_b['id']}", hd)).json()["items"]

    # Dispo mit Recht sieht alles und darf schalten.
    r = await _get(u, f"/api/vorgaenge/{v['id']}", hd)
    assert r.json()["projekt_id"] == u.projekt_a["id"] and r.json()["darf_eigenstaendig_setzen"] is True
    r = await u.client.post(f"/api/vorgaenge/{v['id']}/eigenstaendig", headers=hd, json={"eigenstaendig": False})
    assert r.status_code == 200 and r.json()["verknuepfung_eigenstaendig"] is False


@pytest.mark.asyncio
async def test_zeiterfassung_blendet_zuordnung_bei_eigenstaendig_aus(umgebung):
    u = umgebung
    v = await u.vorgang(auftrag_id=u.auftrag_a["id"])
    await u.client.post(f"/api/vorgaenge/{v['id']}/eigenstaendig", headers=u.h, json={"eigenstaendig": True})
    monteur = await _user_mit_rechten(
        u.mandant, {**VORGANG_RECHTE, "dispo": {"sehen"}}, "Monteur"
    )
    async with system_session(grund="test") as session:
        session.add(Zeiterfassung(
            mandant_id=u.mandant.id, vorgang_id=uuid.UUID(v["id"]), techniker_id=monteur.id,
            start_at=datetime.now(timezone.utc) - timedelta(hours=2), ende_at=datetime.now(timezone.utc),
        ))
    hm = auth_headers(await login(u.client, monteur.email, PW))
    eintraege = (await _get(u, f"/api/zeiterfassung?vorgang_id={v['id']}", hm)).json()
    assert eintraege and eintraege[0]["vorgang_auftrag_id"] is None and eintraege[0]["vorgang_projekt_id"] is None
    eintraege = (await _get(u, f"/api/zeiterfassung?vorgang_id={v['id']}")).json()
    assert eintraege[0]["vorgang_auftrag_id"] == u.auftrag_a["id"]


@pytest.mark.asyncio
async def test_mandantentrennung_fremdes_projekt_und_auftrag(umgebung, make_mandant, make_user):
    u = umgebung
    fremd = await make_mandant("Fremd")
    fremder_admin = await make_user(mandant=fremd, role="mandant_admin", password=PW)
    hf = auth_headers(await login(u.client, fremder_admin.email, PW))
    fremdes_projekt = (await u.client.post("/api/projekte", headers=hf, json={"name": "Fremd"})).json()
    fremder_auftrag = (await u.client.post("/api/auftraege", headers=hf, json={"titel": "Fremd"})).json()

    basis = {"kunde_id": str(u.kunde.id), "titel": "X", "abrechnungsart": "aufwand", "leistungstyp": "stoerung"}
    for extra in ({"auftrag_id": fremder_auftrag["id"]}, {"projekt_id": fremdes_projekt["id"]}):
        r = await u.client.post("/api/vorgaenge", headers=u.h, json={**basis, **extra})
        assert r.status_code == 400
    v = await u.vorgang()
    for extra in ({"auftrag_id": fremder_auftrag["id"]}, {"projekt_id": fremdes_projekt["id"]}):
        assert (await _patch(u, f"/api/vorgaenge/{v['id']}", **extra)).status_code == 400
    # Fremder Mandant sieht den Vorgang samt /verknuepfung nicht.
    assert (await _get(u, f"/api/vorgaenge/{v['id']}/verknuepfung", hf)).status_code in (403, 404)
    assert (await u.client.post(f"/api/vorgaenge/{v['id']}/eigenstaendig", headers=hf, json={"eigenstaendig": True})).status_code == 404


@pytest.mark.asyncio
async def test_verknuepfung_inhalt(umgebung):
    u = umgebung
    ohne = await u.vorgang()
    assert (await _get(u, f"/api/vorgaenge/{ohne['id']}/verknuepfung")).status_code == 404

    eltern = await u.vorgang(auftrag_id=u.auftrag_a["id"], titel="Eltern")
    kind = await u.vorgang(auftrag_id=u.auftrag_a["id"], titel="Kind", parent_vorgang_id=eltern["id"])
    await u.vorgang(auftrag_id=u.auftrag_b["id"], titel="Anderer Auftrag")

    async with system_session(grund="test") as session:
        jetzt = datetime.now(timezone.utc)
        for vid, std in ((eltern["id"], 1), (kind["id"], 2)):
            session.add(Zeiterfassung(
                mandant_id=u.mandant.id, vorgang_id=uuid.UUID(vid), techniker_id=u.admin.id,
                start_at=jetzt - timedelta(hours=std), ende_at=jetzt,
            ))
        # laufender Timer zaehlt nicht
        session.add(Zeiterfassung(
            mandant_id=u.mandant.id, vorgang_id=uuid.UUID(kind["id"]), techniker_id=u.admin.id, start_at=jetzt,
        ))
        for status in ("offen", "behoben"):
            session.add(Mangel(
                mandant_id=u.mandant.id, vorgang_id=uuid.UUID(kind["id"]), beschreibung="M", status=status,
                gemeldet_von=u.admin.id,
            ))

    await _patch(u, f"/api/vorgaenge/{kind['id']}", auftrag_id=u.auftrag_a["id"])  # no-op
    await u.client.post(f"/api/vorgaenge/{kind['id']}/eigenstaendig", headers=u.h, json={"eigenstaendig": True})

    r = await _get(u, f"/api/vorgaenge/{kind['id']}/verknuepfung")
    assert r.status_code == 200
    d = r.json()
    assert d["projekt"] == {"id": u.projekt_a["id"], "name": "Projekt A"}
    assert d["auftrag"] == {"id": u.auftrag_a["id"], "titel": "Auftrag A", "status": "offen"}
    arten = [s["art"] for s in d["herkunft"]]
    assert arten[:2] == ["projekt_angelegt", "auftrag_angelegt"]
    assert arten.count("vorgang_angelegt") == 1 and arten.count("folge_vorgang") == 1
    assert arten[-1] == "eigenstaendig_gesetzt"
    assert all(s["ref_label"] in s["text"] for s in d["herkunft"] if s["ref_label"] and s["art"] != "zuordnung_geaendert")
    daten = [s["datum"] for s in d["herkunft"]]
    assert daten == sorted(daten)
    aktuell = [s for s in d["herkunft"] if s["aktuell"]]
    assert len(aktuell) == 1 and aktuell[0]["ref_id"] == kind["id"] and aktuell[0]["art"] == "folge_vorgang"
    assert aktuell[0]["person_name"] == "Chefin"
    assert next(s for s in d["herkunft"] if s["art"] == "projekt_angelegt")["ref_label"] == "Projekt A"

    rm = d["rueckmeldung"]
    assert rm["arbeitszeit_sekunden"] == 2 * 3600
    assert rm["arbeitszeit_sekunden_auftrag"] == 3 * 3600
    assert rm["offene_maengel"] == 1
    assert rm["positionen_anzahl"] == 0 and rm["positionen_netto"] is None
    assert rm["status"] == "neu"
    assert {g["id"] for g in d["geschwister"]} == {eltern["id"], kind["id"]}
    assert [g["id"] for g in d["geschwister"] if g["ist_aktuell"]] == [kind["id"]]

    # Zuordnungswechsel taucht als Herkunftsschritt auf.
    await u.client.post(f"/api/vorgaenge/{kind['id']}/eigenstaendig", headers=u.h, json={"eigenstaendig": False})
    await _patch(u, f"/api/vorgaenge/{kind['id']}", auftrag_id=u.auftrag_b["id"])
    d = (await _get(u, f"/api/vorgaenge/{kind['id']}/verknuepfung")).json()
    schritt = next(s for s in d["herkunft"] if s["art"] == "zuordnung_geaendert")
    assert schritt["ref_typ"] == "auftrag" and schritt["ref_label"] == "Auftrag B"
    assert "Auftrag A" in schritt["zusatz"]

    # Vorgang nur am Projekt (ohne Auftrag): Geschwister = andere ohne Auftrag am Projekt.
    direkt1 = await u.vorgang(projekt_id=u.projekt_a["id"], titel="d1")
    await u.vorgang(projekt_id=u.projekt_a["id"], titel="d2")
    d = (await _get(u, f"/api/vorgaenge/{direkt1['id']}/verknuepfung")).json()
    assert d["auftrag"] is None and len(d["geschwister"]) == 2
    assert d["rueckmeldung"]["arbeitszeit_sekunden_auftrag"] is None


@pytest.mark.asyncio
async def test_auftrag_und_projekt_zaehler(umgebung):
    u = umgebung
    v1 = await u.vorgang(auftrag_id=u.auftrag_a["id"])
    v2 = await u.vorgang(auftrag_id=u.auftrag_a["id"])
    v3 = await u.vorgang(auftrag_id=u.auftrag_a["id"])
    await u.vorgang(projekt_id=u.projekt_a["id"], faelligkeit_am=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat())
    await _patch(u, f"/api/vorgaenge/{v1['id']}", status="abgeschlossen")
    await _patch(u, f"/api/vorgaenge/{v2['id']}", status="storniert")
    del v3

    a = (await _get(u, f"/api/auftraege/{u.auftrag_a['id']}")).json()
    assert a["projekt_name"] == "Projekt A"
    assert a["vorgaenge_gesamt"] == 3 and a["vorgaenge_erledigt"] == 2
    liste = {x["id"]: x for x in (await _get(u, "/api/auftraege")).json()}
    assert liste[u.auftrag_frei["id"]]["projekt_name"] is None

    p = (await _get(u, f"/api/projekte/{u.projekt_a['id']}")).json()
    assert p["anzahl_auftraege"] == 1
    assert p["anzahl_vorgaenge"] == 4  # inkl. der Vorgaenge in Auftraegen
    assert p["anzahl_offen"] == 2 and p["anzahl_ueberfaellig"] == 1
    pl = {x["id"]: x for x in (await _get(u, "/api/projekte")).json()}
    assert pl[u.projekt_b["id"]]["anzahl_vorgaenge"] == 0 and pl[u.projekt_a["id"]]["anzahl_offen"] == 2


@pytest.mark.asyncio
async def test_registry_und_seed_vorlagen():
    from app.core.rechte_registry import aktionen_fuer_bereich
    from app.seed import SEED_ACCOUNT_TYPEN

    assert "eigenstaendig_setzen" in aktionen_fuer_bereich("vorgaenge")
    assert "eigenstaendig_setzen" in SEED_ACCOUNT_TYPEN["Disponent"]["rechte"]["vorgaenge"]
    assert "eigenstaendig_setzen" not in SEED_ACCOUNT_TYPEN["Techniker"]["rechte"]["vorgaenge"]


def _cfg() -> Config:
    cfg = Config(os.path.join(_BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND, "alembic"))
    return cfg


@pytest.mark.asyncio
async def test_migration_0118_bereinigt_widersprueche_und_ist_reversibel(umgebung):
    u = umgebung
    v = await u.vorgang(auftrag_id=u.auftrag_a["id"])
    # Widerspruch wie vor der Migration herstellen (der Code laesst ihn nicht mehr zu).
    owner = create_engine(os.environ.get("DATABASE_URL_SYNC") or get_settings().database_url_sync)
    try:
        await asyncio.to_thread(command.downgrade, _cfg(), "0117")
        with owner.connect() as conn:
            spalten = {r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'vorgaenge'"))}
            assert "verknuepfung_eigenstaendig" not in spalten
            conn.execute(text("ALTER TABLE vorgaenge NO FORCE ROW LEVEL SECURITY"))
            conn.execute(
                text("UPDATE vorgaenge SET projekt_id = :p WHERE id = :v"),
                {"p": u.projekt_b["id"], "v": v["id"]},
            )
            conn.execute(text("ALTER TABLE vorgaenge FORCE ROW LEVEL SECURITY"))
            conn.commit()

        await asyncio.to_thread(command.upgrade, _cfg(), "head")
        r = await _get(u, f"/api/vorgaenge/{v['id']}")
        assert r.json()["projekt_id"] == u.projekt_a["id"]  # Projekt des Auftrags gewinnt
        assert r.json()["verknuepfung_eigenstaendig"] is False
    finally:
        await asyncio.to_thread(command.upgrade, _cfg(), "head")
        owner.dispose()
