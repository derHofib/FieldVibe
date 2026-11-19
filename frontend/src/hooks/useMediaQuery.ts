import { useEffect, useState } from "react";

/** Folgt einer Media-Query (z. B. für Spalten, die sich nicht per CSS ausblenden lassen). */
export function useMediaQuery(abfrage: string): boolean {
  const [passt, setPasst] = useState(() => typeof window !== "undefined" && !!window.matchMedia?.(abfrage).matches);
  useEffect(() => {
    if (!window.matchMedia) return;
    const mql = window.matchMedia(abfrage);
    const aufAenderung = () => setPasst(mql.matches);
    aufAenderung();
    mql.addEventListener("change", aufAenderung);
    return () => mql.removeEventListener("change", aufAenderung);
  }, [abfrage]);
  return passt;
}
