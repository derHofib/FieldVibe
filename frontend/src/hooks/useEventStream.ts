import { useEffect, useRef } from "react";

import { authStore } from "../api/authStore";
import { streamApi } from "../api/endpoints";

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const RECONNECT_MIN_MS = 3000;
const RECONNECT_MAX_MS = 30000;

type EventHandler = (data: unknown) => void;

/**
 * Subscribes to /api/stream (SSE) for the lifetime of the calling
 * component. EventSource's native retry would re-use the same URL, but the
 * ticket in it is single-purpose and expires after 60 s -- so on every error
 * the connection is closed and re-opened with a freshly requested ticket
 * (exponential backoff). Also re-created when the active token changes
 * (e.g. impersonation start/end).
 */
export function useEventStream(handlers: Record<string, EventHandler>) {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  const token = authStore.getActiveAccessToken();

  useEffect(() => {
    if (!token) return;

    let abgebrochen = false;
    let source: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let wartezeit = RECONNECT_MIN_MS;

    const spaeterVerbinden = () => {
      if (abgebrochen) return;
      timer = setTimeout(() => void verbinden(), wartezeit);
      wartezeit = Math.min(wartezeit * 2, RECONNECT_MAX_MS);
    };

    const verbinden = async () => {
      let ticket: string;
      try {
        ticket = (await streamApi.ticket()).ticket;
      } catch {
        spaeterVerbinden();
        return;
      }
      if (abgebrochen) return;

      const quelle = new EventSource(`${BASE_URL}/api/stream?ticket=${encodeURIComponent(ticket)}`);
      source = quelle;
      quelle.onopen = () => {
        wartezeit = RECONNECT_MIN_MS;
      };
      quelle.onerror = () => {
        quelle.close();
        spaeterVerbinden();
      };

      for (const eventName of Object.keys(handlersRef.current)) {
        quelle.addEventListener(eventName, (ev: MessageEvent) => {
          try {
            handlersRef.current[eventName]?.(JSON.parse(ev.data));
          } catch {
            /* malformed payload, ignore */
          }
        });
      }
    };

    void verbinden();

    return () => {
      abgebrochen = true;
      if (timer) clearTimeout(timer);
      source?.close();
    };
  }, [token]);
}
