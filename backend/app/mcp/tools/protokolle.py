"""Protokoll-Tools: Protokoll anzeigen (MCP-App), Vorlagen entwerfen/ueberarbeiten, Protokoll-Entwuerfe zu Vorgaengen
anlegen/ergaenzen. Vorlagen und Protokolle lesen sowie PDFs liefern laufen ueber lesen/auflisten/dokument_abrufen (lesen.py);
die Hilfsfunktionen dafuer (vorlage_kompakt, _pdf_ergebnis) liegen weiter hier.

Schreiben (Scope fieldvibe.schreiben): Vorlagen im Status "draft" entwerfen/ueberarbeiten und Protokolle im Status
"offen" befuellen.
Abschliessen, Unterschreiben, Veroeffentlichen/Archivieren einer Vorlage und die Zuordnung zu
Leistungstypen gibt es per KI bewusst nicht (rest_client.SCHREIB_ALLOWLIST), ebenso kein Loeschen."""
import base64
from typing import Annotated, Any, Literal

from mcp.server.apps import client_supports_apps
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import BlobResourceContents, CallToolResult, EmbeddedResource, TextContent
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.mcp.ansichten import AENDERUNG_URI, PROTOKOLL_URI, VORLAGE_URI, ui_meta
from app.mcp.anzeige import Namen
from app.mcp.journal import RUECKGAENGIG_HINWEIS, Aktion, operation, pruefung
from app.mcp.aufbereitung import bereinigen, seite_aus
from app.mcp.protokoll_ansicht import protokoll_ansicht, protokoll_text
from app.mcp.protokoll_werte import fehlende_pflichtfelder, werte_abbilden
from app.mcp.rest_client import api_get, api_patch, api_post
from app.mcp.tools._basis import AENDERND, NUR_LESEN, zugriff
from app.mcp.vorlage_entwurf import (
    TYPEN_MIT_OPTIONEN,
    AbschnittEntwurf,
    FeldEntwurf,
    Schritt,
    abschnitte_planen,
    ansicht_schritte,
    feld_body,
    key_aus,
    norm,
    pruefe_abschnitte,
    pruefe_feld,
    zusammenfassung,
)
from app.mcp.zugang import SCOPE_SCHREIBEN

SCHREIB_TOOLS = frozenset({"protokoll_entwurf", "vorlage_entwurf"})

MAX_PDF_BYTES = 5 * 1024 * 1024

_Id = Annotated[str, Field(description="ID (UUID).")]
_NUR_SCHREIBZUGRIFF = " (nur mit Schreibzugriff)"
_ENTWURF_HINWEIS = "Entwurf – bitte im Formular-Baukasten prüfen und veröffentlichen."


def vorlagen_link(schema_id: str) -> str:
    # Die Seite liegt in Feld-App und Office unter derselben Route; frontend_base_url ist die Adresse, auf der
    # der Nutzer ohnehin angemeldet ist (Einwilligung, Passwort-Links), die Office-Domain kennt das Backend nicht.
    return f"{get_settings().frontend_base_url.rstrip('/')}/form-schemas/{schema_id}"


def protokoll_link(protokoll_id: str) -> str:
    return f"{get_settings().frontend_base_url.rstrip('/')}/form-submissions/{protokoll_id}"


def _label(obj: dict[str, Any]) -> str:
    return (obj.get("label") or {}).get("de") or obj["key"]


def vorlage_kompakt(detail: dict[str, Any]) -> dict[str, Any]:
    gruppen = sorted(detail["groups"], key=lambda g: g["reihenfolge"])
    felder = sorted(detail["fields"], key=lambda f: f["reihenfolge"])

    def feld(f: dict[str, Any]) -> dict[str, Any]:
        eintrag: dict[str, Any] = {"key": f["key"], "label": _label(f), "typ": f["feld_typ"], "pflicht": f["pflichtfeld"]}
        if f.get("hilfetext"):
            eintrag["hilfetext"] = f["hilfetext"]
        if (f.get("optionen") or {}).get("werte"):
            eintrag["optionen"] = f["optionen"]["werte"]
        return eintrag

    ergebnis: dict[str, Any] = {
        "id": detail["id"],
        "name": detail["name"],
        "beschreibung": detail["beschreibung"],
        "status": detail["status"],
        "version": detail["version"],
        "abschnitte": [
            {
                "key": g["key"],
                "titel": _label(g),
                "wiederholbar": g["repeatable"],
                "felder": [feld(f) for f in felder if f["group_key"] == g["key"]],
            }
            for g in gruppen
        ],
        "zugeordnete_leistungstypen": [z["leistungstyp"] for z in detail.get("zuordnungen", [])],
    }
    ohne = [feld(f) for f in felder if f["group_key"] is None]
    if ohne:
        ergebnis["felder_ohne_abschnitt"] = ohne
    return ergebnis


def _pdf_ergebnis(daten: bytes, inhaltstyp: str, uri: str, was: str) -> list[TextContent | EmbeddedResource]:
    if "pdf" not in inhaltstyp:
        raise ToolError(f"{was} konnte nicht als PDF erzeugt werden.")
    if len(daten) > MAX_PDF_BYTES:
        return [
            TextContent(
                type="text",
                text=f"{was} ist mit {len(daten) / 1024 / 1024:.1f} MB zu groß für die Übertragung (Grenze 5 MB). "
                "Bitte direkt in der FieldVibe-App als PDF öffnen.",
            )
        ]
    return [
        TextContent(type="text", text=f"{was} als PDF ({len(daten) // 1024 + 1} KB) angehängt."),
        EmbeddedResource(
            type="resource",
            resource=BlobResourceContents(uri=uri, mime_type="application/pdf", blob=base64.b64encode(daten).decode()),
        ),
    ]


class FeldHinzufuegen(FeldEntwurf):
    abschnitt: Annotated[str, Field(min_length=1, description="Abschnitt (Titel oder Key), in den das Feld kommt.")]


class FeldAenderung(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feld: Annotated[str, Field(min_length=1, description="Key oder Beschriftung des bestehenden Feldes.")]
    label: Annotated[str | None, Field(min_length=1, max_length=200, description="Neue Beschriftung.")] = None
    pflicht: bool | None = None
    hilfetext: Annotated[str | None, Field(max_length=500)] = None
    optionen: Annotated[list[str] | None, Field(description="Neue Auswahlliste (nur dropdown/mehrfachauswahl).")] = None


def registrieren(mcp: MCPServer) -> None:
    # --- Lesen ---------------------------------------------------------------------------------

    @mcp.tool(
        name="protokoll_anzeigen",
        title="Protokoll anzeigen",
        description=(
            "Zeigt ein ausgefülltes Protokoll (Submission) als Zusammenfassung: Abschnitte mit Beschriftungen, "
            "Ja/Nein, Zahlen mit Grenzwert-Markierung („über 50“), fehlende Pflichtfelder, Fotos nur als Anzahl, "
            "dazu der Link zum Öffnen in FieldVibe. In Claude-Clients mit MCP Apps erscheint die Ansicht im Chat, "
            "sonst kommt derselbe Inhalt als Text. Für die Rohwerte lesen(typ=\"formular\"), für eine Datei dokument_abrufen. "
            "Braucht die Rechte Vorgänge › sehen und Formulare › sehen."
        ),
        annotations=NUR_LESEN,
        meta=ui_meta(PROTOKOLL_URI),
    )
    async def protokoll_anzeigen(
        ctx: Context,
        protokoll_id: Annotated[str, Field(description="ID des ausgefüllten Protokolls (Submission).")],
    ) -> CallToolResult:
        z = zugriff()
        protokoll = await api_get(z, f"/api/form-submissions/{protokoll_id}")
        schema = await api_get(z, f"/api/form-schemas/{protokoll['schema_id']}")
        # Der Vorgang ist nur Kopfzeile: fehlt er (Recht/Papierkorb), bleibt die Ansicht trotzdem vollstaendig.
        try:
            vorgang = await api_get(z, f"/api/vorgaenge/{protokoll['vorgang_id']}")
        except ToolError:
            vorgang = None
        ansicht = bereinigen(protokoll_ansicht(schema, protokoll, vorgang, protokoll_link(protokoll["id"])))
        text = protokoll_text(ansicht)
        if client_supports_apps(ctx):
            text = "Die Ansicht wird im Chat angezeigt; fasse sie nicht erneut vollständig zusammen.\n\n" + text
        return CallToolResult(content=[TextContent(type="text", text=text)], structured_content=ansicht)

    # --- Protokoll-Entwuerfe zu Vorgaengen ---------------------------------------------------------

    @mcp.tool(
        name="protokoll_entwurf",
        title="Protokoll-Entwurf anlegen oder ergänzen",
        description=(
            "Legt zu einem Vorgang ein Protokoll aus einer veröffentlichten Vorlage an (ohne id: vorgang_id und "
            "vorlage_id nötig; Status „offen“) oder ergänzt ein noch offenes Protokoll (mit id). `werte` ist ein "
            "Objekt: Schlüssel = Feld-Key oder Beschriftung der Vorlage (Groß-/Kleinschreibung egal, siehe "
            "lesen(typ=\"vorlage\")). Felder in einem Abschnitt: "
            '{"Abgasmessung": {"CO-Wert (ppm)": 12}}; wiederholbarer Abschnitt als Liste von Einträgen: '
            '{"Mängel": [{"Beschreibung": "Dichtung porös"}]}. Zahlen als Zahl, Ja/Nein als true/false, '
            "Datum als JJJJ-MM-TT, Dropdown/Mehrfachauswahl mit den Optionen der Vorlage. Beim Ergänzen bleiben bereits "
            "befüllte Felder unverändert, es sei denn `vorhandene_ueberschreiben` ist true; Einträge in wiederholbaren "
            "Abschnitten werden angehängt. Foto, Unterschrift, Datei, GPS, QR-Scan und Fotoplan kann Claude nicht füllen; "
            "Abschließen und Unterschreiben geschieht in der App durch den Techniker. Das Anlegen lässt sich mit "
            "rueckgaengig zurücknehmen (solange das Protokoll offen und unverändert ist), das Ergänzen nicht." + _NUR_SCHREIBZUGRIFF
        ),
        annotations=AENDERND,
        meta=ui_meta(AENDERUNG_URI),
    )
    async def protokoll_entwurf(
        werte: Annotated[dict[str, Any], Field(description="Werte, siehe Beschreibung.")],
        vorgang_id: Annotated[str | None, Field(description="Vorgang (ID); nötig beim Anlegen.")] = None,
        vorlage_id: Annotated[str | None, Field(description="ID einer veröffentlichten Vorlage (published); nötig beim Anlegen.")] = None,
        id: Annotated[str | None, Field(description="ID eines offenen Protokolls (Submission) zum Ergänzen; ohne id wird angelegt.")] = None,
        vorhandene_ueberschreiben: Annotated[bool, Field(description="Nur beim Ergänzen: auch bereits befüllte Felder ersetzen. Standard false.")] = False,
    ) -> dict[str, Any]:
        z = zugriff(SCOPE_SCHREIBEN)
        if id is None:
            if not vorgang_id or not vorlage_id:
                raise ToolError("Zum Anlegen eines Protokolls werden vorgang_id und vorlage_id gebraucht.")
            return await _protokoll_anlegen(z, vorgang_id, vorlage_id, werte)
        return await _protokoll_ergaenzen(z, id, werte, vorhandene_ueberschreiben)

    # --- Vorlagen entwerfen --------------------------------------------------------------------

    @mcp.tool(
        name="vorlage_entwurf",
        title="Protokoll-Vorlage entwerfen oder überarbeiten",
        description=(
            "Ohne id: legt eine neue Protokoll-Vorlage im Formular-Baukasten als ENTWURF an (Status draft; name und "
            "abschnitte nötig). Sie ist erst für Techniker sichtbar, wenn ein Berechtigter sie im Baukasten geprüft und "
            "veröffentlicht und einem Leistungstyp zugeordnet hat; das geht per KI nicht. `abschnitte` ist eine Liste aus "
            "{titel, wiederholbar (Standard false; true z. B. für Mängellisten), felder: [{label, typ, pflicht, hilfetext, "
            "optionen}]}. optionen (Liste von Texten) nur bei dropdown und mehrfachauswahl, dort Pflicht. Sinnvolle "
            "Gliederung: Kopf/Anlagendaten, Prüfpunkte, Messwerte, Mängel (wiederholbar), Abschluss mit Unterschrift. "
            "Vorher mit auflisten(typ=\"vorlage\") prüfen, ob es die Vorlage schon gibt. Braucht das Recht Formulare › "
            "erstellen.\n"
            "Mit id: überarbeitet einen Entwurf über `aenderungen` {abschnitte_hinzufuegen, felder_hinzufuegen, "
            "felder_aendern}: Abschnitte hinzufügen, Felder zu einem Abschnitt hinzufügen, Beschriftung/Pflicht/Hilfetext/"
            "Optionen bestehender Felder ändern. Entfernen und Typwechsel gibt es nicht (im Baukasten). Veröffentlichte "
            "Vorlagen ändert Claude nicht; dafür mit lesen(typ=\"vorlage\") den Aufbau holen und eine neue Variante "
            "entwerfen. Vorlagen-Entwürfe lassen sich nicht per rueckgaengig zurücknehmen (im Baukasten löschen)." + _NUR_SCHREIBZUGRIFF
        ),
        annotations=AENDERND,
        meta=ui_meta(VORLAGE_URI),
    )
    async def vorlage_entwurf(
        id: Annotated[str | None, Field(description="ID eines Vorlagen-Entwurfs zum Überarbeiten; ohne id wird neu entworfen.")] = None,
        name: Annotated[str | None, Field(min_length=1, max_length=200, description="Name der neuen Vorlage (nur ohne id).")] = None,
        beschreibung: Annotated[str | None, Field(max_length=1000, description="Kurzbeschreibung, wofür die Vorlage dient (nur ohne id).")] = None,
        abschnitte: Annotated[list[AbschnittEntwurf] | None, Field(description="Abschnitte mit Feldern (nur ohne id).")] = None,
        aenderungen: Annotated[VorlagenAenderung | None, Field(description="Änderungen (nur mit id).")] = None,
    ) -> dict[str, Any]:
        z = zugriff(SCOPE_SCHREIBEN)
        if id is None:
            if not name or abschnitte is None:
                raise ToolError("Zum Entwerfen einer neuen Vorlage werden name und abschnitte gebraucht.")
            if aenderungen:
                raise ToolError("aenderungen gibt es nur zusammen mit id (Überarbeiten).")
            return await _vorlage_neu(z, name, beschreibung, abschnitte)
        if name or beschreibung or abschnitte:
            raise ToolError("Beim Überarbeiten (mit id) bitte nur aenderungen angeben.")
        if aenderungen is None:
            raise ToolError("Es gibt nichts zu ändern: bitte aenderungen angeben.")
        return await _vorlage_ueberarbeiten(z, id, aenderungen)


async def _protokoll_anlegen(z, vorgang_id: str, vorlage_id: str, werte: dict[str, Any]) -> dict[str, Any]:
    schema = await api_get(z, f"/api/form-schemas/{vorlage_id}")
    if schema["status"] != "published":
        raise ToolError(
            f"Die Vorlage „{schema['name']}“ ist {'noch ein Entwurf' if schema['status'] == 'draft' else 'archiviert'}. "
            "Nur veröffentlichte Vorlagen können ausgefüllt werden; veröffentlichen kann ein Berechtigter im Formular-Baukasten."
        )
    # Vor dem Anlegen komplett pruefen, damit bei einem Eingabefehler kein leeres Protokoll zurueckbleibt.
    werte_abbilden(schema, werte)
    aktion = Aktion(z, tool="protokoll_entwurf", aktionsart="protokoll.anlegen", stufe=1)
    fehler: str | None = None
    with aktion:
        angelegt = await api_post(z, "/api/form-submissions", {"schema_id": vorlage_id}, params={"vorgang_id": vorgang_id})
        label = f"{schema['name']}"
        aktion.neu_erzeugt("formular", angelegt["id"], label)
        vorgang_label = await Namen(z).aufloesen("vorgang", vorgang_id) or str(vorgang_id)
        aktion.ziel("vorgang", vorgang_id, vorgang_label)
        patch, gesetzt, uebersprungen = werte_abbilden(schema, werte, angelegt["values"])
        aktuell = dict(angelegt["values"])
        stand = angelegt
        if patch:
            try:
                stand = await api_patch(z, f"/api/form-submissions/{angelegt['id']}", {"values": patch})
                aktuell = stand["values"]
            except ToolError as exc:
                fehler = (
                    f"Das Protokoll wurde leer angelegt (ID {angelegt['id']}, Status offen), die Werte konnten aber nicht "
                    f"gespeichert werden: {exc}"
                )
        aktion.rueckweg_hinzu(
            operation(
                "DELETE",
                f"/api/form-submissions/{angelegt['id']}",
                None,
                [
                    pruefung(f"/api/form-submissions/{angelegt['id']}", "status", "offen", label=label, feld_label="Status"),
                    pruefung(
                        f"/api/form-submissions/{angelegt['id']}", "updated_at", stand.get("updated_at"), label=label, feld_label="Zuletzt geändert"
                    ),
                ],
            )
        )
    ergebnis = _protokoll_ergebnis(angelegt, schema, aktuell, gesetzt, uebersprungen)
    antwort = await aktion.fertig(
        f"Protokoll „{label}“ zu Vorgang {vorgang_label} als Entwurf angelegt ({len(gesetzt)} Felder befüllt)",
        link=protokoll_link(angelegt["id"]),
        fehler=fehler,
        extra=ergebnis,
    )
    # Die Protokoll-Hinweise (Abschliessen in der App) bleiben fuehrend; der Rueckgaengig-Hinweis kommt dazu.
    antwort["hinweis"] = f"{ergebnis['hinweis']} {RUECKGAENGIG_HINWEIS}"
    return antwort


async def _protokoll_ergaenzen(z, protokoll_id: str, werte: dict[str, Any], ueberschreiben: bool) -> dict[str, Any]:
    protokoll = await api_get(z, f"/api/form-submissions/{protokoll_id}")
    if protokoll["status"] != "offen":
        raise ToolError("Dieses Protokoll ist bereits abgeschlossen. Abgeschlossene Protokolle ändert Claude nicht.")
    schema = await api_get(z, f"/api/form-schemas/{protokoll['schema_id']}")
    patch, gesetzt, uebersprungen = werte_abbilden(schema, werte, protokoll["values"], ueberschreiben)
    aktuell = protokoll["values"]
    aktion = Aktion(z, tool="protokoll_entwurf", aktionsart="protokoll.aendern", stufe=2)
    with aktion:
        if patch:
            aktuell = (await api_patch(z, f"/api/form-submissions/{protokoll_id}", {"values": patch}))["values"]
        vorgang_label = await Namen(z).aufloesen("vorgang", protokoll["vorgang_id"]) or str(protokoll["vorgang_id"])
        aktion.ziel("vorgang", protokoll["vorgang_id"], vorgang_label)
        aktion.ziel("formular", protokoll_id, schema["name"])
    ergebnis = _protokoll_ergebnis(protokoll, schema, aktuell, gesetzt, uebersprungen)
    if not patch:
        return {**ergebnis, "aktion_id": None, "zusammenfassung": "Nichts geändert: Alle Felder waren schon befüllt.", "aenderungen": []}
    # Kein Rueckweg: Werte einzeln zuruecksetzen waere bei wiederholbaren Abschnitten nicht eindeutig.
    antwort = await aktion.fertig(
        f"Protokoll „{schema['name']}“ ergänzt ({len(gesetzt)} Felder)", link=protokoll_link(protokoll_id), extra=ergebnis
    )
    antwort["hinweis"] = ergebnis["hinweis"]
    return antwort


class VorlagenAenderung(BaseModel):
    model_config = ConfigDict(extra="forbid")

    abschnitte_hinzufuegen: Annotated[list[AbschnittEntwurf] | None, Field(description="Neue Abschnitte samt Feldern.")] = None
    felder_hinzufuegen: Annotated[list[FeldHinzufuegen] | None, Field(description="Neue Felder in einem Abschnitt.")] = None
    felder_aendern: Annotated[list[FeldAenderung] | None, Field(description="Änderungen an bestehenden Feldern.")] = None


async def _vorlage_neu(z, name: str, beschreibung: str | None, abschnitte: list[AbschnittEntwurf]) -> dict[str, Any]:
    pruefe_abschnitte(abschnitte)
    plan = abschnitte_planen(abschnitte, set())
    aktion = Aktion(z, tool="vorlage_entwurf", aktionsart="vorlage.anlegen", stufe=1)
    with aktion:
        schema = await api_post(z, "/api/form-schemas", {"name": name, "beschreibung": beschreibung})
        aktion.neu_erzeugt("vorlage", schema["id"], name)
        try:
            await _ausfuehren(z, schema, name, [*ansicht_schritte(), *plan.schritte])
        except ToolError as exc:
            await aktion.fertig(f"Vorlage „{name}“ als Entwurf angelegt, aber unvollständig", link=vorlagen_link(schema["id"]), fehler=str(exc))
            raise
    antwort = await aktion.fertig(f"Vorlagen-Entwurf „{name}“ angelegt", link=vorlagen_link(schema["id"]))
    return {
        **antwort,
        "id": schema["id"],
        "name": schema["name"],
        "status": schema["status"],
        "inhalt": zusammenfassung(abschnitte),
        "hinweis": f"KI-Entwurf, noch nicht veröffentlicht. {_ENTWURF_HINWEIS}",
        **await _vorlage_ansicht(z, schema["id"]),
    }


async def _vorlage_ueberarbeiten(z, vorlage_id: str, a: VorlagenAenderung) -> dict[str, Any]:
    if not (a.abschnitte_hinzufuegen or a.felder_hinzufuegen or a.felder_aendern):
        raise ToolError("Es gibt nichts zu ändern: bitte abschnitte_hinzufuegen, felder_hinzufuegen oder felder_aendern angeben.")
    detail = await api_get(z, f"/api/form-schemas/{vorlage_id}")
    if detail["status"] != "draft":
        raise ToolError("Veröffentlichte Vorlagen ändert Claude nicht – lege eine neue Variante an.")
    schritte = _ueberarbeitung_planen(detail, a.abschnitte_hinzufuegen or [], a.felder_hinzufuegen or [], a.felder_aendern or [])
    # Entwuerfe ohne jede Ansicht (aeltere KI-Entwuerfe) bekommen sie nachtraeglich; wer im Baukasten schon
    # Ansichten angelegt hat, behaelt seine Auswahl.
    if not await api_get(z, f"/api/form-schemas/{vorlage_id}/views"):
        schritte = [*ansicht_schritte(), *schritte]
    aktion = Aktion(z, tool="vorlage_entwurf", aktionsart="vorlage.aendern", stufe=2)
    with aktion:
        aktion.ziel("vorlage", detail["id"], detail["name"])
        try:
            await _ausfuehren(z, detail, detail["name"], schritte)
        except ToolError as exc:
            await aktion.fertig(f"Vorlagen-Entwurf „{detail['name']}“ teilweise überarbeitet", link=vorlagen_link(detail["id"]), fehler=str(exc))
            raise
    antwort = await aktion.fertig(f"Vorlagen-Entwurf „{detail['name']}“ überarbeitet", link=vorlagen_link(detail["id"]))
    return {
        **antwort,
        "id": detail["id"],
        "name": detail["name"],
        "status": detail["status"],
        "angewendet": [s.beschreibung for s in schritte],
        "hinweis": f"KI-Entwurf überarbeitet. {_ENTWURF_HINWEIS}",
        **await _vorlage_ansicht(z, detail["id"]),
    }


async def _vorlage_ansicht(z, schema_id: str) -> dict[str, Any]:
    """Aufbau der Vorlage, wie er jetzt gespeichert ist, fuer die HTML-Ansicht (ui://fieldvibe/vorlage.html)."""
    kompakt = bereinigen(vorlage_kompakt(await api_get(z, f"/api/form-schemas/{schema_id}")))
    ergebnis: dict[str, Any] = {"art": "vorlage", "beschreibung": kompakt["beschreibung"], "abschnitte": kompakt["abschnitte"]}
    if "felder_ohne_abschnitt" in kompakt:
        ergebnis["felder_ohne_abschnitt"] = kompakt["felder_ohne_abschnitt"]
    return ergebnis


async def _ausfuehren(z, schema: dict[str, Any], name: str, schritte) -> None:
    """Fuehrt die REST-Schritte nacheinander aus. Bei einem Fehler bleibt der Entwurf stehen; die Meldung
    nennt ID, Link und was schon angelegt ist, damit der Nutzer ihn im Baukasten vollenden oder loeschen kann
    (Aufraeumen per KI gibt es bewusst nicht: kein DELETE im Allowlist)."""
    fertig: list[str] = []
    for s in schritte:
        try:
            if s.art == "fields_patch":
                await api_patch(z, f"/api/form-schemas/{schema['id']}/fields/{s.feld_id}", s.body)
            else:
                await api_post(z, f"/api/form-schemas/{schema['id']}/{s.art}", s.body)
        except ToolError as exc:
            raise ToolError(
                f"Die Vorlage „{name}“ liegt als Entwurf vor (ID {schema['id']}, {vorlagen_link(schema['id'])}), "
                f"aber „{s.beschreibung}“ konnte nicht angelegt werden: {exc} Bereits angelegt: "
                f"{', '.join(fertig) if fertig else 'nur die leere Vorlage'}. Bitte im Formular-Baukasten "
                "vervollständigen oder löschen."
            ) from exc
        fertig.append(s.beschreibung)


def _protokoll_ergebnis(
    protokoll: dict[str, Any], schema: dict[str, Any], werte: dict[str, Any], gesetzt: list[str], uebersprungen: list[str]
) -> dict[str, Any]:
    ergebnis: dict[str, Any] = {
        "id": protokoll["id"],
        "vorgang_id": protokoll["vorgang_id"],
        "vorlage": schema["name"],
        "status": protokoll["status"],
        "gesetzt": gesetzt,
        "noch_fehlende_pflichtfelder": fehlende_pflichtfelder(schema, werte),
        "hinweis": (
            "Entwurf im Status „offen“. Prüfen, Fotos/Unterschrift ergänzen und Abschließen erfolgt in der "
            "FieldVibe-App (Vorgang › Formulare)."
        ),
    }
    if uebersprungen:
        ergebnis["uebersprungen_weil_bereits_befuellt"] = uebersprungen
    return ergebnis


def _ueberarbeitung_planen(detail, neue_abschnitte, neue_felder, aenderungen):
    belegt = {g["key"] for g in detail["groups"]} | {f["key"] for f in detail["fields"]}
    gruppen = list(detail["groups"])
    schritte: list[Schritt] = []
    neue_felder_je_gruppe: dict[str, int] = {}

    if neue_abschnitte:
        pruefe_abschnitte(neue_abschnitte)
        vorhandene_titel = {norm(_label(g)) for g in gruppen}
        for a in neue_abschnitte:
            if norm(a.titel) in vorhandene_titel:
                raise ToolError(f"Es gibt bereits einen Abschnitt „{a.titel}“; Felder dort mit felder_hinzufuegen ergänzen.")
        start = max((g["reihenfolge"] for g in gruppen), default=-1) + 1
        plan = abschnitte_planen(neue_abschnitte, belegt, start)
        schritte += plan.schritte
        for s, a in zip((s for s in plan.schritte if s.art == "groups"), neue_abschnitte):
            gruppen.append({"key": s.body["key"], "label": s.body["label"], "reihenfolge": s.body["reihenfolge"]})
            neue_felder_je_gruppe[s.body["key"]] = len(a.felder)

    naechste: dict[str, int] = {}
    for g in gruppen:
        felder = [f["reihenfolge"] for f in detail["fields"] if f["group_key"] == g["key"]]
        naechste[g["key"]] = neue_felder_je_gruppe.get(g["key"], max(felder, default=-1) + 1)
    for nf in neue_felder:
        ziel = [g for g in gruppen if nf.abschnitt == g["key"] or norm(nf.abschnitt) == norm(_label(g))]
        if not ziel:
            raise ToolError(
                f"Abschnitt „{nf.abschnitt}“ gibt es nicht. Vorhanden: {', '.join(_label(g) for g in gruppen)}. "
                "Neue Abschnitte mit abschnitte_hinzufuegen anlegen."
            )
        gk = ziel[0]["key"]
        schritte.append(
            Schritt(
                "fields",
                feld_body(nf, key_aus(nf.label, belegt, "feld"), gk, naechste[gk], f"Abschnitt „{_label(ziel[0])}“"),
                f"Feld „{nf.label}“ in „{_label(ziel[0])}“",
            )
        )
        naechste[gk] += 1

    for ae in aenderungen:
        treffer = [f for f in detail["fields"] if ae.feld == f["key"] or norm(ae.feld) == norm(_label(f))]
        if not treffer:
            raise ToolError(f"Feld „{ae.feld}“ gibt es in dieser Vorlage nicht.")
        if len(treffer) > 1:
            raise ToolError(f"Feld „{ae.feld}“ ist mehrdeutig; bitte den Key angeben ({', '.join(f['key'] for f in treffer)}).")
        f = treffer[0]
        body: dict[str, Any] = {}
        if ae.label is not None:
            body["label"] = {"de": ae.label}
        if ae.pflicht is not None:
            body["pflichtfeld"] = ae.pflicht
        if ae.hilfetext is not None:
            body["hilfetext"] = ae.hilfetext
        if ae.optionen is not None:
            if f["feld_typ"] not in TYPEN_MIT_OPTIONEN:
                raise ToolError(f"Feld „{_label(f)}“ ({f['feld_typ']}) hat keine Auswahlliste.")
            body["optionen"] = {**f["optionen"], "werte": pruefe_feld(FeldEntwurf(label=_label(f), typ=f["feld_typ"], optionen=ae.optionen), "Änderung")}
        if not body:
            raise ToolError(f"Für Feld „{_label(f)}“ ist nichts zu ändern angegeben.")
        schritte.append(Schritt("fields_patch", body, f"Feld „{_label(f)}“ geändert", feld_id=f["id"]))
    return schritte
