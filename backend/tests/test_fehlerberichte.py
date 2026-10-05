import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import system_session
from app.models.account_typ import AccountTypRecht
from app.models.fehlerbericht import Fehlerbericht
from app.models.user import User
from app.services import storage_service
from app.services.fehlerbericht_service import (
    ai_bundle_markdown,
    berechne_fingerprint,
    loesche_abgelaufene_fehlerberichte,
    schwaerze,
)
from tests.conftest import auth_headers, login

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.abc_DEF-123"

TOKEN = "service-token-fuer-tests"
TOKEN_HASH = hashlib.sha256(TOKEN.encode()).hexdigest()


def _kontext(fehler: str = "TypeError: x is undefined") -> dict:
    return {
        "netzwerk": [
            {"zeit": "10:00:01", "methode": "GET", "url": "/api/vorgaenge", "status": 200, "dauer_ms": 30},
            {
                "zeit": "10:00:02", "methode": "POST", "url": "/api/anlagen", "status": 500, "dauer_ms": 120,
                "request_body": '{"bezeichnung": "Test"}', "response_body": '{"detail": "Boom"}',
                "request_headers": {"Authorization": "Bearer geheim", "Accept": "json"},
            },
        ],
        "konsole": [
            {"zeit": "10:00:02", "level": "error", "nachricht": fehler,
             "stack": "TypeError: x\n    at render (https://app.de/assets/index-AbC12345.js:10:20)"},
        ],
        "breadcrumbs": [
            {"zeit": "10:00:00", "typ": "route", "ziel": "/anlagen"},
            {"zeit": "10:00:01", "typ": "klick", "ziel": "button#speichern", "text": "Speichern"},
        ],
        "umgebung": {"browser": "Firefox"},
        "sitzung": {"rolle": "mandant_admin"},
        "app_state": {"filter": "alle"},
    }


def _payload(**extra) -> dict:
    daten = {
        "titel": "Speichern schlägt fehl",
        "beschreibung": "Beim Speichern kommt ein Fehler",
        "schweregrad": "hoch",
        "kontext": _kontext(),
        "route": "/anlagen/3f2c1b9e-1111-2222-3333-444455556666",
        "app_version": "1.2.3",
        "commit_sha": "abc123",
    }
    daten.update(extra)
    return {"payload": json.dumps(daten)}


async def _admin_token(client, make_mandant, make_user, name="Betrieb"):
    mandant = await make_mandant(name=name)
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    return mandant, await login(client, admin.email, "pw-123456")


@pytest.fixture
def service_token(monkeypatch):
    monkeypatch.setattr(get_settings(), "fehlerbericht_service_token_hash", TOKEN_HASH)
    return {"Authorization": f"Bearer {TOKEN}"}


# --- Schwaerzung -----------------------------------------------------------


def test_schwaerze_header_und_schluessel():
    ergebnis = schwaerze(
        {
            "request_headers": {"Authorization": "Bearer x", "Cookie": "a=b", "Accept": "json"},
            "response_headers": {"Set-Cookie": "s=1", "X-Api-Key": "k", "X-Auth-Token": "t", "Proxy-Authorization": "p"},
            "login": {"Passwort": "geheim", "password": "x", "neuesKennwort": "y", "userPin": "1234", "IBAN": "DE00"},
            "mapping": "bleibt", "shipping": "bleibt", "pin": "9999",
        }
    )
    assert ergebnis["request_headers"] == {"Authorization": "[entfernt]", "Cookie": "[entfernt]", "Accept": "json"}
    assert set(ergebnis["response_headers"].values()) == {"[entfernt]"}
    assert set(ergebnis["login"].values()) == {"[entfernt]"}
    assert ergebnis["mapping"] == "bleibt" and ergebnis["shipping"] == "bleibt"
    assert ergebnis["pin"] == "[entfernt]"


def test_schwaerze_verschachtelt_und_listen():
    ergebnis = schwaerze({"a": [{"b": {"api_key": "x", "ok": 1}}, [{"clientSecret": "y"}]]})
    assert ergebnis == {"a": [{"b": {"api_key": "[entfernt]", "ok": 1}}, [{"clientSecret": "[entfernt]"}]]}


def test_schwaerze_schluessel_mit_strukturiertem_wert_komplett_entfernt():
    assert schwaerze({"token": {"a": 1}, "credentials": ["x"]}) == {"token": "[entfernt]", "credentials": "[entfernt]"}


def test_schwaerze_header_paarliste():
    assert schwaerze({"headers": [["Authorization", "Bearer x"], ["Accept", "json"]]}) == {
        "headers": [["Authorization", "[entfernt]"], ["Accept", "json"]]
    }


def test_schwaerze_jwt_im_fliesstext():
    ergebnis = schwaerze({"nachricht": f"Fehler bei Token {JWT} im Request", "liste": [f"x{JWT}"]})
    assert JWT not in json.dumps(ergebnis)
    assert ergebnis["nachricht"] == "Fehler bei Token [entfernt] im Request"


def test_schwaerze_laesst_unkritisches_unveraendert():
    original = {"zeit": "10:00", "status": 200, "ok": True, "n": None, "liste": [1, 2.5, "text"], "url": "/api/x?a=1"}
    assert schwaerze(original) == original


# --- Anlegen / Rechte ------------------------------------------------------


@pytest.mark.asyncio
async def test_anlegen_ohne_screenshots(client, make_mandant, make_user):
    mandant, token = await _admin_token(client, make_mandant, make_user)
    resp = await client.post("/api/fehlerberichte", headers=auth_headers(token), data=_payload())
    assert resp.status_code == 201, resp.text
    assert resp.json()["duplikat_von_id"] is None

    detail = await client.get(f"/api/fehlerberichte/{resp.json()['id']}", headers=auth_headers(token))
    body = detail.json()
    assert body["status"] == "neu"
    assert body["mandant_id"] == str(mandant.id)
    assert body["melder_name"] == "Test User"
    assert body["screenshot_original_url"] is None
    assert "email" not in json.dumps(body).lower()
    # Serverseitige Schwaerzung greift auch bei sauberem Frontend-Input nicht kaputt
    assert body["kontext"]["netzwerk"][1]["request_headers"]["Authorization"] == "[entfernt]"


@pytest.mark.asyncio
async def test_anlegen_mit_screenshots_und_loeschen_entfernt_s3(client, make_mandant, make_user):
    _, token = await _admin_token(client, make_mandant, make_user)
    resp = await client.post(
        "/api/fehlerberichte",
        headers=auth_headers(token),
        data=_payload(),
        files={
            "screenshot_original": ("a.png", PNG, "image/png"),
            "screenshot_annotiert": ("b.png", PNG, "image/png"),
        },
    )
    assert resp.status_code == 201, resp.text
    bericht_id = resp.json()["id"]
    detail = (await client.get(f"/api/fehlerberichte/{bericht_id}", headers=auth_headers(token))).json()
    assert detail["screenshot_original_url"].startswith("http")
    assert detail["screenshot_annotiert_url"] is not None

    async with system_session() as session:
        b = await session.get(Fehlerbericht, uuid.UUID(bericht_id))
        keys = [b.screenshot_original_key, b.screenshot_annotiert_key]
    assert all(k and k.startswith("mandanten/") for k in keys)
    assert await storage_service.download_bytes(keys[0]) == PNG

    assert (await client.delete(f"/api/fehlerberichte/{bericht_id}", headers=auth_headers(token))).status_code == 204
    for k in keys:
        with pytest.raises(ClientError):
            await storage_service.download_bytes(k)


@pytest.mark.asyncio
async def test_screenshot_validierung(client, make_mandant, make_user):
    _, token = await _admin_token(client, make_mandant, make_user)
    h = auth_headers(token)
    falscher_typ = await client.post(
        "/api/fehlerberichte", headers=h, data=_payload(), files={"screenshot_original": ("a.gif", PNG, "image/gif")}
    )
    assert falscher_typ.status_code == 415
    falsche_magic = await client.post(
        "/api/fehlerberichte", headers=h, data=_payload(), files={"screenshot_original": ("a.png", b"kein bild", "image/png")}
    )
    assert falsche_magic.status_code == 415
    zu_gross = await client.post(
        "/api/fehlerberichte", headers=h, data=_payload(),
        files={"screenshot_original": ("a.png", PNG + b"\x00" * (5 * 1024 * 1024), "image/png")},
    )
    assert zu_gross.status_code == 413


@pytest.mark.asyncio
async def test_kontext_ueber_1mb_413_und_ungueltiger_payload_422(client, make_mandant, make_user):
    _, token = await _admin_token(client, make_mandant, make_user)
    h = auth_headers(token)
    gross = await client.post("/api/fehlerberichte", headers=h, data=_payload(kontext={"x": "a" * (1024 * 1024 + 10)}))
    assert gross.status_code == 413
    kaputt = await client.post("/api/fehlerberichte", headers=h, data={"payload": "{kein json"})
    assert kaputt.status_code == 422
    ohne_titel = await client.post("/api/fehlerberichte", headers=h, data={"payload": json.dumps({"beschreibung": "x"})})
    assert ohne_titel.status_code == 422


@pytest.mark.asyncio
async def test_mandant_und_user_kommen_aus_auth_nicht_aus_payload(client, make_mandant, make_user):
    mandant, token = await _admin_token(client, make_mandant, make_user)
    fremd = await make_mandant(name="Fremd")
    resp = await client.post(
        "/api/fehlerberichte", headers=auth_headers(token),
        data=_payload(mandant_id=str(fremd.id), user_id=str(uuid.uuid4())),
    )
    assert resp.status_code == 201
    async with system_session() as session:
        b = await session.get(Fehlerbericht, uuid.UUID(resp.json()["id"]))
        assert b.mandant_id == mandant.id


@pytest.mark.asyncio
async def test_recht_fehlt_403_und_custom_mit_recht_201(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")
    h = auth_headers(token)

    assert (await client.post("/api/fehlerberichte", headers=h, data=_payload())).status_code == 403
    assert (await client.get("/api/fehlerberichte", headers=h)).status_code == 403

    async with system_session() as session:
        user = (await session.execute(select(User).where(User.id == techniker.id))).scalar_one()
        for aktion in ("sehen", "erstellen"):
            session.add(
                AccountTypRecht(account_typ_id=user.account_typ_id, bereich="fehlerberichte", aktion=aktion, erlaubt=True)
            )
    assert (await client.post("/api/fehlerberichte", headers=h, data=_payload())).status_code == 201
    assert (await client.get("/api/fehlerberichte", headers=h)).status_code == 200
    # bearbeiten/loeschen nicht vergeben
    bid = (await client.get("/api/fehlerberichte", headers=h)).json()[0]["id"]
    assert (await client.patch(f"/api/fehlerberichte/{bid}", headers=h, json={"status": "gesichtet"})).status_code == 403
    assert (await client.delete(f"/api/fehlerberichte/{bid}", headers=h)).status_code == 403


@pytest.mark.asyncio
async def test_rate_limit_10_pro_stunde(client, make_mandant, make_user):
    _, token = await _admin_token(client, make_mandant, make_user)
    for _ in range(10):
        assert (await client.post("/api/fehlerberichte", headers=auth_headers(token), data=_payload())).status_code == 201
    resp = await client.post("/api/fehlerberichte", headers=auth_headers(token), data=_payload())
    assert resp.status_code == 429


# --- RLS / Sichtbarkeit ----------------------------------------------------


@pytest.mark.asyncio
async def test_rls_mandant_b_sieht_und_aendert_bericht_von_a_nicht(client, make_mandant, make_user):
    _, token_a = await _admin_token(client, make_mandant, make_user, name="Alpha")
    _, token_b = await _admin_token(client, make_mandant, make_user, name="Beta")
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")
    token_s = await login(client, super_admin.email, "pw-123456")

    bid_a = (await client.post("/api/fehlerberichte", headers=auth_headers(token_a), data=_payload())).json()["id"]
    bid_b = (await client.post("/api/fehlerberichte", headers=auth_headers(token_b), data=_payload())).json()["id"]

    hb = auth_headers(token_b)
    assert (await client.get(f"/api/fehlerberichte/{bid_a}", headers=hb)).status_code == 404
    assert (await client.patch(f"/api/fehlerberichte/{bid_a}", headers=hb, json={"status": "behoben"})).status_code == 404
    assert (await client.delete(f"/api/fehlerberichte/{bid_a}", headers=hb)).status_code == 404
    assert (await client.get(f"/api/fehlerberichte/{bid_a}/ai-bundle", headers=hb)).status_code == 404
    assert [b["id"] for b in (await client.get("/api/fehlerberichte", headers=hb)).json()] == [bid_b]
    assert (await client.get("/api/fehlerberichte/zaehler", headers=hb)).json()["gesamt"] == 1

    hs = auth_headers(token_s)
    liste = (await client.get("/api/fehlerberichte", headers=hs)).json()
    assert {b["id"] for b in liste} == {bid_a, bid_b}
    assert {b["mandant_name"] for b in liste} == {"Alpha", "Beta"}
    assert (await client.get("/api/fehlerberichte/zaehler", headers=hs)).json()["gesamt"] == 2
    gefiltert = (await client.get(f"/api/fehlerberichte?mandant_id={liste[0]['mandant_id']}", headers=hs)).json()
    assert len(gefiltert) == 1


@pytest.mark.asyncio
async def test_liste_filter_und_zaehler(client, make_mandant, make_user):
    _, token = await _admin_token(client, make_mandant, make_user)
    h = auth_headers(token)
    await client.post("/api/fehlerberichte", headers=h, data=_payload(titel="Alpha-Problem", kontext={}))
    r2 = await client.post("/api/fehlerberichte", headers=h, data=_payload(titel="Beta", schweregrad="niedrig", kontext={}))
    await client.patch(f"/api/fehlerberichte/{r2.json()['id']}", headers=h, json={"status": "gesichtet"})

    assert len((await client.get("/api/fehlerberichte?q=alpha", headers=h)).json()) == 1
    assert len((await client.get("/api/fehlerberichte?status=gesichtet", headers=h)).json()) == 1
    assert len((await client.get("/api/fehlerberichte?schweregrad=hoch", headers=h)).json()) == 1
    assert len((await client.get("/api/fehlerberichte?limit=1", headers=h)).json()) == 1
    assert "kontext" not in (await client.get("/api/fehlerberichte", headers=h)).json()[0]
    z = (await client.get("/api/fehlerberichte/zaehler", headers=h)).json()
    assert z["neu"] == 1 and z["gesichtet"] == 1 and z["gesamt"] == 2


# --- Fingerprint / Duplikate / PATCH ---------------------------------------


def test_fingerprint_stabil_gegen_ids_zahlen_und_build_hash():
    a = _kontext("Fehler 4711 bei 3f2c1b9e-1111-2222-3333-444455556666")
    b = _kontext("Fehler 9 bei aaaaaaaa-1111-2222-3333-444455556666")
    b["konsole"][0]["stack"] = "TypeError: x\n    at render (https://app.de/assets/index-ZzZ99999.js:77:1)"
    assert berechne_fingerprint(a, "/anlagen/1") == berechne_fingerprint(b, "/anlagen/2?x=1")
    assert berechne_fingerprint(a, "/anlagen/1") != berechne_fingerprint(a, "/vorgaenge/1")
    assert berechne_fingerprint({"konsole": [{"level": "log", "nachricht": "x"}]}, "/x") is None
    assert berechne_fingerprint({}, "/x") is None
    assert berechne_fingerprint({"fehler": "Kaputt"}, "/x") is not None


@pytest.mark.asyncio
async def test_duplikat_erkennung_nur_bei_offenem_bericht_desselben_mandanten(client, make_mandant, make_user):
    _, token_a = await _admin_token(client, make_mandant, make_user, name="Alpha")
    _, token_b = await _admin_token(client, make_mandant, make_user, name="Beta")
    ha, hb = auth_headers(token_a), auth_headers(token_b)

    erster = (await client.post("/api/fehlerberichte", headers=ha, data=_payload())).json()
    assert erster["duplikat_von_id"] is None
    zweiter = (await client.post("/api/fehlerberichte", headers=ha, data=_payload())).json()
    assert zweiter["duplikat_von_id"] == erster["id"]
    assert (await client.get(f"/api/fehlerberichte/{zweiter['id']}", headers=ha)).json()["status"] == "neu"
    # anderer Mandant: kein Treffer
    assert (await client.post("/api/fehlerberichte", headers=hb, data=_payload())).json()["duplikat_von_id"] is None
    # nach "behoben" nicht mehr offen
    for bid in (erster["id"], zweiter["id"]):
        await client.patch(f"/api/fehlerberichte/{bid}", headers=ha, json={"status": "behoben"})
    assert (await client.post("/api/fehlerberichte", headers=ha, data=_payload())).json()["duplikat_von_id"] is None


@pytest.mark.asyncio
async def test_patch_setzt_erledigt_am(client, make_mandant, make_user):
    _, token = await _admin_token(client, make_mandant, make_user)
    h = auth_headers(token)
    bid = (await client.post("/api/fehlerberichte", headers=h, data=_payload())).json()["id"]
    url = f"/api/fehlerberichte/{bid}"

    assert (await client.patch(url, headers=h, json={"status": "in_arbeit"})).json()["erledigt_am"] is None
    for erledigt in ("behoben", "abgelehnt", "duplikat"):
        assert (await client.patch(url, headers=h, json={"status": erledigt})).json()["erledigt_am"] is not None
    resp = await client.patch(url, headers=h, json={"status": "gesichtet", "loesungsnotiz": "Notiz"})
    assert resp.json()["erledigt_am"] is None and resp.json()["loesungsnotiz"] == "Notiz"
    assert (await client.patch(url, headers=h, json={"status": "kaputt"})).status_code == 422
    assert (await client.patch(url, headers=h, json={"duplikat_von_id": bid})).status_code == 422


# --- AI-Bundle -------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_bundle_enthaelt_fehlgeschlagenen_request_und_konsolenfehler(client, make_mandant, make_user):
    _, token = await _admin_token(client, make_mandant, make_user)
    h = auth_headers(token)
    bid = (
        await client.post(
            "/api/fehlerberichte", headers=h, data=_payload(),
            files={"screenshot_original": ("a.png", PNG, "image/png")},
        )
    ).json()["id"]
    resp = await client.get(f"/api/fehlerberichte/{bid}/ai-bundle", headers=h)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    md = resp.text
    assert "POST /api/anlagen -> 500" in md
    assert '{"detail": "Boom"}' in md
    assert "TypeError: x is undefined" in md
    assert "1. [10:00:00] route: /anlagen" in md
    assert "Reproduktion aus Klickpfad" in md and "Alle Requests (2)" in md
    assert md.index("Fehlgeschlagene Requests") < md.index("Alle Requests")
    assert "Geheim" not in md and "Bearer geheim" not in md
    assert "Original (1 h gültig)" in md


def test_ai_bundle_robust_gegen_kaputten_kontext():
    b = Fehlerbericht(
        id=uuid.uuid4(), mandant_id=uuid.uuid4(), titel="T", beschreibung="B", schweregrad="mittel", status="neu",
        kontext={"netzwerk": "kaputt", "konsole": [None, 5, {"level": "error"}], "breadcrumbs": [{"ziel": None}],
                 "umgebung": 7, "app_state": {"x": object()}},
    )
    md = ai_bundle_markdown(b)
    assert "# Fehlerbericht: T" in md
    b.kontext = None
    assert "Fehlgeschlagene Requests (0)" in ai_bundle_markdown(b)


# --- Service-API -----------------------------------------------------------


@pytest.mark.asyncio
async def test_service_api_ohne_hash_setting_404(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "fehlerbericht_service_token_hash", None)
    for pfad in ("", f"/{uuid.uuid4()}", f"/{uuid.uuid4()}/ai-bundle", f"/{uuid.uuid4()}/aehnliche"):
        resp = await client.get(f"/api/service/fehlerberichte{pfad}", headers={"Authorization": f"Bearer {TOKEN}"})
        assert resp.status_code == 404
    assert (await client.patch(f"/api/service/fehlerberichte/{uuid.uuid4()}", json={})).status_code == 404


@pytest.mark.asyncio
async def test_service_api_falscher_token_401_und_limit_429(client, service_token):
    assert (await client.get("/api/service/fehlerberichte")).status_code == 401
    for _ in range(9):
        r = await client.get("/api/service/fehlerberichte", headers={"Authorization": "Bearer falsch"})
        assert r.status_code == 401
    assert (await client.get("/api/service/fehlerberichte", headers={"Authorization": "Bearer falsch"})).status_code == 429
    # auch der richtige Token ist waehrend der Sperre blockiert
    assert (await client.get("/api/service/fehlerberichte", headers=service_token)).status_code == 429


@pytest.mark.asyncio
async def test_service_api_liest_mandantenuebergreifend_und_auditiert(client, make_mandant, make_user, service_token):
    _, token_a = await _admin_token(client, make_mandant, make_user, name="Alpha")
    _, token_b = await _admin_token(client, make_mandant, make_user, name="Beta")
    bid_a = (await client.post("/api/fehlerberichte", headers=auth_headers(token_a), data=_payload())).json()["id"]
    bid_b = (await client.post("/api/fehlerberichte", headers=auth_headers(token_b), data=_payload())).json()["id"]

    liste = (await client.get("/api/service/fehlerberichte", headers=service_token)).json()
    assert {b["id"] for b in liste} == {bid_a, bid_b}
    assert len((await client.get("/api/service/fehlerberichte?status=behoben", headers=service_token)).json()) == 0

    detail = (await client.get(f"/api/service/fehlerberichte/{bid_a}", headers=service_token)).json()
    assert detail["mandant_name"] == "Alpha" and "kontext" in detail
    md = await client.get(f"/api/service/fehlerberichte/{bid_a}/ai-bundle", headers=service_token)
    assert md.status_code == 200 and "POST /api/anlagen -> 500" in md.text
    aehnliche = (await client.get(f"/api/service/fehlerberichte/{bid_a}/aehnliche", headers=service_token)).json()
    assert [b["id"] for b in aehnliche] == [bid_b]
    assert (await client.get(f"/api/service/fehlerberichte/{uuid.uuid4()}", headers=service_token)).status_code == 404

    from app.models.audit_log import AuditLog

    async with system_session() as session:
        eintraege = (await session.execute(select(AuditLog).where(AuditLog.aktion == "fehlerbericht.service_zugriff"))).scalars().all()
    assert any(e.entity_id == uuid.UUID(bid_a) and e.mandant_id is not None for e in eintraege)
    assert len(eintraege) >= 4


@pytest.mark.asyncio
async def test_service_patch_nur_erlaubte_felder(client, make_mandant, make_user, service_token):
    _, token = await _admin_token(client, make_mandant, make_user)
    bid = (await client.post("/api/fehlerberichte", headers=auth_headers(token), data=_payload())).json()["id"]
    url = f"/api/service/fehlerberichte/{bid}"

    resp = await client.patch(
        url, headers=service_token,
        json={"status": "behoben", "loesungsnotiz": "Fix", "fix_commit": "deadbeef", "fix_pr_url": "https://x/pr/1"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "behoben" and body["erledigt_am"] is not None
    assert body["fix_commit"] == "deadbeef" and body["fix_pr_url"] == "https://x/pr/1"

    for verboten in ({"titel": "x"}, {"duplikat_von_id": bid}, {"kontext": {}}, {"mandant_id": str(uuid.uuid4())}):
        assert (await client.patch(url, headers=service_token, json=verboten)).status_code == 422


# --- Loeschjob -------------------------------------------------------------


@pytest.mark.asyncio
async def test_loeschjob_entfernt_alte_berichte_und_s3_objekte(make_mandant, monkeypatch):
    monkeypatch.setattr(get_settings(), "fehlerbericht_aufbewahrung_tage", 90)
    mandant = await make_mandant()
    alt_id, neu_id = uuid.uuid4(), uuid.uuid4()
    key = storage_service.new_fehlerbericht_screenshot_key(mandant.id, alt_id, "original")
    await storage_service.upload_bytes(key, PNG, "image/png")
    async with system_session() as session:
        for bid, alter, k in ((alt_id, 91, key), (neu_id, 89, None)):
            session.add(
                Fehlerbericht(
                    id=bid, mandant_id=mandant.id, titel="t", beschreibung="b", schweregrad="mittel",
                    screenshot_original_key=k, created_at=datetime.now(timezone.utc) - timedelta(days=alter),
                )
            )

    assert await loesche_abgelaufene_fehlerberichte() == 1
    async with system_session() as session:
        ids = (await session.execute(select(Fehlerbericht.id))).scalars().all()
    assert ids == [neu_id]
    with pytest.raises(ClientError):
        await storage_service.download_bytes(key)


# --- Ideen / Änderungswünsche ----------------------------------------------


async def _super_token(client, make_user):
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")
    return await login(client, super_admin.email, "pw-123456")


async def _idee(client, token, **extra) -> str:
    resp = await client.post(
        "/api/fehlerberichte", headers=auth_headers(token),
        data=_payload(art="idee", titel="Export als PDF", schweregrad="mittel", erwartet="Spart Zeit", **extra),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_idee_anlegen_ohne_fingerprint_default_art_fehler(client, make_mandant, make_user):
    _, token = await _admin_token(client, make_mandant, make_user)
    h = auth_headers(token)
    fehler_id = (await client.post("/api/fehlerberichte", headers=h, data=_payload())).json()["id"]
    assert (await client.get(f"/api/fehlerberichte/{fehler_id}", headers=h)).json()["art"] == "fehler"

    # Gleicher Kontext/Route wie der offene Fehler -> bei Fehler waere es ein Duplikat.
    resp = await client.post("/api/fehlerberichte", headers=h, data=_payload(art="idee", schweregrad="niedrig"))
    assert resp.status_code == 201 and resp.json()["duplikat_von_id"] is None
    detail = (await client.get(f"/api/fehlerberichte/{resp.json()['id']}", headers=h)).json()
    assert detail["art"] == "idee" and detail["freigegeben_am"] is None
    async with system_session() as session:
        b = await session.get(Fehlerbericht, uuid.UUID(resp.json()["id"]))
        assert b.fingerprint is None and b.duplikat_von_id is None


@pytest.mark.asyncio
async def test_idee_blockierend_422_und_ungueltige_art_422(client, make_mandant, make_user):
    _, token = await _admin_token(client, make_mandant, make_user)
    h = auth_headers(token)
    assert (await client.post("/api/fehlerberichte", headers=h, data=_payload(art="idee", schweregrad="blockierend"))).status_code == 422
    assert (await client.post("/api/fehlerberichte", headers=h, data=_payload(art="sonstiges"))).status_code == 422


@pytest.mark.asyncio
async def test_filter_art_in_liste_und_zaehler(client, make_mandant, make_user):
    _, token = await _admin_token(client, make_mandant, make_user)
    h = auth_headers(token)
    await client.post("/api/fehlerberichte", headers=h, data=_payload(kontext={}))
    await _idee(client, token)
    await _idee(client, token)
    assert len((await client.get("/api/fehlerberichte?art=idee", headers=h)).json()) == 2
    assert len((await client.get("/api/fehlerberichte?art=fehler", headers=h)).json()) == 1
    assert len((await client.get("/api/fehlerberichte", headers=h)).json()) == 3
    assert (await client.get("/api/fehlerberichte/zaehler?art=idee", headers=h)).json()["gesamt"] == 2
    assert (await client.get("/api/fehlerberichte/zaehler?art=fehler", headers=h)).json()["gesamt"] == 1
    assert (await client.get("/api/fehlerberichte/zaehler", headers=h)).json()["gesamt"] == 3


@pytest.mark.asyncio
async def test_idee_mandant_admin_darf_nicht_patchen_fehler_schon(client, make_mandant, make_user):
    _, token = await _admin_token(client, make_mandant, make_user)
    h = auth_headers(token)
    idee_id = await _idee(client, token)
    fehler_id = (await client.post("/api/fehlerberichte", headers=h, data=_payload())).json()["id"]

    for body in ({"status": "gesichtet"}, {"loesungsnotiz": "x"}, {"duplikat_von_id": fehler_id}):
        resp = await client.patch(f"/api/fehlerberichte/{idee_id}", headers=h, json=body)
        assert resp.status_code == 403, body
        assert "Betreiber" in resp.json()["detail"]
    assert (await client.patch(f"/api/fehlerberichte/{fehler_id}", headers=h, json={"status": "gesichtet"})).status_code == 200
    # Lesen und Loeschen bleiben moeglich.
    assert (await client.get(f"/api/fehlerberichte/{idee_id}", headers=h)).status_code == 200
    assert (await client.delete(f"/api/fehlerberichte/{idee_id}", headers=h)).status_code == 204


@pytest.mark.asyncio
async def test_super_admin_gibt_idee_frei(client, make_mandant, make_user):
    _, token = await _admin_token(client, make_mandant, make_user)
    idee_id = await _idee(client, token)
    hs = auth_headers(await _super_token(client, make_user))
    resp = await client.patch(f"/api/fehlerberichte/{idee_id}", headers=hs, json={"status": "gesichtet"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "gesichtet" and resp.json()["freigegeben_am"] is not None
    resp = await client.patch(f"/api/fehlerberichte/{idee_id}", headers=hs, json={"status": "abgelehnt"})
    assert resp.json()["freigegeben_am"] is None


@pytest.mark.asyncio
async def test_service_idee_freigabe_regeln(client, make_mandant, make_user, service_token):
    _, token = await _admin_token(client, make_mandant, make_user)
    idee_id = await _idee(client, token)
    url = f"/api/service/fehlerberichte/{idee_id}"

    for verboten in ("gesichtet", "abgelehnt", "duplikat"):
        assert (await client.patch(url, headers=service_token, json={"status": verboten})).status_code == 403
    for ziel in ("in_arbeit", "behoben"):
        resp = await client.patch(url, headers=service_token, json={"status": ziel})
        assert resp.status_code == 409 and resp.json()["detail"] == "Idee nicht freigegeben"
    # Notiz (Rueckfrage) ohne Statuswechsel ist erlaubt.
    assert (await client.patch(url, headers=service_token, json={"loesungsnotiz": "Frage"})).status_code == 200

    hs = auth_headers(await _super_token(client, make_user))
    await client.patch(f"/api/fehlerberichte/{idee_id}", headers=hs, json={"status": "gesichtet"})
    assert (await client.patch(url, headers=service_token, json={"status": "in_arbeit"})).status_code == 200
    resp = await client.patch(url, headers=service_token, json={"status": "behoben", "fix_pr_url": "https://x/pr/2"})
    assert resp.status_code == 200 and resp.json()["erledigt_am"] is not None

    liste = (await client.get("/api/service/fehlerberichte?art=idee", headers=service_token)).json()
    assert [b["id"] for b in liste] == [idee_id]
    assert (await client.get("/api/service/fehlerberichte?art=fehler", headers=service_token)).json() == []


@pytest.mark.asyncio
async def test_ai_bundle_idee_und_fehler_art(client, make_mandant, make_user):
    _, token = await _admin_token(client, make_mandant, make_user)
    h = auth_headers(token)
    idee_id = await _idee(client, token)
    md = (await client.get(f"/api/fehlerberichte/{idee_id}/ai-bundle", headers=h)).text
    assert "Idee / Änderungswunsch (nicht freigegeben)" in md
    assert "## Was soll sich ändern?" in md and "## Warum / Nutzen" in md and "Spart Zeit" in md
    assert "Priorität" in md and "Schweregrad" not in md and "Klickpfad" not in md

    hs = auth_headers(await _super_token(client, make_user))
    await client.patch(f"/api/fehlerberichte/{idee_id}", headers=hs, json={"status": "gesichtet"})
    md = (await client.get(f"/api/fehlerberichte/{idee_id}/ai-bundle", headers=hs)).text
    assert "freigegeben am " in md and "nicht freigegeben" not in md

    fehler_id = (await client.post("/api/fehlerberichte", headers=h, data=_payload())).json()["id"]
    assert "**Art:** Fehler" in (await client.get(f"/api/fehlerberichte/{fehler_id}/ai-bundle", headers=h)).text


def test_migration_0099_up_down_up():
    import os
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    backend = os.path.dirname(os.path.dirname(__file__))
    cfg = Config(os.path.join(backend, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(backend, "alembic"))
    engine = create_engine(os.environ.get("DATABASE_URL_SYNC") or get_settings().database_url_sync)

    def spalten():
        return {c["name"] for c in inspect(engine).get_columns("fehlerberichte")}

    try:
        command.downgrade(cfg, "0098")
        assert not {"art", "freigegeben_am"} & spalten()
        command.upgrade(cfg, "head")
        assert {"art", "freigegeben_am"} <= spalten()
        assert "ix_fehlerberichte_art_status" in {i["name"] for i in inspect(engine).get_indexes("fehlerberichte")}
    finally:
        engine.dispose()
