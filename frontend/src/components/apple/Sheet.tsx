import type { ReactNode } from "react";
import { useEffect } from "react";
import { createPortal } from "react-dom";

/** Sheet (Abschnitt 4.1/5.3): auf Mobil ein iOS-Sheet von unten mit Griff,
 * auf Desktop/Tablet (>=768px) derselbe Inhalt als zentrierter Dialog
 * (540px) -- eine Komponente statt zweier Implementierungen, Umschaltung
 * rein per CSS-Breakpoint. `links`/`rechts` sind die Leisten-Aktionen
 * (z. B. "Abbrechen"/"Weiter"). Traegt .ap-sheet-surface fuer die im
 * Dunkelmodus abweichenden Flaechenfarben (siehe index.css). */
export function Sheet({
  offen,
  onClose,
  titel,
  links,
  rechts,
  children,
}: {
  offen: boolean;
  onClose: () => void;
  titel: string;
  links?: ReactNode;
  rechts?: ReactNode;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!offen) return;
    function aufTaste(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", aufTaste);
    return () => document.removeEventListener("keydown", aufTaste);
  }, [offen, onClose]);

  if (!offen) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 md:items-center"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={titel}
        onClick={(e) => e.stopPropagation()}
        className="ap-sheet-surface flex max-h-[92vh] w-full flex-col rounded-t-[12px] bg-gbg md:max-h-[85vh] md:w-[540px] md:rounded-[12px]"
      >
        <div className="flex justify-center pt-2 md:hidden">
          <span className="h-[5px] w-9 rounded-full bg-label3" aria-hidden="true" />
        </div>
        <div className="flex items-center border-b-[0.5px] border-sep px-4 py-3">
          <div className="flex min-w-16 flex-1 justify-start">{links}</div>
          <h2 className="shrink-0 px-2 text-[17px] font-semibold text-label">{titel}</h2>
          <div className="flex min-w-16 flex-1 justify-end">{rechts}</div>
        </div>
        <div className="flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
