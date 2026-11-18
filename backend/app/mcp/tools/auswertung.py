"""Auswertungs-Tools (Scope fieldvibe.lesen): duenne Adapter auf die vorhandenen
Auswertungs-Endpunkte, die Recht und Modul (Statistik bzw. Abrechnung) selbst pruefen."""
from datetime import date
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from app.mcp.aufbereitung import bereinigen
from app.mcp.rest_client import api_get
from app.schemas.statistik import AggregatBereich, AggregatGruppierung, AggregatKennzahl
from app.services.statistik_aggregat_service import GRUPPIERUNGEN, KENNZAHLEN
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

    kombinationen = "; ".join(
        f"Bereich {b}: Kennzahl {', '.join(KENNZAHLEN[b])} mit Gruppierung {', '.join(GRUPPIERUNGEN[b])}"
        for b in KENNZAHLEN
    )

    @mcp.tool(
        name="auswertung",
        title="Auswertung (Kennzahl nach Gruppierung)",
        description=(
            "Freie Auswertung nach fester Whitelist, z. B. Vorgänge je Monat oder Arbeitsstunden je Techniker. "
            f"Gültige Kombinationen: {kombinationen}. Der Zeitraum (von/bis, höchstens 3 Jahre) bezieht sich je "
            "Kennzahl auf ein anderes Datum (Erstellung, Abschluss, Arbeitstag, Rechnungsdatum), die Antwort nennt "
            "es im Feld datumsbezug. Filter: techniker_id, kunde_id, projekt_id, status (nur Bereich vorgaenge). "
            "Bereich rechnungen braucht Modul Abrechnung und das Recht Angebote & Rechnungen; Arbeitszeit nur "
            "für Mitarbeiter, die der Nutzer einsehen darf. Braucht das Statistik-Modul."
        ),
        annotations=NUR_LESEN,
    )
    async def auswertung(
        bereich: Annotated[AggregatBereich, Field(description="vorgaenge oder rechnungen.")],
        kennzahl: AggregatKennzahl,
        gruppierung: AggregatGruppierung,
        von: Annotated[date, Field(description="Beginn (JJJJ-MM-TT).")],
        bis: Annotated[date, Field(description="Ende (JJJJ-MM-TT), höchstens 3 Jahre nach von.")],
        techniker_id: Annotated[str | None, Field(description="Nur dieser Techniker (ID).")] = None,
        kunde_id: Annotated[str | None, Field(description="Nur dieser Kunde (ID).")] = None,
        projekt_id: Annotated[str | None, Field(description="Nur dieses Projekt (ID).")] = None,
        status: Annotated[str | None, Field(description="Nur Vorgänge mit diesem Status (nur Bereich vorgaenge).")] = None,
    ) -> dict[str, Any]:
        z = zugriff()
        return bereinigen(
            await api_get(
                z,
                "/api/statistik/aggregat",
                {
                    "bereich": bereich,
                    "kennzahl": kennzahl,
                    "gruppierung": gruppierung,
                    "von": von.isoformat(),
                    "bis": bis.isoformat(),
                    "techniker_id": techniker_id,
                    "kunde_id": kunde_id,
                    "projekt_id": projekt_id,
                    "status": status,
                },
            )
        )

    @mcp.tool(
        name="arbeitszeit_saldo",
        title="Arbeitszeit-Saldo",
        description=(
            "Soll-, Ist- und Saldo-Stunden eines Mitarbeiters im Zeitraum (höchstens 366 Tage), samt Tageswerten "
            "bis 62 Tage Zeitraum. Ohne user_id der eigene Saldo; für andere Mitarbeiter braucht der Nutzer das "
            "Recht, deren Zeiten zu verwalten."
        ),
        annotations=NUR_LESEN,
    )
    async def arbeitszeit_saldo(
        von: Annotated[date, Field(description="Beginn (JJJJ-MM-TT).")],
        bis: Annotated[date, Field(description="Ende (JJJJ-MM-TT).")],
        user_id: Annotated[str | None, Field(description="Mitarbeiter (ID); leer = eigener Saldo.")] = None,
    ) -> dict[str, Any]:
        z = zugriff()
        daten = await api_get(
            z, "/api/arbeitszeit/saldo", {"von": von.isoformat(), "bis": bis.isoformat(), "user_id": user_id}
        )
        if (bis - von).days + 1 > 62:
            daten = {k: v for k, v in daten.items() if k != "tage"}
            daten["hinweis"] = "Tageswerte nur bei Zeiträumen bis 62 Tage; engeren Zeitraum wählen."
        return bereinigen(daten)
