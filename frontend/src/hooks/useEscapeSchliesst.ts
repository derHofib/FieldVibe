import { useEffect, useRef } from "react";

/** Schließt ein Panel per Escape. `aktiv=false` unterdrückt das (z. B. bei
 * ungesendetem Entwurf). Ein offenes AktionsMenue verbraucht Escape selbst
 * und erreicht dieses Dokument-Listener nicht. */
export function useEscapeSchliesst(onSchliessen: () => void, aktiv = true) {
  const callback = useRef(onSchliessen);
  callback.current = onSchliessen;

  useEffect(() => {
    if (!aktiv) return;
    const beiTaste = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !e.defaultPrevented) callback.current();
    };
    document.addEventListener("keydown", beiTaste);
    return () => document.removeEventListener("keydown", beiTaste);
  }, [aktiv]);
}
