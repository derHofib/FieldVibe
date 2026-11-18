"""Auswertungs-Tools (Scope fieldvibe.lesen): duenne Adapter auf die vorhandenen
Auswertungs-Endpunkte, die Recht und Modul (Statistik bzw. Abrechnung) selbst pruefen."""
from datetime import date
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from app.mcp.aufbereitung import bereinigen
from app.mcp.rest_client import api_get
from app.mcp.tools._basis import zugriff
from app.mcp.tools.lesen import NUR_LESEN


def registrieren(mcp: MCPServer) -> None:
    @mcp.tool(
        name="kennzahlen_vorgaenge",
        title="Kennzahlen zu Vorgängen",
        description=(
            "Kennzahlen über Vorgänge: offene Vorgänge gesamt und je Techniker "
            "(Momentaufnahme), durchschnittliche Durchlaufzeit in Tagen und Anzahl der im "
            "Zeitraum abgeschlossenen Vorgänge. Der Zeitraum betrifft nur die abgeschlossenen "
            "Vorgänge. Braucht das Recht Statistik."
        ),
        annotations=NUR_LESEN,
    )
    async def kennzahlen_vorgaenge(
        von: Annotated[date | None, Field(description="Beginn (JJJJ-MM-TT) für die Durchlaufzeit.")] = None,
        bis: Annotated[date | None, Field(description="Ende (JJJJ-MM-TT) für die Durchlaufzeit.")] = None,
        projekt_id: Annotated[str | None, Field(description="Nur Vorgänge dieses Projekts (ID).")] = None,
    ) -> dict[str, Any]:
        z = zugriff()
        daten = await api_get(
            z,
            "/api/statistik/vorgang-kennzahlen",
            {
                "von": von.isoformat() if von else None,
                "bis": bis.isoformat() if bis else None,
                "projekt_id": projekt_id,
            },
        )
        return bereinigen(daten)

    @mcp.tool(
        name="insights",
        title="Insights (Wochenüberblick)",
        description=(
            "Betriebsüberblick (Insights): Vorgänge nach Status, offene Rechnungssumme und "
            "Verbindlichkeiten, Angebote versendet/angenommen samt Annahmequote und "
            "Auslastung der Techniker. Nur für Mandant-Admins mit aktivem Statistik-Modul."
        ),
        annotations=NUR_LESEN,
    )
    async def insights() -> dict[str, Any]:
        z = zugriff()
        return bereinigen(await api_get(z, "/api/insights"))

    @mcp.tool(
        name="offene_posten",
        title="Offene Posten",
        description=(
            "Offene Posten: Debitoren (offene Ausgangsrechnungen) und Kreditoren (offene "
            "Eingangsrechnungen) mit Summen und Alters-Staffelung (Buckets). Braucht das "
            "Modul Abrechnung und das Recht Angebote & Rechnungen."
        ),
        annotations=NUR_LESEN,
    )
    async def offene_posten() -> dict[str, Any]:
        z = zugriff()
        return bereinigen(await api_get(z, "/api/auswertung/offene-posten"))
