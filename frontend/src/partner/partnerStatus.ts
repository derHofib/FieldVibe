import type { StatusKey } from "../components/apple/status";
import { vorgangStatusZuToken, VORGANG_STATUS_LABEL } from "../components/apple/status";
import type { PartnerVorgang } from "../types";

const GESCHLOSSEN = new Set(["abgeschlossen", "abgerechnet", "storniert"]);

export type AuftragsPhase = "entscheiden" | "aktiv" | "beendet";

/** Gruppierung der Auftragsliste: offene Anfragen zuerst, abgelehnte und
 * geschlossene Auftraege am Ende. */
export function auftragsPhase(a: PartnerVorgang): AuftragsPhase {
  if (a.partner_freigabe_status === "vorgeschlagen") return "entscheiden";
  if (a.partner_freigabe_status === "abgelehnt" || GESCHLOSSEN.has(a.status)) return "beendet";
  return "aktiv";
}

/** Pillen-Token+Label: vor der Annahme zaehlt die Freigabe, nicht der
 * (noch nicht vom Partner bearbeitete) Vorgangsstatus. */
export function auftragsPille(a: PartnerVorgang): { status: StatusKey; label: string } {
  if (a.partner_freigabe_status === "vorgeschlagen") return { status: "neu", label: "Zu entscheiden" };
  if (a.partner_freigabe_status === "abgelehnt") return { status: "geplant", label: "Abgelehnt" };
  return { status: vorgangStatusZuToken(a.status), label: VORGANG_STATUS_LABEL[a.status] };
}

/** Kommentare/Statuswechsel erlaubt das Backend nur nach Annahme und solange
 * der Vorgang nicht geschlossen ist (partner_portal.py, 409). */
export function istBearbeitbar(a: PartnerVorgang): boolean {
  return a.partner_freigabe_status === "angenommen" && !GESCHLOSSEN.has(a.status);
}
