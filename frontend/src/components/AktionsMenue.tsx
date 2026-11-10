import type { LucideIcon } from "lucide-react";
import { MoreHorizontal } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

export interface AktionsMenueEintrag {
  label: string;
  icon?: LucideIcon;
  onClick: () => void;
  /** Destruktive Aktionen stehen am Ende und sind rot gekennzeichnet. */
  destruktiv?: boolean;
  disabled?: boolean;
}

/** Aufklappmenue (Zeilenaktionen, Nutzermenue). Das Menue wird per Portal
 * an <body> gehaengt und fest positioniert -- in einer Tabelle mit
 * overflow-x-auto wuerde es sonst am Rand abgeschnitten. */
export function AktionsMenue({
  eintraege,
  label,
  ausloeser,
  ausrichtung = "rechts",
}: {
  eintraege: (AktionsMenueEintrag | "trenner")[];
  label: string;
  /** Eigener Ausloeser; Standard ist ein Drei-Punkte-Button. */
  ausloeser?: (props: { offen: boolean }) => ReactNode;
  ausrichtung?: "links" | "rechts";
}) {
  const [position, setPosition] = useState<{ top: number; links: number; rechts: number } | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menueRef = useRef<HTMLDivElement>(null);
  const menueId = useId();
  const offen = position !== null;

  const schliessen = (fokusZurueck = true) => {
    setPosition(null);
    if (fokusZurueck) buttonRef.current?.focus();
  };

  const oeffnen = () => {
    const rect = buttonRef.current?.getBoundingClientRect();
    if (!rect) return;
    setPosition({
      top: rect.bottom + 4,
      links: rect.left,
      rechts: window.innerWidth - rect.right,
    });
  };

  useEffect(() => {
    if (!offen) return;
    menueRef.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus();
    const beiKlick = (e: MouseEvent) => {
      const ziel = e.target as Node;
      if (menueRef.current?.contains(ziel) || buttonRef.current?.contains(ziel)) return;
      schliessen(false);
    };
    // Ein feststehendes Menue wuerde beim Scrollen der Tabelle von seiner
    // Zeile wegwandern -- dann lieber schliessen.
    const beiScroll = () => schliessen(false);
    document.addEventListener("mousedown", beiKlick);
    window.addEventListener("resize", beiScroll);
    window.addEventListener("scroll", beiScroll, true);
    return () => {
      document.removeEventListener("mousedown", beiKlick);
      window.removeEventListener("resize", beiScroll);
      window.removeEventListener("scroll", beiScroll, true);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offen]);

  const beiTaste = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      schliessen();
      return;
    }
    if (e.key === "Tab") {
      schliessen(false);
      return;
    }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const knoepfe = Array.from(
      menueRef.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? [],
    );
    const aktuell = knoepfe.indexOf(document.activeElement as HTMLButtonElement);
    const schritt = e.key === "ArrowDown" ? 1 : -1;
    knoepfe[(aktuell + schritt + knoepfe.length) % knoepfe.length]?.focus();
  };

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => (offen ? schliessen() : oeffnen())}
        aria-label={label}
        title={label}
        aria-haspopup="menu"
        aria-expanded={offen}
        aria-controls={offen ? menueId : undefined}
        className={
          ausloeser
            ? undefined
            : "flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 dark:text-stone-400 dark:hover:bg-stone-800"
        }
      >
        {ausloeser ? ausloeser({ offen }) : <MoreHorizontal size={16} strokeWidth={2} />}
      </button>
      {offen &&
        createPortal(
          <div
            ref={menueRef}
            id={menueId}
            role="menu"
            onKeyDown={beiTaste}
            style={{
              position: "fixed",
              top: position.top,
              ...(ausrichtung === "rechts" ? { right: position.rechts } : { left: position.links }),
            }}
            className="z-50 min-w-48 rounded-xl border border-slate-200 bg-white p-1 shadow-lg dark:border-stone-700 dark:bg-stone-900"
          >
            {eintraege.map((eintrag, i) => {
              if (eintrag === "trenner") {
                return <div key={i} role="separator" className="my-1 h-px bg-slate-100 dark:bg-stone-800" />;
              }
              const Icon = eintrag.icon;
              return (
                <button
                  key={i}
                  type="button"
                  role="menuitem"
                  disabled={eintrag.disabled}
                  onClick={() => {
                    schliessen(false);
                    eintrag.onClick();
                  }}
                  className={`flex min-h-11 w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] md:min-h-0 font-medium disabled:opacity-40 ${
                    eintrag.destruktiv
                      ? "text-rose-600 hover:bg-rose-50 dark:text-rose-300 dark:hover:bg-rose-500/10"
                      : "text-slate-700 hover:bg-slate-100 dark:text-stone-200 dark:hover:bg-stone-800"
                  }`}
                >
                  {Icon && <Icon size={14} strokeWidth={2} className="shrink-0" />}
                  {eintrag.label}
                </button>
              );
            })}
          </div>,
          document.body,
        )}
    </>
  );
}
