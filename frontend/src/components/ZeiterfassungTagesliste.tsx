import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

import type { Zeiterfassung } from "../types";
import { formatStundenAlsHHMM } from "../utils/duration";
import {
  ZEITERFASSUNG_KATEGORIE_LABEL,
  ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT,
  formatDauer,
  formatUhrzeit,
  lokalerTag,
} from "../utils/zeiterfassung";

/** Gruppiert Zeiterfassungen nach lokalem Kalendertag, mit Tagessumme
 * (ohne Pause/Urlaub/Krankheit, siehe ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT)
 * und aufklappbaren Einzeleintraegen (Von-Bis, Auftragsnummer bzw.
 * Kategorie, Notiz). */
export function ZeiterfassungTagesliste({
  eintraege,
  onEintragKlick,
}: {
  eintraege: Zeiterfassung[];
  onEintragKlick?: (vorgangId: string) => void;
}) {
  const [offeneTage, setOffeneTage] = useState<Set<string>>(new Set());

  const tageMap = new Map<string, Zeiterfassung[]>();
  for (const eintrag of eintraege) {
    const tag = lokalerTag(eintrag.start_at);
    const liste = tageMap.get(tag);
    if (liste) liste.push(eintrag);
    else tageMap.set(tag, [eintrag]);
  }
  const tage = [...tageMap.entries()].sort(([a], [b]) => a.localeCompare(b));

  function toggle(tag: string) {
    setOffeneTage((vorher) => {
      const neu = new Set(vorher);
      if (neu.has(tag)) neu.delete(tag);
      else neu.add(tag);
      return neu;
    });
  }

  return (
    <div className="space-y-1.5">
      {tage.map(([tag, tagesEintraege]) => {
        const tagessumme = tagesEintraege.reduce(
          (summe, e) =>
            ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT.includes(e.kategorie)
              ? summe
              : summe + formatDauer(e.start_at, e.ende_at),
          0
        );
        const offen = offeneTage.has(tag);
        return (
          <div key={tag} className="overflow-hidden rounded-md bg-slate-50 dark:bg-stone-800/60">
            <button
              onClick={() => toggle(tag)}
              className="btn-touch flex w-full items-center justify-between px-2 py-2 text-left text-sm"
            >
              <span className="flex items-center gap-1.5 font-medium text-slate-700 dark:text-stone-200">
                {offen ? (
                  <ChevronDown size={15} strokeWidth={2} />
                ) : (
                  <ChevronRight size={15} strokeWidth={2} />
                )}
                {new Date(`${tag}T00:00:00`).toLocaleDateString("de-DE", {
                  weekday: "short",
                  day: "2-digit",
                  month: "2-digit",
                })}
              </span>
              <span className="font-medium text-slate-700 dark:text-stone-200">
                {formatStundenAlsHHMM(tagessumme)} Std.
              </span>
            </button>
            {offen && (
              <div className="space-y-1 px-2 pb-2">
                {tagesEintraege
                  .slice()
                  .sort((a, b) => a.start_at.localeCompare(b.start_at))
                  .map((e) => (
                    <button
                      key={e.id}
                      onClick={() => e.vorgang_id && onEintragKlick?.(e.vorgang_id)}
                      disabled={!e.vorgang_id}
                      className="card-interactive btn-touch flex w-full items-center justify-between rounded-md bg-white px-2 py-1.5 text-left text-sm disabled:cursor-default dark:bg-stone-900"
                    >
                      <span className="min-w-0 truncate text-slate-600 dark:text-stone-300">
                        {formatUhrzeit(e.start_at)}–{e.ende_at ? formatUhrzeit(e.ende_at) : "läuft"}
                        {" · "}
                        <span className="font-medium">
                          {e.vorgangsnummer ?? ZEITERFASSUNG_KATEGORIE_LABEL[e.kategorie] ?? e.kategorie}
                        </span>
                        {e.taetigkeit && ` · ${e.taetigkeit}`}
                      </span>
                      <span className="ml-2 shrink-0 font-medium text-slate-700 dark:text-stone-300">
                        {formatStundenAlsHHMM(formatDauer(e.start_at, e.ende_at))} Std.
                      </span>
                    </button>
                  ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
