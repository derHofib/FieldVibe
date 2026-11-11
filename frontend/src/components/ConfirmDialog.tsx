import { createContext, useCallback, useContext, useEffect, useId, useRef, useState, type ReactNode } from "react";

export interface BestaetigungOptionen {
  titel: string;
  /** Benennt die Folge der Aktion, nicht nur "Sind Sie sicher?". */
  text?: string;
  bestaetigenLabel?: string;
  abbrechenLabel?: string;
  /** true (Default): roter Button, Fokus startet auf "Abbrechen". */
  destruktiv?: boolean;
}

type BestaetigenFn = (optionen: BestaetigungOptionen) => Promise<boolean>;

const BestaetigungContext = createContext<BestaetigenFn | null>(null);

interface Offen {
  optionen: BestaetigungOptionen;
  aufloesen: (ok: boolean) => void;
}

const FOKUSSIERBAR = "button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex='-1'])";

function Dialog({ optionen, aufloesen }: Offen) {
  const titelId = useId();
  const textId = useId();
  const boxRef = useRef<HTMLDivElement>(null);
  const abbrechenRef = useRef<HTMLButtonElement>(null);
  const destruktiv = optionen.destruktiv ?? true;

  useEffect(() => {
    const vorher = document.activeElement as HTMLElement | null;
    abbrechenRef.current?.focus();
    return () => vorher?.focus?.();
  }, []);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      aufloesen(false);
      return;
    }
    if (e.key !== "Tab") return;
    const elemente = boxRef.current?.querySelectorAll<HTMLElement>(FOKUSSIERBAR);
    if (!elemente || elemente.length === 0) return;
    const erstes = elemente[0];
    const letztes = elemente[elemente.length - 1];
    if (e.shiftKey && document.activeElement === erstes) {
      e.preventDefault();
      letztes.focus();
    } else if (!e.shiftKey && document.activeElement === letztes) {
      e.preventDefault();
      erstes.focus();
    }
  };

  return (
    <div
      className="fixed inset-0 z-[70] flex items-end justify-center bg-black/40 p-3 sm:items-center"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) aufloesen(false);
      }}
      onKeyDown={onKeyDown}
    >
      <div
        ref={boxRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titelId}
        aria-describedby={optionen.text ? textId : undefined}
        className="w-full max-w-sm space-y-3 rounded-xl bg-white p-4 shadow-xl dark:bg-stone-900 dark:ring-1 dark:ring-stone-800"
      >
        <h2 id={titelId} className="text-base font-semibold text-slate-900 dark:text-stone-100">
          {optionen.titel}
        </h2>
        {optionen.text && (
          <p id={textId} className="text-sm text-slate-600 dark:text-stone-300">
            {optionen.text}
          </p>
        )}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            ref={abbrechenRef}
            type="button"
            onClick={() => aufloesen(false)}
            className="btn-touch rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-stone-700 dark:text-stone-200 dark:hover:bg-stone-800"
          >
            {optionen.abbrechenLabel ?? "Abbrechen"}
          </button>
          <button
            type="button"
            onClick={() => aufloesen(true)}
            className={`btn-touch rounded-md px-4 py-2 text-sm font-semibold text-white ${
              destruktiv
                ? "bg-red-700 hover:bg-red-800 dark:bg-red-600 dark:hover:bg-red-500"
                : "bg-slate-800 hover:bg-slate-900 dark:bg-stone-200 dark:text-stone-900 dark:hover:bg-white"
            }`}
          >
            {optionen.bestaetigenLabel ?? (destruktiv ? "Löschen" : "Bestätigen")}
          </button>
        </div>
      </div>
    </div>
  );
}

export function BestaetigungProvider({ children }: { children: ReactNode }) {
  const [offen, setOffen] = useState<Offen | null>(null);

  const bestaetigen = useCallback<BestaetigenFn>(
    (optionen) =>
      new Promise<boolean>((resolve) => {
        setOffen({
          optionen,
          aufloesen: (ok) => {
            setOffen(null);
            resolve(ok);
          },
        });
      }),
    [],
  );

  return (
    <BestaetigungContext.Provider value={bestaetigen}>
      {children}
      {offen && <Dialog {...offen} />}
    </BestaetigungContext.Provider>
  );
}

/** Promise-Ersatz für window.confirm: `if (!(await bestaetigen({...}))) return;` */
export function useBestaetigung(): BestaetigenFn {
  const ctx = useContext(BestaetigungContext);
  // Ohne Provider (z. B. isoliert gerenderte Komponente im Test) auf den nativen Dialog zurückfallen
  return ctx ?? ((o) => Promise.resolve(window.confirm(o.text ? `${o.titel}\n${o.text}` : o.titel)));
}
