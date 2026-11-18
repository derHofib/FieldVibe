"""MCP-Tools (Etappe 1, nur Lesen): Rechte, Mandantentrennung, Aufbereitung, Fehlerabbildung."""
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.mcpserver.exceptions import ToolError

from app.db.session import system_session
from app.mcp.aufbereitung import SEITENGROESSE, bereinigen, seite_aus
from app.mcp.oauth_provider import KiAccessToken
from app.mcp.tools import _basis
from app.models.mandant import Mandant
from app.models.pruefmittel import Pruefmittel
from app.models.pruefzyklus import Pruefzyklus
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

ERWARTETE_TOOLS = {
    "suchen",
    "vorgaenge_auflisten",
    "vorgang_lesen",
    "auftraege_auflisten",
    "auftrag_lesen",
    "projekte_auflisten",
    "projekt_lesen",
    "kunde_lesen",
    "anlage_lesen",
    "termine_auflisten",
    "pruefungen_faellig",
    "formular_vorlagen",
    "formular_lesen",
    "kennzahlen_vorgaenge",
    "insights",
    "offene_posten",
}


async def _admin_verbindung(make_mandant, make_user, mcp_client):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    admin = await make_user(mandant=mandant, role="mandant_admin")
    return mandant, admin, await verbinden(mcp_client, admin)


# --- Registrierung ------------------------------------------------------------------------


async def test_tools_list_enthaelt_genau_die_lesetools_alle_read_only(make_mandant, make_user, mcp_client):
    _, _, t = await _admin_verbindung(make_mandant, make_user, mcp_client)
    tools = (await mcp_rpc(mcp_client, t["access_token"], "tools/list")).json()["result"]["tools"]
    assert {x["name"] for x in tools} == ERWARTETE_TOOLS
    assert all(x["annotations"]["readOnlyHint"] is True for x in tools)
    # Verbotene Aktionen sind gar nicht erst registriert.
    for name in {x["name"] for x in tools}:
        assert not any(w in name for w in ("loeschen", "anlegen", "abschliessen", "senden", "freigeben", "export"))
    assert all(x["description"] for x in tools)


async def test_ressource_begriffe(make_mandant, make_user, mcp_client):
    _, _, t = await _admin_verbindung(make_mandant, make_user, mcp_client)
    liste = (await mcp_rpc(mcp_client, t["access_token"], "resources/list")).json()["result"]["resources"]
    assert [r["uri"] for r in liste] == ["fieldvibe://begriffe"]
    gelesen = (await mcp_rpc(mcp_client, t["access_token"], "resources/read", {"uri": "fieldvibe://begriffe"})).json()
    text = gelesen["result"]["contents"][0]["text"]
    assert "Begriffsverzeichnis" in text and "Vorgang" in text


def test_begriffe_kopie_entspricht_docs():
    docs = Path(__file__).resolve().parents[2] / "docs" / "BEGRIFFE.md"
    kopie = Path(__file__).resolve().parents[1] / "app" / "mcp" / "begriffe.md"
    if not docs.exists():  # z. B. im Backend-Image ohne docs/
        pytest.skip("docs/ nicht vorhanden")
    assert kopie.read_text(encoding="utf-8") == docs.read_text(encoding="utf-8"), (
        "backend/app/mcp/begriffe.md muss eine Kopie von docs/BEGRIFFE.md sein"
    )


# --- Mandantentrennung und Rechte --------------------------------------------------------------


async def test_mandant_b_sieht_nichts_von_mandant_a(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant_a = await make_mandant("Alpha")
    mandant_b = await make_mandant("Beta")
    await ki_modul_setzen(mandant_a)
    await ki_modul_setzen(mandant_b)
    kunde_a = await make_kunde(mandant=mandant_a, name="Geheimkunde Alpha")
    vorgang_a = await make_vorgang(mandant=mandant_a, kunde=kunde_a, titel="Geheimer Alpha-Vorgang")
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin")
    admin_b = await make_user(mandant=mandant_b, role="mandant_admin")
    ta = await verbinden(mcp_client, admin_a)
    tb = await verbinden(mcp_client, admin_b)

    eigene = await tool_aufrufen(mcp_client, ta["access_token"], "vorgaenge_auflisten")
    assert [e["titel"] for e in eigene["daten"]["eintraege"]] == ["Geheimer Alpha-Vorgang"]

    fremd = await tool_aufrufen(mcp_client, tb["access_token"], "vorgaenge_auflisten")
    assert fremd["daten"]["eintraege"] == []
    # Direkter Zugriff per ID: nicht gefunden, kein Hinweis auf die Existenz.
    for name, args in (
        ("vorgang_lesen", {"vorgang_id": str(vorgang_a.id)}),
        ("kunde_lesen", {"kunde_id": str(kunde_a.id)}),
    ):
        r = await tool_aufrufen(mcp_client, tb["access_token"], name, args)
        assert r["fehler"] is True and "Nicht gefunden" in r["text"], (name, r)
    such = await tool_aufrufen(mcp_client, tb["access_token"], "suchen", {"text": "Geheim"})
    assert such["daten"]["treffer"] == []
    assert "Geheim" in (await tool_aufrufen(mcp_client, ta["access_token"], "suchen", {"text": "Geheim"}))["text"]


async def test_techniker_mit_scope_eigene_sieht_nur_eigene_vorgaenge(
    make_mandant, make_kunde, make_vorgang, mcp_client
):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    kunde = await make_kunde(mandant=mandant)
    tech = await custom_nutzer(
        mandant,
        "Techniker",
        {"vorgaenge": ("sehen",), "ki_zugriff": ("sehen",)},
        scopes_je_bereich={"vorgaenge": "eigene", "ki_zugriff": "mandant"},
    )
    andere = await custom_nutzer(mandant, "Kollege", {"vorgaenge": ("sehen",)})
    eigener = await make_vorgang(mandant=mandant, kunde=kunde, titel="Mein Vorgang", zugewiesener_user_id=tech.id)
    fremder = await make_vorgang(mandant=mandant, kunde=kunde, titel="Fremder Vorgang", zugewiesener_user_id=andere.id)
    t = await verbinden(mcp_client, tech)

    liste = await tool_aufrufen(mcp_client, t["access_token"], "vorgaenge_auflisten")
    assert [e["titel"] for e in liste["daten"]["eintraege"]] == ["Mein Vorgang"]
    assert (await tool_aufrufen(mcp_client, t["access_token"], "vorgang_lesen", {"vorgang_id": str(eigener.id)}))["fehler"] is False
    fremd = await tool_aufrufen(mcp_client, t["access_token"], "vorgang_lesen", {"vorgang_id": str(fremder.id)})
    assert fremd["fehler"] is True and "Nicht gefunden" in fremd["text"]


async def test_fehlendes_fachrecht_wird_als_verstaendlicher_tool_fehler_gemeldet(make_mandant, mcp_client):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    nutzer = await custom_nutzer(mandant, "Nur KI", {"ki_zugriff": ("sehen",)})
    t = await verbinden(mcp_client, nutzer)
    r = await tool_aufrufen(mcp_client, t["access_token"], "vorgaenge_auflisten")
    assert r["fehler"] is True
    assert "Dafür fehlt dir das Recht" in r["text"]
    assert "Traceback" not in r["text"]


async def test_modul_abrechnung_aus_wird_als_fehler_gemeldet(make_mandant, make_user, mcp_client):
    mandant, _, t = await _admin_verbindung(make_mandant, make_user, mcp_client)
    async with system_session(grund="test") as session:
        m = await session.get(Mandant, mandant.id)
        m.deaktivierte_module = [*m.deaktivierte_module, "abrechnung"]
    r = await tool_aufrufen(mcp_client, t["access_token"], "offene_posten")
    assert r["fehler"] is True and "nicht freigeschaltet" in r["text"]


async def test_nicht_gefunden_und_ungueltige_eingabe(make_mandant, make_user, mcp_client):
    _, _, t = await _admin_verbindung(make_mandant, make_user, mcp_client)
    nicht = await tool_aufrufen(mcp_client, t["access_token"], "vorgang_lesen", {"vorgang_id": str(uuid.uuid4())})
    assert nicht["fehler"] and "Nicht gefunden" in nicht["text"]
    ungueltig = await tool_aufrufen(mcp_client, t["access_token"], "vorgang_lesen", {"vorgang_id": "kein-uuid"})
    assert ungueltig["fehler"] and "Ungültige Eingabe" in ungueltig["text"]
    falsches_argument = await tool_aufrufen(mcp_client, t["access_token"], "vorgaenge_auflisten", {"status": "unbekannt"})
    assert falsches_argument["fehler"]


async def test_scope_wird_je_aufruf_geprueft():
    token = KiAccessToken(
        token="t", client_id="c", scopes=[LESEN], user_id=uuid.uuid4(), mandant_id=uuid.uuid4(),
        role="custom", tv=0, kv=uuid.uuid4(),
    )
    marke = auth_context_var.set(AuthenticatedUser(token))
    try:
        assert _basis.zugriff(LESEN) is token
        with pytest.raises(ToolError, match="fieldvibe.schreiben"):
            _basis.zugriff(SCHREIBEN)
    finally:
        auth_context_var.reset(marke)
    with pytest.raises(ToolError, match="Nicht angemeldet"):
        _basis.zugriff(LESEN)


# --- Inhalte --------------------------------------------------------------------------------


async def test_vorgang_lesen_liefert_detail_verlauf_maengel_und_formulare(
    make_mandant, make_user, make_kunde, make_vorgang, mcp_client
):
    mandant, admin, t = await _admin_verbindung(make_mandant, make_user, mcp_client)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, titel="Heizung defekt")
    kopf = auth_headers(await login(mcp_client, admin.email, PASSWORT))
    kommentar = await mcp_client.post(
        f"/api/vorgaenge/{vorgang.id}/events", json={"event_type": "kommentar", "body": "Techniker war vor Ort"}, headers=kopf
    )
    assert kommentar.status_code == 201, kommentar.text

    r = await tool_aufrufen(mcp_client, t["access_token"], "vorgang_lesen", {"vorgang_id": str(vorgang.id)})
    assert r["fehler"] is False
    assert r["daten"]["vorgang"]["titel"] == "Heizung defekt"
    assert any(e.get("body") == "Techniker war vor Ort" for e in r["daten"]["verlauf"]["eintraege"])
    assert r["daten"]["maengel"]["eintraege"] == [] and r["daten"]["formulare"]["eintraege"] == []


async def test_kunde_lesen_mit_standorten_und_anlagen_und_sensible_felder_fehlen(
    make_mandant, make_user, make_kunde, make_anlage, mcp_client
):
    mandant, _, t = await _admin_verbindung(make_mandant, make_user, mcp_client)
    kunde = await make_kunde(mandant=mandant, name="Musterfirma")
    anlage = await make_anlage(
        mandant=mandant, kunde=kunde, bezeichnung="Brenner 1", stammdaten={"hersteller": "Viessmann", "iban": "DE0012345"}
    )
    r = await tool_aufrufen(mcp_client, t["access_token"], "kunde_lesen", {"kunde_id": str(kunde.id)})
    assert r["daten"]["kunde"]["name"] == "Musterfirma"
    assert [a["bezeichnung"] for a in r["daten"]["anlagen"]["eintraege"]] == ["Brenner 1"]
    assert "standorte" in r["daten"]

    a = await tool_aufrufen(mcp_client, t["access_token"], "anlage_lesen", {"anlage_id": str(anlage.id)})
    assert a["daten"]["anlage"]["bezeichnung"] == "Brenner 1"
    assert "Viessmann" in a["text"] and "DE0012345" not in a["text"] and "iban" not in a["text"]
    assert a["daten"]["pruefzyklen"] == []


async def test_suchen_mit_typ_filter(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, _, t = await _admin_verbindung(make_mandant, make_user, mcp_client)
    kunde = await make_kunde(mandant=mandant, name="Brandt Elektro")
    await make_vorgang(mandant=mandant, kunde=kunde, titel="Brandt Wartung")
    alle = await tool_aufrufen(mcp_client, t["access_token"], "suchen", {"text": "Brandt"})
    assert {x["kategorie"] for x in alle["daten"]["treffer"]} >= {"kunde", "vorgang"}
    nur = await tool_aufrufen(mcp_client, t["access_token"], "suchen", {"text": "Brandt", "typ": "kunde"})
    assert {x["kategorie"] for x in nur["daten"]["treffer"]} == {"kunde"}


async def test_listen_sind_auf_100_begrenzt_mit_seiten(make_mandant, make_user, make_kunde, mcp_client):
    mandant, _, t = await _admin_verbindung(make_mandant, make_user, mcp_client)
    kunde = await make_kunde(mandant=mandant)
    async with system_session(grund="test") as session:
        for i in range(105):
            session.add(
                Vorgang(
                    mandant_id=mandant.id, vorgangsnummer=f"V-{i:04d}", kunde_id=kunde.id, titel=f"Vorgang {i}",
                    abrechnungsart="aufwand", leistungstyp="stoerung",
                )
            )
    seite1 = (await tool_aufrufen(mcp_client, t["access_token"], "vorgaenge_auflisten"))["daten"]
    assert len(seite1["eintraege"]) == SEITENGROESSE == 100
    assert seite1["gekuerzt"] is True and seite1["anzahl_gesamt"] == 105 and "seite=2" in seite1["hinweis"]
    seite2 = (await tool_aufrufen(mcp_client, t["access_token"], "vorgaenge_auflisten", {"seite": 2}))["daten"]
    assert len(seite2["eintraege"]) == 5 and seite2["gekuerzt"] is False
    ids = {e["id"] for e in seite1["eintraege"]} | {e["id"] for e in seite2["eintraege"]}
    assert len(ids) == 105


async def test_pruefungen_faellig(make_mandant, make_user, make_kunde, make_anlage, mcp_client):
    mandant, _, t = await _admin_verbindung(make_mandant, make_user, mcp_client)
    anlage = await make_anlage(mandant=mandant, kunde=await make_kunde(mandant=mandant), bezeichnung="Feuerlöscher")
    jetzt = datetime.now(timezone.utc)
    async with system_session(grund="test") as session:
        session.add_all(
            [
                Pruefzyklus(mandant_id=mandant.id, anlage_id=anlage.id, bezeichnung="Bald", intervall_wert=12,
                            intervall_einheit="monat", naechste_pruefung_am=jetzt + timedelta(days=10)),
                Pruefzyklus(mandant_id=mandant.id, anlage_id=anlage.id, bezeichnung="Ueberfaellig", intervall_wert=12,
                            intervall_einheit="monat", naechste_pruefung_am=jetzt - timedelta(days=5)),
                Pruefzyklus(mandant_id=mandant.id, anlage_id=anlage.id, bezeichnung="Spaeter", intervall_wert=12,
                            intervall_einheit="monat", naechste_pruefung_am=jetzt + timedelta(days=100)),
                Pruefmittel(mandant_id=mandant.id, bezeichnung="Messgerät", kalibrierintervall_monate=12,
                            naechste_kalibrierung_am=(jetzt + timedelta(days=20)).date()),
            ]
        )
    r = (await tool_aufrufen(mcp_client, t["access_token"], "pruefungen_faellig", {"tage": 30}))["daten"]
    assert [z["bezeichnung"] for z in r["pruefzyklen"]["eintraege"]] == ["Ueberfaellig", "Bald"]
    assert [m["bezeichnung"] for m in r["pruefmittel"]["eintraege"]] == ["Messgerät"]
    spaeter = (await tool_aufrufen(mcp_client, t["access_token"], "pruefungen_faellig", {"tage": 365}))["daten"]
    assert len(spaeter["pruefzyklen"]["eintraege"]) == 3


async def test_auswertungs_und_uebrige_tools_laufen_fuer_admin(make_mandant, make_user, mcp_client):
    _, _, t = await _admin_verbindung(make_mandant, make_user, mcp_client)
    kennzahlen = await tool_aufrufen(
        mcp_client, t["access_token"], "kennzahlen_vorgaenge", {"von": "2026-01-01", "bis": "2026-12-31"}
    )
    assert kennzahlen["fehler"] is False and kennzahlen["daten"]["offene_vorgaenge_gesamt"] == 0
    assert "vorgaenge_nach_status" in (await tool_aufrufen(mcp_client, t["access_token"], "insights"))["daten"]
    offene = await tool_aufrufen(mcp_client, t["access_token"], "offene_posten")
    assert offene["fehler"] is False and "summe_debitoren" in offene["daten"]
    for name in ("auftraege_auflisten", "projekte_auflisten", "termine_auflisten"):
        r = await tool_aufrufen(mcp_client, t["access_token"], name)
        assert r["fehler"] is False and r["daten"]["eintraege"] == [], name
    assert (await tool_aufrufen(mcp_client, t["access_token"], "auftrag_lesen", {"auftrag_id": str(uuid.uuid4())}))["fehler"]


async def test_formular_vorlagen_und_lesen_fuer_vorgang(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, _, t = await _admin_verbindung(make_mandant, make_user, mcp_client)
    vorgang = await make_vorgang(mandant=mandant, kunde=await make_kunde(mandant=mandant))
    r = await tool_aufrufen(mcp_client, t["access_token"], "formular_vorlagen", {"vorgang_id": str(vorgang.id)})
    assert r["fehler"] is False and r["daten"]["eintraege"] == []
    fehlt = await tool_aufrufen(mcp_client, t["access_token"], "formular_lesen", {"formular_id": str(uuid.uuid4())})
    assert fehlt["fehler"] and "Nicht gefunden" in fehlt["text"]


# --- Aufbereitung (Einheit) ---------------------------------------------------------------------


def test_bereinigen_entfernt_sensible_felder_rekursiv():
    roh = {
        "name": "Firma",
        "iban": "DE1",
        "bank": {"bic": "X", "bank_name": "Sparkasse", "IBAN_nummer": "y"},
        "passwort_hash": "h",
        "mfa_secret_enc": "m",
        "access_token": "t",
        "refresh_token": "r",
        "foto_url": "https://signiert",
        "liste": [{"secret": 1, "ok": 2}],
        "public": "bleibt",
        "basic": "bleibt auch",
    }
    assert bereinigen(roh) == {
        "name": "Firma",
        "bank": {"bank_name": "Sparkasse"},
        "liste": [{"ok": 2}],
        "public": "bleibt",
        "basic": "bleibt auch",
    }


def test_seite_aus_begrenzt_und_kennzeichnet():
    eintraege = [{"n": i} for i in range(230)]
    s1 = seite_aus(eintraege, 1)
    assert len(s1["eintraege"]) == 100 and s1["gekuerzt"] and s1["anzahl_gesamt"] == 230
    s3 = seite_aus(eintraege, 3)
    assert len(s3["eintraege"]) == 30 and not s3["gekuerzt"] and "hinweis" not in s3
    leer = seite_aus(eintraege, 9)
    assert leer["eintraege"] == [] and "leer" in leer["hinweis"]
    abgeschnitten = seite_aus(eintraege[:200], 2, quelle_abgeschnitten=True)
    assert "Obergrenze" in abgeschnitten["hinweis"]
