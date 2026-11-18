import { useEffect, useRef, useState } from "react";

// Ab dieser Breite des Panels passt die rechte Spalte (320px) neben den Inhalt,
// ohne dass Adressen umbrechen.
const ZWEISPALTIG_AB = 900;

/** Breite des Panels, nicht des Viewports: die Liste links ist verschiebbar. */
export function useZweispaltig(moeglich: boolean) {
  const wurzel = useRef<HTMLDivElement>(null);
  const [breit, setBreit] = useState(false);
  useEffect(() => {
    const el = wurzel.current;
    if (!el || !moeglich || typeof ResizeObserver === "undefined") return;
    const beobachter = new ResizeObserver(([eintrag]) => setBreit(eintrag.contentRect.width >= ZWEISPALTIG_AB));
    beobachter.observe(el);
    return () => beobachter.disconnect();
  }, [moeglich]);
  return { wurzel, zweispaltig: moeglich && breit };
}
