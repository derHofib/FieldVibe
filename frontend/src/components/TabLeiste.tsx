import { useRef } from "react";

export interface TabEintrag<T extends string> {
  key: T;
  label: string;
  anzahl?: number;
}

/** Gleichmäßig verteilte Tab-Leiste (Pillen, Tippfläche >= 44 px). Passt auf
 * 390 px ohne Wischen; bei zu vielen Tabs scrollt sie statt umzubrechen.
 * Pfeiltasten wechseln den Tab (Roving-Tabindex). */
export function TabLeiste<T extends string>({
  tabs,
  aktiv,
  onChange,
  label,
}: {
  tabs: TabEintrag<T>[];
  aktiv: T;
  onChange: (key: T) => void;
  label: string;
}) {
  const listeRef = useRef<HTMLDivElement>(null);

  const beiTaste = (e: React.KeyboardEvent, index: number) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const ziel = tabs[(index + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length];
    onChange(ziel.key);
    listeRef.current?.querySelector<HTMLButtonElement>(`[data-tab="${ziel.key}"]`)?.focus();
  };

  return (
    <div
      ref={listeRef}
      role="tablist"
      aria-label={label}
      className="flex gap-1 overflow-x-auto rounded-full bg-slate-200/70 p-1 dark:bg-stone-900"
    >
      {tabs.map((tab, i) => {
        const istAktiv = tab.key === aktiv;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            data-tab={tab.key}
            aria-selected={istAktiv}
            tabIndex={istAktiv ? 0 : -1}
            onClick={() => onChange(tab.key)}
            onKeyDown={(e) => beiTaste(e, i)}
            className={`btn-touch flex min-w-fit flex-1 items-center justify-center gap-1 whitespace-nowrap rounded-full px-3 text-sm font-medium ${
              istAktiv
                ? "bg-white text-slate-800 shadow-xs dark:bg-stone-700 dark:text-stone-50 dark:shadow-none"
                : "text-slate-600 dark:text-stone-400"
            }`}
          >
            {tab.label}
            {tab.anzahl !== undefined && tab.anzahl > 0 && (
              <span className="rounded-full bg-slate-100 px-1.5 text-xs text-slate-500 dark:bg-stone-800 dark:text-stone-300">
                {tab.anzahl}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
