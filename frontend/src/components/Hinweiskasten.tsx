import { AlertTriangle, CircleAlert, Info, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { zerlegeListenFehler } from "../utils/steuer";

type Ton = "warnung" | "fehler" | "info";

// Farbe nur über die Status-Token; das Icon trägt die Bedeutung zusätzlich,
// damit sie nicht allein an der Farbe hängt.
const TON: Record<Ton, { klasse: string; icon: LucideIcon }> = {
  warnung: { klasse: "bg-st-arbeit-bg text-st-arbeit", icon: AlertTriangle },
  fehler: { klasse: "bg-st-fehlt-bg text-st-fehlt", icon: CircleAlert },
  info: { klasse: "bg-st-neu-bg text-st-neu", icon: Info },
};

/** Hinweis-/Fehlerkasten mit Icon, optionalem Titel und Freitext-Inhalt. */
export function Hinweiskasten({
  ton,
  titel,
  children,
}: {
  ton: Ton;
  titel?: string;
  children?: ReactNode;
}) {
  const { klasse, icon: Icon } = TON[ton];
  return (
    <div
      role={ton === "fehler" ? "alert" : "status"}
      className={`flex items-start gap-2 rounded-[var(--radius-ap-md)] p-3 text-[13px] ${klasse}`}
    >
      <Icon size={16} strokeWidth={2} className="mt-px shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1 space-y-1">
        {titel && <p className="font-semibold">{titel}</p>}
        {children}
      </div>
    </div>
  );
}

/** Backend-Fehlermeldung: "Titel:\n- Punkt" wird als Aufzählung im Kasten
 * gezeigt, alles andere als einzelner Text (auf Wunsch ebenfalls im Kasten). */
export function FehlerMeldung({ meldung, alsKasten = false }: { meldung: string; alsKasten?: boolean }) {
  const liste = zerlegeListenFehler(meldung);
  if (liste) {
    return (
      <Hinweiskasten ton="fehler" titel={liste.titel}>
        <ul className="list-disc space-y-0.5 pl-4">
          {liste.punkte.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      </Hinweiskasten>
    );
  }
  if (alsKasten) {
    return (
      <Hinweiskasten ton="fehler">
        <p className="whitespace-pre-line">{meldung}</p>
      </Hinweiskasten>
    );
  }
  return (
    <p role="alert" className="text-xs whitespace-pre-line text-st-fehlt">
      {meldung}
    </p>
  );
}
