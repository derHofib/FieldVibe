"""Zeitplan Phase 3 -- API: kritischer Pfad, Basisplan, Straffen, Vorlagen, PDF."""
import io
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.db.session import system_session
from tests.conftest import auth_headers, login
from tests.test_projekte import _make_custom_mit_projekte_recht, _make_custom_user
from tests.test_zeitplan_api import _admin, _element, _finde, _projekt, _url, _verbinde


async def _kette(client, h, pid):
    """Phase 'Bau' mit A(1-5) -> B(10-12) -> Lieferung-frei, plus Parallelzweig X."""
    await _element(client, h, pid, "phase", "Bau")
    zp = await _element(client, h, pid, "schritt", "A", start_am="2026-06-01", ende_am="2026-06-05")
    phase = _finde(zp, "Bau")
    zp = await _element(client, h, pid, "schritt", "B", start_am="2026-06-10", ende_am="2026-06-12", phase_id=phase["id"])
    zp = await _element(client, h, pid, "meilenstein", "Fertig", start_am="2026-06-20", phase_id=phase["id"])
    zp = await _element(client, h, pid, "schritt", "X", start_am="2026-06-06", ende_am="2026-06-07")
    return zp


@pytest.mark.asyncio
async def test_kritischer_pfad_im_zeitplan(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    zp = await _kette(client, h, pid)
    a, b, m, x = (_finde(zp, t) for t in ("A", "B", "Fertig", "X"))
    await _verbinde(client, h, pid, a, b)
    await _verbinde(client, h, pid, b, m)
    resp = await _verbinde(client, h, pid, a, x)
    zp = resp.json()
    phase = _finde(zp, "Bau")
    assert phase["puffer_tage"] is None and phase["kritisch"] is False
    assert _finde(zp, "X")["puffer_tage"] == 13 and not _finde(zp, "X")["kritisch"]
    assert _finde(zp, "Fertig")["kritisch"] is True
    assert _finde(zp, "Fertig")["puffer_tage"] == 0
    assert _finde(zp, "A")["puffer_tage"] == 11  # B darf bis 19.06. enden (Fertig 20.06.) -> A bis 16.06.
    krit = {(d["vorgaenger_id"], d["nachfolger_id"]): d["kritisch"] for d in zp["abhaengigkeiten"]}
    assert krit[(a["id"], x["id"])] is False
    # Ohne Basisplan: keine Vergleichsfelder
    assert _finde(zp, "A")["basis_ende_am"] is None and _finde(zp, "A")["abweichung_tage"] is None


@pytest.mark.asyncio
async def test_basisplan_abweichung_und_verwaltung(client, make_mandant, make_user):
    _, admin, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    zp = await _kette(client, h, pid)
    resp = await client.post(_url(pid, "/basisplaene"), headers=h, json={"name": "Ursprung"})
    assert resp.status_code == 201
    bp = resp.json()
    assert bp["name"] == "Ursprung" and bp["erstellt_von_name"] == admin.name
    assert bp["anzahl_elemente"] == 5  # Phase (datiert durch Kinder), A, B, Fertig, X

    b = _finde(zp, "B")
    await client.patch(_url(pid, f"/elemente/{b['id']}"), headers=h, json={"ende_am": "2026-06-15"})
    zp = (await client.get(_url(pid) + f"?basisplan_id={bp['id']}", headers=h)).json()
    b = _finde(zp, "B")
    assert (b["basis_start_am"], b["basis_ende_am"]) == ("2026-06-10", "2026-06-12")
    assert b["abweichung_tage"] == 3
    assert _finde(zp, "A")["abweichung_tage"] == 0
    # neues Element nach dem Snapshot hat keine Basis
    zp = await _element(client, h, pid, "schritt", "Neu", start_am="2026-07-01")
    zp = (await client.get(_url(pid) + f"?basisplan_id={bp['id']}", headers=h)).json()
    assert _finde(zp, "Neu")["abweichung_tage"] is None

    zweiter = (await client.post(_url(pid, "/basisplaene"), headers=h, json={"name": "Später"})).json()
    liste = (await client.get(_url(pid, "/basisplaene"), headers=h)).json()
    assert [x["name"] for x in liste] == ["Später", "Ursprung"]
    assert (await client.delete(_url(pid, f"/basisplaene/{bp['id']}"), headers=h)).status_code == 204
    assert (await client.delete(_url(pid, f"/basisplaene/{bp['id']}"), headers=h)).status_code == 404
    assert len((await client.get(_url(pid, "/basisplaene"), headers=h)).json()) == 1
    assert zweiter["id"]


@pytest.mark.asyncio
async def test_basisplan_fremdes_projekt_und_mandant_404(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    _, _, h2 = await _admin(client, make_mandant, make_user)
    p1, p1b = await _projekt(client, h, "P1"), await _projekt(client, h, "P1b")
    await _element(client, h, p1, "schritt", "A", start_am="2026-06-01")
    bp = (await client.post(_url(p1, "/basisplaene"), headers=h, json={"name": "B"})).json()
    # anderes Projekt desselben Mandanten
    assert (await client.get(_url(p1b) + f"?basisplan_id={bp['id']}", headers=h)).status_code == 404
    assert (await client.delete(_url(p1b, f"/basisplaene/{bp['id']}"), headers=h)).status_code == 404
    # anderer Mandant
    p2 = await _projekt(client, h2, "P2")
    assert (await client.get(_url(p2) + f"?basisplan_id={bp['id']}", headers=h2)).status_code == 404
    assert (await client.get(_url(p1, "/basisplaene"), headers=h2)).status_code == 404
    assert (await client.get(_url(p1) + "/pdf", headers=h2)).status_code == 404


@pytest.mark.asyncio
async def test_straffen_vorschau_und_anwenden(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    zp = await _kette(client, h, pid)
    a, b, m = (_finde(zp, t) for t in ("A", "B", "Fertig"))
    await _verbinde(client, h, pid, a, b)
    await _verbinde(client, h, pid, b, m)

    resp = await client.post(_url(pid, "/straffen"), headers=h, json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["zeitplan"] is None
    neu = {x["titel"]: x for x in body["aenderungen"]}
    assert set(neu) == {"B", "Fertig"}
    assert (neu["B"]["alt_start_am"], neu["B"]["neu_start_am"], neu["B"]["neu_ende_am"]) == (
        "2026-06-10", "2026-06-06", "2026-06-08")
    assert neu["Fertig"]["neu_start_am"] == "2026-06-09"
    unveraendert = (await client.get(_url(pid), headers=h)).json()
    assert _finde(unveraendert, "B")["start_am"] == "2026-06-10"  # Vorschau aendert nichts

    resp = await client.post(_url(pid, "/straffen"), headers=h, json={"vorschau": False})
    zp = resp.json()["zeitplan"]
    assert _finde(zp, "B")["start_am"] == "2026-06-06"
    assert _finde(zp, "Fertig")["start_am"] == "2026-06-09"
    assert _finde(zp, "A")["start_am"] == "2026-06-01"
    phase = _finde(zp, "Bau")
    assert (phase["start_am"], phase["ende_am"]) == ("2026-06-06", "2026-06-09")
    # erneut straffen: nichts mehr zu tun
    assert (await client.post(_url(pid, "/straffen"), headers=h, json={})).json()["aenderungen"] == []


@pytest.mark.asyncio
async def test_straffen_phasenfilter_und_gesperrter_meilenstein(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    zp = await _kette(client, h, pid)
    a, b, m, phase = (_finde(zp, t) for t in ("A", "B", "Fertig", "Bau"))
    await _verbinde(client, h, pid, a, b)
    await _verbinde(client, h, pid, b, m)
    # Phase-Filter auf eine fremde/unbekannte Phase -> 400
    assert (await client.post(_url(pid, "/straffen"), headers=h, json={"phase_id": a["id"]})).status_code == 400
    body = (await client.post(_url(pid, "/straffen"), headers=h, json={"phase_id": phase["id"]})).json()
    assert {x["titel"] for x in body["aenderungen"]} == {"B", "Fertig"}


@pytest.mark.asyncio
async def test_straffen_laesst_gesperrten_liefermeilenstein_stehen(client, make_mandant, make_user):
    from tests.test_zeitplan_verknuepfungen import _bestellung

    mandant, admin, h = await _admin(client, make_mandant, make_user)
    b = await _bestellung(mandant, admin, liefertermin=date(2026, 6, 30), nummer="B-9")
    pid = await _projekt(client, h)
    await _element(client, h, pid, "schritt", "A", start_am="2026-06-01", ende_am="2026-06-05")
    await _element(client, h, pid, "meilenstein", "Lieferung", bestellung_id=str(b.id))
    zp = await _element(client, h, pid, "schritt", "Nach", start_am="2026-07-10", ende_am="2026-07-12")
    a, ms, nach = (_finde(zp, t) for t in ("A", "Lieferung", "Nach"))
    await _verbinde(client, h, pid, a, ms)
    await _verbinde(client, h, pid, ms, nach)
    body = (await client.post(_url(pid, "/straffen"), headers=h, json={"vorschau": False})).json()
    assert {x["titel"] for x in body["aenderungen"]} == {"Nach"}
    assert _finde(body["zeitplan"], "Lieferung")["start_am"] == "2026-06-30"
    assert _finde(body["zeitplan"], "Nach")["start_am"] == "2026-06-30"  # Meilenstein: gleicher Tag


def _struktur(zp: dict, start: date) -> tuple[list, list]:
    nach_id = {e["id"]: e for e in zp["elemente"]}
    elemente = sorted(
        (
            e["typ"], e["titel"], nach_id[e["phase_id"]]["titel"] if e["phase_id"] else "",
            (date.fromisoformat(e["start_am"]) - start).days if e["start_am"] else -1,
            (date.fromisoformat(e["ende_am"]) - date.fromisoformat(e["start_am"])).days + 1 if e["start_am"] else -1,
        )
        for e in zp["elemente"]
    )
    deps = sorted(
        (nach_id[d["vorgaenger_id"]]["titel"], nach_id[d["nachfolger_id"]]["titel"], d["art"], d["versatz_tage"])
        for d in zp["abhaengigkeiten"]
    )
    return elemente, deps


@pytest.mark.asyncio
async def test_vorlage_aus_projekt_und_anwenden_ergibt_gleiche_struktur(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h, "Quelle")
    await _element(client, h, pid, "phase", "Bau")
    await _element(client, h, pid, "phase", "Leer")  # ohne datierte Elemente -> weggelassen
    zp = await _element(client, h, pid, "schritt", "A", start_am="2026-06-03", ende_am="2026-06-07")
    bau = _finde(zp, "Bau")
    await _element(client, h, pid, "schritt", "B", start_am="2026-06-10", ende_am="2026-06-12", phase_id=bau["id"])
    await _element(client, h, pid, "meilenstein", "M", start_am="2026-06-15", phase_id=bau["id"])
    zp = await _element(client, h, pid, "schritt", "Ohne Datum")
    a, b, m = (_finde(zp, t) for t in ("A", "B", "M"))
    await _verbinde(client, h, pid, a, b, 2)
    await client.post(_url(pid, "/abhaengigkeiten"), headers=h,
                      json={"vorgaenger_id": b["id"], "nachfolger_id": m["id"], "art": "ende_ende", "versatz_tage": 1})
    quelle = (await client.get(_url(pid), headers=h)).json()

    resp = await client.post(f"/api/projekt-vorlagen/aus-projekt/{pid}", headers=h,
                             json={"name": "Meine Vorlage", "beschreibung": "x"})
    assert resp.status_code == 201, resp.text
    vorlage = resp.json()
    assert vorlage["anzahl_elemente"] == 4  # Phase Bau, A, B, M -- ohne "Leer" und "Ohne Datum"
    assert vorlage["dauer_tage"] == 13  # 03.06. .. 15.06.
    assert len(vorlage["abhaengigkeiten"]) == 2
    assert vorlage["elemente"][0]["typ"] == "phase"
    assert {e["titel"]: (e["offset_tage"], e["dauer_tage"]) for e in vorlage["elemente"]}["M"] == (12, 1)

    liste = (await client.get("/api/projekt-vorlagen", headers=h)).json()
    assert liste == [{"id": vorlage["id"], "name": "Meine Vorlage", "beschreibung": "x",
                      "anzahl_elemente": 4, "dauer_tage": 13}]
    assert (await client.get(f"/api/projekt-vorlagen/{vorlage['id']}", headers=h)).json() == vorlage

    ziel = await _projekt(client, h, "Ziel")
    neuer_start = date(2026, 9, 1)
    resp = await client.post(_url(ziel, "/vorlage-anwenden"), headers=h,
                             json={"vorlage_id": vorlage["id"], "start_am": neuer_start.isoformat()})
    assert resp.status_code == 200, resp.text
    ziel_zp = resp.json()
    erwartet_e, erwartet_d = _struktur(quelle, date(2026, 6, 3))
    erwartet_e = [e for e in erwartet_e if e[1] not in ("Leer", "Ohne Datum")]
    ist_e, ist_d = _struktur(ziel_zp, neuer_start)
    assert ist_e == erwartet_e  # Typ, Titel, Phase, Offset und Dauer (Phasen: abgeleitet) identisch
    assert ist_d == erwartet_d
    assert _finde(ziel_zp, "B")["phase_id"] == _finde(ziel_zp, "Bau")["id"]
    assert _finde(ziel_zp, "A")["phase_id"] is None

    # Anhaengen an bestehenden Plan: Reihenfolge hinten
    zp2 = (await client.post(_url(ziel, "/vorlage-anwenden"), headers=h,
                             json={"vorlage_id": vorlage["id"], "start_am": "2026-10-01"})).json()
    assert len(zp2["elemente"]) == 8
    phasen = sorted((e for e in zp2["elemente"] if e["typ"] == "phase"), key=lambda e: e["plan_reihenfolge"])
    assert [p["start_am"] for p in phasen] == ["2026-09-08", "2026-10-08"]
    assert [p["plan_reihenfolge"] for p in phasen] == [0, 1]

    r = await client.patch(f"/api/projekt-vorlagen/{vorlage['id']}", headers=h, json={"name": "Neu", "beschreibung": None})
    assert r.status_code == 200 and r.json()["name"] == "Neu" and r.json()["beschreibung"] is None
    assert (await client.patch(f"/api/projekt-vorlagen/{vorlage['id']}", headers=h, json={"name": " "})).status_code == 400
    assert (await client.delete(f"/api/projekt-vorlagen/{vorlage['id']}", headers=h)).status_code == 204
    assert (await client.get(f"/api/projekt-vorlagen/{vorlage['id']}", headers=h)).status_code == 404
    assert len((await client.get(_url(ziel), headers=h)).json()["elemente"]) == 8


@pytest.mark.asyncio
async def test_vorlage_aus_leerem_plan_400_und_mandantentrennung(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    _, _, h2 = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    assert (await client.post(f"/api/projekt-vorlagen/aus-projekt/{pid}", headers=h, json={"name": "V"})).status_code == 400
    await _element(client, h, pid, "schritt", "A", start_am="2026-06-01")
    vorlage = (await client.post(f"/api/projekt-vorlagen/aus-projekt/{pid}", headers=h, json={"name": "V"})).json()

    fremdes_projekt = await _projekt(client, h2)
    vid = vorlage["id"]
    assert (await client.get("/api/projekt-vorlagen", headers=h2)).json() == []
    assert (await client.get(f"/api/projekt-vorlagen/{vid}", headers=h2)).status_code == 404
    assert (await client.patch(f"/api/projekt-vorlagen/{vid}", headers=h2, json={"name": "x"})).status_code == 404
    assert (await client.delete(f"/api/projekt-vorlagen/{vid}", headers=h2)).status_code == 404
    r = await client.post(_url(fremdes_projekt, "/vorlage-anwenden"), headers=h2,
                          json={"vorlage_id": vid, "start_am": "2026-09-01"})
    assert r.status_code == 404
    assert (await client.post(f"/api/projekt-vorlagen/aus-projekt/{pid}", headers=h2, json={"name": "V"})).status_code == 404


@pytest.mark.asyncio
async def test_rechte_leser_darf_lesen_aber_nicht_schreiben(client, make_mandant, make_user):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    await _element(client, h, pid, "schritt", "A", start_am="2026-06-01")
    vorlage = (await client.post(f"/api/projekt-vorlagen/aus-projekt/{pid}", headers=h, json={"name": "V"})).json()
    bp = (await client.post(_url(pid, "/basisplaene"), headers=h, json={"name": "B"})).json()

    typ = await _make_custom_mit_projekte_recht(mandant, aktionen={"sehen"})
    user = await _make_custom_user(mandant, typ)
    hl = auth_headers(await login(client, user.email, "hunter2!!"))
    assert (await client.get("/api/projekt-vorlagen", headers=hl)).status_code == 200
    assert (await client.get(f"/api/projekt-vorlagen/{vorlage['id']}", headers=hl)).status_code == 200
    assert (await client.get(_url(pid, "/basisplaene"), headers=hl)).status_code == 200
    assert (await client.get(_url(pid, "/pdf"), headers=hl)).status_code == 200
    assert (await client.get(_url(pid) + f"?basisplan_id={bp['id']}", headers=hl)).status_code == 200
    assert (await client.post(_url(pid, "/basisplaene"), headers=hl, json={"name": "x"})).status_code == 403
    assert (await client.delete(_url(pid, f"/basisplaene/{bp['id']}"), headers=hl)).status_code == 403
    assert (await client.post(_url(pid, "/straffen"), headers=hl, json={})).status_code == 403
    assert (await client.post(_url(pid, "/vorlage-anwenden"), headers=hl,
                              json={"vorlage_id": vorlage["id"], "start_am": "2026-09-01"})).status_code == 403
    assert (await client.post(f"/api/projekt-vorlagen/aus-projekt/{pid}", headers=hl, json={"name": "x"})).status_code == 403
    assert (await client.patch(f"/api/projekt-vorlagen/{vorlage['id']}", headers=hl, json={"name": "x"})).status_code == 403
    assert (await client.delete(f"/api/projekt-vorlagen/{vorlage['id']}", headers=hl)).status_code == 403


@pytest.mark.asyncio
async def test_neue_tabellen_haben_rls_und_policy():
    tabellen = [
        "projekt_basisplaene", "projekt_basisplan_eintraege", "projekt_vorlagen",
        "projekt_vorlage_elemente", "projekt_vorlage_abhaengigkeiten",
    ]
    async with system_session() as session:
        flags = (await session.execute(
            text("SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = ANY(:t)"),
            {"t": tabellen},
        )).all()
        policies = {r[0] for r in (await session.execute(
            text("SELECT tablename FROM pg_policies WHERE policyname = 'mandant_isolation' AND tablename = ANY(:t)"),
            {"t": tabellen},
        )).all()}
    assert {r[0] for r in flags} == set(tabellen)
    assert all(r[1] and r[2] for r in flags)
    assert policies == set(tabellen)


# --- PDF ------------------------------------------------------------------------


def _pdf_text(daten: bytes) -> tuple[int, str]:
    from pypdf import PdfReader

    r = PdfReader(io.BytesIO(daten))
    return len(r.pages), "\n".join(p.extract_text() for p in r.pages)


@pytest.mark.asyncio
async def test_pdf_export_einfach_basisplan_kritisch(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    pid = (await client.post("/api/projekte", headers=h, json={"name": "Neubau Müllerstraße – Haus 7"})).json()["id"]
    zp = await _kette(client, h, pid)
    a, b, m = (_finde(zp, t) for t in ("A", "B", "Fertig"))
    await _verbinde(client, h, pid, a, b)
    await _verbinde(client, h, pid, b, m)
    bp = (await client.post(_url(pid, "/basisplaene"), headers=h, json={"name": "Ursprung – Q2"})).json()

    r = await client.get(_url(pid, "/pdf"), headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    seiten, text_ = _pdf_text(r.content)
    assert seiten == 1 and "Zeitplan" in text_ and "Neubau Müllerstraße - Haus 7" in text_

    r = await client.get(_url(pid, "/pdf") + f"?basisplan_id={bp['id']}&kritischer_pfad=false", headers=h)
    assert r.status_code == 200
    assert "Vergleich mit Basisplan: Ursprung - Q2" in _pdf_text(r.content)[1]
    assert (await client.get(_url(pid, "/pdf") + f"?basisplan_id={pid}", headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_pdf_leerer_plan(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h, "Leer")
    r = await client.get(_url(pid, "/pdf"), headers=h)
    assert r.status_code == 200 and "Zeitplan" in _pdf_text(r.content)[1]


def test_pdf_mehrseitig_60_elemente_und_langer_zeitraum():
    import uuid
    from types import SimpleNamespace

    from app.schemas.projekt import ZeitplanAbhaengigkeit, ZeitplanElement, ZeitplanRead
    from app.services.pdf_service import generate_zeitplan_pdf

    start = date(2026, 1, 5)
    ph = ZeitplanElement(id=uuid.uuid4(), typ="phase", titel="Phase – Ä/Ö/Ü Ω", phase_id=None, start_am=start,
                         ende_am=start + timedelta(days=700), fortschritt=0, plan_reihenfolge=0, zugewiesen_an=None,
                         zugewiesen_name=None, erledigt=False)
    els = [ph]
    for i in range(59):
        s = start + timedelta(days=i * 12)
        els.append(ZeitplanElement(
            id=uuid.uuid4(), typ="schritt" if i % 7 else "meilenstein", titel=f"Schritt {i} – äöüß „lang“ " * 3,
            phase_id=ph.id, start_am=s, ende_am=s if i % 7 == 0 else s + timedelta(days=9), fortschritt=i % 100,
            plan_reihenfolge=i, zugewiesen_an=None, zugewiesen_name="Zuständiger Ünal", erledigt=False,
            kritisch=i % 3 == 0, puffer_tage=0 if i % 3 == 0 else 4,
            basis_start_am=s - timedelta(days=2), basis_ende_am=s + timedelta(days=5), abweichung_tage=1,
        ))
    deps = [ZeitplanAbhaengigkeit(id=uuid.uuid4(), vorgaenger_id=els[i].id, nachfolger_id=els[i + 1].id,
                                  art=("ende_anfang", "anfang_anfang", "ende_ende")[i % 3], versatz_tage=0,
                                  kritisch=i % 3 == 0) for i in range(1, 58)]
    zp = ZeitplanRead(projekt_id=uuid.uuid4(), verschiebe_modus="bei_konflikt", elemente=els, abhaengigkeiten=deps)
    mandant = SimpleNamespace(name="Müller & Söhne", firmendaten={})
    pdf = generate_zeitplan_pdf(mandant, "Großprojekt – Ω", zp, basisplan_name="Basis „1“", kritischer_pfad=True)
    seiten, text_ = _pdf_text(pdf)
    assert seiten >= 2
    assert text_.count("Zeitplan") >= 2  # Kennzeile auf Folgeseiten
    assert text_.count("KW") >= seiten or text_.count("Zeitplan") >= seiten
    assert "Kritischer Pfad" in text_

    kurz = ZeitplanRead(projekt_id=uuid.uuid4(), verschiebe_modus="bei_konflikt", elemente=els[1:3], abhaengigkeiten=[])
    kurz.elemente[0].start_am = kurz.elemente[0].ende_am = start
    kurz.elemente[1].start_am = kurz.elemente[1].ende_am = None
    for e in kurz.elemente:
        e.basis_start_am = e.basis_ende_am = None
    assert generate_zeitplan_pdf(mandant, "Kurz", kurz)
