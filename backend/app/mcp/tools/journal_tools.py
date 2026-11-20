"""rueckgaengig: nimmt eine KI-Aktion aus dem Journal zurueck (gleicher Service wie die Seite KI-Aktivitaet)."""
from typing import Annotated, Any
from uuid import UUID

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field
from sqlalchemy import select

from app.db.session import tenant_session
from app.mcp.rest_client import _aufruf_token
from app.mcp.tools._basis import AENDERND, zugriff
from app.mcp.zugang import SCOPE_SCHREIBEN
from app.models.ki_aktion import KiAktion
from app.services.ki_rueckgaengig import RueckgaengigAbgelehnt, rueckgaengig

SCHREIB_TOOLS = frozenset({"rueckgaengig"})


def registrieren(mcp: MCPServer) -> None:
    @mcp.tool(
        name="rueckgaengig",
        title="KI-Aktion rückgängig machen",
        description=(
            "Nimmt eine frühere Änderung von Claude zurück (aktion_id steht in der Antwort des Schreib-Tools und in "
            "FieldVibe unter KI-Aktivität). Möglich 7 Tage lang, für eigene Aktionen (Administratoren auch für andere) "
            "und nur, solange niemand die betroffenen Felder seitdem geändert hat; sonst passiert nichts und die "
            "Antwort nennt die Abweichungen. Angelegte Datensätze werden dabei in den Papierkorb verschoben, "
            "geänderte Werte wiederhergestellt. Nicht zurücknehmbar sind z. B. Kommentare. (nur mit Schreibzugriff)"
        ),
        annotations=AENDERND,
    )
    async def rueckgaengig_tool(
        aktion_id: Annotated[str, Field(description="ID der Aktion (aktion_id aus der Antwort des Schreib-Tools).")],
    ) -> dict[str, Any]:
        z = zugriff(SCOPE_SCHREIBEN)
        try:
            uuid = UUID(aktion_id)
        except ValueError as exc:
            raise ToolError("aktion_id ist keine gültige ID.") from exc
        try:
            await rueckgaengig(
                mandant_id=z.mandant_id,
                user_id=z.user_id,
                ist_admin=z.role == "mandant_admin",
                aktion_id=uuid,
                token=_aufruf_token(z),
                ausloeser="mcp",
            )
        except RueckgaengigAbgelehnt as exc:
            raise ToolError(exc.meldung) from exc
        async with tenant_session(mandant_id=z.mandant_id) as session:
            zusammenfassung = (await session.execute(select(KiAktion.zusammenfassung).where(KiAktion.id == uuid))).scalar_one_or_none()
        return {
            "aktion_id": aktion_id,
            "status": "rueckgaengig",
            "zusammenfassung": f"Rückgängig gemacht: {zusammenfassung}" if zusammenfassung else "Rückgängig gemacht.",
        }

