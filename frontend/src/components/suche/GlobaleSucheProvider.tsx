import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";

import { GlobaleSuche } from "./GlobaleSuche";

interface GlobaleSucheKontext {
  offen: boolean;
  /** Öffnet das Fenster, optional mit vorbelegtem Suchbegriff (Deep-Link `/suche?q=`). */
  oeffnen: (q?: string) => void;
  schliessen: () => void;
  umschalten: () => void;
}

const Kontext = createContext<GlobaleSucheKontext | null>(null);

export function useGlobaleSucheFenster(): GlobaleSucheKontext {
  const ctx = useContext(Kontext);
  if (!ctx) throw new Error("useGlobaleSucheFenster braucht einen GlobaleSucheProvider");
  return ctx;
}

export function GlobaleSucheProvider({ children }: { children: ReactNode }) {
  const [zustand, setZustand] = useState<{ offen: boolean; q: string; zaehler: number }>({
    offen: false,
    q: "",
    zaehler: 0,
  });

  const oeffnen = useCallback((q?: string) => {
    // Ohne neuen Suchbegriff bleibt ein offenes Fenster, wie es ist (Lupe/„/" bei offenem Fenster).
    setZustand((z) => (z.offen && q === undefined ? z : { offen: true, q: q ?? "", zaehler: z.zaehler + 1 }));
  }, []);
  const schliessen = useCallback(() => setZustand((z) => (z.offen ? { ...z, offen: false } : z)), []);
  const umschalten = useCallback(
    () => setZustand((z) => (z.offen ? { ...z, offen: false } : { offen: true, q: "", zaehler: z.zaehler + 1 })),
    [],
  );

  const wert = useMemo(
    () => ({ offen: zustand.offen, oeffnen, schliessen, umschalten }),
    [zustand.offen, oeffnen, schliessen, umschalten],
  );

  return (
    <Kontext.Provider value={wert}>
      {children}
      {zustand.offen && <GlobaleSuche key={zustand.zaehler} anfang={zustand.q} onSchliessen={schliessen} />}
    </Kontext.Provider>
  );
}
