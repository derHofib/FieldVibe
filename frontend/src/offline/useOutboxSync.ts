import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { getOutboxCount, subscribeOutbox, syncOutbox } from "./outbox";

/** Drives the outbox: tries a sync on mount, whenever the browser comes
 * back online, and once more shortly after (in case the 'online' event
 * fires before the network is actually usable again). Also exposes the
 * live pending-count for the header badge. */
export function useOutboxSync(): number {
  const [count, setCount] = useState(0);
  const queryClient = useQueryClient();

  useEffect(() => {
    let cancelled = false;

    const refreshCount = async () => {
      const n = await getOutboxCount();
      if (!cancelled) setCount(n);
      queryClient.invalidateQueries({ queryKey: ["outbox"] });
    };

    const runSync = async () => {
      await syncOutbox();
      await refreshCount();
      queryClient.invalidateQueries({ queryKey: ["vorgang-events"] });
      queryClient.invalidateQueries({ queryKey: ["feed"] });
    };

    refreshCount();
    runSync();

    // Also attempt a sync right after any queue change (new item queued, or
    // one just cleared) -- not just on the browser's 'online' event, which
    // never fires for a "technically connected but this request failed"
    // blip (flaky server, brief drop) rather than a real offline/online
    // transition. syncOutbox() is a no-op while already running or while
    // truly offline, so this can't pile up concurrent attempts.
    const unsubscribe = subscribeOutbox(() => {
      refreshCount();
      runSync();
    });
    window.addEventListener("online", runSync);
    const retryTimer = window.setInterval(() => {
      if (navigator.onLine) runSync();
    }, 10000);

    return () => {
      cancelled = true;
      unsubscribe();
      window.removeEventListener("online", runSync);
      window.clearInterval(retryTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return count;
}
