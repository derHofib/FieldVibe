import type { ReactNode } from "react";

/** Benannter Abschnitt der Vorgang-Übersicht: Versal-Überschrift (gleiche
 * Schrift wie AbschnittskopfB) mit der Aktion rechts im Kopf, damit klar ist,
 * was ein "Bearbeiten" bearbeitet. Im Office-Panel macht `.office-panel` aus
 * der Karte eine Fläche mit Haarlinie, in der Feld-App bleibt es eine Karte. */
export function Abschnitt({
  titel,
  aktion,
  children,
  className = "",
}: {
  titel: string;
  aktion?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section aria-label={titel} className={`card-ap p-4 ${className}`}>
      <div className="mb-2 flex min-h-6 items-center justify-between gap-2">
        <h2 className="text-sekundaer font-semibold tracking-wide text-label2 uppercase">{titel}</h2>
        {aktion}
      </div>
      {children}
    </section>
  );
}

export const ABSCHNITT_AKTION = "inline-flex min-h-11 items-center whitespace-nowrap text-sekundaer font-medium text-tint-text md:min-h-6";
