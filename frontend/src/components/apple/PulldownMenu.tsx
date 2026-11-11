import type { LucideIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export interface PulldownEintrag {
  label: string;
  icon?: LucideIcon;
  kuerzel?: string;
  /** Destruktive Aktion: rot statt Tint-Hover, steht üblicherweise am Ende. */
  destruktiv?: boolean;
  disabled?: boolean;
  onSelect: () => void;
}
export type PulldownItem = PulldownEintrag | "trenner";

/** Pull-down-Menue (Abschnitt 4.2): eigene Komponente, da es im Projekt noch
 * keine Menue-Komponente gab (siehe AUDIT.md). role="menu"/"menuitem",
 * Pfeiltasten navigieren, Esc schliesst und gibt den Fokus an den
 * Ausloeser zurueck, Klick ausserhalb schliesst ebenfalls. Rendert das
 * Panel per Portal in document.body, damit es nie von einem
 * overflow-hidden-Vorfahren (Toolbar) abgeschnitten wird. */
export function PulldownMenu({
  trigger,
  items,
  ariaLabel,
  richtung = "unten",
}: {
  trigger: (opts: { offen: boolean; toggeln: () => void; triggerRef: React.RefObject<HTMLButtonElement | null> }) => React.ReactNode;
  items: PulldownItem[];
  ariaLabel: string;
  /** "oben": Panel öffnet über dem Auslöser (Auslöser am unteren Fensterrand). */
  richtung?: "unten" | "oben";
}) {
  const [offen, setOffen] = useState(false);
  const [position, setPosition] = useState<{ top?: number; bottom?: number; left: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const eintraege = items.filter((i): i is PulldownEintrag => i !== "trenner");

  function schliessen(fokusZurueck: boolean) {
    setOffen(false);
    if (fokusZurueck) triggerRef.current?.focus();
  }

  function oeffnen() {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (rect) {
      const left = Math.min(rect.left, window.innerWidth - 280);
      setPosition(
        richtung === "oben"
          ? { bottom: window.innerHeight - rect.top + 4, left }
          : { top: rect.bottom + 4, left },
      );
    }
    setOffen(true);
  }

  useEffect(() => {
    if (!offen) return;
    itemRefs.current[0]?.focus();

    function aufKlickAussen(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) schliessen(false);
    }
    document.addEventListener("mousedown", aufKlickAussen);
    return () => document.removeEventListener("mousedown", aufKlickAussen);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offen]);

  function aufTastatur(e: React.KeyboardEvent) {
    const aktuell = itemRefs.current.findIndex((el) => el === document.activeElement);
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation(); // Esc im Menue soll ein umgebendes Seitenpanel nicht mitschliessen
      schliessen(true);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      itemRefs.current[(aktuell + 1) % eintraege.length]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      itemRefs.current[(aktuell - 1 + eintraege.length) % eintraege.length]?.focus();
    }
  }

  return (
    <>
      {trigger({ offen, toggeln: () => (offen ? schliessen(false) : oeffnen()), triggerRef })}
      {offen &&
        position &&
        createPortal(
          <div
            ref={panelRef}
            role="menu"
            aria-label={ariaLabel}
            onKeyDown={aufTastatur}
            className="fixed z-50 w-[264px] rounded-[10px] border-[0.5px] p-[5px]"
            style={{
              top: position.top,
              bottom: position.bottom,
              left: position.left,
              backgroundColor: "var(--menu)",
              backdropFilter: "blur(30px)",
              WebkitBackdropFilter: "blur(30px)",
              borderColor: "var(--sepstrong)",
              boxShadow: "0 10px 30px rgba(0,0,0,.22)",
            }}
          >
            {items.map((item, i) => {
              if (item === "trenner") return <div key={i} className="my-[5px] h-px bg-sep" />;
              const idx = eintraege.indexOf(item);
              const Icon = item.icon;
              return (
                <button
                  key={item.label}
                  ref={(el) => {
                    itemRefs.current[idx] = el;
                  }}
                  role="menuitem"
                  type="button"
                  disabled={item.disabled}
                  onClick={() => {
                    item.onSelect();
                    schliessen(true);
                  }}
                  // min-h-11: Touch-Ziel auf dem Handy (Accounts-Kartenliste), am Desktop kompakt
                  className={`group flex min-h-11 w-full items-center gap-2 rounded-[6px] px-2 text-left focus-visible:outline-none disabled:opacity-40 md:min-h-[30px] ${
                    item.destruktiv
                      ? "text-st-fehlt hover:bg-st-fehlt-bg focus-visible:bg-st-fehlt-bg"
                      : "text-label hover:bg-tint-solid hover:text-white focus-visible:bg-tint-solid focus-visible:text-white"
                  }`}
                >
                  {Icon && <Icon size={15} strokeWidth={2} className="shrink-0" />}
                  <span className="flex-1 text-[13px]">{item.label}</span>
                  {item.kuerzel && (
                    <span className="text-label2 group-hover:text-white/80">{item.kuerzel}</span>
                  )}
                </button>
              );
            })}
          </div>,
          document.body,
        )}
    </>
  );
}
