from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.sla_service import sla_info
from tests.conftest import auth_headers, login

PW = "pw-123456"
ZIELE = {
    "3": {"reaktion_min": 60, "loesung_min": 240},
    "5": {"reaktion_min": 15, "loesung_min": 60},
}


def _zeit(wert: str) -> datetime:
    return datetime.fromisoformat(wert.replace("Z", "+00:00"))


async def _setup(client, make_mandant, make_user, make_kunde, **richtlinie):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW)
    h = auth_headers(await login(client, admin.email, PW))
    kunde = await make_kunde(mandant=mandant)
    body = {"name": "Standard", "ist_standard": True, "ziele": ZIELE, **richtlinie}
    r = await client.post("/api/sla/richtlinien", headers=h, json=body)
    assert r.status_code == 201, r.text
    return h, kunde, r.json()


def _vorgang(kunde, **extra):
    return {
        "kunde_id": str(kunde.id), "titel": "Stoerung", "abrechnungsart": "aufwand",
        "leistungstyp": "stoerung", **extra,
    }


@pytest.mark.asyncio
async def test_fristen_aus_standardrichtlinie(client, make_mandant, make_user, make_kunde):
    h, kunde, _ = await _setup(client, make_mandant, make_user, make_kunde)
    vorgang = (await client.post("/api/vorgaenge", headers=h, json=_vorgang(kunde))).json()
    sla = vorgang["sla"]
    assert sla["status"] == "ok"
    assert _zeit(sla["reaktion_faellig_am"]) - datetime.now(timezone.utc) < timedelta(minutes=61)
    assert _zeit(sla["loesung_faellig_am"]) - _zeit(sla["reaktion_faellig_am"]) == timedelta(minutes=180)


@pytest.mark.asyncio
async def test_ohne_richtlinie_keine_sla(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW)
    h = auth_headers(await login(client, admin.email, PW))
    kunde = await make_kunde(mandant=mandant)
    assert (await client.post("/api/vorgaenge", headers=h, json=_vorgang(kunde))).json()["sla"] is None


@pytest.mark.asyncio
async def test_vertragsrichtlinie_hat_vorrang_und_prioritaetsregel_hebt_nur_an(
    client, make_mandant, make_user, make_kunde
):
    h, kunde, standard = await _setup(client, make_mandant, make_user, make_kunde)
    eigene = (
        await client.post(
            "/api/sla/richtlinien", headers=h,
            json={"name": "Bereitschaft", "ziele": ZIELE, "prioritaet_regeln": {"stoerung": 5}},
        )
    ).json()
    vertrag = (
        await client.post(
            "/api/vertraege", headers=h,
            json={"kunde_id": str(kunde.id), "bezeichnung": "V", "abrechnungsart": "wartungsvertrag",
                  "sla_richtlinie_id": eigene["id"]},
        )
    ).json()
    mit_vertrag = (
        await client.post("/api/vorgaenge", headers=h, json=_vorgang(kunde, vertrag_id=vertrag["id"]))
    ).json()
    assert mit_vertrag["prioritaet"] == 5  # Regel: Stoerung -> 5
    assert _zeit(mit_vertrag["sla"]["reaktion_faellig_am"]) - datetime.now(timezone.utc) < timedelta(minutes=16)
    # Andere Leistungstypen bleiben unberuehrt, hoehere Prioritaeten werden nie gesenkt.
    wartung = (
        await client.post("/api/vorgaenge", headers=h,
                          json=_vorgang(kunde, vertrag_id=vertrag["id"], leistungstyp="wartung", prioritaet=4))
    ).json()
    assert wartung["prioritaet"] == 4
    ohne = (await client.post("/api/vorgaenge", headers=h, json=_vorgang(kunde))).json()
    assert ohne["prioritaet"] == 3  # Standard-Richtlinie hat keine Regel
    assert standard["id"] != eigene["id"]


@pytest.mark.asyncio
async def test_inaktiver_vertrag_faellt_auf_standard_zurueck(client, make_mandant, make_user, make_kunde):
    h, kunde, _ = await _setup(client, make_mandant, make_user, make_kunde)
    eigene = (
        await client.post("/api/sla/richtlinien", headers=h,
                          json={"name": "V", "ziele": ZIELE, "prioritaet_regeln": {"stoerung": 5}})
    ).json()
    vertrag = (
        await client.post("/api/vertraege", headers=h,
                          json={"kunde_id": str(kunde.id), "bezeichnung": "V", "abrechnungsart": "wartungsvertrag",
                                "sla_richtlinie_id": eigene["id"]})
    ).json()
    await client.patch(f"/api/vertraege/{vertrag['id']}", headers=h, json={"aktiv": False})
    vorgang = (await client.post("/api/vorgaenge", headers=h, json=_vorgang(kunde, vertrag_id=vertrag["id"]))).json()
    assert vorgang["prioritaet"] == 3


@pytest.mark.asyncio
async def test_kommentar_erfuellt_die_reaktion(client, make_mandant, make_user, make_kunde):
    h, kunde, _ = await _setup(client, make_mandant, make_user, make_kunde)
    vorgang = (await client.post("/api/vorgaenge", headers=h, json=_vorgang(kunde))).json()
    assert vorgang["sla"]["reagiert_am"] is None
    r = await client.post(
        f"/api/vorgaenge/{vorgang['id']}/events", headers=h, json={"event_type": "kommentar", "body": "Bin dran"}
    )
    assert r.status_code in (200, 201), r.text
    sla = (await client.get(f"/api/vorgaenge/{vorgang['id']}", headers=h)).json()["sla"]
    assert sla["reagiert_am"] is not None and sla["reaktion_ergebnis"] == "erfuellt"


@pytest.mark.asyncio
async def test_wartet_kunde_haelt_die_uhr_an(client, make_mandant, make_user, make_kunde):
    h, kunde, _ = await _setup(client, make_mandant, make_user, make_kunde)
    vorgang = (await client.post("/api/vorgaenge", headers=h, json=_vorgang(kunde))).json()
    vid = vorgang["id"]
    pause = (await client.patch(f"/api/vorgaenge/{vid}", headers=h, json={"status": "wartet_kunde"})).json()
    assert pause["sla"]["status"] == "pausiert"
    assert pause["sla"]["reagiert_am"] is not None  # Statuswechsel weg von neu zaehlt als Reaktion
    weiter = (await client.patch(f"/api/vorgaenge/{vid}", headers=h, json={"status": "in_arbeit"})).json()
    assert weiter["sla"]["status"] == "ok"
    assert _zeit(weiter["sla"]["loesung_faellig_am"]) > datetime.now(timezone.utc) + timedelta(minutes=200)


@pytest.mark.asyncio
async def test_abschluss_beendet_die_loesungsfrist(client, make_mandant, make_user, make_kunde):
    h, kunde, _ = await _setup(client, make_mandant, make_user, make_kunde)
    vid = (await client.post("/api/vorgaenge", headers=h, json=_vorgang(kunde))).json()["id"]
    zu = await client.patch(f"/api/vorgaenge/{vid}", headers=h, json={"status": "abgeschlossen"})
    assert zu.status_code == 200, zu.text
    sla = zu.json()["sla"]
    assert sla["status"] == "erfuellt" and sla["loesung_ergebnis"] == "erfuellt" and sla["geloest_am"]


@pytest.mark.asyncio
async def test_prioritaetswechsel_rechnet_fristen_neu(client, make_mandant, make_user, make_kunde):
    h, kunde, _ = await _setup(client, make_mandant, make_user, make_kunde)
    vorgang = (await client.post("/api/vorgaenge", headers=h, json=_vorgang(kunde))).json()
    neu = (await client.patch(f"/api/vorgaenge/{vorgang['id']}", headers=h, json={"prioritaet": 5})).json()
    assert _zeit(neu["sla"]["loesung_faellig_am"]) < _zeit(vorgang["sla"]["loesung_faellig_am"])
    assert _zeit(neu["sla"]["loesung_faellig_am"]) - datetime.now(timezone.utc) < timedelta(minutes=61)


@pytest.mark.asyncio
async def test_uebernehmen_zaehlt_als_reaktion(client, make_mandant, make_user, make_kunde):
    h, kunde, _ = await _setup(client, make_mandant, make_user, make_kunde)
    vid = (await client.post("/api/vorgaenge", headers=h, json=_vorgang(kunde))).json()["id"]
    r = await client.post(f"/api/vorgaenge/{vid}/uebernehmen", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["sla"]["reaktion_ergebnis"] == "erfuellt"


def _fake(**felder):
    basis = dict(
        sla_richtlinie_id=uuid4(), sla_laeuft_seit=datetime(2026, 1, 1, tzinfo=timezone.utc),
        sla_start_am=datetime(2026, 1, 1, tzinfo=timezone.utc), created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        sla_reaktion_faellig_am=None, sla_loesung_faellig_am=None, sla_reagiert_am=None, sla_geloest_am=None,
        sla_reaktion_ergebnis=None, sla_loesung_ergebnis=None,
    )
    return SimpleNamespace(**{**basis, **felder})


def test_sla_info_statusableitung():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    faellig = start + timedelta(hours=4)
    v = _fake(sla_loesung_faellig_am=faellig)
    assert sla_info(v, jetzt=start + timedelta(hours=1))["status"] == "ok"
    assert sla_info(v, jetzt=start + timedelta(hours=3, minutes=10))["status"] == "gefaehrdet"
    assert sla_info(v, jetzt=start + timedelta(hours=5))["status"] == "verletzt"
    assert sla_info(_fake(sla_laeuft_seit=None), jetzt=start)["status"] == "pausiert"
    assert sla_info(_fake(sla_richtlinie_id=None)) is None
    verletzt = _fake(sla_geloest_am=start, sla_reaktion_ergebnis="verletzt", sla_loesung_ergebnis="erfuellt")
    assert sla_info(verletzt)["status"] == "verletzt"
    # Verletzte Reaktion bleibt auch bei offener Loesung sichtbar.
    assert sla_info(_fake(sla_reaktion_ergebnis="verletzt", sla_reagiert_am=start), jetzt=start)["status"] == "verletzt"
