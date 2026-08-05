import { useEffect, useRef } from "react";

import { authStore } from "../api/authStore";

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

type EventHandler = (data: unknown) => void;

/**
 * Subscribes to /api/stream (SSE) for the lifetime of the calling
 * component. Reconnects on error with a fixed backoff -- EventSource
 * handles the actual retry loop natively, this just re-creates the
 * connection when the active token changes (e.g. impersonation start/end).
 */
export function useEventStream(handlers: Record<string, EventHandler>) {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  const token = authStore.getActiveAccessToken();

  useEffect(() => {
    if (!token) return;

    const source = new EventSource(`${BASE_URL}/api/stream?token=${encodeURIComponent(token)}`);

    const listeners: Array<[string, (ev: MessageEvent) => void]> = [];
    for (const eventName of Object.keys(handlersRef.current)) {
      const listener = (ev: MessageEvent) => {
        try {
          handlersRef.current[eventName]?.(JSON.parse(ev.data));
        } catch {
          /* malformed payload, ignore */
        }
      };
      source.addEventListener(eventName, listener);
      listeners.push([eventName, listener]);
    }

    return () => {
      for (const [eventName, listener] of listeners) {
        source.removeEventListener(eventName, listener);
      }
      source.close();
    };
  }, [token]);
}
