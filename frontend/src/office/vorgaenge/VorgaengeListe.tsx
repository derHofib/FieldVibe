import { ExternalLink } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  GRUPPEN_LABEL,
  STATUS_BADGE,
  STATUS_LABEL,
  gruppiereNachFaelligkeit,
  istUeberfaellig,
} from "../../config/vorgangDarstellung";
import { VorgangDetailPage } from "../../pages/feld/VorgangDetailPage";
import type { FeedCard } from "../../types";
import { Karte } from "../OfficeUi";

/** Liste links, Detail rechts. Das Detail-Panel rendert bewusst die
 * bestehende VorgangDetailPage (per id-Prop statt Route) statt eines
 * Nachbaus: die Seite ist ohnehin fuer eine schmale Spalte entworfen, und
 * ein zweiter Nachbau wuerde fachlich sofort auseinanderlaufen. */
export function VorgaengeListe({
  vorgaenge,
  hasNextPage,
  isFetchingNextPage,
  onMehr,
}: {
  vorgaenge: FeedCard[];
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  onMehr: () => void;
}) {
  const navigate = useNavigate();
  const [gewaehlt, setGewaehlt] = useState<string | null>(null);
  const aktiv = gewaehlt && vorgaenge.some((v) => v.id === gewaehlt) ? gewaehlt : vorgaenge[0]?.id;
  // Gleiche Gruppierung wie im Feed der Feld-App (siehe config/vorgangDarstellung.ts).
  const gruppen = gruppiereNachFaelligkeit(vorgaenge);

  return (
    <div className="grid grid-cols-[minmax(280px,340px)_1fr] gap-4">
      <Karte className="max-h-[calc(100vh-13rem)] overflow-y-auto">
        {gruppen.map(({ gruppe, cards }) => (
          <div key={gruppe}>
            <p className="border-b border-slate-100 bg-slate-50/70 px-3 py-1 text-[10.5px] font-bold tracking-wide text-slate-400 uppercase dark:border-stone-800 dark:bg-stone-800/40 dark:text-stone-500">
              {GRUPPEN_LABEL[gruppe]} <span className="font-medium normal-case">{cards.length}</span>
            </p>
            {cards.map((v) => {
              const ausgewaehlt = v.id === aktiv;
              return (
                <button
                  key={v.id}
                  onClick={() => setGewaehlt(v.id)}
                  className={`block w-full border-b border-slate-100 px-3 py-2.5 text-left last:border-b-0 dark:border-stone-800 ${
                    ausgewaehlt
                      ? "border-l-2 border-l-blue-500 bg-blue-50/60 pl-[10px] dark:bg-blue-500/10"
                      : "hover:bg-slate-50 dark:hover:bg-stone-800/50"
                  }`}
                >
                  <p className="truncate text-[13px] font-semibold text-ind-ink">
                    {v.vorgangsnummer} · {v.titel}
                  </p>
                  <p className="mt-0.5 flex items-center gap-1.5 truncate text-[11.5px] text-ind-ink-3">
                    <span className="truncate">{v.kunde_name}</span>
                    {istUeberfaellig(v.faelligkeit_am) && (
                      <span className="shrink-0 font-bold text-rose-600 dark:text-rose-300">
                        · überfällig
                      </span>
                    )}
                  </p>
                  <span
                    className={`mt-1.5 inline-block px-2 py-0.5 text-[10px] font-semibold ${STATUS_BADGE[v.status]}`}
                  >
                    {STATUS_LABEL[v.status]}
                  </span>
                </button>
              );
            })}
          </div>
        ))}

        {hasNextPage && (
          <button
            onClick={onMehr}
            disabled={isFetchingNextPage}
            className="w-full py-3 text-xs font-semibold text-slate-500 hover:bg-slate-50 disabled:opacity-50 dark:text-stone-400 dark:hover:bg-stone-800/50"
          >
            {isFetchingNextPage ? "Lädt…" : "Mehr laden"}
          </button>
        )}
      </Karte>

      <Karte className="max-h-[calc(100vh-13rem)] overflow-y-auto p-4">
        {aktiv ? (
          <>
            <div className="mb-3 flex justify-end">
              <button
                onClick={() => navigate(`/vorgaenge/${aktiv}`)}
                className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-500 hover:text-slate-700 dark:border-stone-700 dark:text-stone-400 dark:hover:text-stone-200"
              >
                <ExternalLink size={13} strokeWidth={2} />
                Ganze Seite
              </button>
            </div>
            <VorgangDetailPage id={aktiv} />
          </>
        ) : (
          <p className="py-10 text-center text-sm text-ind-ink-3">
            Links einen Vorgang auswählen.
          </p>
        )}
      </Karte>
    </div>
  );
}
