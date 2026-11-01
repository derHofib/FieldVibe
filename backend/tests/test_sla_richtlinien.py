import pytest
from sqlalchemy import text

from tests.conftest import auth_headers, login
from tests.test_steuer_je_position import _migrieren, _spalten, _sync_engine

PW = "pw-123456"
ZIELE = {"5": {"reaktion_min": 30, "loesung_min": 240}, "3": {"reaktion_min": 240}}
STUFEN = [
    {"frist_art": "reaktion", "schwelle_prozent": 75, "aktion": "benachrichtigen", "empfaenger": "zugewiesener"},
    {"frist_art": "reaktion", "schwelle_prozent": 100, "aktion": "mail", "empfaenger": "dispo"},
]


async def _admin(client, make_mandant, make_user, mandant=None):
    mandant = mandant or await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password=PW)
    return mandant, auth_headers(await login(client, user.email, PW))


def _body(name="Wartung 24/7", **extra):
    return {"name": name, "ziele": ZIELE, "stufen": STUFEN, "prioritaet_regeln": {"stoerung": 5}, **extra}


@pytest.mark.asyncio
async def test_anlegen_lesen_und_stufen(client, make_mandant, make_user):
    _, h = await _admin(client, make_mandant, make_user)
    resp = await client.post("/api/sla/richtlinien", headers=h, json=_body())
    assert resp.status_code == 201, resp.text
    daten = resp.json()
    assert daten["kalender"] == "rund_um_die_uhr"
    assert [s["position"] for s in daten["stufen"]] == [0, 1]
    assert daten["prioritaet_regeln"] == {"stoerung": 5}
    liste = (await client.get("/api/sla/richtlinien", headers=h)).json()
    assert [r["id"] for r in liste] == [daten["id"]]


@pytest.mark.asyncio
async def test_patch_ersetzt_stufen_und_standard_ist_exklusiv(client, make_mandant, make_user):
    _, h = await _admin(client, make_mandant, make_user)
    a = (await client.post("/api/sla/richtlinien", headers=h, json=_body("A", ist_standard=True))).json()
    b = (await client.post("/api/sla/richtlinien", headers=h, json=_body("B", ist_standard=True))).json()
    liste = {r["name"]: r for r in (await client.get("/api/sla/richtlinien", headers=h)).json()}
    assert liste["A"]["ist_standard"] is False and liste["B"]["ist_standard"] is True
    resp = await client.patch(f"/api/sla/richtlinien/{a['id']}", headers=h, json={"stufen": STUFEN[:1], "aktiv": False})
    assert resp.status_code == 200
    assert len(resp.json()["stufen"]) == 1 and resp.json()["aktiv"] is False
    assert b["ist_standard"] is True


@pytest.mark.asyncio
async def test_validierung(client, make_mandant, make_user):
    _, h = await _admin(client, make_mandant, make_user)
    post = lambda **k: client.post("/api/sla/richtlinien", headers=h, json=_body(**k))  # noqa: E731
    assert (await post(kalender="geschaeftszeiten")).status_code == 422  # kein Fenster
    assert (await post(kalender="geschaeftszeiten", geschaeftszeiten={"0": [["17:00", "07:00"]]})).status_code == 422
    assert (await post(kalender="geschaeftszeiten", geschaeftszeiten={"7": [["07:00", "17:00"]]})).status_code == 422
    assert (await post(ziele={"9": {"reaktion_min": 5}})).status_code == 422
    assert (await post(prioritaet_regeln={"quatsch": 5})).status_code == 422
    assert (await post(prioritaet_regeln={"stoerung": 6})).status_code == 422
    ok = await post(name="Buero", kalender="geschaeftszeiten", geschaeftszeiten={"0": [["07:00", "17:00"]]})
    assert ok.status_code == 201


@pytest.mark.asyncio
async def test_doppelter_name_ist_konflikt(client, make_mandant, make_user):
    _, h = await _admin(client, make_mandant, make_user)
    assert (await client.post("/api/sla/richtlinien", headers=h, json=_body())).status_code == 201
    assert (await client.post("/api/sla/richtlinien", headers=h, json=_body())).status_code == 409


@pytest.mark.asyncio
async def test_ohne_recht_sla_kein_zugriff(client, make_mandant, make_user):
    mandant, h = await _admin(client, make_mandant, make_user)
    rid = (await client.post("/api/sla/richtlinien", headers=h, json=_body())).json()["id"]
    # Neuer Rechtebereich: Account-Typen ohne ausdrueckliche Vergabe haben ihn nicht.
    for rolle, lesen in (("techniker", 403), ("disponent", 403)):
        user = await make_user(mandant=mandant, role=rolle, password=PW)
        hr = auth_headers(await login(client, user.email, PW))
        assert (await client.get("/api/sla/richtlinien", headers=hr)).status_code == lesen
        assert (await client.post("/api/sla/richtlinien", headers=hr, json=_body("X"))).status_code == 403
        assert (await client.patch(f"/api/sla/richtlinien/{rid}", headers=hr, json={"aktiv": False})).status_code == 403
        assert (await client.delete(f"/api/sla/richtlinien/{rid}", headers=hr)).status_code == 403


@pytest.mark.asyncio
async def test_mandantentrennung(client, make_mandant, make_user, make_kunde):
    _, h1 = await _admin(client, make_mandant, make_user)
    m2, h2 = await _admin(client, make_mandant, make_user)
    rid = (await client.post("/api/sla/richtlinien", headers=h1, json=_body())).json()["id"]
    assert (await client.get("/api/sla/richtlinien", headers=h2)).json() == []
    assert (await client.get(f"/api/sla/richtlinien/{rid}", headers=h2)).status_code == 404
    assert (await client.patch(f"/api/sla/richtlinien/{rid}", headers=h2, json={"aktiv": False})).status_code == 404
    assert (await client.delete(f"/api/sla/richtlinien/{rid}", headers=h2)).status_code == 404
    kunde = await make_kunde(mandant=m2)
    resp = await client.post(
        "/api/vertraege", headers=h2,
        json={"kunde_id": str(kunde.id), "bezeichnung": "V", "abrechnungsart": "pauschale", "sla_richtlinie_id": rid},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_vertrag_zuordnung_und_loeschsperre(client, make_mandant, make_user, make_kunde):
    mandant, h = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    rid = (await client.post("/api/sla/richtlinien", headers=h, json=_body())).json()["id"]
    vertrag = await client.post(
        "/api/vertraege", headers=h,
        json={"kunde_id": str(kunde.id), "bezeichnung": "V", "abrechnungsart": "wartungsvertrag", "sla_richtlinie_id": rid},
    )
    assert vertrag.status_code == 201 and vertrag.json()["sla_richtlinie_id"] == rid
    assert (await client.delete(f"/api/sla/richtlinien/{rid}", headers=h)).status_code == 409
    vid = vertrag.json()["id"]
    ab = await client.patch(f"/api/vertraege/{vid}", headers=h, json={"sla_richtlinie_id": None})
    assert ab.status_code == 200 and ab.json()["sla_richtlinie_id"] is None
    assert (await client.delete(f"/api/sla/richtlinien/{rid}", headers=h)).status_code == 204
    assert (await client.get("/api/sla/richtlinien", headers=h)).json() == []


@pytest.mark.asyncio
async def test_migration_0116_up_down_up():
    engine = _sync_engine()
    try:
        await _migrieren("downgrade", "0115")
        assert "sla_richtlinie_id" not in _spalten(engine, "vertraege")
        await _migrieren("upgrade", "head")
        assert "sla_richtlinie_id" in _spalten(engine, "vertraege")
        with engine.begin() as conn:
            for tabelle in ("sla_richtlinien", "sla_eskalationsstufen"):
                rls, force = conn.execute(
                    text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :t"), {"t": tabelle}
                ).one()
                assert rls and force, tabelle
    finally:
        await _migrieren("upgrade", "head")
        engine.dispose()
