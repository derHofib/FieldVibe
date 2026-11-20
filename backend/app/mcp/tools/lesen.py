"""Lese-Tools (Scope fieldvibe.lesen): suchen, lesen, auflisten, dokument_abrufen (und pruefungen_faellig). Jedes Tool
ruft eine bestehende REST-Route in-process auf (app/mcp/rest_client.py), die Rechte, Scope-Filter und Modul-Schalter
selbst durchsetzt. Die Inhalte entsprechen den frueheren Einzel-Tools (vorgang_lesen, auftraege_auflisten, ...), die
in lesen/auflisten aufgegangen sind (Konzept mcp-ausbau 5.1)."""
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any, Literal
from uuid import UUID

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import EmbeddedResource, TextContent
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.db.session import tenant_session
from app.mcp.aufbereitung import SEITENGROESSE, bereinigen, seite_aus
from app.mcp.protokoll_ansicht import abschnitte_aus
from app.mcp.protokoll_werte import fehlende_pflichtfelder
from app.mcp.rest_client import api_get, api_get_binaer
from app.mcp.tools._basis import NUR_LESEN, zugriff
from app.mcp.tools.protokolle import _pdf_ergebnis, vorlage_kompakt
from app.services import ki_journal_service

_Seite = Annotated[int, Field(ge=1, description="Seite (je 100 Einträge), beginnend bei 1.")]
_Id = Annotated[str, Field(description="ID (UUID), z. B. aus der Suche oder einer Liste.")]

# Die Vorgaenge-API kennt kein offset, nur limit (max. 200).
_VORGAENGE_API_LIMIT = 200
_MAX_XML_ZEICHEN = 200_000

LesbarTyp = Literal[
    "vorgang", "auftrag", "projekt", "aufgabe", "kunde", "anlage", "kontakt_vor_ort", "termin", "telefonat",
    "formular", "vorlage", "angebot", "rechnung", "mangel", "ich", "ki_aktion",
]
ListenTyp = Literal[
    "vorgang", "auftrag", "projekt", "aufgabe", "termin", "telefonat", "vorlage", "angebot", "rechnung", "mitarbeiter", "ki_aktion"
]


async def _optional(aufruf) -> Any:
    """Teilabfragen eines Detail-Tools: fehlt dafuer das Recht, bleibt der Rest nutzbar."""
    try:
        return await aufruf
    except ToolError as exc:
        return {"hinweis": str(exc)}


def _liste(daten: Any) -> list[Any]:
    return daten if isinstance(daten, list) else []


def _seite(daten: Any) -> Any:
    return seite_aus(daten, 1) if isinstance(daten, list) else daten


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


# --- lesen: je Typ eine Funktion (z, id, umfang) -----------------------------------------------------------------


async def _vorgang(z, id_: str, umfang: str) -> dict[str, Any]:
    vorgang = await api_get(z, f"/api/vorgaenge/{id_}")
    kontakte = _kontakte_fuer_ki(vorgang.pop("vor_ort_kontakte", None)) if isinstance(vorgang, dict) else None
    if umfang == "kurz":
        return bereinigen({"vorgang": vorgang, "vor_ort_kontakte": kontakte})
    events = await _optional(api_get(z, f"/api/vorgaenge/{id_}/events"))
    ergebnis = {
        "vorgang": vorgang,
        "vor_ort_kontakte": kontakte,
        "verlauf": _seite(events),
        "maengel": _seite(await _optional(api_get(z, "/api/maengel", {"vorgang_id": id_}))),
        "formulare": _seite(await _optional(api_get(z, "/api/form-submissions", {"vorgang_id": id_}))),
    }
    if umfang == "verlauf":
        ergebnis["telefonate"] = _seite(await _optional(api_get(z, "/api/telefonate", {"vorgang_id": id_})))
        ergebnis["termine"] = _seite(await _optional(api_get(z, "/api/termine", {"vorgang_id": id_})))
    return bereinigen(ergebnis)


async def _auftrag(z, id_: str, umfang: str) -> dict[str, Any]:
    auftrag = await api_get(z, f"/api/auftraege/{id_}")
    if umfang == "kurz":
        return bereinigen({"auftrag": auftrag})
    vorgaenge = await _optional(api_get(z, "/api/vorgaenge", {"auftrag_id": id_, "limit": _VORGAENGE_API_LIMIT}))
    kontakte = _kontakte_fuer_ki(await _optional(api_get(z, f"/api/auftraege/{id_}/vor-ort-kontakte")))
    ergebnis = {"auftrag": auftrag, "vor_ort_kontakte": kontakte, "vorgaenge": _seite(vorgaenge)}
    if umfang == "verlauf":
        ergebnis["aufgaben"] = _seite(await _optional(api_get(z, "/api/projekt-aufgaben", {"auftrag_id": id_})))
    return bereinigen(ergebnis)


async def _projekt(z, id_: str, umfang: str) -> dict[str, Any]:
    projekt = await api_get(z, f"/api/projekte/{id_}")
    if umfang == "kurz":
        return bereinigen({"projekt": projekt})
    return bereinigen(
        {
            "projekt": projekt,
            "spalten": await _optional(api_get(z, f"/api/projekte/{id_}/spalten")),
            "aufgaben": _seite(await _optional(api_get(z, "/api/projekt-aufgaben", {"projekt_id": id_}))),
            "auftraege": _seite(await _optional(api_get(z, "/api/auftraege", {"projekt_id": id_}))),
        }
    )


async def _kunde(z, id_: str, umfang: str) -> dict[str, Any]:
    kunde = await api_get(z, f"/api/kunden/{id_}")
    if umfang == "kurz":
        return bereinigen({"kunde": kunde})
    ergebnis = {
        "kunde": kunde,
        "betreuung": await _optional(api_get(z, f"/api/kunden/{id_}/betreuung")),
        "standorte": _seite(await _optional(api_get(z, "/api/standorte", {"kunde_id": id_}))),
        "anlagen": _seite(await _optional(api_get(z, "/api/anlagen", {"kunde_id": id_}))),
    }
    if umfang == "verlauf":
        ergebnis["telefonate"] = _seite(await _optional(api_get(z, "/api/telefonate", {"kunde_id": id_})))
        ergebnis["kontakte_vor_ort"] = _seite(await _optional(api_get(z, f"/api/kunden/{id_}/vor-ort-kontakte")))
    return bereinigen(ergebnis)


async def _anlage(z, id_: str, umfang: str) -> dict[str, Any]:
    profil = await api_get(z, f"/api/anlagen/{id_}/profil")
    if umfang == "kurz":
        return bereinigen({"anlage": profil})
    return bereinigen({"anlage": profil, "pruefzyklen": await _optional(api_get(z, "/api/pruefzyklen", {"anlage_id": id_}))})


async def _formular(z, id_: str, umfang: str) -> dict[str, Any]:
    protokoll = await api_get(z, f"/api/form-submissions/{id_}")
    ergebnis = bereinigen(protokoll)
    if umfang == "kurz":
        return ergebnis
    schema = await _optional(api_get(z, f"/api/form-schemas/{protokoll['schema_id']}"))
    if "fields" in schema:
        ergebnis["abschnitte"] = bereinigen(abschnitte_aus(schema, protokoll["values"]))
        ergebnis["fehlende_pflichtfelder"] = fehlende_pflichtfelder(schema, protokoll["values"])
    else:
        ergebnis["hinweis"] = f"Keine Gruppierung nach Abschnitten: {schema.get('hinweis', 'Vorlage nicht lesbar')}"
    return ergebnis


async def _vorlage(z, id_: str, umfang: str) -> dict[str, Any]:
    return bereinigen(vorlage_kompakt(await api_get(z, f"/api/form-schemas/{id_}")))


def _einfach(pfad: str):
    async def holen(z, id_: str, umfang: str) -> dict[str, Any]:
        return bereinigen(await api_get(z, pfad.format(id=id_)))

    return holen


_LESER = {
    "vorgang": _vorgang,
    "auftrag": _auftrag,
    "projekt": _projekt,
    "kunde": _kunde,
    "anlage": _anlage,
    "formular": _formular,
    "vorlage": _vorlage,
    "aufgabe": _einfach("/api/projekt-aufgaben/{id}"),
    "termin": _einfach("/api/termine/{id}"),
    "telefonat": _einfach("/api/telefonate/{id}"),
    "angebot": _einfach("/api/angebote/{id}"),
    "rechnung": _einfach("/api/rechnungen/{id}"),
    "mangel": _einfach("/api/maengel/{id}"),
}


async def _kontakt_vor_ort(z, id_: str, kunde_id: str | None) -> dict[str, Any]:
    if not kunde_id:
        raise ToolError(
            "Kontakte vor Ort liest man über ihren Kunden: bitte kunde_id angeben (suchen liefert sie zum Kontakt)."
        )
    liste = await api_get(z, f"/api/kunden/{kunde_id}/vor-ort-kontakte")
    treffer = next((k for k in _liste(liste) if str(k.get("id")) == str(id_)), None)
    if treffer is None:
        raise ToolError("Nicht gefunden: Der Kontakt existiert nicht oder gehört nicht zu diesem Kunden.")
    return bereinigen(treffer)


async def _ich(z) -> dict[str, Any]:
    me = await api_get(z, "/api/auth/me")
    rechte = me.get("rechte") or {}
    return {
        "name": me.get("name"),
        "user_id": str(z.user_id),
        "rolle": me.get("role"),
        "account_typ": me.get("account_typ_name"),
        "mandant": me.get("mandant_name"),
        "sieht_nur_zugewiesene_kunden": me.get("nur_zugewiesene_kunden"),
        "fachrechte": {bereich: sorted(aktionen) for bereich, aktionen in sorted(rechte.items()) if aktionen},
        "reichweite_der_rechte": me.get("rechte_scopes"),
        "deaktivierte_module": me.get("deaktivierte_module"),
        "verbindung": {
            "zugriffsbereiche": sorted(z.scopes),
            "schreiben_erlaubt": "fieldvibe.schreiben" in z.scopes,
        },
        "ki_stufen": (
            "Stufe 1 (Anlegen) und Stufe 2 (Ändern, Verknüpfen) führe ich direkt aus und protokolliere sie im KI-Journal "
            "(rueckgaengig möglich). Stufe 3 (Senden, Abschließen, Löschen, Festschreiben) folgt mit einer späteren "
            "Ausbaustufe; das macht der Mensch in der App."
        ),
    }


async def _ki_aktion(z, id_: str) -> dict[str, Any]:
    try:
        uuid = UUID(id_)
    except ValueError as exc:
        raise ToolError("id ist keine gültige Aktions-ID.") from exc
    async with tenant_session(mandant_id=z.mandant_id) as session:
        aktion = await ki_journal_service.lesen(session, user_id=z.user_id, ist_admin=z.role == "mandant_admin", aktion_id=uuid)
    if aktion is None:
        raise ToolError("Nicht gefunden: Diese Aktion gibt es nicht oder sie gehört einem anderen Nutzer.")
    return aktion.model_dump(mode="json")


# --- auflisten: Filter je Typ als Pydantic-Klasse ----------------------------------------------------------------


class _Filter(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VorgangFilter(_Filter):
    status: Literal["neu", "geplant", "in_arbeit", "wartet_kunde", "abgeschlossen", "abgerechnet", "storniert"] | None = None
    kunde_id: str | None = None
    anlage_id: str | None = None
    standort_id: str | None = None
    projekt_id: str | None = None
    auftrag_id: str | None = None
    leistungstyp: str | None = None
    faellig_von: date | None = None
    faellig_bis: date | None = None


class AuftragFilter(_Filter):
    status: Literal["offen", "in_arbeit", "abgeschlossen", "storniert"] | None = None
    kunde_id: str | None = None
    projekt_id: str | None = None


class ProjektFilter(_Filter):
    vertrag_id: str | None = None


class AufgabeFilter(_Filter):
    projekt_id: str | None = None
    vorgang_id: str | None = None
    auftrag_id: str | None = None
    mir_zugewiesen: bool | None = None
    erledigt: bool | None = None


class TerminFilter(_Filter):
    von: datetime | None = None
    bis: datetime | None = None
    techniker_id: str | None = None
    vorgang_id: str | None = None
    projekt_id: str | None = None


class TelefonatFilter(_Filter):
    kunde_id: str | None = None
    vorgang_id: str | None = None
    rueckruf_offen: bool | None = None


class VorlageFilter(_Filter):
    status: Literal["draft", "published", "archived"] | None = None
    vorgang_id: str | None = None


class AngebotFilter(_Filter):
    status: str | None = None
    kunde_id: str | None = None
    vorgang_id: str | None = None


class RechnungFilter(_Filter):
    status: str | None = None
    kunde_id: str | None = None
    vorgang_id: str | None = None
    suche: str | None = None
    von: date | None = None
    bis: date | None = None
    nur_offen: bool | None = None
    nur_ueberfaellig: bool | None = None


class MitarbeiterFilter(_Filter):
    suche: str | None = None


class KiAktionFilter(_Filter):
    status: Literal["ausgefuehrt", "rueckgaengig", "vorgeschlagen", "abgelehnt", "abgelaufen", "fehlgeschlagen"] | None = None
    suche: str | None = None
    von: date | None = None
    bis: date | None = None


_FILTER: dict[str, type[_Filter]] = {
    "vorgang": VorgangFilter,
    "auftrag": AuftragFilter,
    "projekt": ProjektFilter,
    "aufgabe": AufgabeFilter,
    "termin": TerminFilter,
    "telefonat": TelefonatFilter,
    "vorlage": VorlageFilter,
    "angebot": AngebotFilter,
    "rechnung": RechnungFilter,
    "mitarbeiter": MitarbeiterFilter,
    "ki_aktion": KiAktionFilter,
}


def _filter_pruefen(typ: str, roh: dict[str, Any]) -> dict[str, Any]:
    modell = _FILTER[typ]
    try:
        return modell.model_validate(roh).model_dump(exclude_none=True)
    except ValidationError as exc:
        erlaubt = ", ".join(modell.model_fields)
        probleme = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        raise ToolError(f"Ungültiger Filter für typ={typ} ({probleme}). Erlaubte Filter: {erlaubt}.") from exc


def _bool(wert: bool | None) -> str | None:
    return None if wert is None else ("true" if wert else "false")


async def _auflisten(z, typ: str, f: dict[str, Any], seite: int) -> dict[str, Any]:
    if typ == "vorgang":
        liste = _liste(
            await api_get(
                z,
                "/api/vorgaenge",
                {**{k: _iso(v) if isinstance(v, (date, datetime)) else v for k, v in f.items()}, "limit": _VORGAENGE_API_LIMIT},
            )
        )
        return seite_aus(liste, seite, quelle_abgeschnitten=len(liste) >= _VORGAENGE_API_LIMIT)
    if typ == "auftrag":
        return seite_aus(_liste(await api_get(z, "/api/auftraege", f)), seite)
    if typ == "projekt":
        return seite_aus(_liste(await api_get(z, "/api/projekte", f)), seite)
    if typ == "aufgabe":
        params = {**f, "mir_zugewiesen": _bool(f.get("mir_zugewiesen")), "erledigt": _bool(f.get("erledigt"))}
        return seite_aus(_liste(await api_get(z, "/api/projekt-aufgaben", params)), seite)
    if typ == "termin":
        params = {k: _iso(v) if isinstance(v, (date, datetime)) else v for k, v in f.items()}
        return seite_aus(_liste(await api_get(z, "/api/termine", params)), seite)
    if typ == "telefonat":
        liste = _liste(
            await api_get(
                z,
                "/api/telefonate",
                {**f, "rueckruf_offen": "true" if f.get("rueckruf_offen") else None, "seite": seite, "limit": SEITENGROESSE},
            )
        )
        ergebnis: dict[str, Any] = {"eintraege": bereinigen(liste), "seite": seite, "gekuerzt": len(liste) >= SEITENGROESSE}
        if ergebnis["gekuerzt"]:
            ergebnis["hinweis"] = f"Weitere Einträge mit seite={seite + 1} abrufen."
        return ergebnis
    if typ == "vorlage":
        if f.get("vorgang_id"):
            # Vorlagen, die fuer diesen Vorgang ausfuellbar sind (Leistungstyp-Zuordnung), inkl. Pflicht vor Abschluss.
            return seite_aus(_liste(await api_get(z, "/api/form-submissions/verfuegbar", {"vorgang_id": f["vorgang_id"]})), seite)
        daten = _liste(await api_get(z, "/api/form-schemas", {"status": f.get("status")}))
        kompakt = [{k: v[k] for k in ("id", "name", "beschreibung", "status", "version")} for v in daten]
        return seite_aus(kompakt, seite)
    if typ == "angebot":
        return seite_aus(_liste(await api_get(z, "/api/angebote", f)), seite)
    if typ == "rechnung":
        params = {
            **{k: _iso(v) if isinstance(v, (date, datetime)) else v for k, v in f.items() if k != "suche"},
            "q": f.get("suche"),
            "nur_offen": _bool(f.get("nur_offen")),
            "nur_ueberfaellig": _bool(f.get("nur_ueberfaellig")),
            "limit": 200,
        }
        liste = _liste(await api_get(z, "/api/rechnungen", params))
        return seite_aus(liste, seite, quelle_abgeschnitten=len(liste) >= 200)
    if typ == "mitarbeiter":
        liste = _liste(await api_get(z, "/api/users/auswahl"))
        suche = (f.get("suche") or "").lower()
        if suche:
            liste = [u for u in liste if suche in str(u.get("name", "")).lower()]
        return seite_aus(liste, seite)
    # ki_aktion
    async with tenant_session(mandant_id=z.mandant_id) as session:
        eintraege, gesamt = await ki_journal_service.auflisten(
            session,
            user_id=z.user_id,
            ist_admin=z.role == "mandant_admin",
            status=f.get("status"),
            von=f.get("von"),
            bis=f.get("bis"),
            q=f.get("suche"),
            limit=SEITENGROESSE,
            offset=(seite - 1) * SEITENGROESSE,
        )
    ergebnis = {
        "eintraege": [e.model_dump(mode="json") for e in eintraege],
        "seite": seite,
        "anzahl_gesamt": gesamt,
        "gekuerzt": seite * SEITENGROESSE < gesamt,
    }
    if ergebnis["gekuerzt"]:
        ergebnis["hinweis"] = f"Weitere Einträge mit seite={seite + 1} abrufen."
    return ergebnis


# --- Tools -------------------------------------------------------------------------------------------------------


def registrieren(mcp: MCPServer) -> None:
    @mcp.tool(
        name="suchen",
        title="In FieldVibe suchen",
        description=(
            "Volltextsuche als Einstieg: findet Kunden (Name/Kundennummer), Vorgänge, Anlagen, "
            "Rechnungen, Kontakte vor Ort (Mieter, Bauherr, Hausmeister; Typ vor_ort_kontakt, die ID ist die "
            "des Kontakts, kunde_id der Auftraggeber) und Tags (Suchtext mit # beginnen). "
            "Liefert je Kategorie die besten Treffer mit ID, die dann mit lesen geöffnet werden "
            "(Aufträge und Projekte findest du mit auflisten). "
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
        name="lesen",
        title="Datensatz lesen",
        description=(
            "Liest einen Datensatz per ID. typ: vorgang (das Ticket/der Einsatz mit Verlauf, Mängeln, Protokollen, "
            "Kontakten vor Ort; das, was im Alltag „Auftrag“ heißt), auftrag (die übergeordnete Entität, die mehrere "
            "Vorgänge bündelt, samt Vorgängen), projekt (Kanban-Spalten, Aufgaben, Aufträge), aufgabe, kunde (mit "
            "Standorten, Anlagen, Betreuung), anlage (Betriebsmittel mit Historie und Prüfzyklen), kontakt_vor_ort "
            "(braucht zusätzlich kunde_id), termin, telefonat, formular (ausgefülltes Protokoll mit Werten, Abschnitten, "
            "Grenzwert-Markierung und fehlenden Pflichtfeldern), vorlage (Aufbau einer Protokoll-Vorlage), angebot, "
            "rechnung, mangel, ich (id ignorieren: dein Name, Rolle, wirksame Fachrechte, Zugriffsbereiche der "
            "Verbindung, ob Schreiben erlaubt ist) und ki_aktion (ein Eintrag aus dem KI-Journal). "
            "umfang: kurz = nur der Kopf; voll = Kopf und Teilabfragen (Standard); verlauf = zusätzlich Telefonate/Termine "
            "bzw. Aufgaben, wo es sie gibt. Für Dateien dokument_abrufen. Sichtbar ist nur, was der Nutzer in der App "
            "sehen darf."
        ),
        annotations=NUR_LESEN,
    )
    async def lesen(
        typ: Annotated[LesbarTyp, Field(description="Art des Datensatzes.")],
        id: Annotated[str | None, Field(description="ID (UUID); bei typ=ich weglassen.")] = None,
        umfang: Annotated[Literal["kurz", "voll", "verlauf"], Field(description="Detailtiefe, Standard voll.")] = "voll",
        kunde_id: Annotated[str | None, Field(description="Nur für typ=kontakt_vor_ort: Kunde des Kontakts (ID).")] = None,
    ) -> dict[str, Any]:
        z = zugriff()
        if typ == "ich":
            return await _ich(z)
        if not id:
            raise ToolError(f"Für typ={typ} wird eine id gebraucht.")
        if typ == "kontakt_vor_ort":
            return await _kontakt_vor_ort(z, id, kunde_id)
        if typ == "ki_aktion":
            return await _ki_aktion(z, id)
        return await _LESER[typ](z, id, umfang)

    @mcp.tool(
        name="auflisten",
        title="Datensätze auflisten",
        description=(
            "Listet Datensätze eines Typs, gefiltert über `filter` (Objekt; unbekannte Filter werden mit der Liste der "
            "erlaubten abgelehnt). Je Seite höchstens 100 Einträge (seite). Typen und Filter: "
            "vorgang (das Ticket/der Einsatz, nicht die Entität Auftrag; neueste Aktivität zuerst; höchstens 200 je "
            "Filter): status (neu, geplant, in_arbeit, wartet_kunde, abgeschlossen, abgerechnet, storniert), kunde_id, "
            "anlage_id, standort_id, projekt_id, auftrag_id, leistungstyp, faellig_von, faellig_bis (JJJJ-MM-TT). "
            "auftrag (Entität Auftrag): status (offen, in_arbeit, abgeschlossen, storniert), kunde_id, projekt_id. "
            "projekt: vertrag_id. aufgabe: projekt_id, vorgang_id, auftrag_id, mir_zugewiesen, erledigt. "
            "termin (Dispo): von, bis, techniker_id, vorgang_id, projekt_id. "
            "telefonat: kunde_id, vorgang_id, rueckruf_offen. "
            "vorlage (Protokoll-Vorlagen): status (draft, published, archived) oder vorgang_id (dann die für diesen "
            "Vorgang verfügbaren Vorlagen, inkl. Pflicht vor Abschluss). "
            "angebot: status, kunde_id, vorgang_id. "
            "rechnung: status, kunde_id, vorgang_id, suche, von, bis, nur_offen, nur_ueberfaellig. "
            "mitarbeiter (zuweisbare Nutzer mit ID): suche. "
            "ki_aktion (KI-Journal, eigene Einträge; Administratoren alle): status, suche, von, bis. "
            "Sichtbar ist nur, was der Nutzer in der App sehen darf."
        ),
        annotations=NUR_LESEN,
    )
    async def auflisten(
        typ: Annotated[ListenTyp, Field(description="Art der Datensätze.")],
        filter: Annotated[dict[str, Any] | None, Field(description="Filter je Typ, siehe Beschreibung.")] = None,
        seite: _Seite = 1,
    ) -> dict[str, Any]:
        z = zugriff()
        return await _auflisten(z, typ, _filter_pruefen(typ, filter or {}), seite)

    @mcp.tool(
        name="dokument_abrufen",
        title="Dokument als PDF abrufen",
        description=(
            "Liefert ein Dokument als PDF (bei rechnung auch als XML). typ: protokoll (id = Protokoll/Submission; ein "
            "offenes Protokoll ist nur eine Vorschau), maengelprotokoll (id = Vorgang-ID; alle erfassten Mängel; "
            "Modul Abrechnung), angebot, rechnung (format pdf oder xml). Größer als 5 MB wird nicht übertragen. "
            "Ein Protokoll-PDF braucht eine Druckansicht der Vorlage."
        ),
        annotations=NUR_LESEN,
    )
    async def dokument_abrufen(
        typ: Annotated[Literal["protokoll", "maengelprotokoll", "angebot", "rechnung"], Field(description="Art des Dokuments.")],
        id: Annotated[str, Field(description="ID des Dokuments bzw. beim Mängelprotokoll des Vorgangs.")],
        format: Annotated[Literal["pdf", "xml"], Field(description="pdf (Standard); xml nur bei rechnung.")] = "pdf",
    ) -> list[TextContent | EmbeddedResource]:
        z = zugriff()
        if format == "xml":
            if typ != "rechnung":
                raise ToolError("XML gibt es nur bei Rechnungen (typ=rechnung).")
            daten, _ = await api_get_binaer(z, f"/api/rechnungen/{id}/xml")
            text = daten.decode("utf-8", errors="replace")
            if len(text) > _MAX_XML_ZEICHEN:
                raise ToolError("Das XML ist zu groß für die Übertragung; bitte in der FieldVibe-App herunterladen.")
            return [TextContent(type="text", text=text)]
        if typ == "protokoll":
            daten, inhalt = await api_get_binaer(z, f"/api/form-submissions/{id}/pdf")
            return _pdf_ergebnis(daten, inhalt, f"fieldvibe://protokoll/{id}.pdf", "Das Protokoll")
        if typ == "maengelprotokoll":
            daten, inhalt = await api_get_binaer(z, "/api/maengel/protokoll/pdf", {"vorgang_id": id})
            return _pdf_ergebnis(daten, inhalt, f"fieldvibe://maengelprotokoll/{id}.pdf", "Das Mängelprotokoll")
        pfad = "angebote" if typ == "angebot" else "rechnungen"
        daten, inhalt = await api_get_binaer(z, f"/api/{pfad}/{id}/pdf")
        return _pdf_ergebnis(daten, inhalt, f"fieldvibe://{typ}/{id}.pdf", "Das Angebot" if typ == "angebot" else "Die Rechnung")

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
