import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";

const FOKUSSIERBAR = "button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex='-1'])";

/**
 * Anlegen-/Bearbeiten-Formular außerhalb der Liste: auf dem Handy als Sheet von
 * unten, ab md (Office, Desktop) als Panel von rechts. Eine Komponente für
 * beide, damit Feld-App-Seiten, die im Office eingebettet laufen, nicht
 * verzweigen müssen.
 */
export function SeitenPanel({
  offen,
  titel,
  onClose,
  children,
}: {
  offen: boolean;
  titel: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const titelId = useId();
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!offen) return;
    const vorher = document.activeElement as HTMLElement | null;
    // Fokus ins Formular statt auf "Schließen", damit sofort getippt werden kann
    const ziel = boxRef.current?.querySelector<HTMLElement>("input, select, textarea") ?? boxRef.current;
    ziel?.focus();
    return () => vorher?.focus?.();
  }, [offen]);

  if (!offen) return null;

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
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
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 md:items-stretch md:justify-end"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      onKeyDown={onKeyDown}
    >
      <div
        ref={boxRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titelId}
        tabIndex={-1}
        className="flex max-h-[90vh] w-full flex-col rounded-t-2xl bg-white shadow-xl outline-none md:max-h-none md:max-w-md md:rounded-none dark:bg-stone-900 dark:ring-1 dark:ring-stone-800"
      >
        <div className="flex items-center justify-between gap-2 px-4 pt-4 pb-2">
          <h2 id={titelId} className="text-base font-semibold text-slate-900 dark:text-stone-100">
            {titel}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Schließen"
            className="btn-touch rounded-md p-1 text-slate-500 hover:bg-slate-100 dark:text-stone-400 dark:hover:bg-stone-800"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <div className="space-y-3 overflow-y-auto px-4 pb-4">{children}</div>
      </div>
    </div>
  );
}
