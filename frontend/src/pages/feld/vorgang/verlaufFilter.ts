import type { OutboxItem } from "../../../offline/db";
import type { VerlaufEintrag } from "./konstanten";

export type VerlaufFilter = "alle" | "kommentare" | "telefonate" | "system" | "email";

export const VERLAUF_FILTER_OPTIONEN: { wert: VerlaufFilter; label: string }[] = [
  { wert: "alle", label: "Alle" },
  { wert: "kommentare", label: "Kommentare" },
  { wert: "telefonate", label: "Telefonate" },
  { wert: "email", label: "E-Mail" },
  { wert: "system", label: "System" },
];

/** Telefonate zählen weder zu "Kommentare" noch zu "System" -- sie haben einen eigenen Filter. */
export function verlaufEintragPasst(eintrag: VerlaufEintrag, filter: VerlaufFilter): boolean {
  if (filter === "alle") return true;
  if (eintrag.art === "email") return filter === "email";
  const typ = eintrag.event.event_type;
  if (filter === "telefonate") return typ === "telefonat";
  if (filter === "email") return false;
  if (typ === "telefonat") return false;
  if (filter === "system") return eintrag.event.is_system || typ === "status_change";
  // "kommentare": alles Nutzergenerierte -- Kommentar, Foto, Unterschrift, Dokument.
  return !eintrag.event.is_system && typ !== "status_change";
}

export function outboxItemPasst(item: OutboxItem, filter: VerlaufFilter): boolean {
  if (filter === "alle") return true;
  if (filter === "email") return false; // Outbox kennt keine E-Mails.
  if (filter === "telefonate") return item.kind === "telefonat";
  if (filter === "system") return item.kind === "status";
  return item.kind !== "status" && item.kind !== "telefonat";
}
