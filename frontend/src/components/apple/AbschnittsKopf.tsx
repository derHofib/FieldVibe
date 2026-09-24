import type { ReactNode } from "react";

/** Abschnittskopf Variante A (Abschnitt 4.2): grosse Listen-Übersichts-
 * Überschrift, z. B. "Heute"/"Diese Woche" in der Auftragsliste. */
export function AbschnittskopfA({ titel, anzahl }: { titel: string; anzahl?: number }) {
  return (
    <div className="flex items-baseline justify-between px-5 pt-[18px] pb-2">
      <h2 className="ap-heading text-xl font-bold text-label">{titel}</h2>
      {anzahl !== undefined && <span className="text-[15px] text-label2">{anzahl}</span>}
    </div>
  );
}

/** Abschnittskopf Variante B (Abschnitt 4.2): kleine Versal-Überschrift vor
 * einer Gruppierten Liste, z. B. "HERKUNFT"/"PROJEKT"/"OPTIONEN". */
export function AbschnittskopfB({ titel }: { titel: string }) {
  return (
    <p className="px-8 pt-[22px] pb-[7px] text-[13px] font-semibold tracking-wide text-label2 uppercase">{titel}</p>
  );
}

/** Fußzeile unter einer Gruppierten Liste (Abschnitt 4.2), z. B. Hinweistext. */
export function AbschnittsFusszeile({ children }: { children: ReactNode }) {
  return <p className="px-8 pt-[7px] text-[13px] text-label2">{children}</p>;
}
