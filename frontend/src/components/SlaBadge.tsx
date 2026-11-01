import { Timer } from "lucide-react";

import type { SlaInfo, SlaStatus } from "../types";

const KLASSE: Record<SlaStatus, string> = {
  ok: "text-st-erledigt bg-st-erledigt-bg",
  gefaehrdet: "text-st-arbeit bg-st-arbeit-bg",
  verletzt: "text-st-fehlt bg-st-fehlt-bg",
  pausiert: "text-st-wartet bg-st-wartet-bg",
  erfuellt: "text-st-erledigt bg-st-erledigt-bg",
};

const LABEL: Record<SlaStatus, string> = {
  ok: "SLA",
  gefaehrdet: "SLA gefährdet",
  verletzt: "SLA verletzt",
  pausiert: "SLA pausiert",
  erfuellt: "SLA erfüllt",
};

/** Kürzeste noch offene Frist (Reaktion zählt nur, solange noch nicht reagiert wurde). */
export function naechsteSlaFrist(sla: SlaInfo): string | null {
  const offen = [sla.reagiert_am ? null : sla.reaktion_faellig_am, sla.geloest_am ? null : sla.loesung_faellig_am].filter(
    (f): f is string => !!f,
  );
  if (offen.length === 0) return null;
  return offen.reduce((a, b) => (new Date(a) < new Date(b) ? a : b));
}

export function formatRestzeit(faelligMs: number, jetztMs: number): string {
  const diffMin = Math.round((faelligMs - jetztMs) / 60000);
  const betrag = Math.abs(diffMin);
  const text =
    betrag >= 2880 ? `${Math.round(betrag / 1440)} Tg.` : betrag >= 60 ? `${Math.floor(betrag / 60)} Std. ${betrag % 60} Min.` : `${betrag} Min.`;
  return diffMin >= 0 ? `noch ${text}` : `${text} überfällig`;
}

/** SLA-Pille: Status wird nie nur über Farbe vermittelt, sondern über Text und Restzeit. */
export function SlaBadge({ sla, jetzt = Date.now() }: { sla: SlaInfo | null | undefined; jetzt?: number }) {
  if (!sla) return null;
  const frist = sla.status === "ok" || sla.status === "gefaehrdet" || sla.status === "verletzt" ? naechsteSlaFrist(sla) : null;
  const rest = frist ? formatRestzeit(new Date(frist).getTime(), jetzt) : null;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-[var(--radius-ap-pill)] px-2 py-0.5 text-xs font-semibold ${KLASSE[sla.status]}`}
      title={frist ? `Nächste Frist: ${new Date(frist).toLocaleString("de-DE")}` : undefined}
    >
      <Timer size={12} strokeWidth={1.75} aria-hidden="true" />
      {LABEL[sla.status]}
      {rest && <span className="font-normal">· {rest}</span>}
    </span>
  );
}
