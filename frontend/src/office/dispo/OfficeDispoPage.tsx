import { useInfiniteQuery } from "@tanstack/react-query";
import { Inbox } from "lucide-react";
import { useEffect, useRef } from "react";

import { feedApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import type { FeedCard, FeedResponse } from "../../types";
import { SeitenKopf } from "../OfficeUi";
import { VorgaengeKanban } from "../vorgaenge/VorgaengeKanban";

/** Dispo als Kanban ueber alle offenen Vorgaenge. Teilt sich die
 * Spalten-Komponente mit der Vorgangs-Ansicht -- gleiche Karten, gleiche
 * Statusfarben, nur ein anderer Einstieg (hier ohne Ansicht-Umschalter, weil
 * Dispo genau diese eine Sicht braucht). */
export function OfficeDispoPage() {
  const { data, fetchNextPage, hasNextPage, isLoading } = useInfiniteQuery({
    queryKey: ["feed", { dispo: "true" }],
    queryFn: async ({ pageParam }: { pageParam: string | undefined }): Promise<FeedResponse> =>
      feedApi.get({ ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  // Das Board zeigt alle Spalten nebeneinander -- ohne vollstaendiges
  // Nachladen fehlten in einzelnen Spalten Karten, die nur noch nicht
  // geladen sind.
  const hasNextPageRef = useRef(hasNextPage);
  hasNextPageRef.current = hasNextPage;
  const fetchNextPageRef = useRef(fetchNextPage);
  fetchNextPageRef.current = fetchNextPage;
  useEffect(() => {
    let abgebrochen = false;
    (async () => {
      let seiten = 0;
      while (!abgebrochen && hasNextPageRef.current && seiten < 20) {
        await fetchNextPageRef.current();
        seiten++;
      }
    })();
    return () => {
      abgebrochen = true;
    };
  }, []);

  const vorgaenge: FeedCard[] = data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <div>
      <SeitenKopf titel="Dispo" anzahl={vorgaenge.length} />
      {isLoading ? (
        <p className="py-10 text-center text-sm text-slate-400 dark:text-stone-500">Lädt…</p>
      ) : vorgaenge.length === 0 ? (
        <EmptyState icon={Inbox} text="Keine Vorgänge zu disponieren." />
      ) : (
        <VorgaengeKanban vorgaenge={vorgaenge} />
      )}
    </div>
  );
}
