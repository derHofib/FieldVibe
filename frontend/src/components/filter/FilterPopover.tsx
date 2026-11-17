import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { OperatorSchritt, SpaltenSchritt, WertSchritt } from "./FilterSchritte";
import type { FilterFeld } from "./typen";
import type { FilterEntwurfZustand } from "./useFilterEntwurf";

/** Hülle im Stil von `PulldownMenu` (Fläche `--menu`, Radius 10, 0.5-px-Rand, Schatten). Positionslogik wie dort:
 * unter dem Auslöser, am rechten Fensterrand zurückgeschoben. Klick außerhalb und Esc schließen; Klicks auf
 * Elemente mit `data-filter-anker` zählen als "innen", damit deren eigener Handler entscheiden kann. */
export function PopoverRahmen({
  anker,
  breite = 264,
  onSchliessen,
  ariaLabel,
  neuPositionieren,
  children,
}: {
  anker: HTMLElement | null;
  breite?: number;
  /** Ändert sich dieser Wert (z. B. der Schritt), wird neu unter dem Anker positioniert. */
  neuPositionieren?: unknown;
  onSchliessen: () => void;
  ariaLabel: string;
  children: ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);

  useLayoutEffect(() => {
    const rect = anker?.getBoundingClientRect();
    if (!rect) return;
    const top = rect.bottom + 4;
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - breite - 8));
    setPosition((p) => (p && p.top === top && p.left === left ? p : { top, left }));
  }, [anker, breite, neuPositionieren]);

  useEffect(() => {
    function aufKlickAussen(e: MouseEvent) {
      const ziel = e.target as HTMLElement;
      if (panelRef.current?.contains(ziel) || ziel.closest?.("[data-filter-anker]")) return;
      onSchliessen();
    }
    document.addEventListener("mousedown", aufKlickAussen);
    return () => document.removeEventListener("mousedown", aufKlickAussen);
  }, [onSchliessen]);

  if (!position) return null;
  return createPortal(
    <div
      ref={panelRef}
      role="dialog"
      aria-label={ariaLabel}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          e.stopPropagation();
          onSchliessen();
          anker?.focus();
        }
      }}
      className="fixed z-50 rounded-[10px] border-[0.5px] p-[5px]"
      style={{
        top: position.top,
        left: position.left,
        width: breite,
        backgroundColor: "var(--menu)",
        backdropFilter: "blur(30px)",
        WebkitBackdropFilter: "blur(30px)",
        borderColor: "var(--sepstrong)",
        boxShadow: "0 10px 30px rgba(0,0,0,.22)",
      }}
    >
      {children}
    </div>,
    document.body,
  );
}

/** Office: die drei Schritte (Spalte, Bedingung, Wert) im Popover. */
export function FilterPopover<T>({
  felder,
  e,
  anker,
  onSuche,
}: {
  felder: FilterFeld<T>[];
  e: FilterEntwurfZustand<T>;
  anker: HTMLElement | null;
  onSuche: (text: string) => void;
}) {
  const entwurf = e.entwurf;
  if (!entwurf) return null;
  return (
    <PopoverRahmen anker={anker} breite={entwurf.schritt === 3 ? 320 : 264} neuPositionieren={entwurf.schritt} onSchliessen={e.schliessen} ariaLabel="Filter hinzufügen">
      {entwurf.schritt === 1 && <SpaltenSchritt felder={felder} e={e} variante="office" onSuche={onSuche} />}
      {entwurf.schritt === 2 && <OperatorSchritt e={e} variante="office" />}
      {entwurf.schritt === 3 && <WertSchritt e={e} variante="office" />}
    </PopoverRahmen>
  );
}
