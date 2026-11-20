"""MCP-Ausbau Etappe A: verknuepfen, *_speichern, rueckgaengig, lesen/auflisten (neue Tools direkt), Registry."""
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.session import system_session
from app.mcp.aktionen import AKTIONEN, RUECKWEG_ROUTEN, UUID_MUSTER
from app.models.audit_log import AuditLog
from app.models.auftrag import Auftrag
from app.models.ki_aktion import KiAktion
from app.models.projekt import Projekt
from app.models.vorgang import Vorgang
from tests.conftest import auth_headers, login
from tests.mcp_helfer import (
    LESEN,
    PASSWORT,
    SCHREIBEN,
    custom_nutzer,
    ki_modul_setzen,
    mcp_client,  # noqa: F401
    mcp_laeuft,  # noqa: F401
    mcp_rpc,
    tool_aufrufen,
    verbinden,
)


async def _bereit(make_mandant, make_user, mcp_client, scopes=None):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    admin = await make_user(mandant=mandant, role="mandant_admin")
    t = await verbinden(mcp_client, admin, scopes or [LESEN, SCHREIBEN])
    kopf = auth_headers(await login(mcp_client, admin.email, PASSWORT))
    return mandant, admin, t["access_token"], kopf


async def _auftrag(mandant, admin, kunde, titel) -> uuid.UUID:
    async with system_session(grund="test") as db:
        a = Auftrag(mandant_id=mandant.id, kunde_id=kunde.id, titel=titel, erstellt_von=admin.id)
        db.add(a)
        await db.flush()
        return a.id


async def _vorgang_holen(id_) -> Vorgang:
    async with system_session(grund="test") as session:
        return await session.get(Vorgang, id_)


async def _journal(aktion_id) -> KiAktion:
    async with system_session(grund="test") as session:
        return await session.get(KiAktion, uuid.UUID(aktion_id))


async def _journal_alle(mandant_id) -> list[KiAktion]:
    async with system_session(grund="test") as session:
        return list((await session.execute(select(KiAktion).where(KiAktion.mandant_id == mandant_id))).scalars())


# --- verknuepfen ---------------------------------------------------------------------------------------


async def test_verknuepfen_zwei_vorgaenge_mit_auftrag_journal_und_rueckgaengig(
    make_mandant, make_user, make_kunde, make_vorgang, mcp_client
):
    mandant, admin, token, _ = await _bereit(make_mandant, make_user, mcp_client)
    kunde = await make_kunde(mandant=mandant)
    alt = await _auftrag(mandant, admin, kunde, "Wartung 2026")
    neu = await _auftrag(mandant, admin, kunde, "Sanierung Lindenstraße")
    v1 = await make_vorgang(mandant=mandant, kunde=kunde)
    v2 = await make_vorgang(mandant=mandant, kunde=kunde, auftrag_id=alt)

    r = await tool_aufrufen(
        mcp_client, token, "verknuepfen",
        {"objekt_typ": "vorgang", "objekt_ids": [str(v1.id), str(v2.id)], "mit_typ": "auftrag", "mit_id": str(neu)},
    )
    assert r["fehler"] is False, r["text"]
    d = r["daten"]
    assert d["zusammenfassung"] == "2 Vorgänge mit Auftrag Sanierung Lindenstraße verknüpft"
    assert d["stufe"] == 2 and d["rueckgaengig_bis"] and "rueckgaengig" in d["hinweis"]
    assert (await _vorgang_holen(v1.id)).auftrag_id == neu and (await _vorgang_holen(v2.id)).auftrag_id == neu

    # Journal: Vorher/Nachher je Vorgang, genau ein Eintrag fuer den ganzen Aufruf
    eintrag = await _journal(d["aktion_id"])
    assert eintrag.tool == "verknuepfen" and eintrag.aktionsart == "vorgang.verknuepfen" and eintrag.status == "ausgefuehrt"
    felder = {(a["id"], a["feld"]): a for a in eintrag.aenderungen}
    assert felder[(str(v2.id), "auftrag_id")]["vorher"]["anzeige"] == "Wartung 2026"
    assert felder[(str(v2.id), "auftrag_id")]["nachher"]["anzeige"] == "Sanierung Lindenstraße"
    assert felder[(str(v1.id), "auftrag_id")]["vorher"]["anzeige"] is None
    assert len(await _journal_alle(mandant.id)) == 1

    # Erneutes Verknuepfen ohne Wirkung: kein neuer Journal-Eintrag
    nochmal = await tool_aufrufen(
        mcp_client, token, "verknuepfen",
        {"objekt_typ": "vorgang", "objekt_ids": [str(v1.id)], "mit_typ": "auftrag", "mit_id": str(neu)},
    )
    assert nochmal["fehler"] is False and nochmal["daten"]["aktion_id"] is None
    assert len(await _journal_alle(mandant.id)) == 1

    z = await tool_aufrufen(mcp_client, token, "rueckgaengig", {"aktion_id": d["aktion_id"]})
    assert z["fehler"] is False, z["text"]
    assert (await _vorgang_holen(v1.id)).auftrag_id is None
    assert (await _vorgang_holen(v2.id)).auftrag_id == alt
    assert (await _journal(d["aktion_id"])).status == "rueckgaengig"
    nochmal_z = await tool_aufrufen(mcp_client, token, "rueckgaengig", {"aktion_id": d["aktion_id"]})
    assert nochmal_z["fehler"] is True


async def test_rueckgaengig_meldet_konflikt_nach_manueller_aenderung(
    make_mandant, make_user, make_kunde, make_vorgang, mcp_client
):
    mandant, admin, token, kopf = await _bereit(make_mandant, make_user, mcp_client)
    kunde = await make_kunde(mandant=mandant)
    a1 = await _auftrag(mandant, admin, kunde, "A1")
    a2 = await _auftrag(mandant, admin, kunde, "A2")
    v = await make_vorgang(mandant=mandant, kunde=kunde)
    r = await tool_aufrufen(
        mcp_client, token, "verknuepfen", {"objekt_typ": "vorgang", "objekt_ids": [str(v.id)], "mit_typ": "auftrag", "mit_id": str(a1)}
    )
    assert r["fehler"] is False, r["text"]
    # Ein Mensch haengt den Vorgang in der App um
    p = await mcp_client.patch(f"/api/vorgaenge/{v.id}", json={"auftrag_id": str(a2)}, headers=kopf)
    assert p.status_code == 200, p.text

    z = await tool_aufrufen(mcp_client, token, "rueckgaengig", {"aktion_id": r["daten"]["aktion_id"]})
    assert z["fehler"] is True and "geändert" in z["text"] and "A2" in z["text"]
    assert (await _vorgang_holen(v.id)).auftrag_id == a2
    assert (await _journal(r["daten"]["aktion_id"])).status == "ausgefuehrt"


async def test_verknuepfen_techniker_mit_scope_eigene_nicht_an_fremdem_vorgang(
    make_mandant, make_user, make_kunde, make_vorgang, mcp_client
):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    admin = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant)
    auftrag = await _auftrag(mandant, admin, kunde, "A")
    tech = await custom_nutzer(
        mandant,
        "Techniker",
        {"vorgaenge": ("sehen", "bearbeiten"), "projekte": ("sehen",), "ki_zugriff": ("sehen", "bearbeiten")},
        scopes_je_bereich={"vorgaenge": "eigene", "ki_zugriff": "mandant"},
    )
    kollege = await custom_nutzer(mandant, "Kollege", {"vorgaenge": ("sehen",)})
    fremder = await make_vorgang(mandant=mandant, kunde=kunde, zugewiesener_user_id=kollege.id)
    eigener = await make_vorgang(mandant=mandant, kunde=kunde, zugewiesener_user_id=tech.id)
    t = await verbinden(mcp_client, tech, [LESEN, SCHREIBEN])
    nein = await tool_aufrufen(
        mcp_client, t["access_token"], "verknuepfen",
        {"objekt_typ": "vorgang", "objekt_ids": [str(fremder.id)], "mit_typ": "auftrag", "mit_id": str(auftrag)},
    )
    assert nein["fehler"] is True
    assert (await _vorgang_holen(fremder.id)).auftrag_id is None
    assert await _journal_alle(mandant.id) == []
    # Teilerfolg: eigener Vorgang geht, der fremde stoppt; Erledigtes steht im Journal und die Antwort nennt den Fehler
    teil = await tool_aufrufen(
        mcp_client, t["access_token"], "verknuepfen",
        {"objekt_typ": "vorgang", "objekt_ids": [str(eigener.id), str(fremder.id)], "mit_typ": "auftrag", "mit_id": str(auftrag)},
    )
    assert teil["fehler"] is False and teil["daten"]["fehler"] and str(fremder.id) in teil["daten"]["fehler"]
    assert (await _vorgang_holen(eigener.id)).auftrag_id == auftrag
    assert len(await _journal_alle(mandant.id)) == 1


async def test_lese_scope_sieht_verknuepfen_nicht_und_kann_es_nicht_aufrufen(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, admin, token, _ = await _bereit(make_mandant, make_user, mcp_client, [LESEN])
    namen = {x["name"] for x in (await mcp_rpc(mcp_client, token, "tools/list")).json()["result"]["tools"]}
    assert "verknuepfen" not in namen and "vorgang_speichern" not in namen and "rueckgaengig" not in namen
    kunde = await make_kunde(mandant=mandant)
    v = await make_vorgang(mandant=mandant, kunde=kunde)
    r = await tool_aufrufen(
        mcp_client, token, "verknuepfen", {"objekt_typ": "vorgang", "objekt_ids": [str(v.id)], "mit_typ": "projekt", "mit_id": str(uuid.uuid4())}
    )
    assert r["fehler"] is True


async def test_verknuepfen_unbekannte_kombination_und_anlage_und_blockiert_von(
    make_mandant, make_user, make_kunde, make_anlage, make_vorgang, mcp_client
):
    mandant, admin, token, _ = await _bereit(make_mandant, make_user, mcp_client)
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    v1 = await make_vorgang(mandant=mandant, kunde=kunde)
    v2 = await make_vorgang(mandant=mandant, kunde=kunde)
    falsch = await tool_aufrufen(
        mcp_client, token, "verknuepfen", {"objekt_typ": "auftrag", "objekt_ids": [str(v1.id)], "mit_typ": "anlage", "mit_id": str(anlage.id)}
    )
    assert falsch["fehler"] is True and "Möglich" in falsch["text"]

    ok = await tool_aufrufen(
        mcp_client, token, "verknuepfen", {"objekt_typ": "vorgang", "objekt_ids": [str(v1.id)], "mit_typ": "anlage", "mit_id": str(anlage.id)}
    )
    assert ok["fehler"] is False, ok["text"]
    blockiert = await tool_aufrufen(
        mcp_client, token, "verknuepfen", {"objekt_typ": "vorgang", "objekt_ids": [str(v1.id)], "mit_typ": "vorgang", "mit_id": str(v2.id)}
    )
    assert blockiert["fehler"] is False, blockiert["text"]
    zurueck = await tool_aufrufen(mcp_client, token, "rueckgaengig", {"aktion_id": ok["daten"]["aktion_id"]})
    assert zurueck["fehler"] is False, zurueck["text"]
    # Loesen einer Abhaengigkeit mit anschliessendem Rueckgaengig stellt sie wieder her
    los = await tool_aufrufen(
        mcp_client, token, "verknuepfen",
        {"objekt_typ": "vorgang", "objekt_ids": [str(v1.id)], "mit_typ": "vorgang", "mit_id": str(v2.id), "loesen": True},
    )
    assert los["fehler"] is False and "nicht mehr blockiert" in los["daten"]["zusammenfassung"]
    wieder = await tool_aufrufen(mcp_client, token, "rueckgaengig", {"aktion_id": los["daten"]["aktion_id"]})
    assert wieder["fehler"] is False, wieder["text"]
    liste = await tool_aufrufen(mcp_client, token, "lesen", {"typ": "vorgang", "id": str(v1.id), "umfang": "kurz"})
    assert liste["fehler"] is False


# --- vorgang_speichern ---------------------------------------------------------------------------------


async def test_vorgang_speichern_anlegen_aendern_leeren_und_status_sperre(make_mandant, make_user, make_kunde, mcp_client):
    mandant, admin, token, _ = await _bereit(make_mandant, make_user, mcp_client)
    kunde = await make_kunde(mandant=mandant)
    r = await tool_aufrufen(
        mcp_client, token, "vorgang_speichern",
        {"kunde_id": str(kunde.id), "titel": "Pumpe tauschen", "leistungstyp": "wartung", "zugewiesener_user_id": str(admin.id)},
    )
    assert r["fehler"] is False, r["text"]
    [erzeugt] = r["daten"]["erzeugt"]
    v = await _vorgang_holen(uuid.UUID(erzeugt["id"]))
    assert v.erstellt_via == "ki" and v.status == "neu" and v.zugewiesener_user_id == admin.id
    assert r["daten"]["link"].endswith(f"/vorgaenge/{v.id}")

    frist = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0)
    aender = await tool_aufrufen(
        mcp_client, token, "vorgang_speichern",
        {"id": str(v.id), "faelligkeit_am": frist.isoformat(), "titel": "Pumpe tauschen (EG)", "status": "in_arbeit"},
    )
    assert aender["fehler"] is False, aender["text"]
    felder = {a["feld"]: a for a in aender["daten"]["aenderungen"]}
    assert set(felder) == {"faelligkeit_am", "titel", "status"} and felder["titel"]["vorher"] == "Pumpe tauschen"
    assert (await _vorgang_holen(v.id)).status == "in_arbeit"

    leer = await tool_aufrufen(mcp_client, token, "vorgang_speichern", {"id": str(v.id), "felder_leeren": ["faelligkeit_am", "zugewiesener_user_id"]})
    assert leer["fehler"] is False, leer["text"]
    nachher = await _vorgang_holen(v.id)
    assert nachher.faelligkeit_am is None and nachher.zugewiesener_user_id is None and nachher.titel == "Pumpe tauschen (EG)"
    # Pflichtfeld laesst sich nicht leeren, Widerspruch wird abgelehnt
    assert (await tool_aufrufen(mcp_client, token, "vorgang_speichern", {"id": str(v.id), "felder_leeren": ["titel"]}))["fehler"] is True
    assert (
        await tool_aufrufen(mcp_client, token, "vorgang_speichern", {"id": str(v.id), "titel": "x", "felder_leeren": ["titel"]})
    )["fehler"] is True
    # Unveraendert: keine Journal-Zeile
    anzahl = len(await _journal_alle(mandant.id))
    gleich = await tool_aufrufen(mcp_client, token, "vorgang_speichern", {"id": str(v.id), "titel": "Pumpe tauschen (EG)"})
    assert gleich["fehler"] is False and gleich["daten"]["aktion_id"] is None
    assert len(await _journal_alle(mandant.id)) == anzahl

    for status in ("abgeschlossen", "storniert", "abgerechnet"):
        s = await tool_aufrufen(mcp_client, token, "vorgang_speichern", {"id": str(v.id), "status": status})
        assert s["fehler"] is True and "nächsten Ausbaustufe" in s["text"] or status == "abgerechnet" and s["fehler"] is True
    assert (await _vorgang_holen(v.id)).status == "in_arbeit"
    # Anlegen ohne Pflichtfeld
    assert (await tool_aufrufen(mcp_client, token, "vorgang_speichern", {"kunde_id": str(kunde.id), "titel": "x"}))["fehler"] is True


async def test_vorgang_speichern_undo_anlegen_und_aendern(make_mandant, make_user, make_kunde, mcp_client):
    mandant, admin, token, _ = await _bereit(make_mandant, make_user, mcp_client)
    kunde = await make_kunde(mandant=mandant)
    r = await tool_aufrufen(
        mcp_client, token, "vorgang_speichern", {"kunde_id": str(kunde.id), "titel": "Neu", "leistungstyp": "beratung"}
    )
    vid = uuid.UUID(r["daten"]["erzeugt"][0]["id"])
    a = await tool_aufrufen(mcp_client, token, "vorgang_speichern", {"id": str(vid), "titel": "Geaendert", "prioritaet": 1})
    z1 = await tool_aufrufen(mcp_client, token, "rueckgaengig", {"aktion_id": a["daten"]["aktion_id"]})
    assert z1["fehler"] is False, z1["text"]
    v = await _vorgang_holen(vid)
    assert v.titel == "Neu" and v.prioritaet == 3
    # Das Anlegen ist nach einer spaeteren Aenderung (auch einer zurueckgenommenen) nicht mehr "unveraendert": Konflikt.
    z2 = await tool_aufrufen(mcp_client, token, "rueckgaengig", {"aktion_id": r["daten"]["aktion_id"]})
    assert z2["fehler"] is True and "Zuletzt geändert" in z2["text"]
    assert (await _vorgang_holen(vid)).geloescht_am is None
    frisch = await tool_aufrufen(
        mcp_client, token, "vorgang_speichern", {"kunde_id": str(kunde.id), "titel": "Nur angelegt", "leistungstyp": "beratung"}
    )
    z3 = await tool_aufrufen(mcp_client, token, "rueckgaengig", {"aktion_id": frisch["daten"]["aktion_id"]})
    assert z3["fehler"] is False, z3["text"]
    assert (await _vorgang_holen(uuid.UUID(frisch["daten"]["erzeugt"][0]["id"]))).geloescht_am is not None


async def test_audit_log_traegt_ki_aktion_id(make_mandant, make_user, make_kunde, mcp_client):
    mandant, admin, token, _ = await _bereit(make_mandant, make_user, mcp_client)
    kunde = await make_kunde(mandant=mandant)
    r = await tool_aufrufen(
        mcp_client, token, "vorgang_speichern", {"kunde_id": str(kunde.id), "titel": "Audit", "leistungstyp": "planung"}
    )
    aktion_id = r["daten"]["aktion_id"]
    async with system_session(grund="test") as session:
        zeilen = list((await session.execute(select(AuditLog).where(AuditLog.mandant_id == mandant.id))).scalars())
    markiert = [z for z in zeilen if z.payload.get("ki_aktion_id") == aktion_id]
    assert markiert and all(z.payload.get("quelle") == "ki" for z in markiert)


# --- auftrag/projekt/aufgabe/termin/kunde_speichern ---------------------------------------------------


async def _anlegen_aendern_undo(mcp_client, token, tool, anlegen, aender, pruefen, kopf=None, basis=None):
    """Anlegen -> Aendern -> Aenderung zurueck; danach ein zweites, unveraendertes Anlegen -> zurueck (verschwindet)."""
    r = await tool_aufrufen(mcp_client, token, tool, anlegen)
    assert r["fehler"] is False, r["text"]
    [erzeugt] = r["daten"]["erzeugt"]
    a = await tool_aufrufen(mcp_client, token, tool, {"id": erzeugt["id"], **aender})
    assert a["fehler"] is False, a["text"]
    assert a["daten"]["aenderungen"], a["daten"]
    await pruefen("nachher", erzeugt["id"])
    z = await tool_aufrufen(mcp_client, token, "rueckgaengig", {"aktion_id": a["daten"]["aktion_id"]})
    assert z["fehler"] is False, z["text"]
    await pruefen("zurueck", erzeugt["id"])
    zweites = await tool_aufrufen(mcp_client, token, tool, anlegen)
    assert zweites["fehler"] is False, zweites["text"]
    z = await tool_aufrufen(mcp_client, token, "rueckgaengig", {"aktion_id": zweites["daten"]["aktion_id"]})
    assert z["fehler"] is False, z["text"]
    if kopf is not None:
        weg = await mcp_client.get(f"{basis}/{zweites['daten']['erzeugt'][0]['id']}", headers=kopf)
        assert weg.status_code == 404, weg.text
    return zweites["daten"]["erzeugt"][0]["id"]


async def test_auftrag_und_projekt_speichern(make_mandant, make_user, make_kunde, mcp_client):
    mandant, admin, token, kopf = await _bereit(make_mandant, make_user, mcp_client)
    kunde = await make_kunde(mandant=mandant)

    async def pruefe_auftrag(wann, id_):
        async with system_session(grund="test") as s:
            a = await s.get(Auftrag, uuid.UUID(id_))
        assert a.titel == ("Neuer Titel" if wann == "nachher" else "Wallbox") and a.erstellt_via == "ki"

    aid = await _anlegen_aendern_undo(
        mcp_client, token, "auftrag_speichern", {"titel": "Wallbox", "kunde_id": str(kunde.id)}, {"titel": "Neuer Titel"}, pruefe_auftrag, kopf, "/api/auftraege"
    )
    async with system_session(grund="test") as s:
        assert (await s.get(Auftrag, uuid.UUID(aid))).geloescht_am is not None
    st = await tool_aufrufen(mcp_client, token, "auftrag_speichern", {"titel": "X", "status": "abgeschlossen"})
    assert st["fehler"] is True

    async def pruefe_projekt(wann, id_):
        async with system_session(grund="test") as s:
            p = await s.get(Projekt, uuid.UUID(id_))
        assert p.name == ("Umbau Ost" if wann == "nachher" else "Umbau") and p.erstellt_via == "ki"

    await _anlegen_aendern_undo(mcp_client, token, "projekt_speichern", {"name": "Umbau"}, {"name": "Umbau Ost"}, pruefe_projekt, kopf, "/api/projekte")


async def test_aufgabe_termin_kunde_speichern(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, admin, token, kopf = await _bereit(make_mandant, make_user, mcp_client)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)

    async def api(pfad):
        r = await mcp_client.get(pfad, headers=kopf)
        return r.json() if r.status_code == 200 else None

    async def pruefe_aufgabe(wann, id_):
        a = await api(f"/api/projekt-aufgaben/{id_}")
        if wann == "nachher":
            assert a["erledigt_am"] is not None and a["titel"] == "Rueckruf Kunde"
        else:
            assert a["erledigt_am"] is None and a["titel"] == "Rueckruf Kunde"

    await _anlegen_aendern_undo(
        mcp_client, token, "aufgabe_speichern", {"titel": "Rueckruf Kunde", "zugewiesen_an": str(admin.id)}, {"erledigt": True}, pruefe_aufgabe, kopf, "/api/projekt-aufgaben"
    )

    start = datetime.now(timezone.utc).replace(microsecond=0, second=0) + timedelta(days=1)

    async def pruefe_termin(wann, id_):
        t = await api(f"/api/termine/{id_}")
        erwartet = start + timedelta(hours=2 if wann == "nachher" else 0)
        assert datetime.fromisoformat(t["start_at"]) == erwartet

    await _anlegen_aendern_undo(
        mcp_client, token, "termin_speichern",
        {"vorgang_id": str(vorgang.id), "techniker_id": str(admin.id), "titel": "Wartung", "start_at": start.isoformat(), "ende_at": (start + timedelta(hours=4)).isoformat()},
        {"start_at": (start + timedelta(hours=2)).isoformat(), "ende_at": (start + timedelta(hours=6)).isoformat()},
        pruefe_termin,
        kopf,
        "/api/termine",
    )
    assert (await tool_aufrufen(mcp_client, token, "termin_speichern", {"id": str(uuid.uuid4()), "vorgang_id": str(vorgang.id)}))["fehler"] is True

    async def pruefe_kunde(wann, id_):
        k = await api(f"/api/kunden/{id_}")
        assert k["name"] == ("Müller GmbH" if wann == "nachher" else "Mueller") and k["notiz"] == ("Neu" if wann == "nachher" else None)

    await _anlegen_aendern_undo(
        mcp_client, token, "kunde_speichern", {"art": "kunde", "name": "Mueller"}, {"art": "kunde", "name": "Müller GmbH", "notiz": "Neu"}, pruefe_kunde, kopf, "/api/kunden"
    )
    falsch = await tool_aufrufen(mcp_client, token, "kunde_speichern", {"art": "kunde", "name": "X", "rolle": "mieter"})
    assert falsch["fehler"] is True and "rolle" in falsch["text"]


async def test_standort_und_kontakt_vor_ort_speichern(make_mandant, make_user, make_kunde, mcp_client):
    mandant, admin, token, kopf = await _bereit(make_mandant, make_user, mcp_client)
    kunde = await make_kunde(mandant=mandant)

    async def pruefe_standort(wann, id_):
        r = await mcp_client.get(f"/api/standorte/{id_}", headers=kopf)
        assert r.json()["bezeichnung"] == ("Halle 2" if wann == "nachher" else "Halle 1")

    await _anlegen_aendern_undo(
        mcp_client, token, "kunde_speichern",
        {"art": "standort", "kunde_id": str(kunde.id), "bezeichnung": "Halle 1", "adresse": {"strasse": "Weg 1", "plz": "50667", "ort": "Köln"}},
        {"art": "standort", "bezeichnung": "Halle 2"},
        pruefe_standort,
        kopf,
        "/api/standorte",
    )

    async def pruefe_kontakt(wann, id_):
        r = await mcp_client.get(f"/api/kunden/{kunde.id}/vor-ort-kontakte", headers=kopf)
        eintraege = [k for k in r.json() if k["id"] == id_]
        assert eintraege and eintraege[0]["telefon"] == ("0221 2" if wann == "nachher" else "0221 1")

    await _anlegen_aendern_undo(
        mcp_client, token, "kunde_speichern",
        {"art": "kontakt_vor_ort", "kunde_id": str(kunde.id), "name": "Herr Kuhn", "rolle": "hausmeister", "telefon": "0221 1"},
        {"art": "kontakt_vor_ort", "kunde_id": str(kunde.id), "telefon": "0221 2"},
        pruefe_kontakt,
    )
    ohne_kunde = await tool_aufrufen(mcp_client, token, "kunde_speichern", {"art": "kontakt_vor_ort", "rolle": "mieter", "name": "A"})
    assert ohne_kunde["fehler"] is True


# --- lesen / auflisten ---------------------------------------------------------------------------------


async def test_lesen_ich_auflisten_filter_und_ki_aktion(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, admin, token, _ = await _bereit(make_mandant, make_user, mcp_client)
    kunde = await make_kunde(mandant=mandant)
    v = await make_vorgang(mandant=mandant, kunde=kunde)
    ich = await tool_aufrufen(mcp_client, token, "lesen", {"typ": "ich"})
    assert ich["fehler"] is False, ich["text"]
    assert ich["daten"]["user_id"] == str(admin.id) and ich["daten"]["verbindung"]["schreiben_erlaubt"] is True
    assert "Stufe 3" in ich["daten"]["ki_stufen"] and ich["daten"]["fachrechte"]

    unbekannt = await tool_aufrufen(mcp_client, token, "auflisten", {"typ": "vorgang", "filter": {"farbe": "rot"}})
    assert unbekannt["fehler"] is True and "Erlaubte Filter" in unbekannt["text"] and "kunde_id" in unbekannt["text"]
    liste = await tool_aufrufen(mcp_client, token, "auflisten", {"typ": "vorgang", "filter": {"kunde_id": str(kunde.id)}})
    assert [e["id"] for e in liste["daten"]["eintraege"]] == [str(v.id)]
    ma = await tool_aufrufen(mcp_client, token, "auflisten", {"typ": "mitarbeiter", "filter": {"suche": admin.name[:3]}})
    assert ma["fehler"] is False and ma["daten"]["anzahl_gesamt"] >= 1

    r = await tool_aufrufen(mcp_client, token, "vorgang_speichern", {"id": str(v.id), "titel": "Neu benannt"})
    ki = await tool_aufrufen(mcp_client, token, "auflisten", {"typ": "ki_aktion"})
    assert [e["id"] for e in ki["daten"]["eintraege"]] == [r["daten"]["aktion_id"]]
    eins = await tool_aufrufen(mcp_client, token, "lesen", {"typ": "ki_aktion", "id": r["daten"]["aktion_id"]})
    assert eins["fehler"] is False and eins["daten"]["tool"] == "vorgang_speichern"
    ohne_id = await tool_aufrufen(mcp_client, token, "lesen", {"typ": "vorgang"})
    assert ohne_id["fehler"] is True
    kontakt_ohne_kunde = await tool_aufrufen(mcp_client, token, "lesen", {"typ": "kontakt_vor_ort", "id": str(uuid.uuid4())})
    assert kontakt_ohne_kunde["fehler"] is True and "kunde_id" in kontakt_ohne_kunde["text"]


async def test_ki_aktionen_sind_je_nutzer_getrennt_und_mandantengetrennt(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant_a, admin_a, token_a, _ = await _bereit(make_mandant, make_user, mcp_client)
    kunde = await make_kunde(mandant=mandant_a)
    v = await make_vorgang(mandant=mandant_a, kunde=kunde)
    r = await tool_aufrufen(mcp_client, token_a, "vorgang_speichern", {"id": str(v.id), "titel": "A"})
    _, admin_b, token_b, _ = await _bereit(make_mandant, make_user, mcp_client)
    fremd = await tool_aufrufen(mcp_client, token_b, "rueckgaengig", {"aktion_id": r["daten"]["aktion_id"]})
    assert fremd["fehler"] is True
    assert (await tool_aufrufen(mcp_client, token_b, "auflisten", {"typ": "ki_aktion"}))["daten"]["eintraege"] == []


# --- Registry ------------------------------------------------------------------------------------------


def test_registry_routen_gibt_es_wirklich_und_rueckweg_ist_getrennt():
    from app.main import app

    beispiel = str(uuid.uuid4())
    vorhanden = {
        (m.upper(), re.sub(r"\{[^}]+\}", beispiel, pfad)) for pfad, ops in app.openapi()["paths"].items() for m in ops
    }
    for route in (*AKTIONEN, *RUECKWEG_ROUTEN):
        assert any(m == route.methode and route.regex.fullmatch(p) for m, p in vorhanden), (route.methode, route.pfad_muster)
    # Loeschen von Datensaetzen nur im Rueckweg; in AKTIONEN darf DELETE nur Verknuepfungen loesen
    for route in AKTIONEN:
        if route.methode == "DELETE":
            assert route.aktionsart.endswith("entknuepfen"), route
    assert all(UUID_MUSTER in r.pfad_muster or r.pfad_muster == "/api/vorgaenge" for r in AKTIONEN if r.methode in ("PATCH", "DELETE"))
