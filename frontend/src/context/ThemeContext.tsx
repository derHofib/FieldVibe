import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

// "system" = automatisch (folgt prefers-color-scheme), siehe Abschnitt 2.1
// des UI-Redesign-Auftrags. Kein gespeicherter Wert in localStorage bedeutet
// ebenfalls "system" -- das ist der Standard.
export type Appearance = "system" | "light" | "dark";
type AngewandtesTheme = "light" | "dark";

interface ThemeContextValue {
  appearance: Appearance;
  angewandtesTheme: AngewandtesTheme;
  setAppearance: (a: Appearance) => void;
  /** Desktop-Toolbar-Umschalter (Mond/Sonne): wechselt zwischen hell/dunkel
   * und verlaesst dabei "automatisch", falls das gerade aktiv war -- eine
   * bewusste Nutzerentscheidung ueberschreibt die Systemvorgabe. */
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);
const STORAGE_KEY = "ui.appearance";

function ermittleGespeicherteAppearance(): Appearance {
  try {
    const wert = localStorage.getItem(STORAGE_KEY);
    if (wert === "light" || wert === "dark" || wert === "system") return wert;
  } catch {
    // privater Modus o. Ae. -- dann eben immer "system" fuer diese Sitzung
  }
  return "system";
}

function systemPraefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

// Muss exakt dasselbe Ergebnis liefern wie das Inline-Script in index.html
// (dort dupliziert, weil es vor dem ersten Paint laufen muss, also bevor
// dieses Modul ueberhaupt geladen ist).
function ermittleAngewandtesTheme(appearance: Appearance): AngewandtesTheme {
  if (appearance === "system") return systemPraefersDark() ? "dark" : "light";
  return appearance;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [appearance, setAppearanceState] = useState<Appearance>(ermittleGespeicherteAppearance);
  const [angewandtesTheme, setAngewandtesTheme] = useState<AngewandtesTheme>(() =>
    ermittleAngewandtesTheme(appearance),
  );

  useEffect(() => {
    setAngewandtesTheme(ermittleAngewandtesTheme(appearance));
    try {
      localStorage.setItem(STORAGE_KEY, appearance);
    } catch {
      // siehe oben -- Auswahl gilt dann nur fuer diese Sitzung
    }
  }, [appearance]);

  // "Automatisch" reagiert live auf Systemwechsel (z. B. macOS' taeglicher
  // Hell/Dunkel-Wechsel oder ein manueller Wechsel in den Systemeinstellungen),
  // ohne dass ein Reload noetig ist.
  useEffect(() => {
    if (appearance !== "system") return;
    const medienabfrage = window.matchMedia("(prefers-color-scheme: dark)");
    const aufSystemwechsel = () => setAngewandtesTheme(medienabfrage.matches ? "dark" : "light");
    medienabfrage.addEventListener("change", aufSystemwechsel);
    return () => medienabfrage.removeEventListener("change", aufSystemwechsel);
  }, [appearance]);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", angewandtesTheme === "dark");
  }, [angewandtesTheme]);

  function toggleTheme() {
    setAppearanceState(angewandtesTheme === "dark" ? "light" : "dark");
  }

  return (
    <ThemeContext.Provider value={{ appearance, angewandtesTheme, setAppearance: setAppearanceState, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme muss innerhalb von ThemeProvider verwendet werden");
  return ctx;
}
