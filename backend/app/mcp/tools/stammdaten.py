"""Anlegen/Aendern von Stammdaten und Verknuepfen (Scope fieldvibe.schreiben + Recht ki_zugriff.bearbeiten).

Je Objektart ein *_speichern-Tool (ohne id anlegen, mit id aendern; Ablauf in app/mcp/speichern.py) und ein
gemeinsames `verknuepfen`. Alles laeuft ueber die Fachrouten und schreibt ins KI-Journal; Loeschen, Abschliessen,
Stornieren und Senden gibt es hier nicht (Stufe 3, kommt spaeter) -- das macht der Mensch in der App."""
from datetime import date, datetime
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, Field

from app.mcp.ansichten import AENDERUNG_URI, ui_meta
from app.mcp.anzeige import EINGEBETTET, Namen, app_link, eintrag, feld_label
from app.mcp.journal import Aktion, operation, pruefung
from app.mcp.oauth_provider import KiAccessToken
from app.mcp.rest_client import api_get, api_patch, api_post, api_verknuepfung_loesen
from app.mcp.speichern import ARTEN, speichern
from app.mcp.tools._basis import AENDERND, zugriff
from app.mcp.zugang import SCOPE_SCHREIBEN

SCHREIB_TOOLS = frozenset(
    {
        "vorgang_speichern",
        "auftrag_speichern",
        "projekt_speichern",
        "aufgabe_speichern",
        "termin_speichern",
        "kunde_speichern",
        "verknuepfen",
    }
)

_Id = Annotated[str, Field(description="ID (UUID), z. B. aus der Suche oder einer Liste.")]
_Leeren = Annotated[
    list[str] | None,
    Field(description="Felder, die auf leer gesetzt werden sollen (nur beim Ändern). Nicht übergebene Felder bleiben unverändert."),
]
_NUR_SCHREIBZUGRIFF = " (nur mit Schreibzugriff)"
_RUECKGAENGIG = " Jede Änderung steht im KI-Journal und lässt sich 7 Tage lang mit rueckgaengig zurücknehmen."


class Adresse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strasse: Annotated[str | None, Field(max_length=200, description="Straße und Hausnummer.")] = None
    plz: Annotated[str | None, Field(max_length=20)] = None
    ort: Annotated[str | None, Field(max_length=100)] = None


def _iso(wert: date | datetime | None) -> str | None:
    return wert.isoformat() if wert is not None else None


def _werte(**felder: Any) -> dict[str, Any]:
    """Nur uebergebene Felder: "nicht uebergeben" (None) ist etwas anderes als "leeren" (felder_leeren)."""
    ergebnis: dict[str, Any] = {}
    for name, wert in felder.items():
        if wert is None:
            continue
        if isinstance(wert, BaseModel):
            wert = wert.model_dump(exclude_none=True)
        elif isinstance(wert, (date, datetime)):
            wert = wert.isoformat()
        ergebnis[name] = wert
    return ergebnis


# --- verknuepfen -------------------------------------------------------------------------------------------------

_KOMBINATIONEN = (
    "vorgang -> auftrag, vorgang -> projekt, auftrag -> projekt, vorgang -> anlage, vorgang -> vorgang (blockiert von), "
    "kontakt_vor_ort -> vorgang, kontakt_vor_ort -> auftrag, kontakt_vor_ort -> projekt"
)
_PLURAL = {"vorgang": ("Vorgang", "Vorgänge"), "auftrag": ("Auftrag", "Aufträge"), "kontakt_vor_ort": ("Kontakt vor Ort", "Kontakte vor Ort")}
_ZIEL_PFAD = {"vorgang": "vorgaenge", "auftrag": "auftraege", "projekt": "projekte"}
_FELD_FUER_ZIEL = {("vorgang", "auftrag"): "auftrag_id", ("vorgang", "projekt"): "projekt_id", ("auftrag", "projekt"): "projekt_id"}
_UNTERSTUETZT = {
    ("vorgang", "auftrag"),
    ("vorgang", "projekt"),
    ("auftrag", "projekt"),
    ("vorgang", "anlage"),
    ("vorgang", "vorgang"),
    ("kontakt_vor_ort", "vorgang"),
    ("kontakt_vor_ort", "auftrag"),
    ("kontakt_vor_ort", "projekt"),
}


def _kopf_label(typ: str, o: dict[str, Any]) -> str:
    return ARTEN[typ].label(o)


async def _link_aenderung(
    aktion: Aktion, namen: Namen, typ: str, id_: str, label: str, feld: str, feld_bez: str, alt: str | None, neu: str | None
) -> None:
    aktion.aenderungen.append(
        {
            "typ": typ,
            "id": str(id_),
            "label": label,
            "feld": feld,
            "feld_label": feld_bez,
            "vorher": eintrag(alt, alt),
            "nachher": eintrag(neu, neu),
        }
    )


async def _feld_verknuepfen(
    z: KiAccessToken, aktion: Aktion, namen: Namen, objekt_typ: str, id_: str, mit_typ: str, mit_id: str, loesen: bool
) -> bool:
    """vorgang -> auftrag/projekt, auftrag -> projekt: setzt (oder leert) ein Feld per PATCH. Gibt an, ob sich etwas aendert.
    Loesen heisst hier: Feld auf null (der Vorgang bleibt an seinem Projekt, wenn nur der Auftrag geloest wird -- das
    entscheidet die Route). "Eigenstaendig fuehren" (Vorgang bewusst ohne Zuordnung) ist ein eigener App-Schritt."""
    art = ARTEN[objekt_typ]
    feld = _FELD_FUER_ZIEL[(objekt_typ, mit_typ)]
    pfad = f"{art.basis}/{id_}"
    vorher = await api_get(z, pfad)
    label = art.label(vorher)
    aktuell = vorher.get(feld)
    ziel_wert = None if loesen else mit_id
    if loesen and mit_id and aktuell is not None and str(aktuell) != str(mit_id):
        raise ToolError(f"{art.bezeichnung} „{label}“ gehört nicht zu diesem {mit_typ.capitalize()}; nichts gelöst.")
    if (aktuell is None and ziel_wert is None) or (aktuell is not None and ziel_wert is not None and str(aktuell) == str(ziel_wert)):
        return False
    nachher = await api_patch(z, pfad, {feld: ziel_wert})
    namen.merken(objekt_typ, id_, label)
    aktion.ziel(objekt_typ, id_, label)
    geaendert = await aktion.vergleichen(namen, objekt_typ, id_, label, vorher, nachher, list(dict.fromkeys([feld, "projekt_id"] if objekt_typ == "vorgang" else [feld])))
    rueck = {f: vorher.get(f) for f in geaendert}
    pruefungen = [
        pruefung(pfad, f, nachher.get(f), label=label, feld_label=feld_label(objekt_typ, f), erwartet_anzeige=await namen.anzeige(f, nachher.get(f), nachher), anzeige_feld=EINGEBETTET.get(f))
        for f in geaendert
    ]
    aktion.rueckweg_hinzu(operation("PATCH", pfad, rueck, pruefungen))
    return True


async def _anlage_verknuepfen(z, aktion, namen, id_, anlage_id, loesen) -> bool:
    vorgang = await api_get(z, f"/api/vorgaenge/{id_}")
    label = _kopf_label("vorgang", vorgang)
    vorhandene = await api_get(z, f"/api/vorgaenge/{id_}/anlagen")
    schon = any(str(a["id"]) == str(anlage_id) for a in vorhandene) or str(vorgang.get("anlage_id")) == str(anlage_id)
    anlage_label = await namen.aufloesen("anlage", anlage_id) or str(anlage_id)
    if loesen:
        if not any(str(a["id"]) == str(anlage_id) for a in vorhandene):
            if str(vorgang.get("anlage_id")) == str(anlage_id):
                raise ToolError(
                    f"Die Anlage „{anlage_label}“ ist die Hauptanlage von „{label}“. Die ändert vorgang_speichern (anlage_id)."
                )
            return False
        await api_verknuepfung_loesen(z, f"/api/vorgaenge/{id_}/anlagen/{anlage_id}")
        aktion.rueckweg_hinzu(operation("POST", f"/api/vorgaenge/{id_}/anlagen", {"anlage_ids": [str(anlage_id)]}))
        await _link_aenderung(aktion, namen, "vorgang", id_, label, "anlage", "Weitere Anlage", anlage_label, None)
    else:
        if schon:
            return False
        await api_post(z, f"/api/vorgaenge/{id_}/anlagen", {"anlage_ids": [str(anlage_id)]})
        aktion.rueckweg_hinzu(operation("DELETE", f"/api/vorgaenge/{id_}/anlagen/{anlage_id}"))
        await _link_aenderung(aktion, namen, "vorgang", id_, label, "anlage", "Weitere Anlage", None, anlage_label)
    aktion.ziel("vorgang", id_, label)
    return True


async def _abhaengigkeit(z, aktion, namen, id_, blockierer_id, loesen) -> bool:
    vorgang = await api_get(z, f"/api/vorgaenge/{id_}")
    label = _kopf_label("vorgang", vorgang)
    liste = await api_get(z, f"/api/vorgaenge/{id_}/abhaengigkeiten")
    besteht = any(str(a["blockiert_von_id"]) == str(blockierer_id) for a in liste.get("blockiert_von", []))
    blockierer = await namen.aufloesen("vorgang", blockierer_id) or str(blockierer_id)
    if loesen:
        if not besteht:
            return False
        await api_verknuepfung_loesen(z, f"/api/vorgaenge/{id_}/abhaengigkeiten/{blockierer_id}")
        aktion.rueckweg_hinzu(operation("POST", f"/api/vorgaenge/{id_}/abhaengigkeiten", {"blockiert_von_id": str(blockierer_id)}))
        await _link_aenderung(aktion, namen, "vorgang", id_, label, "blockiert_von", "Blockiert von", blockierer, None)
    else:
        if besteht:
            return False
        await api_post(z, f"/api/vorgaenge/{id_}/abhaengigkeiten", {"blockiert_von_id": str(blockierer_id)})
        aktion.rueckweg_hinzu(operation("DELETE", f"/api/vorgaenge/{id_}/abhaengigkeiten/{blockierer_id}"))
        await _link_aenderung(aktion, namen, "vorgang", id_, label, "blockiert_von", "Blockiert von", None, blockierer)
    aktion.ziel("vorgang", id_, label)
    return True


async def _kontakt_zuordnen(z, aktion, namen, kontakt_id, mit_typ, mit_id, loesen) -> bool:
    basis = f"/api/{_ZIEL_PFAD[mit_typ]}/{mit_id}/vor-ort-kontakte"
    liste = await api_get(z, basis)
    vorhanden = next((e for e in liste if str(e["kontakt"]["id"]) == str(kontakt_id) and e["herkunft"] == mit_typ), None)
    ziel_label = await namen.aufloesen(mit_typ, mit_id) or str(mit_id)
    if loesen:
        if vorhanden is None:
            return False
        kontakt = vorhanden["kontakt"]
        label = kontakt.get("name") or kontakt.get("telefon") or "Kontakt"
        await api_verknuepfung_loesen(z, f"/api/vor-ort-kontakt-zuordnungen/{vorhanden['zuordnung_id']}")
        aktion.rueckweg_hinzu(
            operation("POST", basis, {"kontakt_id": str(kontakt_id), "ist_hauptkontakt": bool(vorhanden["ist_hauptkontakt"])})
        )
        await _link_aenderung(aktion, namen, "kontakt_vor_ort", kontakt_id, label, "zuordnung", f"Zugeordnet zu {mit_typ.capitalize()}", ziel_label, None)
    else:
        if vorhanden is not None:
            return False
        neu = await api_post(z, basis, {"kontakt_id": str(kontakt_id)})
        kontakt = neu["kontakt"]
        label = kontakt.get("name") or kontakt.get("telefon") or "Kontakt"
        aktion.rueckweg_hinzu(operation("DELETE", f"/api/vor-ort-kontakt-zuordnungen/{neu['zuordnung_id']}"))
        await _link_aenderung(aktion, namen, "kontakt_vor_ort", kontakt_id, label, "zuordnung", f"Zugeordnet zu {mit_typ.capitalize()}", None, ziel_label)
    aktion.ziel("kontakt_vor_ort", kontakt_id, label)
    return True


def _satz(n: int, objekt_typ: str, mit_typ: str, ziel_label: str, loesen: bool) -> str:
    if objekt_typ == "kontakt_vor_ort":
        nomen = _PLURAL["kontakt_vor_ort"][0 if n == 1 else 1]
    else:
        nomen = _PLURAL.get(objekt_typ, (objekt_typ.capitalize(),) * 2)[0 if n == 1 else 1]
    ziel_nomen = {"vorgang": "Vorgang", "auftrag": "Auftrag", "projekt": "Projekt", "anlage": "Anlage"}[mit_typ]
    if mit_typ == "vorgang" and objekt_typ == "vorgang":
        return f"{n} {nomen} {'nicht mehr ' if loesen else ''}blockiert von Vorgang {ziel_label}"
    if loesen:
        return f"{n} {nomen} von {ziel_nomen} {ziel_label} gelöst"
    return f"{n} {nomen} mit {ziel_nomen} {ziel_label} verknüpft"


async def verknuepfen_ausfuehren(
    z: KiAccessToken, objekt_typ: str, objekt_ids: list[str], mit_typ: str, mit_id: str, loesen: bool
) -> dict[str, Any]:
    if (objekt_typ, mit_typ) not in _UNTERSTUETZT:
        raise ToolError(f"Diese Kombination gibt es nicht. Möglich: {_KOMBINATIONEN}.")
    ids = list(dict.fromkeys(objekt_ids))
    if not 1 <= len(ids) <= 50:
        raise ToolError("objekt_ids braucht 1 bis 50 IDs.")
    if objekt_typ == mit_typ == "vorgang" and mit_id in ids:
        raise ToolError("Ein Vorgang kann sich nicht selbst blockieren.")
    namen = Namen(z)
    aktion = Aktion(z, tool="verknuepfen", aktionsart=f"{objekt_typ}.{'entknuepfen' if loesen else 'verknuepfen'}", stufe=2)
    ziel_label = await namen.aufloesen(mit_typ, mit_id)
    if ziel_label is None:
        raise ToolError(f"Nicht gefunden: {mit_typ.capitalize()} {mit_id} existiert nicht oder ist für dich nicht sichtbar.")
    aktion.ziel(mit_typ, mit_id, ziel_label)
    erledigt = 0
    unveraendert = 0
    fehler: str | None = None
    with aktion:
        for i, id_ in enumerate(ids):
            try:
                if (objekt_typ, mit_typ) in _FELD_FUER_ZIEL:
                    geaendert = await _feld_verknuepfen(z, aktion, namen, objekt_typ, id_, mit_typ, mit_id, loesen)
                elif mit_typ == "anlage":
                    geaendert = await _anlage_verknuepfen(z, aktion, namen, id_, mit_id, loesen)
                elif objekt_typ == "vorgang" and mit_typ == "vorgang":
                    geaendert = await _abhaengigkeit(z, aktion, namen, id_, mit_id, loesen)
                else:
                    geaendert = await _kontakt_zuordnen(z, aktion, namen, id_, mit_typ, mit_id, loesen)
            except ToolError as exc:
                if erledigt == 0:
                    raise
                rest = ids[i:]
                fehler = f"Abgebrochen bei {id_}: {exc} Nicht bearbeitet: {', '.join(rest)}."
                break
            if geaendert:
                erledigt += 1
            else:
                unveraendert += 1
    if erledigt == 0:
        return {
            "aktion_id": None,
            "zusammenfassung": "Nichts zu tun: Die Verknüpfung besteht bereits" if not loesen else "Nichts zu tun: Es gab keine solche Verknüpfung.",
            "aenderungen": [],
            "erzeugt": [],
            "link": app_link(mit_typ, mit_id),
            "rueckgaengig_bis": None,
        }
    zusammenfassung = _satz(erledigt, objekt_typ, mit_typ, ziel_label, loesen)
    if unveraendert:
        zusammenfassung += f" ({unveraendert} schon so)"
    return await aktion.fertig(zusammenfassung, link=app_link(mit_typ, mit_id), fehler=fehler)


# --- Tools -------------------------------------------------------------------------------------------------------


def registrieren(mcp: MCPServer) -> None:
    meta = ui_meta(AENDERUNG_URI)

    @mcp.tool(
        name="vorgang_speichern",
        title="Vorgang anlegen oder ändern",
        description=(
            "Legt einen Vorgang (Ticket/Einsatz, nicht die Entität Auftrag) an (ohne id) oder ändert ihn (mit id). "
            "Anlegen: kunde_id, titel und leistungstyp sind Pflicht; Status „neu“, abrechnungsart Standard aufwand. "
            "Ändern: nur die übergebenen Felder werden geändert; zum Leeren eines Felds felder_leeren nutzen "
            "(z. B. [\"faelligkeit_am\"] oder [\"zugewiesener_user_id\"]). zugewiesener_user_id ist die User-ID des "
            "Mitarbeiters (lesen(typ=\"ich\") zeigt dich selbst; andere Mitarbeiter findet suchen/die App). Status nur "
            "neu, geplant, in_arbeit oder wartet_kunde (wiedervorlage_tage nur zusammen mit wartet_kunde); Abschließen "
            "und Stornieren macht der Mensch in der App. Auftrag/Projekt zuordnen: verknuepfen." + _RUECKGAENGIG + _NUR_SCHREIBZUGRIFF
        ),
        annotations=AENDERND,
        meta=meta,
    )
    async def vorgang_speichern(
        id: Annotated[str | None, Field(description="Vorgang-ID zum Ändern; ohne id wird angelegt.")] = None,
        kunde_id: Annotated[str | None, Field(description="Kunde (ID); Pflicht beim Anlegen.")] = None,
        titel: Annotated[str | None, Field(min_length=1, max_length=200)] = None,
        beschreibung: Annotated[str | None, Field(max_length=4000)] = None,
        leistungstyp: Annotated[
            Literal["installation", "pruefung", "wartung", "stoerung", "beratung", "planung"] | None,
            Field(description="Art der Leistung; Pflicht beim Anlegen."),
        ] = None,
        abrechnungsart: Annotated[
            Literal["pauschale", "aufwand", "festpreis", "wartungsvertrag", "gewaehrleistung"] | None, Field()
        ] = None,
        prioritaet: Annotated[int | None, Field(ge=1, le=5, description="1 = höchste, 5 = niedrigste.")] = None,
        anlage_id: Annotated[str | None, Field(description="Hauptanlage (ID).")] = None,
        standort_id: Annotated[str | None, Field(description="Standort (ID).")] = None,
        faelligkeit_am: Annotated[datetime | None, Field(description="Fälligkeit (ISO-Datum/Zeit).")] = None,
        zugewiesener_user_id: Annotated[str | None, Field(description="Zuständiger Mitarbeiter (User-ID).")] = None,
        status: Annotated[str | None, Field(description="neu, geplant, in_arbeit oder wartet_kunde.")] = None,
        wiedervorlage_tage: Annotated[int | None, Field(gt=0, description="Nur mit status=wartet_kunde: Tage bis zur Wiedervorlage.")] = None,
        felder_leeren: _Leeren = None,
    ) -> dict[str, Any]:
        z = zugriff(SCOPE_SCHREIBEN)
        if status is not None and status not in ("neu", "geplant", "in_arbeit", "wartet_kunde"):
            if status in ("abgeschlossen", "storniert", "abgerechnet"):
                raise ToolError("Abschließen/Stornieren per Claude kommt mit der nächsten Ausbaustufe; bitte in der App.")
            raise ToolError("Status muss neu, geplant, in_arbeit oder wartet_kunde sein.")
        werte = _werte(
            kunde_id=kunde_id,
            titel=titel,
            beschreibung=beschreibung,
            leistungstyp=leistungstyp,
            abrechnungsart=abrechnungsart,
            prioritaet=prioritaet,
            anlage_id=anlage_id,
            standort_id=standort_id,
            faelligkeit_am=faelligkeit_am,
            zugewiesener_user_id=zugewiesener_user_id,
            status=status,
            wiedervorlage_tage=wiedervorlage_tage,
        )
        return await speichern(z, ARTEN["vorgang"], tool="vorgang_speichern", id_=id, werte=werte, leeren=felder_leeren)

    @mcp.tool(
        name="auftrag_speichern",
        title="Auftrag anlegen oder ändern",
        description=(
            "Legt einen Auftrag an (ohne id) oder ändert ihn (mit id). Ein Auftrag ist die übergeordnete Entität, die "
            "mehrere Vorgänge bündelt (nicht der Vorgang selbst). Pflicht beim Anlegen: titel. Status nur offen oder "
            "in_arbeit; Abschließen/Stornieren in der App. Vorgänge zuordnen: verknuepfen. Nicht übergebene Felder "
            "bleiben beim Ändern unverändert, Leeren mit felder_leeren." + _RUECKGAENGIG + _NUR_SCHREIBZUGRIFF
        ),
        annotations=AENDERND,
        meta=meta,
    )
    async def auftrag_speichern(
        id: Annotated[str | None, Field(description="Auftrag-ID zum Ändern; ohne id wird angelegt.")] = None,
        titel: Annotated[str | None, Field(min_length=1, max_length=200)] = None,
        beschreibung: Annotated[str | None, Field(max_length=4000)] = None,
        kunde_id: Annotated[str | None, Field(description="Kunde (ID).")] = None,
        projekt_id: Annotated[str | None, Field(description="Projekt (ID); für Zuordnungen bevorzugt verknuepfen.")] = None,
        standort_id: Annotated[str | None, Field(description="Standort (ID).")] = None,
        einheit: Annotated[str | None, Field(max_length=100, description="Einheit/Wohnung vor Ort.")] = None,
        kunden_referenz: Annotated[str | None, Field(max_length=200, description="Ihr Zeichen/Bestellnummer des Kunden.")] = None,
        status: Annotated[Literal["offen", "in_arbeit"] | None, Field(description="offen oder in_arbeit.")] = None,
        felder_leeren: _Leeren = None,
    ) -> dict[str, Any]:
        z = zugriff(SCOPE_SCHREIBEN)
        werte = _werte(
            titel=titel, beschreibung=beschreibung, kunde_id=kunde_id, projekt_id=projekt_id, standort_id=standort_id,
            einheit=einheit, kunden_referenz=kunden_referenz, status=status,
        )
        return await speichern(z, ARTEN["auftrag"], tool="auftrag_speichern", id_=id, werte=werte, leeren=felder_leeren)

    @mcp.tool(
        name="projekt_speichern",
        title="Projekt anlegen oder ändern",
        description=(
            "Legt ein Projekt (Kanban/Zeitplan mit Aufgaben, Aufträgen und Vorgängen) an (ohne id) oder ändert es "
            "(mit id). Pflicht beim Anlegen: name. Archivieren und Löschen macht der Mensch in der App. Nicht "
            "übergebene Felder bleiben beim Ändern unverändert, Leeren mit felder_leeren." + _RUECKGAENGIG + _NUR_SCHREIBZUGRIFF
        ),
        annotations=AENDERND,
        meta=meta,
    )
    async def projekt_speichern(
        id: Annotated[str | None, Field(description="Projekt-ID zum Ändern; ohne id wird angelegt.")] = None,
        name: Annotated[str | None, Field(min_length=1, max_length=200)] = None,
        beschreibung: Annotated[str | None, Field(max_length=4000)] = None,
        kunde_id: Annotated[str | None, Field(description="Auftraggeber (Kunde-ID).")] = None,
        standort_id: Annotated[str | None, Field(description="Standort (ID).")] = None,
        felder_leeren: _Leeren = None,
    ) -> dict[str, Any]:
        z = zugriff(SCOPE_SCHREIBEN)
        werte = _werte(name=name, beschreibung=beschreibung, kunde_id=kunde_id, standort_id=standort_id)
        return await speichern(z, ARTEN["projekt"], tool="projekt_speichern", id_=id, werte=werte, leeren=felder_leeren)

    @mcp.tool(
        name="aufgabe_speichern",
        title="Aufgabe anlegen oder ändern",
        description=(
            "Legt eine Aufgabe an (ohne id) oder ändert sie (mit id): Aufgaben eines Projekts (Kanban) und „Meine "
            "Aufgaben“ (ohne Projekt, dann ist sie dir zugewiesen). Pflicht beim Anlegen: titel. Eine Aufgabe hängt "
            "an einem Vorgang ODER einem Auftrag, nicht an beiden. erledigt=true hakt sie ab. Löschen macht der Mensch "
            "in der App. Nicht übergebene Felder bleiben unverändert, Leeren mit felder_leeren." + _RUECKGAENGIG + _NUR_SCHREIBZUGRIFF
        ),
        annotations=AENDERND,
        meta=meta,
    )
    async def aufgabe_speichern(
        id: Annotated[str | None, Field(description="Aufgaben-ID zum Ändern; ohne id wird angelegt.")] = None,
        titel: Annotated[str | None, Field(min_length=1, max_length=200)] = None,
        beschreibung: Annotated[str | None, Field(max_length=4000)] = None,
        projekt_id: Annotated[str | None, Field(description="Projekt (ID).")] = None,
        spalte_id: Annotated[str | None, Field(description="Kanban-Spalte des Projekts (ID).")] = None,
        faelligkeit_am: Annotated[date | None, Field(description="Fälligkeit, Datum JJJJ-MM-TT.")] = None,
        prioritaet: Annotated[Literal["niedrig", "mittel", "hoch"] | None, Field()] = None,
        zugewiesen_an: Annotated[str | None, Field(description="Zuständiger Mitarbeiter (User-ID).")] = None,
        erledigt: Annotated[bool | None, Field(description="true = erledigt, false = wieder offen.")] = None,
        vorgang_id: Annotated[str | None, Field(description="Verknüpfter Vorgang (ID).")] = None,
        auftrag_id: Annotated[str | None, Field(description="Verknüpfter Auftrag (ID).")] = None,
        felder_leeren: _Leeren = None,
    ) -> dict[str, Any]:
        z = zugriff(SCOPE_SCHREIBEN)
        werte = _werte(
            titel=titel, beschreibung=beschreibung, projekt_id=projekt_id, spalte_id=spalte_id, faelligkeit_am=faelligkeit_am,
            prioritaet=prioritaet, zugewiesen_an=zugewiesen_an, erledigt=erledigt, vorgang_id=vorgang_id, auftrag_id=auftrag_id,
        )
        if "vorgang_id" in werte and "auftrag_id" in werte:
            raise ToolError("Eine Aufgabe hängt entweder an einem Vorgang oder an einem Auftrag, nicht an beiden.")
        return await speichern(z, ARTEN["aufgabe"], tool="aufgabe_speichern", id_=id, werte=werte, leeren=felder_leeren)

    @mcp.tool(
        name="termin_speichern",
        title="Termin anlegen oder verschieben",
        description=(
            "Legt einen Termin der Dispo an (ohne id) oder ändert ihn (mit id): verschieben (start_at/ende_at), "
            "umbesetzen (techniker_id), Titel, Notiz, Fahr-/Pausenzeit, status geplant oder bestätigt. Pflicht beim "
            "Anlegen: vorgang_id, techniker_id, titel, start_at, ende_at. Absagen/Abschließen und Löschen macht der "
            "Mensch in der App. Die Antwort nennt Warnungen (z. B. Überschneidung mit anderen Terminen des "
            "Technikers). Braucht das Modul Dispo." + _RUECKGAENGIG + _NUR_SCHREIBZUGRIFF
        ),
        annotations=AENDERND,
        meta=meta,
    )
    async def termin_speichern(
        id: Annotated[str | None, Field(description="Termin-ID zum Ändern; ohne id wird angelegt.")] = None,
        vorgang_id: Annotated[str | None, Field(description="Vorgang (ID); nur beim Anlegen.")] = None,
        techniker_id: Annotated[str | None, Field(description="Techniker (User-ID).")] = None,
        titel: Annotated[str | None, Field(min_length=1, max_length=200)] = None,
        start_at: Annotated[datetime | None, Field(description="Beginn (ISO 8601 mit Zeitzone).")] = None,
        ende_at: Annotated[datetime | None, Field(description="Ende (ISO 8601 mit Zeitzone).")] = None,
        notiz: Annotated[str | None, Field(max_length=4000)] = None,
        fahrzeit_minuten: Annotated[int | None, Field(ge=0)] = None,
        pause_minuten: Annotated[int | None, Field(ge=0)] = None,
        status: Annotated[Literal["geplant", "bestaetigt"] | None, Field()] = None,
        felder_leeren: _Leeren = None,
    ) -> dict[str, Any]:
        z = zugriff(SCOPE_SCHREIBEN)
        werte = _werte(
            vorgang_id=vorgang_id, techniker_id=techniker_id, titel=titel, start_at=start_at, ende_at=ende_at, notiz=notiz,
            fahrzeit_minuten=fahrzeit_minuten, pause_minuten=pause_minuten, status=status,
        )
        if id is not None and "vorgang_id" in werte:
            raise ToolError("Der Vorgang eines Termins lässt sich nicht ändern; lege bei Bedarf einen neuen Termin an.")
        return await speichern(z, ARTEN["termin"], tool="termin_speichern", id_=id, werte=werte, leeren=felder_leeren)

    @mcp.tool(
        name="kunde_speichern",
        title="Kunde, Standort oder Kontakt vor Ort anlegen/ändern",
        description=(
            "Legt Stammdaten an (ohne id) oder ändert sie (mit id); art wählt, was: kunde (name, typ, adresse, notiz), "
            "standort (Betriebsstätte eines Kunden: kunde_id, bezeichnung, adresse, aktiv) oder kontakt_vor_ort "
            "(Mieter, Bauherr, Hausmeister … am Einsatzort: kunde_id, rolle, name oder telefon, einheit, email, hinweis). "
            "Pflicht beim Anlegen: kunde: name; standort: kunde_id und bezeichnung; kontakt_vor_ort: kunde_id, rolle und "
            "name oder telefon. Beim Ändern eines kontakt_vor_ort ist kunde_id nötig (suchen liefert sie). Keine "
            "Bank-, Portal- oder Rechtedaten, kein Löschen. Kontakte einem Vorgang zuordnen: verknuepfen. Nicht "
            "übergebene Felder bleiben unverändert, Leeren mit felder_leeren." + _RUECKGAENGIG + _NUR_SCHREIBZUGRIFF
        ),
        annotations=AENDERND,
        meta=meta,
    )
    async def kunde_speichern(
        art: Annotated[Literal["kunde", "standort", "kontakt_vor_ort"], Field(description="Was gespeichert wird.")],
        id: Annotated[str | None, Field(description="ID zum Ändern; ohne id wird angelegt.")] = None,
        kunde_id: Annotated[str | None, Field(description="Kunde (ID): bei standort und kontakt_vor_ort der Auftraggeber.")] = None,
        name: Annotated[str | None, Field(min_length=1, max_length=200, description="Kunde: Firmen-/Personenname; Kontakt: Name.")] = None,
        typ: Annotated[Literal["privat", "gewerbe", "oeffentlich", "hausverwaltung"] | None, Field(description="Nur kunde.")] = None,
        adresse: Annotated[Adresse | None, Field(description="Nur kunde und standort.")] = None,
        notiz: Annotated[str | None, Field(max_length=4000, description="Nur kunde.")] = None,
        bezeichnung: Annotated[str | None, Field(min_length=1, max_length=200, description="Nur standort.")] = None,
        aktiv: Annotated[bool | None, Field(description="Nur standort.")] = None,
        standort_id: Annotated[str | None, Field(description="Nur kontakt_vor_ort: zugehöriger Standort (ID).")] = None,
        rolle: Annotated[
            Literal["mieter", "eigentuemer", "bauherr", "hausmeister", "nutzer", "sonstige"] | None,
            Field(description="Nur kontakt_vor_ort."),
        ] = None,
        einheit: Annotated[str | None, Field(max_length=100, description="Nur kontakt_vor_ort: Wohnung/Einheit.")] = None,
        telefon: Annotated[str | None, Field(max_length=50, description="Nur kontakt_vor_ort.")] = None,
        telefon2: Annotated[str | None, Field(max_length=50, description="Nur kontakt_vor_ort.")] = None,
        email: Annotated[str | None, Field(max_length=200, description="Nur kontakt_vor_ort.")] = None,
        erreichbarkeit: Annotated[str | None, Field(max_length=200, description="Nur kontakt_vor_ort.")] = None,
        hinweis: Annotated[str | None, Field(max_length=1000, description="Nur kontakt_vor_ort.")] = None,
        felder_leeren: _Leeren = None,
    ) -> dict[str, Any]:
        z = zugriff(SCOPE_SCHREIBEN)
        je_art = {
            "kunde": {"name": name, "typ": typ, "adresse": adresse, "notiz": notiz},
            "standort": {"bezeichnung": bezeichnung, "adresse": adresse, "aktiv": aktiv},
            "kontakt_vor_ort": {
                "standort_id": standort_id, "name": name, "rolle": rolle, "einheit": einheit, "telefon": telefon,
                "telefon2": telefon2, "email": email, "erreichbarkeit": erreichbarkeit, "hinweis": hinweis,
            },
        }
        gegeben = {
            "name": name, "typ": typ, "adresse": adresse, "notiz": notiz, "bezeichnung": bezeichnung, "aktiv": aktiv,
            "standort_id": standort_id, "rolle": rolle, "einheit": einheit, "telefon": telefon, "telefon2": telefon2,
            "email": email, "erreichbarkeit": erreichbarkeit, "hinweis": hinweis,
        }
        fremd = [f for f, v in gegeben.items() if v is not None and f not in je_art[art]]
        if fremd:
            raise ToolError(f"Für art={art} gibt es diese Felder nicht: {', '.join(fremd)}. Möglich: {', '.join(je_art[art])}.")
        werte = _werte(**je_art[art])
        if art == "standort" and id is None and kunde_id:
            werte["kunde_id"] = kunde_id
        return await speichern(
            z,
            ARTEN[art],
            tool="kunde_speichern",
            id_=id,
            werte=werte,
            leeren=felder_leeren,
            kunde_id=kunde_id if art == "kontakt_vor_ort" else None,
        )

    @mcp.tool(
        name="verknuepfen",
        title="Datensätze verknüpfen oder lösen",
        description=(
            "Verknüpft einen oder mehrere (bis 50) Datensätze mit einem Ziel, z. B. Vorgänge mit einem Auftrag "
            "(objekt_typ=\"vorgang\", mit_typ=\"auftrag\"). Mögliche Kombinationen: " + _KOMBINATIONEN + ". "
            "Beim Auftrag bestimmt dieser das Projekt des Vorgangs. Vorgang -> Vorgang heißt „blockiert von“ (mit_id ist "
            "der blockierende Vorgang). loesen=true entfernt die Verknüpfung wieder (Zuordnungsfeld wird leer; der "
            "Datensatz selbst bleibt). Wird nacheinander ausgeführt; bei einem Fehler stoppt es, das Bisherige bleibt "
            "bestehen und ist im Journal. Vorgänge, die in der App „eigenständig“ geführt werden, lassen sich nicht "
            "umhängen." + _RUECKGAENGIG + _NUR_SCHREIBZUGRIFF
        ),
        annotations=AENDERND,
        meta=meta,
    )
    async def verknuepfen(
        objekt_typ: Annotated[Literal["vorgang", "auftrag", "kontakt_vor_ort"], Field(description="Art der zu verknüpfenden Datensätze.")],
        objekt_ids: Annotated[list[str], Field(min_length=1, max_length=50, description="IDs der Datensätze.")],
        mit_typ: Annotated[Literal["auftrag", "projekt", "anlage", "vorgang"], Field(description="Art des Ziels.")],
        mit_id: Annotated[str, Field(description="ID des Ziels.")],
        loesen: Annotated[bool, Field(description="true: Verknüpfung entfernen statt herstellen.")] = False,
    ) -> dict[str, Any]:
        z = zugriff(SCOPE_SCHREIBEN)
        return await verknuepfen_ausfuehren(z, objekt_typ, objekt_ids, mit_typ, mit_id, loesen)
