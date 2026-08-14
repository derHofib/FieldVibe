import { useNavigate } from "react-router-dom";

import {
  KANBAN_SPALTEN,
  STATUS_LABEL,
  istUeberfaellig,
  tageSeit,
} from "../../config/vorgangDarstellung";
import type { FeedCard, VorgangStatus } from "../../types";

/** Spalten nach Status. Bewusst ohne Drag&Drop in dieser Ausbaustufe: ein
 * Statuswechsel loest im Backend Folgelogik aus (Pruefzyklen, Mangel-
 * Workflow, Abrechnung), das gehoert nicht hinter eine unbeabsichtigte
 * Wischgeste. Zum Aendern fuehrt der Klick in die Detailansicht. */
export function VorgaengeKanban({ vorgaenge }: { vorgaenge: FeedCard[] }) {
  const navigate = useNavigate();

  const nachStatus = (status: VorgangStatus) => vorgaenge.filter((v) => v.status === status);

  return (
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
      {KANBAN_SPALTEN.map((status) => {
        const spalte = nachStatus(status);
        return (
          <div key={status} className="min-w-0">
            <div className="mb-2 flex items-center justify-between px-1">
              <span className="text-xs font-bold text-slate-500 dark:text-stone-400">
                {STATUS_LABEL[status]}
              </span>
              <span className="rounded-full bg-slate-100 px-1.5 text-[10px] font-bold text-slate-400 dark:bg-stone-800 dark:text-stone-500">
                {spalte.length}
              </span>
            </div>

            <div className="space-y-2">
              {spalte.map((v) => {
                const ueberfaellig = istUeberfaellig(v.faelligkeit_am);
                return (
                  <button
                    key={v.id}
                    onClick={() => navigate(`/vorgaenge/${v.id}`)}
                    className={`card-interactive block w-full rounded-xl border bg-white p-3 text-left dark:bg-stone-900 ${
                      ueberfaellig
                        ? "border-rose-300 dark:border-rose-500/40"
                        : "border-slate-200 dark:border-stone-800"
                    }`}
                  >
                    <p className="text-[10.5px] font-bold text-slate-400 dark:text-stone-500">
                      {v.vorgangsnummer}
                    </p>
                    <p className="mt-0.5 text-[13px] font-semibold text-slate-800 dark:text-stone-100">
                      {v.titel}
                    </p>
                    <p className="mt-2 truncate text-[11.5px] text-slate-500 dark:text-stone-400">
                      {v.kunde_name}
                    </p>
                    <div className="mt-1.5 flex items-center justify-between gap-2">
                      {ueberfaellig ? (
                        <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-semibold text-rose-700 dark:bg-rose-500/15 dark:text-rose-300">
                          {tageSeit(v.faelligkeit_am!)} Tage
                        </span>
                      ) : (
                        <span />
                      )}
                      {v.zugewiesener_name && (
                        <span
                          title={v.zugewiesener_name}
                          className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-violet-100 text-[9px] font-bold text-violet-700 dark:bg-violet-500/15 dark:text-violet-300"
                        >
                          {v.zugewiesener_name
                            .split(" ")
                            .map((t) => t[0])
                            .slice(0, 2)
                            .join("")}
                        </span>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
