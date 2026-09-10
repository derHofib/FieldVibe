// Rechtsseitiges Slide-over-Panel -- Industry-Standardmuster fuer
// Detail-/Bearbeiten-Ansichten, die zu viel Inhalt fuer ein zentriertes
// Modal haben (z.B. verschachtelte Unterlisten) oder bei denen der Kontext
// der dahinterliegenden Seite sichtbar bleiben soll. Ersetzt in diesen
// Faellen das aeltere "fixed inset-0 flex items-center justify-center"-
// Modal-Rezept. Haarlinie statt Schatten-Karte, eckig statt rounded-xl --
// siehe fieldvibe-design-Skill.
import { X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

interface SeitenPanelProps {
  onClose: () => void;
  title: string;
  children: ReactNode;
  // Fuer Inhalte mit mehr Spalten (z.B. Formulare mit Nebeneinander-
  // Layouts) -- Default passt fuer die meisten Detail-/Formular-Panels.
  breit?: boolean;
}

export function SeitenPanel({ onClose, title, children, breit = false }: SeitenPanelProps) {
  // Panel wird zunaechst ausserhalb des sichtbaren Bereichs gerendert und
  // erst im naechsten Frame eingeblendet, damit die CSS-Transition beim
  // OEFFNEN greift (ein sofort gesetztes translate-x-0 haette keinen
  // Ausgangszustand zum Uebergang).
  const [eingeblendet, setEingeblendet] = useState(false);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setEingeblendet(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  return (
    <div
      className={`fixed inset-0 z-50 flex justify-end bg-slate-900/35 transition-opacity duration-200 ${
        eingeblendet ? "opacity-100" : "opacity-0"
      }`}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={`flex h-full w-full ${breit ? "max-w-2xl" : "max-w-md"} flex-col border-l border-ind-line bg-ind-bg shadow-2xl transition-transform duration-200 ease-out ${
          eingeblendet ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between gap-3 border-b border-ind-line px-5 py-4">
          <h2 className="min-w-0 truncate text-base font-bold text-ind-ink">{title}</h2>
          <button
            onClick={onClose}
            className="btn-touch btn-industry btn-industry-secondary btn-industry-icon shrink-0"
          >
            <X size={16} strokeWidth={1.5} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </div>
  );
}
