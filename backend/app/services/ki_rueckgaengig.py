"""Rueckgaengig einer KI-Aktion (Konzept mcp-ausbau, 3.5). Genutzt vom MCP-Tool `rueckgaengig` und von
POST /api/ki/aktionen/{id}/rueckgaengig (Seite KI-Aktivitaet).

Ablauf: Frist und Status pruefen, dann ALLE Pruefungen des Journals gegen den aktuellen Stand (ist das Feld
noch so, wie die KI es hinterlassen hat?). Gibt es eine Abweichung, passiert nichts und der Aufrufer bekommt
die Konfliktliste. Erst dann laufen die Rueckweg-Operationen in umgekehrter Reihenfolge ueber die Fachrouten
-- in-process mit den Rechten dessen, der das Rueckgaengig ausloest."""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import select

from app.db.session import tenant_session
from app.mcp.anzeige import format_wert, gleich
from app.mcp.rest_client import _anfrage_mit_token, aktion_id_var
from app.models.ki_aktion import KiAktion
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)

_NICHT_VERFUEGBAR = "nicht mehr verfügbar"


@dataclass
class Konflikt:
    label: str
    feld_label: str
    erwartet_anzeige: str | None
    aktuell_anzeige: str | None

    def als_dict(self) -> dict[str, str | None]:
        return {
            "label": self.label,
            "feld_label": self.feld_label,
            "erwartet_anzeige": self.erwartet_anzeige,
            "aktuell_anzeige": self.aktuell_anzeige,
        }


@dataclass
class RueckgaengigAbgelehnt(Exception):
    """status_code wie in der REST-API: 403 (fremd), 404, 400 (nicht mehr moeglich), 409 (Konflikt)."""

    status_code: int
    meldung: str
    konflikte: list[Konflikt] = field(default_factory=list)

    def __str__(self) -> str:
        return self.meldung


def konflikt_text(konflikte: list[Konflikt]) -> str:
    teile = [
        f"{k.label}: {k.feld_label} ist jetzt „{k.aktuell_anzeige or '—'}“ (erwartet „{k.erwartet_anzeige or '—'}“)"
        for k in konflikte
    ]
    return "; ".join(teile)


def _pruefungen(rueckweg: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ergebnis = []
    for op in rueckweg:
        p = op.get("pruefung")
        ergebnis.extend(p if isinstance(p, list) else [p] if p else [])
    return ergebnis


async def _konflikte(token: str, rueckweg: list[dict[str, Any]]) -> list[Konflikt]:
    abrufe: dict[tuple[str, str], Any] = {}
    konflikte: list[Konflikt] = []
    for p in _pruefungen(rueckweg):
        schluessel = (p["pfad"], repr(sorted((p.get("params") or {}).items())))
        if schluessel not in abrufe:
            try:
                abrufe[schluessel] = (
                    await _anfrage_mit_token(token, "GET", p["pfad"], params=p.get("params"))
                ).json()
            except ToolError:
                abrufe[schluessel] = None
        daten = abrufe[schluessel]
        if daten is not None and p.get("element"):
            feld_name, wert = p["element"]
            daten = next((e for e in daten if isinstance(e, dict) and str(e.get(feld_name)) == str(wert)), None)
        label, feld_label, erwartet = p.get("label") or "", p.get("feld_label") or p["feld"], p.get("erwartet_anzeige")
        if daten is None:
            konflikte.append(Konflikt(label, feld_label, erwartet, _NICHT_VERFUEGBAR))
            continue
        aktuell = len(daten) if p["feld"] == "#anzahl" and isinstance(daten, list) else (
            daten.get(p["feld"]) if isinstance(daten, dict) else None
        )
        if gleich(p.get("erwartet"), aktuell):
            continue
        anzeige = (daten.get(p["anzeige_feld"]) if p.get("anzeige_feld") and isinstance(daten, dict) else None) or (
            format_wert(aktuell)
        )
        if erwartet is None:
            erwartet = format_wert(p.get("erwartet"))
        konflikte.append(Konflikt(label, feld_label, erwartet, anzeige))
    return konflikte


async def rueckgaengig(
    *,
    mandant_id: UUID,
    user_id: UUID,
    ist_admin: bool,
    aktion_id: UUID,
    token: str,
    ausloeser: Literal["mcp", "app"],
) -> UUID:
    """Macht die Aktion rueckgaengig und liefert ihre ID. Wirft RueckgaengigAbgelehnt, wenn das nicht (mehr)
    geht oder die Daten seitdem veraendert wurden."""
    jetzt = datetime.now(timezone.utc)
    abbruch: RueckgaengigAbgelehnt | None = None
    async with tenant_session(mandant_id=mandant_id) as session:
        aktion = (
            await session.execute(select(KiAktion).where(KiAktion.id == aktion_id).with_for_update())
        ).scalar_one_or_none()
        if aktion is None:
            raise RueckgaengigAbgelehnt(404, "Aktion nicht gefunden.")
        if aktion.user_id != user_id and not ist_admin:
            raise RueckgaengigAbgelehnt(
                403, "Nur der Auslöser der Aktion oder ein Administrator kann sie rückgängig machen."
            )
        if aktion.status == "rueckgaengig":
            raise RueckgaengigAbgelehnt(400, "Diese Aktion wurde bereits rückgängig gemacht.")
        if aktion.status != "ausgefuehrt" or not aktion.rueckweg:
            raise RueckgaengigAbgelehnt(400, "Diese Aktion lässt sich nicht rückgängig machen.")
        if aktion.rueckgaengig_bis is None or jetzt >= aktion.rueckgaengig_bis:
            raise RueckgaengigAbgelehnt(400, "Die Frist zum Rückgängigmachen (7 Tage) ist abgelaufen.")

        konflikte = await _konflikte(token, aktion.rueckweg)
        if konflikte:
            raise RueckgaengigAbgelehnt(
                409,
                "Rückgängig nicht möglich, weil sich die Daten seitdem geändert haben: " + konflikt_text(konflikte),
                konflikte,
            )

        marke = aktion_id_var.set(aktion.id)
        try:
            for op in reversed(aktion.rueckweg):
                try:
                    await _anfrage_mit_token(token, op["methode"], op["pfad"], body=op.get("body"), rueckweg=True)
                except (ToolError, PermissionError) as exc:
                    # Schon Zurueckgenommenes bleibt zurueckgenommen; das Journal behaelt den Status und nennt den Grund.
                    text = f"Rückgängig nicht vollständig: {exc}"
                    aktion.fehler = text
                    abbruch = RueckgaengigAbgelehnt(400, text)
                    break
        finally:
            aktion_id_var.reset(marke)

        if abbruch is None:
            aktion.status = "rueckgaengig"
            aktion.rueckgaengig_am = jetzt
            aktion.rueckgaengig_von = user_id
            await log_action(
                session,
                aktion="ki_aktion_rueckgaengig",
                mandant_id=mandant_id,
                actor_user_id=user_id,
                entity_type="ki_aktion",
                entity_id=aktion.id,
                payload={"tool": aktion.tool, "aktionsart": aktion.aktionsart, "ausloeser": ausloeser},
            )
    if abbruch is not None:
        raise abbruch
    return aktion_id
