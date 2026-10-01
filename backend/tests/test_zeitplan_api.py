import uuid

import pytest

from tests.conftest import auth_headers, login
from tests.test_projekte import _make_custom_mit_projekte_recht, _make_custom_user

PW = "pw-123456"


async def _admin(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW)
    token = await login(client, admin.email, PW)
    return mandant, admin, auth_headers(token)


async def _projekt(client, h, name="Neubau") -> str:
    return (await client.post("/api/projekte", headers=h, json={"name": name})).json()["id"]


def _url(pid, suffix=""):
    return f"/api/projekte/{pid}/zeitplan{suffix}"


async def _element(client, h, pid, typ="schritt", titel="X", **kw) -> dict:
    resp = await client.post(_url(pid, "/elemente"), headers=h, json={"typ": typ, "titel": titel, **kw})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _finde(zp: dict, titel: str) -> dict:
    return next(e for e in zp["elemente"] if e["titel"] == titel)


async def _verbinde(client, h, pid, a, b, versatz=0):
    return await client.post(
        _url(pid, "/abhaengigkeiten"),
        headers=h,
        json={"vorgaenger_id": a["id"], "nachfolger_id": b["id"], "versatz_tage": versatz},
    )


@pytest.mark.asyncio
async def test_leerer_zeitplan_hat_standardmodus(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    resp = await client.get(_url(pid), headers=h)
    assert resp.status_code == 200
    assert resp.json() == {
        "projekt_id": pid,
        "verschiebe_modus": "bei_konflikt",
        "elemente": [],
        "abhaengigkeiten": [],
    }


@pytest.mark.asyncio
async def test_elemente_anlegen_regeln(client, make_mandant, make_user):
    _, admin, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)

    await _element(client, h, pid, "phase", "Rohbau", start_am="2026-06-01", ende_am="2026-06-30")
    zp = await _element(client, h, pid, "schritt", "Fundament", start_am="2026-06-02")
    phase = _finde(zp, "Rohbau")
    assert phase["start_am"] is None  # Phasen-Spanne abgeleitet, Eingabe ignoriert
    assert _finde(zp, "Fundament")["ende_am"] == "2026-06-02"  # nur Start -> Ein-Tages-Schritt

    zp = await _element(
        client, h, pid, "meilenstein", "Abnahme", start_am="2026-06-10", ende_am="2026-06-20", phase_id=phase["id"],
        zugewiesen_an=str(admin.id),
    )
    ms = _finde(zp, "Abnahme")
    assert (ms["start_am"], ms["ende_am"]) == ("2026-06-10", "2026-06-10")
    assert ms["zugewiesen_name"] == admin.name
    phase = _finde(zp, "Rohbau")
    assert (phase["start_am"], phase["ende_am"]) == ("2026-06-10", "2026-06-10")
    assert zp["elemente"][0]["typ"] == "phase"  # Phasen zuerst

    zp = await _element(client, h, pid, "schritt", "Zweiter", phase_id=phase["id"])
    assert _finde(zp, "Zweiter")["plan_reihenfolge"] == _finde(zp, "Abnahme")["plan_reihenfolge"] + 1

    # Phase in Phase / unbekannte Phase / fremder Nutzer
    r = await client.post(_url(pid, "/elemente"), headers=h,
                          json={"typ": "phase", "titel": "P2", "phase_id": phase["id"]})
    assert r.status_code == 400
    r = await client.post(_url(pid, "/elemente"), headers=h,
                          json={"typ": "schritt", "titel": "S", "phase_id": str(uuid.uuid4())})
    assert r.status_code == 400
    r = await client.post(_url(pid, "/elemente"), headers=h,
                          json={"typ": "schritt", "titel": "S", "zugewiesen_an": str(uuid.uuid4())})
    assert r.status_code == 400
    r = await client.post(_url(pid, "/elemente"), headers=h,
                          json={"typ": "schritt", "titel": "S", "start_am": "2026-06-05", "ende_am": "2026-06-01"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_kanban_zeigt_schritte_aber_keine_phasen_und_meilensteine(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    await _element(client, h, pid, "phase", "Phase")
    await _element(client, h, pid, "meilenstein", "Meilenstein", start_am="2026-06-01")
    zp = await _element(client, h, pid, "schritt", "Schritt", start_am="2026-06-01", ende_am="2026-06-03")
    schritt = _finde(zp, "Schritt")

    spalten = (await client.get(f"/api/projekte/{pid}/spalten", headers=h)).json()
    liste = (await client.get(f"/api/projekt-aufgaben?projekt_id={pid}", headers=h)).json()
    assert [a["titel"] for a in liste] == ["Schritt"]
    assert liste[0]["spalte_id"] == spalten[0]["id"]
    assert liste[0]["typ"] == "schritt"
    assert liste[0]["start_am"] == "2026-06-01" and liste[0]["ende_am"] == "2026-06-03"

    alle = (await client.get("/api/projekt-aufgaben", headers=h)).json()
    assert [a["titel"] for a in alle] == ["Schritt"]

    phase_id = _finde(zp, "Phase")["id"]
    assert (await client.get(f"/api/projekt-aufgaben/{phase_id}", headers=h)).status_code == 404

    # Abhaken im Kanban zieht den Fortschritt mit
    await client.patch(f"/api/projekt-aufgaben/{schritt['id']}", headers=h, json={"erledigt": True})
    zp = (await client.get(_url(pid), headers=h)).json()
    assert _finde(zp, "Schritt")["fortschritt"] == 100 and _finde(zp, "Schritt")["erledigt"] is True


@pytest.mark.asyncio
async def test_abhaengigkeit_crud_und_mitverschiebung(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    await _element(client, h, pid, "schritt", "A", start_am="2026-06-01", ende_am="2026-06-05")
    await _element(client, h, pid, "schritt", "B", start_am="2026-06-06", ende_am="2026-06-10")
    zp = await _element(client, h, pid, "schritt", "C", start_am="2026-06-11", ende_am="2026-06-15")
    a, b, c = _finde(zp, "A"), _finde(zp, "B"), _finde(zp, "C")

    r = await _verbinde(client, h, pid, a, b)
    assert r.status_code == 200
    r = await _verbinde(client, h, pid, b, c)
    zp = r.json()
    assert len(zp["abhaengigkeiten"]) == 2
    assert zp["abhaengigkeiten"][0]["art"] == "ende_anfang"
    ab = zp["abhaengigkeiten"][0]

    # A verlaengern -> B und C werden mitverschoben, Antwort enthaelt sie
    r = await client.patch(_url(pid, f"/elemente/{a['id']}"), headers=h, json={"ende_am": "2026-06-08"})
    assert r.status_code == 200
    zp = r.json()
    assert (_finde(zp, "B")["start_am"], _finde(zp, "B")["ende_am"]) == ("2026-06-09", "2026-06-13")
    assert (_finde(zp, "C")["start_am"], _finde(zp, "C")["ende_am"]) == ("2026-06-14", "2026-06-18")

    # Versatz aendern schiebt den Nachfolger (Konfliktregel)
    r = await client.patch(_url(pid, f"/abhaengigkeiten/{ab['id']}"), headers=h, json={"versatz_tage": 2})
    zp = r.json()
    assert _finde(zp, "B")["start_am"] == "2026-06-11"
    assert _finde(zp, "C")["start_am"] == "2026-06-16"
    assert next(x for x in zp["abhaengigkeiten"] if x["id"] == ab["id"])["versatz_tage"] == 2

    # Loeschen verschiebt nichts
    r = await client.delete(_url(pid, f"/abhaengigkeiten/{ab['id']}"), headers=h)
    zp = r.json()
    assert len(zp["abhaengigkeiten"]) == 1
    assert _finde(zp, "B")["start_am"] == "2026-06-11"


@pytest.mark.asyncio
async def test_neue_abhaengigkeit_verschiebt_nachfolger_inklusive_kette(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    await _element(client, h, pid, "schritt", "A", start_am="2026-06-10", ende_am="2026-06-12")
    await _element(client, h, pid, "schritt", "B", start_am="2026-06-01", ende_am="2026-06-02")
    zp = await _element(client, h, pid, "schritt", "C", start_am="2026-06-03", ende_am="2026-06-04")
    a, b, c = _finde(zp, "A"), _finde(zp, "B"), _finde(zp, "C")
    await _verbinde(client, h, pid, b, c)
    zp = (await _verbinde(client, h, pid, a, b)).json()
    assert (_finde(zp, "B")["start_am"], _finde(zp, "B")["ende_am"]) == ("2026-06-13", "2026-06-14")
    assert _finde(zp, "C")["start_am"] == "2026-06-15"


@pytest.mark.asyncio
async def test_zyklus_duplikat_und_regelverletzungen(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    await _element(client, h, pid, "schritt", "A", start_am="2026-06-01", ende_am="2026-06-02")
    await _element(client, h, pid, "schritt", "B", start_am="2026-06-03", ende_am="2026-06-04")
    await _element(client, h, pid, "schritt", "C", start_am="2026-06-05", ende_am="2026-06-06")
    await _element(client, h, pid, "schritt", "Ohne Datum")
    zp = await _element(client, h, pid, "phase", "Phase")
    a, b, c = _finde(zp, "A"), _finde(zp, "B"), _finde(zp, "C")
    ohne, phase = _finde(zp, "Ohne Datum"), _finde(zp, "Phase")
    await _verbinde(client, h, pid, a, b)
    await _verbinde(client, h, pid, b, c)

    r = await _verbinde(client, h, pid, c, a)
    assert r.status_code == 409
    assert r.json()["detail"] == "Diese Verbindung würde einen Kreis erzeugen"
    assert (await _verbinde(client, h, pid, b, a)).status_code == 409
    assert (await _verbinde(client, h, pid, a, b)).status_code == 409  # Duplikat
    assert (await _verbinde(client, h, pid, a, a)).status_code == 400
    assert (await _verbinde(client, h, pid, a, ohne)).status_code == 400
    assert (await _verbinde(client, h, pid, phase, a)).status_code == 400
    assert (await _verbinde(client, h, pid, a, phase)).status_code == 400


@pytest.mark.asyncio
async def test_phase_verschieben_und_phase_ende_allein_400(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    zp = await _element(client, h, pid, "phase", "Phase")
    phase = _finde(zp, "Phase")
    await _element(client, h, pid, "schritt", "A", phase_id=phase["id"], start_am="2026-06-01", ende_am="2026-06-04")
    zp = await _element(client, h, pid, "schritt", "B", phase_id=phase["id"], start_am="2026-06-05", ende_am="2026-06-10")
    await _element(client, h, pid, "schritt", "Danach", start_am="2026-06-11", ende_am="2026-06-12")
    zp = (await client.get(_url(pid), headers=h)).json()
    b, danach = _finde(zp, "B"), _finde(zp, "Danach")
    await _verbinde(client, h, pid, b, danach)
    assert (_finde(zp, "Phase")["start_am"], _finde(zp, "Phase")["ende_am"]) == ("2026-06-01", "2026-06-10")

    r = await client.patch(_url(pid, f"/elemente/{phase['id']}"), headers=h, json={"ende_am": "2026-06-20"})
    assert r.status_code == 400

    r = await client.patch(
        _url(pid, f"/elemente/{phase['id']}"), headers=h, json={"start_am": "2026-06-04", "ende_am": "2026-06-13"}
    )
    assert r.status_code == 200
    zp = r.json()
    assert _finde(zp, "A")["start_am"] == "2026-06-04"
    assert _finde(zp, "B")["ende_am"] == "2026-06-13"
    assert (_finde(zp, "Phase")["start_am"], _finde(zp, "Phase")["ende_am"]) == ("2026-06-04", "2026-06-13")
    assert _finde(zp, "Danach")["start_am"] == "2026-06-14"


@pytest.mark.asyncio
async def test_modus_immer_zieht_nachfolger_nach_vorne(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    await _element(client, h, pid, "schritt", "A", start_am="2026-06-05", ende_am="2026-06-08")
    zp = await _element(client, h, pid, "schritt", "B", start_am="2026-06-09", ende_am="2026-06-12")
    a, b = _finde(zp, "A"), _finde(zp, "B")
    await _verbinde(client, h, pid, a, b)

    r = await client.patch(_url(pid, "/einstellungen"), headers=h, json={"verschiebe_modus": "immer"})
    assert r.status_code == 200 and r.json()["verschiebe_modus"] == "immer"
    zp = (await client.patch(
        _url(pid, f"/elemente/{a['id']}"), headers=h, json={"start_am": "2026-06-01", "ende_am": "2026-06-04"}
    )).json()
    assert _finde(zp, "B")["start_am"] == "2026-06-05"

    assert (await client.patch(_url(pid, "/einstellungen"), headers=h,
                               json={"verschiebe_modus": "egal"})).status_code == 422


@pytest.mark.asyncio
async def test_fortschritt_und_loeschen(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    zp = await _element(client, h, pid, "phase", "Phase")
    phase = _finde(zp, "Phase")
    await _element(client, h, pid, "schritt", "A", phase_id=phase["id"], start_am="2026-06-01", ende_am="2026-06-02")
    zp = await _element(client, h, pid, "schritt", "B", phase_id=phase["id"], start_am="2026-06-03", ende_am="2026-06-04")
    a, b = _finde(zp, "A"), _finde(zp, "B")
    await _verbinde(client, h, pid, a, b)

    r = await client.patch(_url(pid, f"/elemente/{a['id']}"), headers=h, json={"fortschritt": 100})
    assert _finde(r.json(), "A")["erledigt"] is True
    r = await client.patch(_url(pid, f"/elemente/{a['id']}"), headers=h, json={"fortschritt": 40})
    assert _finde(r.json(), "A")["erledigt"] is False and _finde(r.json(), "A")["fortschritt"] == 40
    assert (await client.patch(_url(pid, f"/elemente/{a['id']}"), headers=h, json={"fortschritt": 101})).status_code == 422
    assert (await client.patch(_url(pid, f"/elemente/{a['id']}"), headers=h, json={"titel": None})).status_code == 422

    zp = (await client.delete(_url(pid, f"/elemente/{a['id']}"), headers=h)).json()
    assert all(e["titel"] != "A" for e in zp["elemente"])
    assert zp["abhaengigkeiten"] == []
    assert _finde(zp, "Phase")["start_am"] == "2026-06-03"  # Spanne ohne A

    zp = (await client.delete(_url(pid, f"/elemente/{phase['id']}"), headers=h)).json()
    assert _finde(zp, "B")["phase_id"] is None
    assert (await client.delete(_url(pid, f"/elemente/{phase['id']}"), headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_element_in_andere_phase_verschieben_aktualisiert_spannen(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    await _element(client, h, pid, "phase", "P1")
    zp = await _element(client, h, pid, "phase", "P2")
    p1, p2 = _finde(zp, "P1"), _finde(zp, "P2")
    zp = await _element(client, h, pid, "schritt", "A", phase_id=p1["id"], start_am="2026-06-01", ende_am="2026-06-02")
    a = _finde(zp, "A")
    r = await client.patch(_url(pid, f"/elemente/{a['id']}"), headers=h, json={"phase_id": p2["id"]})
    zp = r.json()
    assert _finde(zp, "P1")["start_am"] is None
    assert _finde(zp, "P2")["start_am"] == "2026-06-01"
    r = await client.patch(_url(pid, f"/elemente/{p1['id']}"), headers=h, json={"phase_id": p2["id"]})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_abhaengigkeit_ueber_projektgrenzen_400(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    p1, p2 = await _projekt(client, h, "P1"), await _projekt(client, h, "P2")
    a = _finde(await _element(client, h, p1, "schritt", "A", start_am="2026-06-01"), "A")
    b = _finde(await _element(client, h, p2, "schritt", "B", start_am="2026-06-05"), "B")
    assert (await _verbinde(client, h, p1, a, b)).status_code == 400
    # Element eines anderen Projekts ist ueber diese Projekt-URL nicht erreichbar
    assert (await client.patch(_url(p1, f"/elemente/{b['id']}"), headers=h, json={"titel": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_mandantentrennung(client, make_mandant, make_user):
    _, _, h1 = await _admin(client, make_mandant, make_user)
    _, _, h2 = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h1)
    a = _finde(await _element(client, h1, pid, "schritt", "A", start_am="2026-06-01"), "A")
    b = _finde(await _element(client, h1, pid, "schritt", "B", start_am="2026-06-05"), "B")
    zp = (await _verbinde(client, h1, pid, a, b)).json()
    abh = zp["abhaengigkeiten"][0]

    assert (await client.get(_url(pid), headers=h2)).status_code == 404
    assert (await client.post(_url(pid, "/elemente"), headers=h2, json={"typ": "phase", "titel": "x"})).status_code == 404
    assert (await client.patch(_url(pid, f"/elemente/{a['id']}"), headers=h2, json={"titel": "x"})).status_code == 404
    assert (await client.delete(_url(pid, f"/elemente/{a['id']}"), headers=h2)).status_code == 404
    assert (await client.delete(_url(pid, f"/abhaengigkeiten/{abh['id']}"), headers=h2)).status_code == 404
    assert (await client.patch(_url(pid, "/einstellungen"), headers=h2,
                               json={"verschiebe_modus": "immer"})).status_code == 404

    # Eigenes Projekt, fremdes Element im Body -> 400 (kein Leck)
    pid2 = await _projekt(client, h2)
    c = _finde(await _element(client, h2, pid2, "schritt", "C", start_am="2026-06-01"), "C")
    assert (await _verbinde(client, h2, pid2, c, a)).status_code == 400


@pytest.mark.asyncio
async def test_leser_darf_lesen_aber_nicht_aendern(client, make_mandant, make_user):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    a = _finde(await _element(client, h, pid, "schritt", "A", start_am="2026-06-01"), "A")

    account_typ = await _make_custom_mit_projekte_recht(mandant, aktionen={"sehen"})
    user = await _make_custom_user(mandant, account_typ)
    hl = auth_headers(await login(client, user.email, "hunter2!!"))

    assert (await client.get(_url(pid), headers=hl)).status_code == 200
    assert (await client.post(_url(pid, "/elemente"), headers=hl, json={"typ": "phase", "titel": "x"})).status_code == 403
    assert (await client.patch(_url(pid, f"/elemente/{a['id']}"), headers=hl, json={"titel": "x"})).status_code == 403
    assert (await client.delete(_url(pid, f"/elemente/{a['id']}"), headers=hl)).status_code == 403
    assert (await client.post(_url(pid, "/abhaengigkeiten"), headers=hl,
                              json={"vorgaenger_id": a["id"], "nachfolger_id": a["id"]})).status_code == 403
    assert (await client.patch(_url(pid, "/einstellungen"), headers=hl,
                               json={"verschiebe_modus": "immer"})).status_code == 403
