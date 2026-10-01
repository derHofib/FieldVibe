const KLICK_ANZAHL = 5;
const KLICK_FENSTER_MS = 2000;

/** Fuegt einen Klick hinzu und meldet, ob die letzten KLICK_ANZAHL Klicks in
 * KLICK_FENSTER_MS lagen. Nach Erfolg startet die Folge neu. */
export function klickFolge(zeiten: number[], jetzt: number): { zeiten: number[]; erreicht: boolean } {
  const neu = [...zeiten, jetzt].filter((t) => jetzt - t <= KLICK_FENSTER_MS);
  if (neu.length >= KLICK_ANZAHL) return { zeiten: [], erreicht: true };
  return { zeiten: neu, erreicht: false };
}

// e.code statt e.key: auf macOS liefert Alt+P ein Sonderzeichen als key.
export function istVersteckteTastenkombi(e: { code: string; shiftKey: boolean; altKey: boolean }): boolean {
  return e.code === "KeyP" && e.shiftKey && e.altKey;
}
