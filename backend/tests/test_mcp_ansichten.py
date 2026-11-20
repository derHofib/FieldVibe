"""MCP-Ansichten (Konzept formulare, Etappe C): Herkunft "ki" ueber den MCP-Server, formular_lesen gruppiert,
protokoll_anzeigen mit/ohne MCP Apps, ui://-Ressourcen."""
import json

from sqlalchemy import select

from app.db.session import system_session
from app.mcp.ansichten import AENDERUNG_URI, PROTOKOLL_URI, VORLAGE_URI
from app.mcp.protokoll_ansicht import abschnitte_aus, protokoll_text
from app.models.form_modul import FormSubmission
from tests.mcp_helfer import (
    LESEN,
    SCHREIBEN,
    mcp_client,  # noqa: F401
    mcp_laeuft,  # noqa: F401
    mcp_rpc,
    tool_aufrufen,
)
from tests.test_mcp_protokolle import (
    _bereit,
    _detail,
    _schreibverbindung,
    _veroeffentlichen,
    _vorlage_entwerfen,
)

APPS_ID = "io.modelcontextprotocol/ui"
APPS_MIME = "text/html;profile=mcp-app"


async def _mit_grenzwert_bereit(make_mandant, make_user, make_kunde, make_vorgang, mcp_client, grenze=1000):
    """Vorlage per KI entworfen, Grenzwert fuer den CO-Wert im Baukasten gesetzt (REST), veroeffentlicht."""
    mandant, admin, token, kopf = await _schreibverbindung(make_mandant, make_user, mcp_client)
    daten = await _vorlage_entwerfen(mcp_client, token)
    detail = await _detail(mcp_client, kopf, daten["id"])
    co = next(f for f in detail["fields"] if f["key"] == "co_wert_ppm")
    r = await mcp_client.patch(
        f"/api/form-schemas/{daten['id']}/fields/{co['id']}", json={"validation": {"warn_max": grenze}}, headers=kopf
    )
    assert r.status_code == 200, r.text
    await _veroeffentlichen(mcp_client, kopf, daten["id"])
    vorgang = await make_vorgang(mandant=mandant, kunde=await make_kunde(mandant=mandant), leistungstyp="wartung")
    return mandant, token, kopf, daten["id"], vorgang


# --- erstellt_via -------------------------------------------------------------------------------------


async def test_ki_kennzeichnung_kommt_ueber_mcp_an(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, token, kopf, vorlage_id, vorgang = await _bereit(make_mandant, make_user, make_kunde, make_vorgang, mcp_client)
    detail = await _detail(mcp_client, kopf, vorlage_id)
    assert detail["erstellt_via"] == "ki"
    liste = (await mcp_client.get("/api/form-schemas", headers=kopf)).json()
    assert [s["erstellt_via"] for s in liste] == ["ki"]

    r = await tool_aufrufen(
        mcp_client, token, "protokoll_entwurf_anlegen", {"vorgang_id": str(vorgang.id), "vorlage_id": vorlage_id, "werte": {"CO-Wert (ppm)": 3}}
    )
    assert r["fehler"] is False, r["text"]
    sub = (await mcp_client.get(f"/api/form-submissions/{r['daten']['id']}", headers=kopf)).json()
    assert sub["erstellt_via"] == "ki"
    uebersicht = (await mcp_client.get("/api/form-submissions/uebersicht", headers=kopf)).json()
    assert [e["erstellt_via"] for e in uebersicht["eintraege"]] == ["ki"]

    # Ein von einem Menschen in der App angelegtes Protokoll derselben Vorlage bleibt "app".
    menschlich = await mcp_client.post(
        "/api/form-submissions", params={"vorgang_id": str(vorgang.id)}, json={"schema_id": vorlage_id}, headers=kopf
    )
    assert menschlich.json()["erstellt_via"] == "app"
    async with system_session(grund="test") as session:
        vias = {s.erstellt_via for s in (await session.execute(select(FormSubmission))).scalars()}
    assert vias == {"ki", "app"}


# --- formular_lesen -----------------------------------------------------------------------------------


async def test_formular_lesen_gruppiert_nach_abschnitten(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, token, kopf, vorlage_id, vorgang = await _mit_grenzwert_bereit(make_mandant, make_user, make_kunde, make_vorgang, mcp_client)
    angelegt = await tool_aufrufen(
        mcp_client, token, "protokoll_entwurf_anlegen",
        {
            "vorgang_id": str(vorgang.id), "vorlage_id": vorlage_id,
            "werte": {"Prüfpunkte": {"Brenner gereinigt": False}, "CO-Wert (ppm)": "1500,5", "Mängel": [{"Beschreibung": "Dichtung porös"}]},
        },
    )
    r = await tool_aufrufen(mcp_client, token, "formular_lesen", {"formular_id": angelegt["daten"]["id"]})
    assert r["fehler"] is False, r["text"]
    d = r["daten"]
    assert d["values"]["messwerte"][0]["co_wert_ppm"] == "1500.5"  # Rohwerte bleiben
    abschnitte = {a["titel"]: a for a in d["abschnitte"]}
    assert list(abschnitte) == ["Kopf und Anlagendaten", "Prüfpunkte", "Messwerte", "Mängel", "Abschluss"]
    pruef = {f["label"]: f for f in abschnitte["Prüfpunkte"]["eintraege"][0]["felder"]}
    assert pruef["Brenner gereinigt"]["anzeige"] == "Nein" and pruef["Brenner gereinigt"]["wert"] is False
    co = {f["label"]: f for f in abschnitte["Messwerte"]["eintraege"][0]["felder"]}["CO-Wert (ppm)"]
    assert co["anzeige"] == "1500,5" and co["grenzwert"] == {"richtung": "ueber", "grenze": "1000", "text": "über 1000"}
    assert abschnitte["Mängel"]["wiederholbar"] is True
    assert abschnitte["Mängel"]["eintraege"][0]["felder"][0]["anzeige"] == "Dichtung porös"
    assert "Unterschrift Kunde" in d["fehlende_pflichtfelder"]


async def test_formular_lesen_ohne_formulare_recht_bleibt_bei_rohwerten(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    from tests.mcp_helfer import custom_nutzer, verbinden

    mandant, token, kopf, vorlage_id, vorgang = await _mit_grenzwert_bereit(make_mandant, make_user, make_kunde, make_vorgang, mcp_client)
    angelegt = await tool_aufrufen(
        mcp_client, token, "protokoll_entwurf_anlegen", {"vorgang_id": str(vorgang.id), "vorlage_id": vorlage_id, "werte": {"CO-Wert (ppm)": 3}}
    )
    leser = await custom_nutzer(mandant, "Leser", {"vorgaenge": ("sehen",), "ki_zugriff": ("sehen",)})
    t = await verbinden(mcp_client, leser, [LESEN])
    r = await tool_aufrufen(mcp_client, t["access_token"], "formular_lesen", {"formular_id": angelegt["daten"]["id"]})
    assert r["fehler"] is False, r["text"]
    assert "abschnitte" not in r["daten"] and r["daten"]["values"] and "Gruppierung" in r["daten"]["hinweis"]


def test_abschnitte_aus_ohne_gruppen_und_ohne_werte():
    schema = {
        "groups": [],
        "fields": [{"key": "a", "feld_typ": "text", "label": {"de": "Anlage"}, "reihenfolge": 0, "group_key": None, "pflichtfeld": False, "validation": {}}],
    }
    assert abschnitte_aus(schema, {}) == [
        {"titel": "Allgemein", "wiederholbar": False, "eintraege": [{"felder": [{"label": "Anlage", "typ": "text", "pflicht": False, "anzeige": "—", "leer": True}]}]}
    ]


# --- protokoll_anzeigen -------------------------------------------------------------------------------


async def _protokoll_mit_foto(mcp_client, token, kopf, vorlage_id, vorgang) -> str:
    angelegt = await tool_aufrufen(
        mcp_client, token, "protokoll_entwurf_anlegen",
        {
            "vorgang_id": str(vorgang.id), "vorlage_id": vorlage_id,
            "werte": {
                "Wartungsdatum": "2026-11-18", "Prüfpunkte": {"Brenner gereinigt": True}, "CO-Wert (ppm)": 1500, "Zustand": 4,
                "Mängel": [{"Beschreibung": "Dichtung porös"}],
            },
        },
    )
    assert angelegt["fehler"] is False, angelegt["text"]
    pid = angelegt["daten"]["id"]
    # Das Foto kommt in der Praxis aus der Feld-App; hier direkt per REST wie dort (inkl. signierter URL und Key).
    r = await mcp_client.patch(
        f"/api/form-submissions/{pid}",
        json={"values": {"maengel": [{"beschreibung": "Dichtung porös", "foto": {"key": "mandant/geheim-schluessel.jpg", "url": "https://s3.example/signiert?X-Amz-Signature=abc"}}]}},
        headers=kopf,
    )
    assert r.status_code == 200, r.text
    return pid


async def test_protokoll_anzeigen_liefert_text_und_strukturierte_daten(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, token, kopf, vorlage_id, vorgang = await _mit_grenzwert_bereit(make_mandant, make_user, make_kunde, make_vorgang, mcp_client)
    pid = await _protokoll_mit_foto(mcp_client, token, kopf, vorlage_id, vorgang)
    r = await tool_aufrufen(mcp_client, token, "protokoll_anzeigen", {"protokoll_id": pid})
    assert r["fehler"] is False, r["text"]
    d = r["daten"]
    assert d["art"] == "protokoll" and d["vorlage"] == "Wartung Gastherme" and d["status"] == "offen" and d["erstellt_via"] == "ki"
    assert d["vorgang"]["id"] == str(vorgang.id) and d["vorgang"]["nummer"] == vorgang.vorgangsnummer
    assert d["fotos_anzahl"] == 1
    assert d["fehlende_pflichtfelder"] == ["Unterschrift Kunde"]
    assert d["link"].endswith(f"/form-submissions/{pid}")
    co = {f["label"]: f for a in d["abschnitte"] for e in a["eintraege"] for f in e["felder"]}["CO-Wert (ppm)"]
    assert co["grenzwert"]["text"] == "über 1000"
    # Ohne Apps: lesbarer Text mit denselben Inhalten, ohne Apps-Hinweis.
    assert "Messwerte" in r["text"] and "CO-Wert (ppm): 1500 ⚠ über 1000" in r["text"] and "Brenner gereinigt: Ja" in r["text"]
    assert "Noch fehlende Pflichtfelder: Unterschrift Kunde" in r["text"] and f"/form-submissions/{pid}" in r["text"]
    assert "Fotos: 1" in r["text"] and "Ansicht wird im Chat" not in r["text"]
    # Keine Storage-Keys, signierten Links oder Tokens.
    gesamt = r["text"] + json.dumps(d)
    for verboten in ("geheim-schluessel", "X-Amz", "s3.example", "Bearer", "eyJ"):
        assert verboten not in gesamt


async def test_protokoll_anzeigen_mit_apps_clientfaehigkeit_im_modernen_umschlag(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    from mcp.shared.inbound import MCP_METHOD_HEADER, MCP_NAME_HEADER, MCP_PROTOCOL_VERSION_HEADER  # noqa: F401

    mandant, token, kopf, vorlage_id, vorgang = await _mit_grenzwert_bereit(make_mandant, make_user, make_kunde, make_vorgang, mcp_client)
    pid = await _protokoll_mit_foto(mcp_client, token, kopf, vorlage_id, vorgang)
    from tests.mcp_helfer import verbinden  # noqa: F401

    version = "2026-07-28"
    body = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {
            "name": "protokoll_anzeigen", "arguments": {"protokoll_id": pid},
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": version,
                "io.modelcontextprotocol/clientCapabilities": {"extensions": {APPS_ID: {"mimeTypes": [APPS_MIME]}}},
            },
        },
    }
    antwort = await mcp_client.post(
        "/mcp", content=json.dumps(body),
        headers={
            "Accept": "application/json, text/event-stream", "Content-Type": "application/json",
            "Authorization": f"Bearer {token}", "mcp-protocol-version": version, "mcp-method": "tools/call", "mcp-name": "protokoll_anzeigen",
        },
    )
    assert antwort.status_code == 200, antwort.text
    ergebnis = antwort.json()["result"]
    text = ergebnis["content"][0]["text"]
    assert text.startswith("Die Ansicht wird im Chat angezeigt")
    assert ergebnis["structuredContent"]["art"] == "protokoll"


# --- Registrierung: Werkzeug-Metadaten und ui://-Ressourcen ------------------------------------------------


async def test_tools_tragen_ui_verweis_und_ressourcen_sind_abrufbar(make_mandant, make_user, mcp_client):
    from tests.mcp_helfer import verbinden

    mandant, admin, token, kopf = await _schreibverbindung(make_mandant, make_user, mcp_client)
    tools = {t["name"]: t for t in (await mcp_rpc(mcp_client, token, "tools/list")).json()["result"]["tools"]}
    assert tools["protokoll_anzeigen"]["_meta"]["ui"]["resourceUri"] == PROTOKOLL_URI
    assert tools["protokoll_anzeigen"]["annotations"]["readOnlyHint"] is True
    for name in ("vorlage_entwurf",):
        assert tools[name]["_meta"]["ui"]["resourceUri"] == VORLAGE_URI
    assert "_meta" not in tools["dokument_abrufen"] or "ui" not in tools["dokument_abrufen"]["_meta"]
    for name in ("vorgang_speichern", "verknuepfen", "kommentar_anlegen", "protokoll_entwurf"):
        assert tools[name]["_meta"]["ui"]["resourceUri"] == AENDERUNG_URI

    liste = {r["uri"]: r for r in (await mcp_rpc(mcp_client, token, "resources/list")).json()["result"]["resources"]}
    assert liste[PROTOKOLL_URI]["mimeType"] == APPS_MIME and liste[VORLAGE_URI]["mimeType"] == APPS_MIME and liste[AENDERUNG_URI]["mimeType"] == APPS_MIME
    for uri in (PROTOKOLL_URI, VORLAGE_URI, AENDERUNG_URI):
        inhalt = (await mcp_rpc(mcp_client, token, "resources/read", {"uri": uri})).json()["result"]["contents"][0]
        assert inhalt["mimeType"] == APPS_MIME
        html = inhalt["text"]
        assert html.startswith("<!doctype html>") and "prefers-color-scheme: dark" in html
        assert "/*STIL*/" not in html and "/*BRUECKE*/" not in html and "ui/initialize" in html
        # Keine externen Skripte/Stile/Bilder, kein innerHTML mit Daten, keine Tokens.
        assert "<script src" not in html and "<link" not in html and "@import" not in html and "innerHTML" not in html
        assert "Authorization" not in html and "Bearer" not in html


async def test_schreib_scope_tools_bleiben_ohne_scope_ungelistet(make_mandant, make_user, mcp_client):
    from tests.mcp_helfer import ki_modul_setzen, verbinden

    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    admin = await make_user(mandant=mandant, role="mandant_admin")
    t = await verbinden(mcp_client, admin, [LESEN])
    namen = {x["name"] for x in (await mcp_rpc(mcp_client, t["access_token"], "tools/list")).json()["result"]["tools"]}
    assert "protokoll_anzeigen" in namen and "vorlage_entwurf" not in namen


async def test_vorlage_entwerfen_liefert_ansichtsdaten(make_mandant, make_user, mcp_client):
    mandant, admin, token, kopf = await _schreibverbindung(make_mandant, make_user, mcp_client)
    daten = await _vorlage_entwerfen(mcp_client, token)
    assert daten["art"] == "vorlage" and daten["status"] == "draft" and daten["beschreibung"] == "Jahreswartung"
    titel = [a["titel"] for a in daten["abschnitte"]]
    assert titel == ["Kopf und Anlagendaten", "Prüfpunkte", "Messwerte", "Mängel", "Abschluss"]
    betriebsart = daten["abschnitte"][0]["felder"][1]
    assert betriebsart["typ"] == "dropdown" and betriebsart["optionen"] == ["Heizen", "Warmwasser", "Heizen und Warmwasser"]
    assert daten["link"].endswith(f"/form-schemas/{daten['id']}")

    r = await tool_aufrufen(
        mcp_client, token, "protokoll_vorlage_ueberarbeiten",
        {"vorlage_id": daten["id"], "felder_hinzufuegen": [{"abschnitt": "Messwerte", "label": "Abgastemperatur", "typ": "zahl"}]},
    )
    assert r["fehler"] is False, r["text"]
    messwerte = next(a for a in r["daten"]["abschnitte"] if a["titel"] == "Messwerte")
    assert "Abgastemperatur" in [f["label"] for f in messwerte["felder"]] and r["daten"]["art"] == "vorlage"


def test_protokoll_text_ohne_vorgang_und_gekennzeichnet():
    ansicht = {
        "vorlage": "X", "version": 2, "status": "abgeschlossen", "vorgang": None, "erstellt_via": "app",
        "abschnitte": [], "fotos_anzahl": 0, "fehlende_pflichtfelder": [], "link": "https://office.example/form-submissions/1",
    }
    text = protokoll_text(ansicht)
    assert text.startswith("Protokoll „X“ (Version 2), Status abgeschlossen.") and "von Claude" not in text
    assert "Fotos" not in text and "Pflichtfelder" not in text and text.endswith("https://office.example/form-submissions/1")
    assert "von Claude angelegt" in protokoll_text({**ansicht, "erstellt_via": "ki"})


async def test_server_meldet_apps_erweiterung(make_mandant, make_user, mcp_client):
    """Das SDK nennt die Erweiterung nur im modernen Umschlag (server/discover); die Initialize-Antwort des
    aelteren Protokolls enthaelt im zustandslosen Betrieb keine `extensions` (siehe Uebergabebericht)."""
    from tests.mcp_helfer import ki_modul_setzen, verbinden

    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    admin = await make_user(mandant=mandant, role="mandant_admin")
    t = await verbinden(mcp_client, admin, [LESEN])
    version = "2026-07-28"
    body = {
        "jsonrpc": "2.0", "id": 1, "method": "server/discover",
        "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": version, "io.modelcontextprotocol/clientCapabilities": {}}},
    }
    r = await mcp_client.post(
        "/mcp", content=json.dumps(body),
        headers={
            "Accept": "application/json, text/event-stream", "Content-Type": "application/json",
            "Authorization": f"Bearer {t['access_token']}", "mcp-protocol-version": version, "mcp-method": "server/discover",
        },
    )
    assert r.status_code == 200, r.text
    assert APPS_ID in r.json()["result"]["capabilities"]["extensions"]
