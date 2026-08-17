import { useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { feedApi } from "../api/endpoints";
import { cacheFeedItems, getCachedFeedItems } from "../offline/cache";
import type { FeedResponse } from "../types";

/** Gemeinsame Datenlogik von Feed (Handy) und den Vorgangs-/Dispo-Ansichten
 * im Office: Infinite Query mit demselben queryKey (damit die
 * SSE-Invalidierung aus useAppLiveDaten beide Oberflaechen frisch haelt) und
 * Offline-Rueckfall auf den zwischengespeicherten letzten Feed-Stand. Nur
 * die erste Seite spiegelt in den Cache -- der soll "der Feed wie zuletzt
 * gesehen" abbilden, nicht jede je gescrollte Seite ansammeln. */
export function useVorgangsListe(filter: Record<string, string>) {
  return useInfiniteQuery({
    queryKey: ["feed", filter],
    queryFn: async ({ pageParam }: { pageParam: string | undefined }): Promise<FeedResponse> => {
      try {
        const result = await feedApi.get({
          ...filter,
          ...(pageParam ? { cursor: pageParam } : {}),
        });
        if (!pageParam) await cacheFeedItems(result.items);
        return result;
      } catch (err) {
        if (!navigator.onLine && !pageParam) {
          const cached = await getCachedFeedItems();
          if (cached.length > 0) return { items: cached, next_cursor: null };
        }
        throw err;
      }
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

/** Laedt alle restlichen Seiten nach, solange `aktiv` gilt (Kartenansicht,
 * Kanban, Raster, Dispo-Board) -- dort werden alle Treffer nebeneinander
 * gezeigt, eine nur seitenweise nachgeladene Liste haette dort Luecken, die
 * nur wie fehlende Vorgaenge aussehen. Per Ref, damit der Effekt nicht bei
 * jeder nachgeladenen Seite neu startet, sondern nur wenn `aktiv` selbst
 * wechselt. Deckelung bei 20 Seiten als Notbremse gegen Endlosschleifen. */
export function useAlleSeitenLaden(
  aktiv: boolean,
  hasNextPage: boolean,
  fetchNextPage: () => Promise<unknown>,
) {
  const hasNextPageRef = useRef(hasNextPage);
  hasNextPageRef.current = hasNextPage;
  const fetchNextPageRef = useRef(fetchNextPage);
  fetchNextPageRef.current = fetchNextPage;

  useEffect(() => {
    if (!aktiv) return;
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
  }, [aktiv]);
}
