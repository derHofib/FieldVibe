import { Check } from "lucide-react";

import { useTheme, type Appearance } from "../context/ThemeContext";

const OPTIONEN: { wert: Appearance; label: string }[] = [
  { wert: "system", label: "Automatisch" },
  { wert: "light", label: "Hell" },
  { wert: "dark", label: "Dunkel" },
];

/** Drei-Wege-Auswahl fuer die Einstellungen-Seiten (Abschnitt 2.1) -- als
 * gruppierte-Liste-Zeilen mit Haekchen rechts, analog zu anderen
 * Einfachauswahl-Listen im Auftrag (z. B. "Neuer Auftrag"-Sheet). */
export function AppearancePicker() {
  const { appearance, setAppearance } = useTheme();

  return (
    <div className="overflow-hidden rounded-[var(--radius-ap-card)] bg-cell">
      {OPTIONEN.map((opt, i) => (
        <button
          key={opt.wert}
          type="button"
          onClick={() => setAppearance(opt.wert)}
          className="flex w-full items-center justify-between px-4 py-3 text-left"
          style={i > 0 ? { boxShadow: "inset 0 0.5px 0 var(--sep)" } : undefined}
        >
          <span className="text-[17px] text-label">{opt.label}</span>
          {appearance === opt.wert && <Check size={18} strokeWidth={2.5} className="text-tint" />}
        </button>
      ))}
    </div>
  );
}
