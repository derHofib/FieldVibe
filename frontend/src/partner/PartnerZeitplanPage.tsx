import { useQuery } from "@tanstack/react-query";
import { CalendarRange, Check } from "lucide-react";

import { partnerPortalApi } from "../api/endpoints";
import { AbschnittskopfB } from "../components/apple/AbschnittsKopf";
import { GroupedList, GroupedListRow } from "../components/apple/GroupedList";
import { EmptyState } from "../components/EmptyState";
import { SkeletonList } from "../components/Skeleton";
import type { PartnerZeitplanEintrag } from "../types";
import { formatKurz, heuteTag, montagVon, parseTag } from "../office/projekte/zeitplan/zeitplanLogik";

function zeitraumText(e: PartnerZeitplanEintrag): string {
  if (!e.start_am) return "Ohne Datum";
  const start = formatKurz(parseTag(e.start_am));
  if (!e.ende_am || e.ende_am === e.start_am) return start;
  return `${start} – ${formatKurz(parseTag(e.ende_am))}`;
}

/** Liegt der Eintrag (teilweise) in der aktuellen Kalenderwoche (Mo-So)? */
export function liegtDieseWoche(e: PartnerZeitplanEintrag, heute: number): boolean {
  if (!e.start_am) return false;
  const montag = montagVon(heute);
  const start = parseTag(e.start_am);
  const ende = e.ende_am ? parseTag(e.ende_am) : start;
  return start <= montag + 6 && ende >= montag;
}

/** Zeitplan des Partnerportals (Route /partnerportal/zeitplan): die dem
 * Partner zugewiesenen Schritte (Fremdgewerk) je Projekt, rein lesend. */
export function PartnerZeitplanPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["partnerportal-zeitplan"], queryFn: () => partnerPortalApi.zeitplan() });
  const heute = heuteTag();

  const nachProjekt = new Map<string, PartnerZeitplanEintrag[]>();
  for (const e of [...(data ?? [])].sort((a, b) => (a.start_am ?? "9999").localeCompare(b.start_am ?? "9999"))) {
    nachProjekt.set(e.projekt_name, [...(nachProjekt.get(e.projekt_name) ?? []), e]);
  }

  return (
    <main className="mx-auto max-w-2xl px-3 py-4 pb-10">
      <h1 className="ap-heading px-5 pt-2 pb-1 text-[26px] font-bold text-label">Zeitplan</h1>
      <p className="px-5 text-[15px] text-label2">Ihre Schritte in den Projekten, nur zur Ansicht.</p>

      {isLoading ? (
        <div className="px-4 pt-4">
          <SkeletonList count={4} />
        </div>
      ) : error ? (
        <p role="alert" className="px-5 pt-4 text-sm text-st-fehlt">
          Der Zeitplan konnte nicht geladen werden.
        </p>
      ) : nachProjekt.size === 0 ? (
        <div className="px-4 pt-4">
          <EmptyState icon={CalendarRange} text="Ihnen sind noch keine Schritte zugewiesen." />
        </div>
      ) : (
        [...nachProjekt.entries()].map(([projekt, eintraege]) => (
          <section key={projekt} aria-label={projekt}>
            <AbschnittskopfB titel={projekt} />
            <div className="px-4">
              <GroupedList>
                {eintraege.map((e, i) => {
                  const dieseWoche = !e.erledigt && liegtDieseWoche(e, heute);
                  return (
                    <div key={e.id} className={dieseWoche ? "bg-tintbg" : ""}>
                      <GroupedListRow last={i === eintraege.length - 1} minHoehe={56}>
                        <div className="min-w-0 flex-1">
                          <p className={`truncate text-[17px] ${e.erledigt ? "text-label2 line-through" : "text-label"}`}>{e.titel}</p>
                          <p className="truncate text-[13px] text-label2">
                            {e.phase_titel ? `${e.phase_titel} · ` : ""}
                            {zeitraumText(e)}
                          </p>
                        </div>
                        <div className="flex shrink-0 flex-col items-end gap-1">
                          {dieseWoche && <span className="rounded-full bg-tint-solid px-2 py-0.5 text-[11px] font-semibold text-white">Diese Woche</span>}
                          {e.erledigt ? (
                            <span className="flex items-center gap-1 text-[13px] font-semibold text-st-erledigt">
                              <Check size={14} strokeWidth={2.5} aria-hidden="true" /> Erledigt
                            </span>
                          ) : (
                            <span className="flex items-center gap-2 text-[13px] text-label2 tabular-nums">
                              <span className="h-1.5 w-14 overflow-hidden rounded-full bg-fill2" role="img" aria-label={`Fortschritt ${e.fortschritt} Prozent`}>
                                <span className="block h-full rounded-full bg-tint-solid" style={{ width: `${Math.min(100, Math.max(0, e.fortschritt))}%` }} />
                              </span>
                              {e.fortschritt} %
                            </span>
                          )}
                        </div>
                      </GroupedListRow>
                    </div>
                  );
                })}
              </GroupedList>
            </div>
          </section>
        ))
      )}
    </main>
  );
}
