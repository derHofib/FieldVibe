import { CheckCircle2, Info, X, XCircle } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

import { ApiError } from "../api/client";

type ToastArt = "erfolg" | "fehler" | "info";

interface ToastEintrag {
  id: number;
  art: ToastArt;
  text: string;
}

interface ToastApi {
  erfolg: (text: string) => void;
  fehler: (text: string) => void;
  info: (text: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

// Fehler bleiben länger stehen: man muss sie lesen können, bevor sie verschwinden.
const DAUER_MS: Record<ToastArt, number> = { erfolg: 4000, info: 4000, fehler: 8000 };

const STIL: Record<ToastArt, string> = {
  erfolg: "bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
  fehler: "bg-red-50 text-red-900 dark:bg-red-950 dark:text-red-200",
  info: "bg-slate-800 text-white dark:bg-stone-700 dark:text-stone-100",
};

const ICON = { erfolg: CheckCircle2, fehler: XCircle, info: Info };

/** Meldungstext aus einem Mutationsfehler; ApiError-Texte sind bereits deutsch. */
export function fehlerText(err: unknown, fallback: string): string {
  return err instanceof ApiError && err.message ? err.message : fallback;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastEintrag[]>([]);
  const naechsteId = useRef(1);

  const entfernen = useCallback((id: number) => {
    setToasts((alt) => alt.filter((t) => t.id !== id));
  }, []);

  const zeige = useCallback(
    (art: ToastArt, text: string) => {
      const id = naechsteId.current++;
      setToasts((alt) => [...alt.slice(-3), { id, art, text }]);
      window.setTimeout(() => entfernen(id), DAUER_MS[art]);
    },
    [entfernen],
  );

  const api = useMemo<ToastApi>(
    () => ({
      erfolg: (text) => zeige("erfolg", text),
      fehler: (text) => zeige("fehler", text),
      info: (text) => zeige("info", text),
    }),
    [zeige],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      {/* bottom-24: über der schwebenden Bottom-Nav der Feld-App */}
      <div className="pointer-events-none fixed inset-x-0 bottom-24 z-[60] flex flex-col items-center gap-2 px-3 md:bottom-6">
        {toasts.map((t) => {
          const Icon = ICON[t.art];
          return (
            <div
              key={t.id}
              // Fehler als assertive Ansage (alert), sonst höfliches status
              role={t.art === "fehler" ? "alert" : "status"}
              className={`pointer-events-auto flex w-full max-w-sm items-start gap-2 rounded-lg px-3 py-2.5 text-sm shadow-lg ${STIL[t.art]}`}
            >
              <Icon size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
              <span className="min-w-0 flex-1">{t.text}</span>
              <button
                type="button"
                onClick={() => entfernen(t.id)}
                aria-label="Meldung schließen"
                className="shrink-0 rounded p-0.5 opacity-70 hover:opacity-100"
              >
                <X size={16} aria-hidden="true" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast braucht einen ToastProvider");
  return ctx;
}
