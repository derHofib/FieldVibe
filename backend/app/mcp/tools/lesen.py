"""Lese-Tools (Scope fieldvibe.lesen). Jedes Tool ruft eine bestehende REST-Route in-process
auf (app/mcp/rest_client.py), die Rechte, Scope-Filter und Modul-Schalter selbst durchsetzt."""
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from app.mcp.aufbereitung import SEITENGROESSE, bereinigen, seite_aus
from app.mcp.protokoll_ansicht import abschnitte_aus
from app.mcp.protokoll_werte import fehlende_pflichtfelder
from app.mcp.rest_client import api_get
from app.mcp.tools._basis import zugriff

NUR_LESEN = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

_Seite = Annotated[int, Field(ge=1, description="Seite (je 100 Einträge), beginnend bei 1.")]
_Id = Annotated[str, Field(description="ID (UUID), z. B. aus der Suche oder einer Liste.")]

# Die Vorgaenge-API kennt kein offset, nur limit (max. 200).
_VORGAENGE_API_LIMIT = 200


async def _optional(aufruf) -> Any:
    """Teilabfragen eines Detail-Tools: fehlt dafuer das Recht, bleibt der Rest nutzbar."""
    try:
        return await aufruf
    except ToolError as exc:
        return {"hinweis": str(exc)}


def _liste(daten: Any) -> list[Any]:
    return daten if isinstance(daten, list) else []


def _kontakte_fuer_ki(daten: Any) -> Any:
    """Kontakte vor Ort in der knappen Form fuer das Modell: ohne E-Mail und Erreichbarkeit, mit Herkunft
    (auf welcher Ebene der Kontakt zugeordnet ist). Ein Hinweis-Dict (fehlendes Recht) geht unveraendert durch."""
    if not isinstance(daten, list):
        return daten
    ergebnis = []
    for eintrag in daten:
        kontakt = eintrag.get("kontakt") or {}
        ergebnis.append(
            {
                "name": kontakt.get("name"),
                "rolle": kontakt.get("rolle"),
                "einheit": kontakt.get("einheit"),
                "telefon": kontakt.get("telefon"),
                "hinweis": kontakt.get("hinweis"),
                "hauptkontakt": bool(eintrag.get("ist_hauptkontakt")),
                "herkunft": eintrag.get("herkunft"),
                "herkunft_titel": eintrag.get("herkunft_titel"),
            }
        )
    return ergebnis


def _iso(wert: date | datetime | None) -> str | None:
    return wert.isoformat() if wert else None


def registrieren(mcp: MCPServer) -> None:
    @mcp.tool(
        name="suchen",
        title="In FieldVibe suchen",
        description=(
            "Volltextsuche als Einstieg: findet Kunden (Name/Kundennummer), Vorgänge, Anlagen, "
            "Rechnungen, Kontakte vor Ort (Mieter, Bauherr, Hausmeister; Typ vor_ort_kontakt, die ID ist die "
            "des Kontakts, kunde_id der Auftraggeber) und Tags (Suchtext mit # beginnen). "
            "Liefert je Kategorie die besten Treffer "
            "mit ID, die dann mit kunde_lesen, vorgang_lesen oder anlage_lesen geöffnet werden. "
            "Sichtbar ist nur, was der Nutzer auch in der App sehen darf."
        ),
        annotations=NUR_LESEN,
    )
    async def suchen(
        text: Annotated[str, Field(min_length=1, description="Suchtext, z. B. Kundenname oder Titel.")],
        typ: Annotated[
            Literal["kunde", "anlage", "vorgang", "rechnung", "vor_ort_kontakt", "tag"] | None,
            Field(description="Optional nur diese Kategorie."),
        ] = None,
    ) -> dict[str, Any]:
        z = zugriff()
        daten = await api_get(z, "/api/search", {"q": text})
        treffer = _liste(daten.get("treffer"))
        if typ:
            treffer = [t for t in treffer if t.get("kategorie") == typ]
        return {"treffer": bereinigen(treffer)}

    @mcp.tool(
        name="vorgaenge_auflisten",
        title="Vorgänge auflisten",
        description=(
            "Listet Vorgänge (das Ticket/der Einsatz mit Titel, Status, Chat und Zeit; nicht zu "
            "verwechseln mit der Entität Auftrag). Neueste Aktivität zuerst. Status: neu, geplant, "
            "in_arbeit, wartet_kunde, abgeschlossen, abgerechnet, storniert. Ein Techniker mit "
            "eingeschränktem Recht sieht nur seine eigenen Vorgänge. Die Schnittstelle liefert "
            "höchstens 200 Vorgänge je Filter, in Seiten zu 100."
        ),
        annotations=NUR_LESEN,
    )
    async def vorgaenge_auflisten(
        status: Annotated[
            Literal["neu", "geplant", "in_arbeit", "wartet_kunde", "abgeschlossen", "abgerechnet", "storniert"] | None,
            Field(description="Nur Vorgänge mit diesem Status."),
        ] = None,
        kunde_id: Annotated[str | None, Field(description="Nur Vorgänge dieses Kunden (ID).")] = None,
        anlage_id: Annotated[str | None, Field(description="Nur Vorgänge an dieser Anlage (ID).")] = None,
        standort_id: Annotated[str | None, Field(description="Nur Vorgänge an diesem Standort (ID).")] = None,
        projekt_id: Annotated[str | None, Field(description="Nur Vorgänge dieses Projekts (ID).")] = None,
        auftrag_id: Annotated[str | None, Field(description="Nur Vorgänge dieses Auftrags (ID).")] = None,
        leistungstyp: Annotated[str | None, Field(description="Nur dieser Leistungstyp.")] = None,
        faellig_von: Annotated[date | None, Field(description="Fällig ab (inklusive), Datum JJJJ-MM-TT.")] = None,
        faellig_bis: Annotated[date | None, Field(description="Fällig bis (inklusive), Datum JJJJ-MM-TT.")] = None,
        seite: _Seite = 1,
    ) -> dict[str, Any]:
        z = zugriff()
        daten = await api_get(
            z,
            "/api/vorgaenge",
            {
                "status": status,
                "kunde_id": kunde_id,
                "anlage_id": anlage_id,
                "standort_id": standort_id,
                "projekt_id": projekt_id,
                "auftrag_id": auftrag_id,
                "leistungstyp": leistungstyp,
                "faellig_von": _iso(faellig_von),
                "faellig_bis": _iso(faellig_bis),
                "limit": _VORGAENGE_API_LIMIT,
            },
        )
        liste = _liste(daten)
        return seite_aus(liste, seite, quelle_abgeschnitten=len(liste) >= _VORGAENGE_API_LIMIT)

    @mcp.tool(
        name="vorgang_lesen",
        title="Vorgang lesen",
        description=(
            "Liest einen Vorgang vollständig: Stammdaten, Verlauf (Events: Kommentare, Fotos, "
            "Statuswechsel; neueste zuerst, höchstens 100), Mängel (Defekt, der zu Angebot und "
            "Rechnung führt), ausgefüllte Formulare/Protokolle (Submissions mit Werten) und die Kontakte "
            "vor Ort (Name, Rolle, Einheit, Telefon, Hinweis, Herkunft: Vorgang, Auftrag oder Projekt)."
        ),
        annotations=NUR_LESEN,
    )
    async def vorgang_lesen(vorgang_id: _Id) -> dict[str, Any]:
        z = zugriff()
        vorgang = await api_get(z, f"/api/vorgaenge/{vorgang_id}")
        events = await _optional(api_get(z, f"/api/vorgaenge/{vorgang_id}/events"))
        maengel = await _optional(api_get(z, "/api/maengel", {"vorgang_id": vorgang_id}))
        formulare = await _optional(api_get(z, "/api/form-submissions", {"vorgang_id": vorgang_id}))
        kontakte = _kontakte_fuer_ki(vorgang.pop("vor_ort_kontakte", None)) if isinstance(vorgang, dict) else None
        return bereinigen(
            {
                "vorgang": vorgang,
                "vor_ort_kontakte": kontakte,
                "verlauf": seite_aus(events, 1) if isinstance(events, list) else events,
                "maengel": seite_aus(maengel, 1) if isinstance(maengel, list) else maengel,
                "formulare": seite_aus(formulare, 1) if isinstance(formulare, list) else formulare,
            }
        )

    @mcp.tool(
        name="telefonate_auflisten",
        title="Telefonate auflisten",
        description=(
            "Listet erfasste Telefonate (Gesprächspartner, Richtung, Ergebnis, Dauer, Notiz, Rückruf), neueste "
            "zuerst. Filter nach Kunde, Vorgang oder nur offene Rückrufe (dann nach Rückruf-Termin sortiert). "
            "Sichtbar ist nur, was der Nutzer in der App sehen darf. Höchstens 100 Einträge je Aufruf."
        ),
        annotations=NUR_LESEN,
    )
    async def telefonate_auflisten(
        kunde_id: Annotated[str | None, Field(description="Nur Telefonate dieses Kunden (ID).")] = None,
        vorgang_id: Annotated[str | None, Field(description="Nur Telefonate zu diesem Vorgang (ID).")] = None,
        rueckruf_offen: Annotated[bool, Field(description="Nur Telefonate mit offenem Rückruf.")] = False,
        seite: _Seite = 1,
    ) -> dict[str, Any]:
        z = zugriff()
        liste = _liste(
            await api_get(
                z,
                "/api/telefonate",
                {
                    "kunde_id": kunde_id,
                    "vorgang_id": vorgang_id,
                    "rueckruf_offen": "true" if rueckruf_offen else None,
                    "seite": seite,
                    "limit": SEITENGROESSE,
                },
            )
        )
        ergebnis: dict[str, Any] = {
            "eintraege": bereinigen(liste),
            "seite": seite,
            "gekuerzt": len(liste) >= SEITENGROESSE,
        }
        if ergebnis["gekuerzt"]:
            ergebnis["hinweis"] = f"Weitere Einträge mit seite={seite + 1} abrufen."
        return ergebnis

    @mcp.tool(
        name="auftraege_auflisten",
        title="Aufträge auflisten",
        description=(
            "Listet Aufträge, die separate Entität Auftrag (Office-Bereich Aufträge), die mehrere "
            "Vorgänge bündeln kann. Status: offen, in_arbeit, abgeschlossen, storniert. "
            "Nicht dasselbe wie ein Vorgang (dafür vorgaenge_auflisten)."
        ),
        annotations=NUR_LESEN,
    )
    async def auftraege_auflisten(
        status: Annotated[
            Literal["offen", "in_arbeit", "abgeschlossen", "storniert"] | None,
            Field(description="Nur Aufträge mit diesem Status."),
        ] = None,
        kunde_id: Annotated[str | None, Field(description="Nur Aufträge dieses Kunden (ID).")] = None,
        projekt_id: Annotated[str | None, Field(description="Nur Aufträge dieses Projekts (ID).")] = None,
        seite: _Seite = 1,
    ) -> dict[str, Any]:
        z = zugriff()
        daten = await api_get(
            z, "/api/auftraege", {"status": status, "kunde_id": kunde_id, "projekt_id": projekt_id}
        )
        return seite_aus(_liste(daten), seite)

    @mcp.tool(
        name="auftrag_lesen",
        title="Auftrag lesen",
        description=(
            "Liest einen Auftrag (Entität Auftrag, nicht Vorgang), die zugehörigen Vorgänge und die Kontakte "
            "vor Ort (Name, Rolle, Einheit, Telefon, Hinweis, Herkunft: Auftrag oder Projekt)."
        ),
        annotations=NUR_LESEN,
    )
    async def auftrag_lesen(auftrag_id: _Id) -> dict[str, Any]:
        z = zugriff()
        auftrag = await api_get(z, f"/api/auftraege/{auftrag_id}")
        vorgaenge = await _optional(
            api_get(z, "/api/vorgaenge", {"auftrag_id": auftrag_id, "limit": _VORGAENGE_API_LIMIT})
        )
        kontakte = _kontakte_fuer_ki(await _optional(api_get(z, f"/api/auftraege/{auftrag_id}/vor-ort-kontakte")))
        return bereinigen(
            {
                "auftrag": auftrag,
                "vor_ort_kontakte": kontakte,
                "vorgaenge": seite_aus(vorgaenge, 1) if isinstance(vorgaenge, list) else vorgaenge,
            }
        )

    @mcp.tool(
        name="projekte_auflisten",
        title="Projekte auflisten",
        description=(
            "Listet Projekte (Kanban/Zeitplan-Bereich mit Aufgaben und zugehörigen Aufträgen und "
            "Vorgängen). Optional nur die eines Vertrags."
        ),
        annotations=NUR_LESEN,
    )
    async def projekte_auflisten(
        vertrag_id: Annotated[str | None, Field(description="Nur Projekte dieses Vertrags (ID).")] = None,
        seite: _Seite = 1,
    ) -> dict[str, Any]:
        z = zugriff()
        daten = await api_get(z, "/api/projekte", {"vertrag_id": vertrag_id})
        return seite_aus(_liste(daten), seite)

    @mcp.tool(
        name="projekt_lesen",
        title="Projekt lesen",
        description=(
            "Liest ein Projekt mit seinen Kanban-Spalten und Aufgaben (Status der Aufgaben, "
            "Zuständige, Fälligkeiten) sowie den zugehörigen Aufträgen."
        ),
        annotations=NUR_LESEN,
    )
    async def projekt_lesen(projekt_id: _Id) -> dict[str, Any]:
        z = zugriff()
        projekt = await api_get(z, f"/api/projekte/{projekt_id}")
        spalten = await _optional(api_get(z, f"/api/projekte/{projekt_id}/spalten"))
        aufgaben = await _optional(api_get(z, "/api/projekt-aufgaben", {"projekt_id": projekt_id}))
        auftraege = await _optional(api_get(z, "/api/auftraege", {"projekt_id": projekt_id}))
        return bereinigen(
            {
                "projekt": projekt,
                "spalten": spalten,
                "aufgaben": seite_aus(aufgaben, 1) if isinstance(aufgaben, list) else aufgaben,
                "auftraege": seite_aus(auftraege, 1) if isinstance(auftraege, list) else auftraege,
            }
        )

    @mcp.tool(
        name="kunde_lesen",
        title="Kunde lesen",
        description=(
            "Liest einen Kunden mit seinen Standorten (Sites) und Anlagen (Betriebsmittel beim "
            "Kunden). Für dessen Vorgänge vorgaenge_auflisten mit kunde_id verwenden."
        ),
        annotations=NUR_LESEN,
    )
    async def kunde_lesen(kunde_id: _Id) -> dict[str, Any]:
        z = zugriff()
        kunde = await api_get(z, f"/api/kunden/{kunde_id}")
        standorte = await _optional(api_get(z, "/api/standorte", {"kunde_id": kunde_id}))
        anlagen = await _optional(api_get(z, "/api/anlagen", {"kunde_id": kunde_id}))
        betreuung = await _optional(api_get(z, f"/api/kunden/{kunde_id}/betreuung"))
        return bereinigen(
            {
                "kunde": kunde,
                "betreuung": betreuung,
                "standorte": seite_aus(standorte, 1) if isinstance(standorte, list) else standorte,
                "anlagen": seite_aus(anlagen, 1) if isinstance(anlagen, list) else anlagen,
            }
        )

    @mcp.tool(
        name="anlage_lesen",
        title="Anlage lesen",
        description=(
            "Liest eine Anlage (Betriebsmittel beim Kunden) mit Kunde, Historie (Vorgänge, "
            "Arbeitsstunden) und ihren Prüfzyklen (Wartungsintervalle mit nächster Fälligkeit)."
        ),
        annotations=NUR_LESEN,
    )
    async def anlage_lesen(anlage_id: _Id) -> dict[str, Any]:
        z = zugriff()
        profil = await api_get(z, f"/api/anlagen/{anlage_id}/profil")
        pruefzyklen = await _optional(api_get(z, "/api/pruefzyklen", {"anlage_id": anlage_id}))
        return bereinigen({"anlage": profil, "pruefzyklen": pruefzyklen})

    @mcp.tool(
        name="termine_auflisten",
        title="Termine auflisten",
        description=(
            "Listet Termine der Dispo (Einsatzplanung der Techniker), optional nach Zeitraum, "
            "Techniker, Vorgang oder Projekt. Nur wenn das Modul Dispo aktiv und das Recht "
            "vorhanden ist."
        ),
        annotations=NUR_LESEN,
    )
    async def termine_auflisten(
        von: Annotated[datetime | None, Field(description="Beginn des Zeitraums, ISO-Datum/-Zeit.")] = None,
        bis: Annotated[datetime | None, Field(description="Ende des Zeitraums, ISO-Datum/-Zeit.")] = None,
        techniker_id: Annotated[str | None, Field(description="Nur Termine dieses Technikers (User-ID).")] = None,
        vorgang_id: Annotated[str | None, Field(description="Nur Termine dieses Vorgangs (ID).")] = None,
        projekt_id: Annotated[str | None, Field(description="Nur Termine dieses Projekts (ID).")] = None,
        seite: _Seite = 1,
    ) -> dict[str, Any]:
        z = zugriff()
        daten = await api_get(
            z,
            "/api/termine",
            {
                "von": _iso(von),
                "bis": _iso(bis),
                "techniker_id": techniker_id,
                "vorgang_id": vorgang_id,
                "projekt_id": projekt_id,
            },
        )
        return seite_aus(_liste(daten), seite)

    @mcp.tool(
        name="pruefungen_faellig",
        title="Fällige Prüfungen",
        description=(
            "Zeigt, was in den nächsten Tagen fällig wird (überfällige eingeschlossen): Prüfzyklen "
            "der Anlagen (Wartungsintervalle) und Prüfmittel (Messgeräte, Kalibrierung). "
            "Sortiert nach Fälligkeit."
        ),
        annotations=NUR_LESEN,
    )
    async def pruefungen_faellig(
        tage: Annotated[int, Field(ge=0, le=730, description="Zeitraum in Tagen ab heute.")] = 30,
    ) -> dict[str, Any]:
        z = zugriff()
        grenze = datetime.now(timezone.utc) + timedelta(days=tage)
        zyklen = await _optional(api_get(z, "/api/pruefzyklen"))
        mittel = await _optional(api_get(z, "/api/pruefmittel"))

        def _faellig(eintraege: Any, feld: str, nur_aktive: bool) -> Any:
            if not isinstance(eintraege, list):
                return eintraege
            treffer = []
            for e in eintraege:
                if nur_aktive and not e.get("aktiv", True):
                    continue
                roh = e.get(feld)
                if not roh:
                    continue
                faellig = datetime.fromisoformat(str(roh).replace("Z", "+00:00"))
                if faellig.tzinfo is None:
                    faellig = faellig.replace(tzinfo=timezone.utc)
                if faellig <= grenze:
                    treffer.append(e)
            treffer.sort(key=lambda e: str(e.get(feld)))
            return seite_aus(treffer, 1)

        return {
            "stichtag_bis": grenze.date().isoformat(),
            "pruefzyklen": _faellig(zyklen, "naechste_pruefung_am", True),
            "pruefmittel": _faellig(mittel, "naechste_kalibrierung_am", False),
        }

    @mcp.tool(
        name="formular_vorlagen",
        title="Formular-Vorlagen eines Vorgangs",
        description=(
            "Welche Formular-/Protokoll-Vorlagen für einen Vorgang verfügbar sind (z. B. "
            "Wartungs- oder Prüfprotokoll), inkl. ob sie vor dem Abschluss Pflicht sind."
        ),
        annotations=NUR_LESEN,
    )
    async def formular_vorlagen(vorgang_id: _Id) -> dict[str, Any]:
        z = zugriff()
        daten = await api_get(z, "/api/form-submissions/verfuegbar", {"vorgang_id": vorgang_id})
        return seite_aus(_liste(daten), 1)

    @mcp.tool(
        name="formular_lesen",
        title="Ausgefülltes Formular lesen",
        description=(
            "Liest ein ausgefülltes Formular/Protokoll (Submission) mit allen Werten, Status und Vorgang. Die Werte "
            "stehen roh unter `values` (Feld-Keys) und zusätzlich unter `abschnitte` gruppiert nach den Abschnitten "
            "der Vorlage mit Beschriftungen, Grenzwert-Markierung und Hinweis auf fehlende Pflichtfelder; Fotos nur "
            "als Hinweis. Die Gruppierung braucht das Recht Formulare › sehen, ohne bleibt es bei den Rohwerten."
        ),
        annotations=NUR_LESEN,
    )
    async def formular_lesen(formular_id: Annotated[str, Field(description="ID der Submission.")]) -> dict[str, Any]:
        z = zugriff()
        protokoll = await api_get(z, f"/api/form-submissions/{formular_id}")
        ergebnis = bereinigen(protokoll)
        schema = await _optional(api_get(z, f"/api/form-schemas/{protokoll['schema_id']}"))
        if "fields" in schema:
            ergebnis["abschnitte"] = bereinigen(abschnitte_aus(schema, protokoll["values"]))
            ergebnis["fehlende_pflichtfelder"] = fehlende_pflichtfelder(schema, protokoll["values"])
        else:
            ergebnis["hinweis"] = f"Keine Gruppierung nach Abschnitten: {schema.get('hinweis', 'Vorlage nicht lesbar')}"
        return ergebnis
