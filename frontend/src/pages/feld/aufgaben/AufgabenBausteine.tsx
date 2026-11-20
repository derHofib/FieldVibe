import { Columns3, Lock } from "lucide-react";

import type { ProjektAufgabe } from "../../../types";
import { PRIORITAET_LABEL } from "./aufgabenLogik";

const PRIORITAET_PUNKT: Record<ProjektAufgabe["prioritaet"], string> = {
  hoch: "bg-st-fehlt-dot",
  mittel: "bg-st-arbeit-dot",
  niedrig: "bg-st-geplant-dot",
};

/** Privat (Schloss, Violett wie Status "wartet") oder Kanban-Karte mit dem Namen ihrer Spalte. */
export function QuelleAnzeige({ aufgabe }: { aufgabe: Pick<ProjektAufgabe, "projekt_id" | "spalte_name"> }) {
  if (!aufgabe.projekt_id) {
    return (
      <span className="inline-flex items-center gap-1.5 font-medium text-st-wartet">
        <Lock size={13} strokeWidth={1.5} aria-hidden="true" />
        Privat
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-label2">
      <Columns3 size={13} strokeWidth={1.5} aria-hidden="true" />
      {aufgabe.spalte_name ?? "Projekt-Aufgabe"}
    </span>
  );
}

export function PrioritaetAnzeige({ prioritaet }: { prioritaet: ProjektAufgabe["prioritaet"] }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-label">
      <span className={`h-2 w-2 rounded-full ${PRIORITAET_PUNKT[prioritaet]}`} aria-hidden="true" />
      {PRIORITAET_LABEL[prioritaet]}
    </span>
  );
}

/** "2/5 Unteraufgaben" bzw. "Checkliste 1/3"; null, wenn es weder noch gibt. */
export function fortschrittText(a: Pick<ProjektAufgabe, "unteraufgaben_gesamt" | "unteraufgaben_erledigt" | "checkliste">): string | null {
  if (a.unteraufgaben_gesamt) return `${a.unteraufgaben_erledigt ?? 0}/${a.unteraufgaben_gesamt} Unteraufgaben`;
  if (a.checkliste.length > 0) return `Checkliste ${a.checkliste.filter((p) => p.erledigt).length}/${a.checkliste.length}`;
  return null;
}
