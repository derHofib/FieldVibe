import type { LucideIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export interface PulldownEintrag {
  label: string;
  icon?: LucideIcon;
  kuerzel?: string;
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
}: {
  trigger: (opts: { offen: boolean; toggeln: () => void; triggerRef: React.RefObject<HTMLButtonElement | null> }) => React.ReactNode;
  items: PulldownItem[];
  ariaLabel: string;
}) {
  const [offen, setOffen] = useState(false);
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);
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
    if (rect) setPosition({ top: rect.bottom + 4, left: Math.min(rect.left, window.innerWidth - 280) });
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
                  onClick={() => {
                    item.onSelect();
                    schliessen(true);
                  }}
                  className="group flex h-[30px] w-full items-center gap-2 rounded-[6px] px-2 text-left text-label hover:bg-tint-solid hover:text-white focus-visible:bg-tint-solid focus-visible:text-white focus-visible:outline-none"
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
