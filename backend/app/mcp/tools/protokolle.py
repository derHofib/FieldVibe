"""Protokoll-Tools: Vorlagen lesen und entwerfen, Protokoll-Entwuerfe zu Vorgaengen anlegen, PDFs liefern.

Lesen (Scope fieldvibe.lesen): Vorlagen auflisten/lesen, PDFs. Schreiben (Scope fieldvibe.schreiben):
Vorlagen im Status "draft" entwerfen/ueberarbeiten und Protokolle im Status "offen" befuellen.
Abschliessen, Unterschreiben, Veroeffentlichen/Archivieren einer Vorlage und die Zuordnung zu
Leistungstypen gibt es per KI bewusst nicht (rest_client.SCHREIB_ALLOWLIST), ebenso kein Loeschen."""
import base64
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import BlobResourceContents, EmbeddedResource, TextContent
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.mcp.aufbereitung import bereinigen, seite_aus
from app.mcp.protokoll_werte import fehlende_pflichtfelder, werte_abbilden
from app.mcp.rest_client import api_get, api_get_binaer, api_patch, api_post
from app.mcp.tools._basis import NUR_ADDITIV, zugriff
from app.mcp.tools.lesen import NUR_LESEN
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

SCHREIB_TOOLS = frozenset(
    {
        "protokoll_entwurf_anlegen",
        "protokoll_entwurf_ergaenzen",
        "protokoll_vorlage_entwerfen",
        "protokoll_vorlage_ueberarbeiten",
    }
)

MAX_PDF_BYTES = 5 * 1024 * 1024

_Id = Annotated[str, Field(description="ID (UUID).")]
_NUR_SCHREIBZUGRIFF = " (nur mit Schreibzugriff)"
_ENTWURF_HINWEIS = "Entwurf – bitte im Formular-Baukasten prüfen und veröffentlichen."


def vorlagen_link(schema_id: str) -> str:
    # Die Seite liegt in Feld-App und Office unter derselben Route; frontend_base_url ist die Adresse, auf der
    # der Nutzer ohnehin angemeldet ist (Einwilligung, Passwort-Links), die Office-Domain kennt das Backend nicht.
    return f"{get_settings().frontend_base_url.rstrip('/')}/form-schemas/{schema_id}"


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
        name="protokoll_vorlagen_auflisten",
        title="Protokoll-Vorlagen auflisten",
        description=(
            "Listet die Protokoll-/Formular-Vorlagen des Betriebs (Name, Status draft/published/archived, "
            "Version). Vor dem Entwerfen einer neuen Vorlage prüfen, ob es schon eine gibt. "
            "Braucht das Recht Formulare › sehen."
        ),
        annotations=NUR_LESEN,
    )
    async def protokoll_vorlagen_auflisten(
        status: Annotated[Literal["draft", "published", "archived"] | None, Field(description="Optional nach Status filtern.")] = None,
        seite: Annotated[int, Field(ge=1, description="Seite (je 100 Einträge).")] = 1,
    ) -> dict[str, Any]:
        z = zugriff()
        daten = await api_get(z, "/api/form-schemas", {"status": status})
        kompakt = [{k: v[k] for k in ("id", "name", "beschreibung", "status", "version")} for v in daten]
        return seite_aus(kompakt, seite)

    @mcp.tool(
        name="protokoll_vorlage_lesen",
        title="Protokoll-Vorlage lesen",
        description=(
            "Liest den Aufbau einer Vorlage: Abschnitte (wiederholbar oder nicht) mit Feldern, Typ, Pflicht, "
            "Hilfetext und Auswahloptionen. Nötig, um ein Protokoll auszufüllen oder eine Variante zu entwerfen. "
            "Braucht das Recht Formulare › sehen."
        ),
        annotations=NUR_LESEN,
    )
    async def protokoll_vorlage_lesen(vorlage_id: _Id) -> dict[str, Any]:
        z = zugriff()
        return bereinigen(vorlage_kompakt(await api_get(z, f"/api/form-schemas/{vorlage_id}")))

    @mcp.tool(
        name="protokoll_pdf",
        title="Protokoll als PDF",
        description=(
            "Liefert ein Protokoll (ausgefülltes Formular) als PDF. Ein noch offenes Protokoll ist nur eine "
            "Vorschau mit Hinweis. Größer als 5 MB wird nicht übertragen. Voraussetzung: die Vorlage hat "
            "eine Druckansicht."
        ),
        annotations=NUR_LESEN,
    )
    async def protokoll_pdf(
        protokoll_id: Annotated[str, Field(description="ID des ausgefüllten Protokolls (Submission).")],
    ) -> list[TextContent | EmbeddedResource]:
        z = zugriff()
        daten, typ = await api_get_binaer(z, f"/api/form-submissions/{protokoll_id}/pdf")
        return _pdf_ergebnis(daten, typ, f"fieldvibe://protokoll/{protokoll_id}.pdf", "Das Protokoll")

    @mcp.tool(
        name="maengelprotokoll_pdf",
        title="Mängelprotokoll als PDF",
        description="Liefert das Mängelprotokoll eines Vorgangs (alle erfassten Mängel) als PDF. Benötigt das Modul Abrechnung.",
        annotations=NUR_LESEN,
    )
    async def maengelprotokoll_pdf(vorgang_id: _Id) -> list[TextContent | EmbeddedResource]:
        z = zugriff()
        daten, typ = await api_get_binaer(z, "/api/maengel/protokoll/pdf", {"vorgang_id": vorgang_id})
        return _pdf_ergebnis(daten, typ, f"fieldvibe://maengelprotokoll/{vorgang_id}.pdf", "Das Mängelprotokoll")

    # --- Protokoll-Entwuerfe zu Vorgaengen ---------------------------------------------------------

    @mcp.tool(
        name="protokoll_entwurf_anlegen",
        title="Protokoll-Entwurf zu Vorgang anlegen",
        description=(
            "Legt zu einem Vorgang ein Protokoll aus einer veröffentlichten Vorlage an (Status „offen“) und trägt "
            "die übergebenen Werte ein. `werte` ist ein Objekt: Schlüssel = Feld-Key oder Beschriftung der "
            "Vorlage (Groß-/Kleinschreibung egal, siehe protokoll_vorlage_lesen). Felder in einem Abschnitt: "
            '{"Abgasmessung": {"CO-Wert (ppm)": 12}}; wiederholbarer Abschnitt als Liste von Einträgen: '
            '{"Mängel": [{"Beschreibung": "Dichtung porös"}]}. Zahlen als Zahl, Ja/Nein als true/false, '
            "Datum als JJJJ-MM-TT, Dropdown/Mehrfachauswahl mit den Optionen der Vorlage. Foto, Unterschrift, "
            "Datei, GPS, QR-Scan und Fotoplan kann Claude nicht füllen. Abschließen und Unterschreiben "
            "geschieht in der App durch den Techniker." + _NUR_SCHREIBZUGRIFF
        ),
        annotations=NUR_ADDITIV,
    )
    async def protokoll_entwurf_anlegen(
        vorgang_id: _Id,
        vorlage_id: Annotated[str, Field(description="ID einer veröffentlichten Vorlage (published).")],
        werte: Annotated[dict[str, Any], Field(description="Werte, siehe Beschreibung.")],
    ) -> dict[str, Any]:
        z = zugriff(SCOPE_SCHREIBEN)
        schema = await api_get(z, f"/api/form-schemas/{vorlage_id}")
        if schema["status"] != "published":
            raise ToolError(
                f"Die Vorlage „{schema['name']}“ ist {'noch ein Entwurf' if schema['status'] == 'draft' else 'archiviert'}. "
                "Nur veröffentlichte Vorlagen können ausgefüllt werden; veröffentlichen kann ein Berechtigter im Formular-Baukasten."
            )
        # Vor dem Anlegen komplett pruefen, damit bei einem Eingabefehler kein leeres Protokoll zurueckbleibt.
        werte_abbilden(schema, werte)
        angelegt = await api_post(z, "/api/form-submissions", {"schema_id": vorlage_id}, params={"vorgang_id": vorgang_id})
        patch, gesetzt, uebersprungen = werte_abbilden(schema, werte, angelegt["values"])
        aktuell = dict(angelegt["values"])
        if patch:
            try:
                gespeichert = await api_patch(z, f"/api/form-submissions/{angelegt['id']}", {"values": patch})
            except ToolError as exc:
                raise ToolError(
                    f"Das Protokoll wurde leer angelegt (ID {angelegt['id']}, Status offen), die Werte konnten aber nicht "
                    f"gespeichert werden: {exc}"
                ) from exc
            aktuell = gespeichert["values"]
        return _protokoll_ergebnis(angelegt, schema, aktuell, gesetzt, uebersprungen)

    @mcp.tool(
        name="protokoll_entwurf_ergaenzen",
        title="Protokoll-Entwurf ergänzen",
        description=(
            "Ergänzt ein noch offenes Protokoll um weitere Werte (gleiches Format wie bei "
            "protokoll_entwurf_anlegen). Bereits befüllte Felder bleiben unverändert, es sei denn "
            "`vorhandene_ueberschreiben` ist true; Einträge in wiederholbaren Abschnitten werden angehängt. "
            "Abgeschlossene Protokolle ändert Claude nicht." + _NUR_SCHREIBZUGRIFF
        ),
        annotations=NUR_ADDITIV,
    )
    async def protokoll_entwurf_ergaenzen(
        protokoll_id: Annotated[str, Field(description="ID des offenen Protokolls (Submission).")],
        werte: Annotated[dict[str, Any], Field(description="Werte, siehe protokoll_entwurf_anlegen.")],
        vorhandene_ueberschreiben: Annotated[bool, Field(description="Auch bereits befüllte Felder ersetzen. Standard false.")] = False,
    ) -> dict[str, Any]:
        z = zugriff(SCOPE_SCHREIBEN)
        protokoll = await api_get(z, f"/api/form-submissions/{protokoll_id}")
        if protokoll["status"] != "offen":
            raise ToolError("Dieses Protokoll ist bereits abgeschlossen. Abgeschlossene Protokolle ändert Claude nicht.")
        schema = await api_get(z, f"/api/form-schemas/{protokoll['schema_id']}")
        patch, gesetzt, uebersprungen = werte_abbilden(schema, werte, protokoll["values"], vorhandene_ueberschreiben)
        aktuell = protokoll["values"]
        if patch:
            aktuell = (await api_patch(z, f"/api/form-submissions/{protokoll_id}", {"values": patch}))["values"]
        return _protokoll_ergebnis(protokoll, schema, aktuell, gesetzt, uebersprungen)

    # --- Vorlagen entwerfen --------------------------------------------------------------------

    @mcp.tool(
        name="protokoll_vorlage_entwerfen",
        title="Protokoll-Vorlage entwerfen",
        description=(
            "Legt eine neue Protokoll-Vorlage im Formular-Baukasten als ENTWURF an (Status draft). Sie ist erst "
            "für Techniker sichtbar, wenn ein Berechtigter sie im Baukasten geprüft und veröffentlicht und einem "
            "Leistungstyp zugeordnet hat; das geht per KI nicht. `abschnitte` ist eine Liste aus {titel, "
            "wiederholbar (Standard false; true z. B. für Mängellisten), felder: [{label, typ, pflicht, hilfetext, "
            "optionen}]}. optionen (Liste von Texten) nur bei dropdown und mehrfachauswahl, dort Pflicht. "
            "Sinnvolle Gliederung: Kopf/Anlagendaten, Prüfpunkte, Messwerte, Mängel (wiederholbar), Abschluss "
            "mit Unterschrift. Vorher mit protokoll_vorlagen_auflisten prüfen, ob es die Vorlage schon gibt. "
            "Braucht das Recht Formulare › erstellen." + _NUR_SCHREIBZUGRIFF
        ),
        annotations=NUR_ADDITIV,
    )
    async def protokoll_vorlage_entwerfen(
        name: Annotated[str, Field(min_length=1, max_length=200, description="Name der Vorlage.")],
        abschnitte: Annotated[list[AbschnittEntwurf], Field(description="Abschnitte mit Feldern.")],
        beschreibung: Annotated[str | None, Field(max_length=1000, description="Kurzbeschreibung, wofür die Vorlage dient.")] = None,
    ) -> dict[str, Any]:
        z = zugriff(SCOPE_SCHREIBEN)
        pruefe_abschnitte(abschnitte)
        plan = abschnitte_planen(abschnitte, set())
        schema = await api_post(z, "/api/form-schemas", {"name": name, "beschreibung": beschreibung})
        await _ausfuehren(z, schema, name, [*ansicht_schritte(), *plan.schritte])
        return {
            "id": schema["id"],
            "name": schema["name"],
            "status": schema["status"],
            "zusammenfassung": zusammenfassung(abschnitte),
            "link": vorlagen_link(schema["id"]),
            "hinweis": f"KI-Entwurf, noch nicht veröffentlicht. {_ENTWURF_HINWEIS}",
        }

    @mcp.tool(
        name="protokoll_vorlage_ueberarbeiten",
        title="Protokoll-Vorlage-Entwurf überarbeiten",
        description=(
            "Überarbeitet eine Vorlage, solange sie Entwurf (draft) ist: Abschnitte hinzufügen, Felder zu einem "
            "bestehenden oder in diesem Aufruf angelegten Abschnitt hinzufügen, Beschriftung/Pflicht/Hilfetext/"
            "Optionen bestehender Felder ändern. Entfernen und Typwechsel gibt es nicht (im Baukasten). "
            "Veröffentlichte Vorlagen ändert Claude nicht; dafür mit protokoll_vorlage_lesen den Aufbau holen und "
            "eine neue Variante mit protokoll_vorlage_entwerfen anlegen." + _NUR_SCHREIBZUGRIFF
        ),
        annotations=NUR_ADDITIV,
    )
    async def protokoll_vorlage_ueberarbeiten(
        vorlage_id: _Id,
        abschnitte_hinzufuegen: Annotated[list[AbschnittEntwurf] | None, Field(description="Neue Abschnitte samt Feldern.")] = None,
        felder_hinzufuegen: Annotated[list[FeldHinzufuegen] | None, Field(description="Neue Felder in einem Abschnitt.")] = None,
        felder_aendern: Annotated[list[FeldAenderung] | None, Field(description="Änderungen an bestehenden Feldern.")] = None,
    ) -> dict[str, Any]:
        z = zugriff(SCOPE_SCHREIBEN)
        if not (abschnitte_hinzufuegen or felder_hinzufuegen or felder_aendern):
            raise ToolError("Es gibt nichts zu ändern: bitte abschnitte_hinzufuegen, felder_hinzufuegen oder felder_aendern angeben.")
        detail = await api_get(z, f"/api/form-schemas/{vorlage_id}")
        if detail["status"] != "draft":
            raise ToolError("Veröffentlichte Vorlagen ändert Claude nicht – lege eine neue Variante an.")
        schritte = _ueberarbeitung_planen(detail, abschnitte_hinzufuegen or [], felder_hinzufuegen or [], felder_aendern or [])
        # Entwuerfe ohne jede Ansicht (aeltere KI-Entwuerfe) bekommen sie nachtraeglich; wer im Baukasten schon
        # Ansichten angelegt hat, behaelt seine Auswahl.
        if not await api_get(z, f"/api/form-schemas/{vorlage_id}/views"):
            schritte = [*ansicht_schritte(), *schritte]
        await _ausfuehren(z, detail, detail["name"], schritte)
        return {
            "id": detail["id"],
            "name": detail["name"],
            "status": detail["status"],
            "angewendet": [s.beschreibung for s in schritte],
            "link": vorlagen_link(detail["id"]),
            "hinweis": f"KI-Entwurf überarbeitet. {_ENTWURF_HINWEIS}",
        }


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
