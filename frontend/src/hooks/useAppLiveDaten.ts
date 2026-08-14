import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useOutboxSync } from "../offline/useOutboxSync";
import { useEventStream } from "./useEventStream";

function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const setTrue = () => setOnline(true);
    const setFalse = () => setOnline(false);
    window.addEventListener("online", setTrue);
    window.addEventListener("offline", setFalse);
    return () => {
      window.removeEventListener("online", setTrue);
      window.removeEventListener("offline", setFalse);
    };
  }, []);
  return online;
}

/** SSE-Invalidierung + Outbox-Sync + Online-Status, gemeinsam fuer alle
 * Mitarbeiter-Shells (Feld-App und Office). Bewusst hier statt in einem
 * Layout: nichts davon ist an eine Bildschirmgroesse gebunden, und zwei
 * Kopien wuerden bei jedem neuen Event-Typ auseinanderlaufen. */
export function useAppLiveDaten(): { outboxCount: number; isOnline: boolean } {
  const queryClient = useQueryClient();
  const outboxCount = useOutboxSync();
  const isOnline = useOnlineStatus();

  useEventStream({
    feed_update: () => {
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      queryClient.invalidateQueries({ queryKey: ["stories"] });
    },
    vorgang_event: (data) => {
      const payload = data as { vorgang_id: string };
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", payload.vorgang_id] });
    },
    notification: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    timer: (data) => {
      const payload = data as { vorgang_id: string };
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung-laufend"] });
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung", payload.vorgang_id] });
    },
  });

  return { outboxCount, isOnline };
}
