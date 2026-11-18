import { formatDatum } from "../../components/filter/auswerten";

/** "heute 14:12" / "gestern" / "14.11." / "14.11.2025" -- kurz genug für Tabellenzellen. */
export function relativDatum(iso: string, mitUhrzeit = false, jetzt: Date = new Date()): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const tag = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((tag(jetzt) - tag(d)) / 86_400_000);
  const uhr = d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  if (diff === 0) return mitUhrzeit ? `heute ${uhr}` : "heute";
  if (diff === 1) return "gestern";
  return d.getFullYear() === jetzt.getFullYear() ? formatDatum(iso, true) : formatDatum(iso);
}

export function langesDatum(iso: string): string {
  return formatDatum(iso);
}
