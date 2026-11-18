"""MCP-Protokoll-Tools (Etappe 2): Vorlagen entwerfen/ueberarbeiten, Protokoll-Entwuerfe, PDFs, Auswertungen, Prompts."""
import base64
import json
from datetime import date

import pytest
from sqlalchemy import select

import app.mcp.tools.protokolle as protokolle_tools
from app.db.session import system_session
from app.mcp.protokoll_werte import werte_abbilden
from app.mcp.server import integration
from app.mcp.vorlage_entwurf import key_aus
from app.models.audit_log import AuditLog
from app.models.form_modul import FormSubmission
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

ABSCHNITTE = [
    {
        "titel": "Kopf und Anlagendaten",
        "felder": [
            {"label": "Wartungsdatum", "typ": "datum", "pflicht": True},
            {"label": "Betriebsart", "typ": "dropdown", "optionen": ["Heizen", "Warmwasser", "Heizen und Warmwasser"]},
        ],
    },
    {
        "titel": "Prüfpunkte",
        "felder": [
            {"label": "Brenner gereinigt", "typ": "ja_nein", "pflicht": True},
            {"label": "Geprüfte Bauteile", "typ": "mehrfachauswahl", "optionen": ["Zündelektrode", "Siphon", "Wärmetauscher"]},
        ],
    },
    {
        "titel": "Messwerte",
        "felder": [
            {"label": "CO-Wert (ppm)", "typ": "zahl", "pflicht": True, "hilfetext": "Grenzwert 1000 ppm"},
            {"label": "Zustand", "typ": "bewertung"},
        ],
    },
    {
        "titel": "Mängel",
        "wiederholbar": True,
        "felder": [
            {"label": "Beschreibung", "typ": "textarea"},
            {"label": "Foto", "typ": "foto"},
        ],
    },
    {
        "titel": "Abschluss",
        "felder": [{"label": "Unterschrift Kunde", "typ": "unterschrift", "pflicht": True}],
    },
]


async def _admin(make_mandant, make_user):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    admin = await make_user(mandant=mandant, role="mandant_admin")
    return mandant, admin


async def _schreibverbindung(make_mandant, make_user, mcp_client):
    mandant, admin = await _admin(make_mandant, make_user)
    t = await verbinden(mcp_client, admin, [LESEN, SCHREIBEN])
    kopf = auth_headers(await login(mcp_client, admin.email, PASSWORT))
    return mandant, admin, t["access_token"], kopf


async def _vorlage_entwerfen(mcp_client, token, abschnitte=None, name="Wartung Gastherme") -> dict:
    r = await tool_aufrufen(
        mcp_client, token, "protokoll_vorlage_entwerfen",
        {"name": name, "beschreibung": "Jahreswartung", "abschnitte": abschnitte or ABSCHNITTE},
    )
    assert r["fehler"] is False, r["text"]
    return r["daten"]


async def _detail(mcp_client, kopf, schema_id) -> dict:
    r = await mcp_client.get(f"/api/form-schemas/{schema_id}", headers=kopf)
    assert r.status_code == 200, r.text
    return r.json()


async def _veroeffentlichen(mcp_client, kopf, schema_id):
    """Das macht in der Praxis der Mensch im Baukasten."""
    r = await mcp_client.patch(f"/api/form-schemas/{schema_id}", json={"status": "published"}, headers=kopf)
    assert r.status_code == 200, r.text


# --- Vorlage entwerfen -------------------------------------------------------------------------


async def test_vorlage_entwerfen_erzeugt_draft_mit_gruppen_feldern_pflicht_und_optionen(make_mandant, make_user, mcp_client):
    mandant, admin, token, kopf = await _schreibverbindung(make_mandant, make_user, mcp_client)
    daten = await _vorlage_entwerfen(mcp_client, token)
    assert daten["status"] == "draft"
    assert daten["link"].endswith(f"/form-schemas/{daten['id']}")
    assert "Entwurf" in daten["hinweis"] and "veröffentlichen" in daten["hinweis"]
    assert [a["abschnitt"] for a in daten["zusammenfassung"]][:2] == ["Kopf und Anlagendaten", "Prüfpunkte"]

    detail = await _detail(mcp_client, kopf, daten["id"])
    assert detail["status"] == "draft" and detail["name"] == "Wartung Gastherme" and detail["beschreibung"] == "Jahreswartung"
    gruppen = {g["label"]["de"]: g for g in sorted(detail["groups"], key=lambda g: g["reihenfolge"])}
    assert list(gruppen) == ["Kopf und Anlagendaten", "Prüfpunkte", "Messwerte", "Mängel", "Abschluss"]
    assert [g["repeatable"] for g in gruppen.values()] == [False, False, False, True, False]
    assert gruppen["Prüfpunkte"]["key"] == "pruefpunkte" and gruppen["Mängel"]["key"] == "maengel"

    felder = {f["label"]["de"]: f for f in detail["fields"]}
    assert felder["Wartungsdatum"]["feld_typ"] == "datum" and felder["Wartungsdatum"]["pflichtfeld"] is True
    assert felder["Betriebsart"]["optionen"] == {"werte": ["Heizen", "Warmwasser", "Heizen und Warmwasser"]}
    assert felder["Geprüfte Bauteile"]["feld_typ"] == "mehrfachauswahl"
    assert felder["CO-Wert (ppm)"]["hilfetext"] == "Grenzwert 1000 ppm" and felder["CO-Wert (ppm)"]["key"] == "co_wert_ppm"
    assert felder["Foto"]["group_key"] == "maengel" and felder["Foto"]["feld_typ"] == "foto"
    assert felder["Unterschrift Kunde"]["feld_typ"] == "unterschrift"
    assert felder["Brenner gereinigt"]["pflichtfeld"] is True and felder["Zustand"]["pflichtfeld"] is False
    assert len({f["key"] for f in detail["fields"]} | {g["key"] for g in detail["groups"]}) == len(detail["fields"]) + len(detail["groups"])
    assert detail["zuordnungen"] == []  # Zuordnung zu Leistungstypen bleibt beim Menschen

    async with system_session(grund="test") as session:
        aktionen = {
            a.aktion
            for a in (
                await session.execute(select(AuditLog).where(AuditLog.mandant_id == mandant.id, AuditLog.payload["quelle"].astext == "ki"))
            ).scalars()
        }
    assert {"ki_formular_vorlage_angelegt", "ki_formular_abschnitt_angelegt", "ki_formular_feld_angelegt"} <= aktionen


async def test_vorlage_ist_im_baukasten_lesbar_und_vorlage_lesen_tool_zeigt_aufbau(make_mandant, make_user, mcp_client):
    _, _, token, _ = await _schreibverbindung(make_mandant, make_user, mcp_client)
    daten = await _vorlage_entwerfen(mcp_client, token)
    gelesen = await tool_aufrufen(mcp_client, token, "protokoll_vorlage_lesen", {"vorlage_id": daten["id"]})
    abschnitte = {a["titel"]: a for a in gelesen["daten"]["abschnitte"]}
    assert abschnitte["Mängel"]["wiederholbar"] is True and abschnitte["Messwerte"]["wiederholbar"] is False
    betriebsart = next(f for f in abschnitte["Kopf und Anlagendaten"]["felder"] if f["label"] == "Betriebsart")
    assert betriebsart["optionen"] == ["Heizen", "Warmwasser", "Heizen und Warmwasser"] and betriebsart["typ"] == "dropdown"
    liste = await tool_aufrufen(mcp_client, token, "protokoll_vorlagen_auflisten", {"status": "draft"})
    assert [e["name"] for e in liste["daten"]["eintraege"]] == ["Wartung Gastherme"]
    assert (await tool_aufrufen(mcp_client, token, "protokoll_vorlagen_auflisten", {"status": "published"}))["daten"]["eintraege"] == []


async def test_vorlage_entwerfen_ohne_recht_formulare_erstellen(make_mandant, mcp_client):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    nutzer = await custom_nutzer(mandant, "Lesender", {"formulare": ("sehen",), "ki_zugriff": ("sehen", "bearbeiten")})
    t = await verbinden(mcp_client, nutzer, [LESEN, SCHREIBEN])
    r = await tool_aufrufen(mcp_client, t["access_token"], "protokoll_vorlage_entwerfen", {"name": "X", "abschnitte": ABSCHNITTE[:1]})
    assert r["fehler"] is True and "Dafür fehlt dir das Recht" in r["text"]
    assert "Traceback" not in r["text"]
    assert (await tool_aufrufen(mcp_client, t["access_token"], "protokoll_vorlagen_auflisten"))["daten"]["eintraege"] == []


@pytest.mark.parametrize(
    "abschnitte,fragment",
    [
        ([{"titel": "A", "felder": [{"label": "Auswahl", "typ": "dropdown"}]}], "braucht mindestens eine Option"),
        ([{"titel": "A", "felder": [{"label": "Text", "typ": "text", "optionen": ["x"]}]}], "nur bei dropdown"),
        ([{"titel": "A", "felder": [{"label": "X", "typ": "unbekannt"}]}], "typ"),
        ([{"titel": "A", "felder": [{"label": "X", "typ": "text"}, {"label": "x", "typ": "zahl"}]}], "eindeutig"),
        ([{"titel": "A", "felder": [{"label": "X", "typ": "text"}]}, {"titel": "a", "felder": [{"label": "Y", "typ": "text"}]}], "eindeutig"),
        ([], "Mindestens ein Abschnitt"),
    ],
)
async def test_ungueltige_entwuerfe_werden_abgelehnt_ohne_reste(make_mandant, make_user, mcp_client, abschnitte, fragment):
    _, _, token, kopf = await _schreibverbindung(make_mandant, make_user, mcp_client)
    r = await tool_aufrufen(mcp_client, token, "protokoll_vorlage_entwerfen", {"name": "Kaputt", "abschnitte": abschnitte})
    assert r["fehler"] is True and fragment in r["text"], r["text"]
    assert (await mcp_client.get("/api/form-schemas", headers=kopf)).json() == []


async def test_teilfehler_nennt_id_des_angelegten_entwurfs(make_mandant, make_user, mcp_client, monkeypatch):
    _, _, token, kopf = await _schreibverbindung(make_mandant, make_user, mcp_client)
    original = protokolle_tools.api_post
    aufrufe = {"n": 0}

    async def kaputt(z, pfad, body=None, params=None):
        aufrufe["n"] += 1
        if aufrufe["n"] == 4:
            from mcp.server.mcpserver.exceptions import ToolError

            raise ToolError("Server kaputt")
        return await original(z, pfad, body, params)

    monkeypatch.setattr(protokolle_tools, "api_post", kaputt)
    r = await tool_aufrufen(mcp_client, token, "protokoll_vorlage_entwerfen", {"name": "Halb", "abschnitte": ABSCHNITTE})
    assert r["fehler"] is True
    [vorlage] = (await mcp_client.get("/api/form-schemas", headers=kopf)).json()
    assert vorlage["id"] in r["text"] and "Baukasten" in r["text"] and "Server kaputt" in r["text"]
    assert vorlage["status"] == "draft"


# --- Vorlage ueberarbeiten -----------------------------------------------------------------------


async def test_vorlage_ueberarbeiten_nur_im_entwurf(make_mandant, make_user, mcp_client):
    _, _, token, kopf = await _schreibverbindung(make_mandant, make_user, mcp_client)
    daten = await _vorlage_entwerfen(mcp_client, token)
    r = await tool_aufrufen(
        mcp_client, token, "protokoll_vorlage_ueberarbeiten",
        {
            "vorlage_id": daten["id"],
            "abschnitte_hinzufuegen": [{"titel": "Bemerkungen", "felder": [{"label": "Notiz", "typ": "textarea"}]}],
            "felder_hinzufuegen": [
                {"abschnitt": "Messwerte", "label": "O2-Wert (%)", "typ": "zahl"},
                {"abschnitt": "Bemerkungen", "label": "Kundenwunsch", "typ": "text"},
            ],
            "felder_aendern": [
                {"feld": "co-wert (ppm)", "pflicht": False, "hilfetext": "Grenzwert 500 ppm"},
                {"feld": "Betriebsart", "label": "Betriebsmodus", "optionen": ["Heizen", "Nur Warmwasser"]},
            ],
        },
    )
    assert r["fehler"] is False, r["text"]
    detail = await _detail(mcp_client, kopf, daten["id"])
    felder = {f["label"]["de"]: f for f in detail["fields"]}
    assert felder["O2-Wert (%)"]["group_key"] == "messwerte" and felder["O2-Wert (%)"]["reihenfolge"] == 2
    assert felder["Kundenwunsch"]["group_key"] == "bemerkungen" and felder["Kundenwunsch"]["reihenfolge"] == 1
    assert felder["CO-Wert (ppm)"]["pflichtfeld"] is False and felder["CO-Wert (ppm)"]["hilfetext"] == "Grenzwert 500 ppm"
    assert felder["Betriebsmodus"]["optionen"] == {"werte": ["Heizen", "Nur Warmwasser"]}
    assert next(g for g in detail["groups"] if g["key"] == "bemerkungen")["repeatable"] is False
    assert detail["status"] == "draft"

    await _veroeffentlichen(mcp_client, kopf, daten["id"])
    abgelehnt = await tool_aufrufen(
        mcp_client, token, "protokoll_vorlage_ueberarbeiten",
        {"vorlage_id": daten["id"], "felder_aendern": [{"feld": "Notiz", "label": "Neu"}]},
    )
    assert abgelehnt["fehler"] is True and "Veröffentlichte Vorlagen ändert Claude nicht" in abgelehnt["text"]
    assert {f["label"]["de"] for f in (await _detail(mcp_client, kopf, daten["id"]))["fields"]} == set(felder)


async def test_vorlage_ueberarbeiten_unbekannte_bezuege_aendern_nichts(make_mandant, make_user, mcp_client):
    _, _, token, kopf = await _schreibverbindung(make_mandant, make_user, mcp_client)
    daten = await _vorlage_entwerfen(mcp_client, token)
    vorher = await _detail(mcp_client, kopf, daten["id"])
    for argumente, fragment in (
        ({"felder_hinzufuegen": [{"abschnitt": "Gibt es nicht", "label": "X", "typ": "text"}]}, "gibt es nicht"),
        ({"felder_aendern": [{"feld": "Nope", "pflicht": True}]}, "gibt es in dieser Vorlage nicht"),
        ({"felder_aendern": [{"feld": "Zustand", "optionen": ["a"]}]}, "keine Auswahlliste"),
        ({"abschnitte_hinzufuegen": [{"titel": "Messwerte", "felder": [{"label": "X", "typ": "text"}]}]}, "bereits einen Abschnitt"),
        ({}, "nichts zu ändern"),
    ):
        r = await tool_aufrufen(mcp_client, token, "protokoll_vorlage_ueberarbeiten", {"vorlage_id": daten["id"], **argumente})
        assert r["fehler"] is True and fragment in r["text"], (argumente, r["text"])
    assert await _detail(mcp_client, kopf, daten["id"]) == vorher


# --- Protokoll-Entwuerfe --------------------------------------------------------------------------


async def _bereit(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, admin, token, kopf = await _schreibverbindung(make_mandant, make_user, mcp_client)
    daten = await _vorlage_entwerfen(mcp_client, token)
    await _veroeffentlichen(mcp_client, kopf, daten["id"])
    vorgang = await make_vorgang(mandant=mandant, kunde=await make_kunde(mandant=mandant), leistungstyp="wartung")
    return mandant, token, kopf, daten["id"], vorgang


async def _submissions(vorgang_id) -> list[FormSubmission]:
    async with system_session(grund="test") as session:
        return list((await session.execute(select(FormSubmission).where(FormSubmission.vorgang_id == vorgang_id))).scalars())


async def test_protokoll_entwurf_mit_label_mapping_status_offen(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, token, kopf, vorlage_id, vorgang = await _bereit(make_mandant, make_user, make_kunde, make_vorgang, mcp_client)
    r = await tool_aufrufen(
        mcp_client, token, "protokoll_entwurf_anlegen",
        {
            "vorgang_id": str(vorgang.id),
            "vorlage_id": vorlage_id,
            "werte": {
                "wartungsdatum": "18.11.2026",
                "BETRIEBSART": "heizen und warmwasser",
                "Prüfpunkte": {"Brenner gereinigt": "Ja", "Geprüfte Bauteile": ["siphon", "Zündelektrode"]},
                "CO-Wert (ppm)": "12,5",
                "Zustand": 4,
                "Mängel": [{"Beschreibung": "Dichtung porös"}, {"beschreibung": "Siphon verschmutzt"}],
            },
        },
    )
    assert r["fehler"] is False, r["text"]
    d = r["daten"]
    assert d["status"] == "offen" and "App" in d["hinweis"]
    assert set(d["noch_fehlende_pflichtfelder"]) == {"Unterschrift Kunde"}
    [sub] = await _submissions(vorgang.id)
    assert sub.status == "offen" and sub.abgeschlossen_am is None
    assert sub.values["kopf_und_anlagendaten"] == [{"wartungsdatum": "2026-11-18", "betriebsart": "Heizen und Warmwasser"}]
    assert sub.values["pruefpunkte"] == [{"brenner_gereinigt": True, "geprufte_bauteile".replace("geprufte", "gepruefte"): ["Siphon", "Zündelektrode"]}]
    assert sub.values["messwerte"] == [{"co_wert_ppm": "12.5", "zustand": 4}]
    assert sub.values["maengel"] == [{"beschreibung": "Dichtung porös"}, {"beschreibung": "Siphon verschmutzt"}]
    # Die Feld-App liest dasselbe Protokoll ueber die normale API.
    gelesen = await mcp_client.get(f"/api/form-submissions/{sub.id}", headers=kopf)
    assert gelesen.json()["values"] == sub.values


async def test_protokoll_entwurf_fehler_bei_unbekanntem_oder_nicht_fuellbarem_feld(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, token, kopf, vorlage_id, vorgang = await _bereit(make_mandant, make_user, make_kunde, make_vorgang, mcp_client)

    async def versuch(werte):
        return await tool_aufrufen(
            mcp_client, token, "protokoll_entwurf_anlegen", {"vorgang_id": str(vorgang.id), "vorlage_id": vorlage_id, "werte": werte}
        )

    unbekannt = await versuch({"Schornsteinfeger": "x"})
    assert unbekannt["fehler"] and "Unbekanntes Feld „Schornsteinfeger“" in unbekannt["text"] and "CO-Wert (ppm)" in unbekannt["text"]
    foto = await versuch({"Mängel": [{"Foto": "bild.jpg"}]})
    assert foto["fehler"] and "kann Claude nicht ausfüllen" in foto["text"]
    unterschrift = await versuch({"Abschluss": {"Unterschrift Kunde": "Max"}})
    assert unterschrift["fehler"] and "Unterschrift" in unterschrift["text"]
    option = await versuch({"Betriebsart": "Kühlen"})
    assert option["fehler"] and "Erlaubt: Heizen" in option["text"]
    zahl = await versuch({"CO-Wert (ppm)": "viel"})
    assert zahl["fehler"] and "erwartet eine Zahl" in zahl["text"]
    wiederholt = await versuch({"Beschreibung": "x"})
    assert wiederholt["fehler"] and "wiederholbaren Abschnitt „Mängel“" in wiederholt["text"]
    bewertung = await versuch({"Zustand": 9})
    assert bewertung["fehler"] and "von 1 bis 5" in bewertung["text"]
    # Fehlerhafte Eingaben legen kein leeres Protokoll an.
    assert await _submissions(vorgang.id) == []


async def test_protokoll_entwurf_aus_unveroeffentlichter_vorlage_wird_abgelehnt(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, admin, token, kopf = await _schreibverbindung(make_mandant, make_user, mcp_client)
    entwurf = await _vorlage_entwerfen(mcp_client, token)
    vorgang = await make_vorgang(mandant=mandant, kunde=await make_kunde(mandant=mandant))
    r = await tool_aufrufen(
        mcp_client, token, "protokoll_entwurf_anlegen", {"vorgang_id": str(vorgang.id), "vorlage_id": entwurf["id"], "werte": {}}
    )
    assert r["fehler"] and "noch ein Entwurf" in r["text"]
    assert await _submissions(vorgang.id) == []


async def test_protokoll_ergaenzen_additiv_und_nicht_an_abgeschlossenem(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, token, kopf, vorlage_id, vorgang = await _bereit(make_mandant, make_user, make_kunde, make_vorgang, mcp_client)
    angelegt = await tool_aufrufen(
        mcp_client, token, "protokoll_entwurf_anlegen",
        {"vorgang_id": str(vorgang.id), "vorlage_id": vorlage_id, "werte": {"CO-Wert (ppm)": 10, "Mängel": [{"Beschreibung": "Erster"}]}},
    )
    pid = angelegt["daten"]["id"]
    r = await tool_aufrufen(
        mcp_client, token, "protokoll_entwurf_ergaenzen",
        {"protokoll_id": pid, "werte": {"CO-Wert (ppm)": 99, "Zustand": 3, "Mängel": [{"Beschreibung": "Zweiter"}]}},
    )
    assert r["fehler"] is False, r["text"]
    assert r["daten"]["uebersprungen_weil_bereits_befuellt"] == ["CO-Wert (ppm)"]
    [sub] = await _submissions(vorgang.id)
    assert sub.values["messwerte"] == [{"co_wert_ppm": "10", "zustand": 3}]
    assert [z["beschreibung"] for z in sub.values["maengel"]] == ["Erster", "Zweiter"]

    ueber = await tool_aufrufen(
        mcp_client, token, "protokoll_entwurf_ergaenzen",
        {"protokoll_id": pid, "werte": {"CO-Wert (ppm)": 99}, "vorhandene_ueberschreiben": True},
    )
    assert ueber["fehler"] is False
    assert (await _submissions(vorgang.id))[0].values["messwerte"][0]["co_wert_ppm"] == "99"

    # Abschliessen macht der Mensch; danach lehnt das Tool ab.
    async with system_session(grund="test") as session:
        s = await session.get(FormSubmission, sub.id)
        s.status = "abgeschlossen"
    zu = await tool_aufrufen(mcp_client, token, "protokoll_entwurf_ergaenzen", {"protokoll_id": pid, "werte": {"Zustand": 1}})
    assert zu["fehler"] and "bereits abgeschlossen" in zu["text"]
    assert (await _submissions(vorgang.id))[0].values["messwerte"][0]["zustand"] == 3


async def test_protokoll_entwurf_mandant_b_kommt_nicht_an_vorgang_von_a(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant_a, token_a, kopf_a, vorlage_a, vorgang_a = await _bereit(make_mandant, make_user, make_kunde, make_vorgang, mcp_client)
    _, _, token_b, kopf_b = await _schreibverbindung(make_mandant, make_user, mcp_client)
    b_vorlage = await _vorlage_entwerfen(mcp_client, token_b, name="B")
    await _veroeffentlichen(mcp_client, kopf_b, b_vorlage["id"])
    r = await tool_aufrufen(
        mcp_client, token_b, "protokoll_entwurf_anlegen", {"vorgang_id": str(vorgang_a.id), "vorlage_id": b_vorlage["id"], "werte": {}}
    )
    assert r["fehler"] is True and "Nicht gefunden" in r["text"]
    fremd = await tool_aufrufen(mcp_client, token_b, "protokoll_vorlage_lesen", {"vorlage_id": vorlage_a})
    assert fremd["fehler"] is True and "Nicht gefunden" in fremd["text"]
    assert await _submissions(vorgang_a.id) == []


# --- PDFs ------------------------------------------------------------------------------------------


async def _pdf_resource(mcp_client, token, name, argumente) -> tuple[str, dict]:
    resp = await mcp_rpc(mcp_client, token, "tools/call", {"name": name, "arguments": argumente})
    ergebnis = resp.json()["result"]
    assert not ergebnis.get("isError"), ergebnis
    text = next(c["text"] for c in ergebnis["content"] if c["type"] == "text")
    ressourcen = [c["resource"] for c in ergebnis["content"] if c["type"] == "resource"]
    return text, ressourcen[0] if ressourcen else {}


async def test_pdf_tools_liefern_pdf_blob(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, token, kopf, vorlage_id, vorgang = await _bereit(make_mandant, make_user, make_kunde, make_vorgang, mcp_client)
    sicht = await mcp_client.post(f"/api/form-schemas/{vorlage_id}/views", json={"type": "print", "name": "Druck"}, headers=kopf)
    assert sicht.status_code == 201, sicht.text
    angelegt = await tool_aufrufen(
        mcp_client, token, "protokoll_entwurf_anlegen", {"vorgang_id": str(vorgang.id), "vorlage_id": vorlage_id, "werte": {"CO-Wert (ppm)": 5}}
    )
    pid = angelegt["daten"]["id"]
    text, res = await _pdf_resource(mcp_client, token, "protokoll_pdf", {"protokoll_id": pid})
    assert "PDF" in text and res["mimeType"] == "application/pdf" and res["uri"] == f"fieldvibe://protokoll/{pid}.pdf"
    assert base64.b64decode(res["blob"]).startswith(b"%PDF")

    await tool_aufrufen(mcp_client, token, "mangel_erfassen", {"vorgang_id": str(vorgang.id), "beschreibung": "Undicht"})
    text, res = await _pdf_resource(mcp_client, token, "maengelprotokoll_pdf", {"vorgang_id": str(vorgang.id)})
    assert res["mimeType"] == "application/pdf" and base64.b64decode(res["blob"]).startswith(b"%PDF")


async def test_pdf_ueber_5_mb_liefert_hinweis_statt_blob(make_mandant, make_user, make_kunde, make_vorgang, mcp_client, monkeypatch):
    mandant, token, kopf, vorlage_id, vorgang = await _bereit(make_mandant, make_user, make_kunde, make_vorgang, mcp_client)

    async def gross(z, pfad, params=None):
        return b"%PDF" + b"0" * (6 * 1024 * 1024), "application/pdf"

    monkeypatch.setattr(protokolle_tools, "api_get_binaer", gross)
    text, res = await _pdf_resource(mcp_client, token, "maengelprotokoll_pdf", {"vorgang_id": str(vorgang.id)})
    assert res == {} and "5 MB" in text and "App" in text


async def test_pdf_ohne_druckansicht_gibt_verstaendlichen_fehler(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, token, kopf, vorlage_id, vorgang = await _bereit(make_mandant, make_user, make_kunde, make_vorgang, mcp_client)
    angelegt = await tool_aufrufen(
        mcp_client, token, "protokoll_entwurf_anlegen", {"vorgang_id": str(vorgang.id), "vorlage_id": vorlage_id, "werte": {}}
    )
    r = await tool_aufrufen(mcp_client, token, "protokoll_pdf", {"protokoll_id": angelegt["daten"]["id"]})
    assert r["fehler"] and "Druckansicht" in r["text"]


# --- Auswertung --------------------------------------------------------------------------------------


async def test_auswertung_ruft_aggregat_mit_parametern_und_meldet_ungueltige_kombinationen(
    make_mandant, make_user, make_kunde, make_vorgang, mcp_client
):
    mandant, admin = await _admin(make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    await make_vorgang(mandant=mandant, kunde=kunde, status="neu")
    await make_vorgang(mandant=mandant, kunde=kunde, status="neu")
    await make_vorgang(mandant=mandant, kunde=kunde, status="in_arbeit")
    t = await verbinden(mcp_client, admin)
    heute = date.today()
    args = {"bereich": "vorgaenge", "kennzahl": "anzahl_erstellt", "gruppierung": "status", "von": f"{heute.year}-01-01", "bis": f"{heute.year}-12-31"}
    r = await tool_aufrufen(mcp_client, t["access_token"], "auswertung", args)
    assert r["fehler"] is False, r["text"]
    zeilen = {z["schluessel"]: z["wert"] for z in r["daten"]["zeilen"]}
    assert zeilen == {"neu": 2.0, "in_arbeit": 1.0} and r["daten"]["gesamt"] == 3.0
    nur = await tool_aufrufen(mcp_client, t["access_token"], "auswertung", {**args, "status": "neu", "kunde_id": str(kunde.id)})
    assert [z["wert"] for z in nur["daten"]["zeilen"]] == [2.0]
    kaputt = await tool_aufrufen(mcp_client, t["access_token"], "auswertung", {**args, "bereich": "rechnungen"})
    assert kaputt["fehler"] and "passt nicht zum Bereich" in kaputt["text"]
    falsch = await tool_aufrufen(mcp_client, t["access_token"], "auswertung", {**args, "gruppierung": "sql_injection"})
    assert falsch["fehler"]
    tools = (await mcp_rpc(mcp_client, t["access_token"], "tools/list")).json()["result"]["tools"]
    beschreibung = next(x["description"] for x in tools if x["name"] == "auswertung")
    assert "anzahl_erstellt" in beschreibung and "umsatz_netto" in beschreibung


async def test_arbeitszeit_saldo(make_mandant, make_user, mcp_client):
    _, admin = await _admin(make_mandant, make_user)
    t = await verbinden(mcp_client, admin)
    r = await tool_aufrufen(mcp_client, t["access_token"], "arbeitszeit_saldo", {"von": "2026-11-02", "bis": "2026-11-06"})
    assert r["fehler"] is False, r["text"]
    assert {"soll_stunden", "ist_stunden", "saldo_stunden", "tage"} <= set(r["daten"]) and len(r["daten"]["tage"]) == 5
    lang = await tool_aufrufen(mcp_client, t["access_token"], "arbeitszeit_saldo", {"von": "2026-01-01", "bis": "2026-06-30"})
    assert "tage" not in lang["daten"] and "62 Tage" in lang["daten"]["hinweis"]


# --- Prompts ---------------------------------------------------------------------------------------------


async def test_prompts_sind_gelistet_und_nennen_die_richtigen_tools(make_mandant, make_user, mcp_client):
    _, admin = await _admin(make_mandant, make_user)
    t = await verbinden(mcp_client, admin)
    liste = (await mcp_rpc(mcp_client, t["access_token"], "prompts/list")).json()["result"]["prompts"]
    assert {p["name"] for p in liste} == {"protokoll_vorlage_entwerfen", "wartungsprotokoll_zu_vorgang_ausfuellen", "monatsbericht"}

    async def holen(name, argumente):
        antwort = (await mcp_rpc(mcp_client, t["access_token"], "prompts/get", {"name": name, "arguments": argumente})).json()
        return "".join(m["content"]["text"] for m in antwort["result"]["messages"])

    vorlage = await holen("protokoll_vorlage_entwerfen", {"thema": "Wartung Gas-Brennwerttherme", "vorgaben": "Abgasmessung"})
    assert "Wartung Gas-Brennwerttherme" in vorlage and "Abgasmessung" in vorlage
    assert "protokoll_vorlagen_auflisten" in vorlage and "protokoll_vorlage_entwerfen" in vorlage and "Unterschrift" in vorlage
    wartung = await holen("wartungsprotokoll_zu_vorgang_ausfuellen", {"vorgang_id": "abc"})
    assert "abc" in wartung and "protokoll_entwurf_anlegen" in wartung and "abschließen" in wartung
    bericht = await holen("monatsbericht", {"monat": "2026-10"})
    assert "2026-10" in bericht and "auswertung" in bericht and "kennzahlen_vorgaenge" in bericht and "Markdown" in bericht


# --- Reine Logik ---------------------------------------------------------------------------------------------


def test_keys_aus_labels_ascii_und_eindeutig():
    belegt: set[str] = set()
    assert key_aus("Prüfpunkte Größe", belegt, "feld") == "pruefpunkte_groesse"
    assert key_aus("Prüfpunkte Größe", belegt, "feld") == "pruefpunkte_groesse_2"
    assert key_aus("CO-Wert (ppm)", belegt, "feld") == "co_wert_ppm"
    assert key_aus("12 Monate", belegt, "feld") == "feld_12_monate"
    assert key_aus("???", belegt, "abschnitt") == "abschnitt"
    assert key_aus("Zeileé", belegt, "feld") == "zeilee"


_SCHEMA = {
    "groups": [
        {"key": "kopf", "label": {"de": "Kopf"}, "repeatable": False},
        {"key": "maengel", "label": {"de": "Mängel"}, "repeatable": True},
    ],
    "fields": [
        {"key": "notiz", "label": {"de": "Notiz"}, "feld_typ": "text", "group_key": None, "optionen": {}, "pflichtfeld": False},
        {"key": "datum", "label": {"de": "Datum"}, "feld_typ": "datum", "group_key": "kopf", "optionen": {}, "pflichtfeld": True},
        {"key": "text", "label": {"de": "Text"}, "feld_typ": "text", "group_key": "maengel", "optionen": {}, "pflichtfeld": False},
        {"key": "gps", "label": {"de": "Standort"}, "feld_typ": "gps", "group_key": None, "optionen": {}, "pflichtfeld": False},
    ],
}


def test_werte_abbilden_flach_gruppe_und_wiederholbar():
    patch, gesetzt, uebersprungen = werte_abbilden(
        _SCHEMA, {"NOTIZ": "hi", "Datum": "2026-01-02", "Mängel": [{"Text": "a"}]}
    )
    assert patch == {"notiz": "hi", "kopf": [{"datum": "2026-01-02"}], "maengel": [{"text": "a"}]}
    assert gesetzt == ["Notiz", "Datum", "Mängel (Eintrag 1)"] and uebersprungen == []


def test_werte_abbilden_ueberspringt_vorhandenes_und_haengt_zeilen_an():
    bestehend = {"notiz": "alt", "kopf": [{"datum": "2025-01-01"}], "maengel": [{"text": "x"}]}
    patch, gesetzt, uebersprungen = werte_abbilden(_SCHEMA, {"Notiz": "neu", "Kopf": {"Datum": "2026-01-02"}, "Mängel": {"Text": "y"}}, bestehend)
    assert patch == {"kopf": [{"datum": "2025-01-01"}], "maengel": [{"text": "x"}, {"text": "y"}]}
    assert set(uebersprungen) == {"Notiz", "Datum"}
    patch, _, _ = werte_abbilden(_SCHEMA, {"Notiz": "neu"}, bestehend, ueberschreiben=True)
    assert patch == {"notiz": "neu"}


def test_werte_abbilden_gps_nicht_fuellbar():
    from mcp.server.mcpserver.exceptions import ToolError

    with pytest.raises(ToolError, match="kann Claude nicht ausfüllen"):
        werte_abbilden(_SCHEMA, {"Standort": "52.5,13.4"})
    with pytest.raises(ToolError, match="Unbekanntes Feld"):
        werte_abbilden(_SCHEMA, {"Quatsch": 1})
