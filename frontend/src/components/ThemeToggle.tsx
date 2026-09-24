import { Moon, Sun } from "lucide-react";

import { useTheme } from "../context/ThemeContext";

/** Desktop-Toolbar-Umschalter (Abschnitt 2.1): ein Klick wechselt zwischen
 * hell/dunkel. Die volle Drei-Wege-Auswahl (Automatisch/Hell/Dunkel) gibt es
 * separat in den Einstellungen, siehe AppearancePicker.tsx. */
export function ThemeToggle() {
  const { angewandtesTheme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      aria-label={angewandtesTheme === "dark" ? "Helles Design" : "Dunkles Design"}
      title={angewandtesTheme === "dark" ? "Helles Design" : "Dunkles Design"}
      className="btn-ap-toolbar"
    >
      {angewandtesTheme === "dark" ? <Sun size={16} strokeWidth={2} /> : <Moon size={16} strokeWidth={2} />}
    </button>
  );
}
