"""Schreib-Tools (Scope fieldvibe.schreiben + Recht ki_zugriff.bearbeiten): nur additiv und als
Entwurf. Kommentar, Mangel und neuer Vorgang (Status "neu", ohne Zuweisung -- die Disposition bleibt
beim Buero). Alles laeuft ueber die bestehenden Routen und ist dadurch im Verlauf mit "via Claude"
und im Audit-Log mit quelle=ki gekennzeichnet."""
from datetime import datetime
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from app.mcp.aufbereitung import bereinigen
from app.mcp.rest_client import api_post
from app.mcp.tools._basis import NUR_ADDITIV, zugriff
from app.mcp.zugang import SCOPE_SCHREIBEN

# Nur mit Schreib-Scope sichtbar (server.py filtert die Tool-Liste, die Pruefung je Aufruf bleibt).
SCHREIB_TOOLS = frozenset({"kommentar_anlegen", "mangel_erfassen", "vorgang_anlegen"})

_Id = Annotated[str, Field(description="ID (UUID), z. B. aus der Suche oder einer Liste.")]
_NUR_SCHREIBZUGRIFF = " (nur mit Schreibzugriff)"


def registrieren(mcp: MCPServer) -> None:
    @mcp.tool(
        name="kommentar_anlegen",
        title="Kommentar an Vorgang anlegen",
        description=(
            "Legt einen internen Kommentar (Besprechungs-/Einsatznotiz) im Verlauf eines Vorgangs an. "
            "Er erscheint dort mit dem Hinweis „via Claude“, ist nicht für den Kunden sichtbar und "
            "kann nicht per KI geändert oder gelöscht werden. @-Erwähnungen wirken wie in der App. "
            "Geht nicht bei abgeschlossenen Vorgängen." + _NUR_SCHREIBZUGRIFF
        ),
        annotations=NUR_ADDITIV,
    )
    async def kommentar_anlegen(
        vorgang_id: _Id,
        text: Annotated[str, Field(min_length=1, max_length=4000, description="Text des Kommentars.")],
    ) -> dict[str, Any]:
        z = zugriff(SCOPE_SCHREIBEN)
        ereignis = await api_post(
            z,
            f"/api/vorgaenge/{vorgang_id}/events",
            {"event_type": "kommentar", "body": text, "kundensichtbar": False},
        )
        return {
            "id": ereignis["id"],
            "vorgang_id": ereignis["vorgang_id"],
            "hinweis": "Kommentar angelegt (im Verlauf als „via Claude“ gekennzeichnet).",
        }

    @mcp.tool(
        name="mangel_erfassen",
        title="Mangel erfassen",
        description=(
            "Erfasst einen Mangel (Defekt) zu einem Vorgang, optional mit Anlage. Der Mangel startet "
            "im Status „offen“; Angebot, Reparatur und Statuswechsel macht das Büro in der App. "
            "Benötigt das Modul Abrechnung." + _NUR_SCHREIBZUGRIFF
        ),
        annotations=NUR_ADDITIV,
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
        return {
            **bereinigen({k: mangel[k] for k in ("id", "vorgang_id", "anlage_id", "schweregrad", "status")}),
            "hinweis": "Mangel erfasst (im Verlauf als „via Claude“ gekennzeichnet).",
        }

    @mcp.tool(
        name="vorgang_anlegen",
        title="Vorgang anlegen",
        description=(
            "Legt einen neuen Vorgang (Ticket/Einsatz) für einen Kunden an. Er startet im Status „neu“ "
            "und ohne Zuweisung oder Termin; die Disposition macht das Büro. leistungstyp ist Pflicht, "
            "weil davon abhängt, welche Protokoll-Vorlagen angeboten werden. abrechnungsart ist "
            "standardmäßig „aufwand“ (Abrechnung nach Aufwand) und kann im Büro angepasst werden. "
            "Der angelegte Vorgang trägt im Verlauf den Hinweis „via Claude“." + _NUR_SCHREIBZUGRIFF
        ),
        annotations=NUR_ADDITIV,
    )
    async def vorgang_anlegen(
        kunde_id: Annotated[str, Field(description="Kunde (ID), z. B. aus der Suche.")],
        titel: Annotated[str, Field(min_length=1, max_length=200, description="Kurztitel des Vorgangs.")],
        leistungstyp: Annotated[
            Literal["installation", "pruefung", "wartung", "stoerung", "beratung", "planung"],
            Field(description="Art der Leistung (Pflicht)."),
        ],
        beschreibung: Annotated[str | None, Field(max_length=4000, description="Was ist zu tun / was wurde gemeldet?")] = None,
        abrechnungsart: Annotated[
            Literal["pauschale", "aufwand", "festpreis", "wartungsvertrag", "gewaehrleistung"],
            Field(description="Standard aufwand."),
        ] = "aufwand",
        prioritaet: Annotated[int, Field(ge=1, le=5, description="1 = höchste, 5 = niedrigste, Standard 3.")] = 3,
        anlage_id: Annotated[str | None, Field(description="Betroffene Anlage (ID).")] = None,
        standort_id: Annotated[str | None, Field(description="Standort (ID).")] = None,
        faelligkeit_am: Annotated[datetime | None, Field(description="Gewünschte Fälligkeit (ISO-Datum/Zeit).")] = None,
    ) -> dict[str, Any]:
        z = zugriff(SCOPE_SCHREIBEN)
        vorgang = await api_post(
            z,
            "/api/vorgaenge",
            {
                "kunde_id": kunde_id,
                "titel": titel,
                "beschreibung": beschreibung,
                "leistungstyp": leistungstyp,
                "abrechnungsart": abrechnungsart,
                "prioritaet": prioritaet,
                "anlage_id": anlage_id,
                "standort_id": standort_id,
                "faelligkeit_am": faelligkeit_am.isoformat() if faelligkeit_am else None,
            },
        )
        return {
            **{k: vorgang[k] for k in ("id", "vorgangsnummer", "titel", "status", "leistungstyp", "abrechnungsart")},
            "hinweis": "Vorgang im Status „neu“ angelegt, ohne Zuweisung; die Disposition erfolgt im Büro.",
        }
