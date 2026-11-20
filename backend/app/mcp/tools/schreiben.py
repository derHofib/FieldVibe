"""Schreib-Tools (Scope fieldvibe.schreiben + Recht ki_zugriff.bearbeiten): Kommentar, Mangel und Telefonat anlegen.
Vorgaenge und andere Stammdaten legt stammdaten.py an. Alles laeuft ueber die bestehenden Routen (im Verlauf "via
Claude", im Audit-Log quelle=ki) und steht im KI-Journal; Mangel und Telefonat lassen sich zuruecknehmen, ein
Kommentar nicht (Verlaufseintraege sind unveraenderlich)."""
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from app.mcp.ansichten import AENDERUNG_URI, ui_meta
from app.mcp.anzeige import Namen, app_link
from app.mcp.journal import Aktion, operation, pruefung
from app.mcp.rest_client import api_get, api_post
from app.mcp.tools._basis import NUR_ADDITIV, zugriff
from app.mcp.zugang import SCOPE_SCHREIBEN

# Nur mit Schreib-Scope sichtbar (server.py filtert die Tool-Liste, die Pruefung je Aufruf bleibt).
SCHREIB_TOOLS = frozenset({"kommentar_anlegen", "mangel_erfassen", "telefonat_erfassen"})

_Id = Annotated[str, Field(description="ID (UUID), z. B. aus der Suche oder einer Liste.")]
_NUR_SCHREIBZUGRIFF = " (nur mit Schreibzugriff)"


def registrieren(mcp: MCPServer) -> None:
    @mcp.tool(
        name="kommentar_anlegen",
        title="Kommentar anlegen",
        description=(
            "Legt einen internen Kommentar (Besprechungs-/Einsatznotiz) im Verlauf eines Vorgangs an (ziel_typ "
            "„vorgang“; Aufträge, Projekte und Kunden haben in FieldVibe keinen Kommentar-Verlauf). Er erscheint dort "
            "mit dem Hinweis „via Claude“, ist nicht für den Kunden sichtbar und kann nicht per KI geändert, gelöscht "
            "oder zurückgenommen werden. @-Erwähnungen wirken wie in der App. Geht nicht bei abgeschlossenen "
            "Vorgängen." + _NUR_SCHREIBZUGRIFF
        ),
        annotations=NUR_ADDITIV,
        meta=ui_meta(AENDERUNG_URI),
    )
    async def kommentar_anlegen(
        ziel_id: Annotated[str, Field(description="ID des Vorgangs, an den der Kommentar kommt.")],
        text: Annotated[str, Field(min_length=1, max_length=4000, description="Text des Kommentars.")],
        ziel_typ: Annotated[Literal["vorgang"], Field(description="Derzeit nur vorgang.")] = "vorgang",
    ) -> dict[str, Any]:
        z = zugriff(SCOPE_SCHREIBEN)
        aktion = Aktion(z, tool="kommentar_anlegen", aktionsart="kommentar.anlegen", stufe=1)
        with aktion:
            ereignis = await api_post(
                z,
                f"/api/vorgaenge/{ziel_id}/events",
                {"event_type": "kommentar", "body": text, "kundensichtbar": False},
            )
            label = await Namen(z).aufloesen("vorgang", ziel_id) or str(ziel_id)
            aktion.ziel("vorgang", ziel_id, label)
            aktion.neu_erzeugt("kommentar", ereignis["id"], "Kommentar")
        antwort = await aktion.fertig(f"Kommentar an Vorgang {label} angelegt", link=app_link("vorgang", ziel_id))
        antwort["id"] = ereignis["id"]
        antwort["vorgang_id"] = ereignis["vorgang_id"]
        antwort["hinweis"] = "Kommentar angelegt (im Verlauf als „via Claude“ gekennzeichnet); er lässt sich nicht zurücknehmen."
        return antwort

    @mcp.tool(
        name="mangel_erfassen",
        title="Mangel erfassen",
        description=(
            "Erfasst einen Mangel (Defekt) zu einem Vorgang, optional mit Anlage. Der Mangel startet "
            "im Status „offen“; Angebot, Reparatur und Statuswechsel macht das Büro in der App. "
            "Benötigt das Modul Abrechnung." + _NUR_SCHREIBZUGRIFF
        ),
        annotations=NUR_ADDITIV,
        meta=ui_meta(AENDERUNG_URI),
    )
    async def mangel_erfassen(
        vorgang_id: _Id,
        beschreibung: Annotated[str, Field(min_length=1, max_length=2000, description="Was ist defekt/mangelhaft?")],
        schweregrad: Annotated[
            Literal["kritisch", "hoch", "mittel", "niedrig"],
            Field(description="Schweregrad, Standard mittel."),
        ] = "mittel",
        anlage_id: Annotated[str | None, Field(description="Betroffene Anlage (muss zum Vorgang gehören).")] = None,
    ) -> dict[str, Any]:
        z = zugriff(SCOPE_SCHREIBEN)
        aktion = Aktion(z, tool="mangel_erfassen", aktionsart="mangel.anlegen", stufe=1)
        with aktion:
            mangel = await api_post(
                z,
                "/api/maengel",
                {
                    "vorgang_id": vorgang_id,
                    "beschreibung": beschreibung,
                    "schweregrad": schweregrad,
                    "anlage_id": anlage_id,
                },
            )
            label = await Namen(z).aufloesen("vorgang", vorgang_id) or str(vorgang_id)
            aktion.ziel("vorgang", vorgang_id, label)
            aktion.neu_erzeugt("mangel", mangel["id"], beschreibung[:80])
            # Zurueck nur, solange der Mangel noch genau so dasteht (Status/Angebot macht das Buero).
            aktion.rueckweg_hinzu(
                operation(
                    "DELETE",
                    f"/api/maengel/{mangel['id']}",
                    None,
                    [
                        pruefung(f"/api/maengel/{mangel['id']}", "updated_at", mangel["updated_at"], label=beschreibung[:80], feld_label="Zuletzt geändert"),
                    ],
                )
            )
        antwort = await aktion.fertig(f"Mangel zu Vorgang {label} erfasst ({schweregrad})", link=app_link("mangel", mangel["id"], mangel))
        antwort.update(id=mangel["id"], vorgang_id=mangel["vorgang_id"], schweregrad=mangel["schweregrad"], status=mangel["status"])
        return antwort

    @mcp.tool(
        name="telefonat_erfassen",
        title="Telefonat erfassen",
        description=(
            "Erfasst ein Telefonat zu einem Vorgang oder direkt zu einem Kunden (z. B. nach einer Sprachnotiz "
            "oder Zusammenfassung). Es erscheint am Vorgang im Verlauf bzw. im Kontaktverlauf des Kunden mit "
            "dem Hinweis „via Claude“ und ist nie für den Kunden sichtbar. Bei Ergebnis „erreicht“ ist eine "
            "Notiz Pflicht. Optional ein Rückruf-Termin (der Erfasser wird dann erinnert). Arbeitszeit buchen "
            "und Telefonate ändern oder löschen bleibt beim Menschen in der App." + _NUR_SCHREIBZUGRIFF
        ),
        annotations=NUR_ADDITIV,
        meta=ui_meta(AENDERUNG_URI),
    )
    async def telefonat_erfassen(
        partner_name: Annotated[str, Field(min_length=1, max_length=200, description="Name des Gesprächspartners.")],
        richtung: Annotated[Literal["ausgehend", "eingehend"], Field(description="Wer hat angerufen?")],
        ergebnis: Annotated[
            Literal["erreicht", "nicht_erreicht", "mailbox"], Field(description="Ausgang des Anrufs.")
        ],
        vorgang_id: Annotated[str | None, Field(description="Vorgang (ID), zu dem das Telefonat gehört.")] = None,
        kunde_id: Annotated[
            str | None, Field(description="Kunde (ID); Pflicht, wenn kein Vorgang angegeben ist.")
        ] = None,
        partner_nummer: Annotated[str | None, Field(max_length=50, description="Telefonnummer des Partners.")] = None,
        beginn: Annotated[datetime | None, Field(description="Beginn des Gesprächs (ISO 8601); Standard: jetzt.")] = None,
        dauer_minuten: Annotated[
            int | None, Field(ge=0, le=1440, description="Gesprächsdauer in Minuten (nur bei „erreicht“).")
        ] = None,
        notiz: Annotated[
            str | None, Field(max_length=10000, description="Gesprächsnotiz; Pflicht bei Ergebnis „erreicht“.")
        ] = None,
        rueckruf_am: Annotated[
            datetime | None, Field(description="Rückruf-Termin (ISO 8601); der Erfasser wird dann erinnert.")
        ] = None,
    ) -> dict[str, Any]:
        z = zugriff(SCOPE_SCHREIBEN)
        if not vorgang_id and not kunde_id:
            raise ToolError("Bitte vorgang_id oder kunde_id angeben.")
        aktion = Aktion(z, tool="telefonat_erfassen", aktionsart="telefonat.anlegen", stufe=1)
        with aktion:
            telefonat = await api_post(
                z,
                "/api/telefonate",
                {
                    "vorgang_id": vorgang_id or None,
                    "kunde_id": kunde_id or None,
                    "partner_name": partner_name,
                    "partner_nummer": partner_nummer,
                    "richtung": richtung,
                    "ergebnis": ergebnis,
                    "beginn": (beginn or datetime.now(timezone.utc)).isoformat(),
                    "dauer_sekunden": dauer_minuten * 60 if dauer_minuten is not None else None,
                    "notiz": notiz,
                    "rueckruf_am": rueckruf_am.isoformat() if rueckruf_am else None,
                },
            )
            label = f"Telefonat mit {partner_name}"
            aktion.neu_erzeugt("telefonat", telefonat["id"], label)
            aktion.rueckweg_hinzu(
                operation(
                    "DELETE",
                    f"/api/telefonate/{telefonat['id']}",
                    None,
                    [pruefung(f"/api/telefonate/{telefonat['id']}", "updated_at", telefonat["updated_at"], label=label, feld_label="Zuletzt geändert")],
                )
            )
        antwort = await aktion.fertig(f"{label} erfasst ({ergebnis.replace('_', ' ')})", link=app_link("telefonat", telefonat["id"]))
        antwort.update(id=telefonat["id"], vorgang_id=telefonat.get("vorgang_id"), kunde_id=telefonat.get("kunde_id"), ergebnis=telefonat["ergebnis"])
        return antwort
