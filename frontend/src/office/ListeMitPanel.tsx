import { X } from "lucide-react";
import type { ReactNode } from "react";

import { useEscapeSchliesst } from "../hooks/useEscapeSchliesst";
import { Karte } from "./OfficeUi";

/** Liste links, Detailpanel rechts (Muster der Vorgangsliste). Ohne Auswahl
 * nutzt die Liste die volle Breite. Escape und das X schließen das Panel. */
export function ListeMitPanel({
  liste,
  panel,
  panelTitel,
  onSchliessen,
}: {
  liste: ReactNode;
  /** null = kein Panel offen */
  panel: ReactNode | null;
  panelTitel: string;
  onSchliessen: () => void;
}) {
  useEscapeSchliesst(onSchliessen, panel !== null);

  return (
    <div
      className={`grid items-start gap-4 ${
        panel !== null ? "grid-cols-[minmax(0,1fr)_minmax(420px,520px)]" : "grid-cols-1"
      }`}
    >
      <div className="min-w-0">{liste}</div>
      {panel !== null && (
        <Karte className="sticky top-16 max-h-[calc(100vh-6rem)] overflow-y-auto">
          <section aria-label={panelTitel}>
            <div className="flex justify-end px-2 pt-2">
              <button
                onClick={onSchliessen}
                aria-label="Panel schließen"
                title="Schließen (Esc)"
                className="rounded-full p-1.5 text-label2 hover:bg-fill hover:text-label"
              >
                <X size={16} strokeWidth={2} />
              </button>
            </div>
            <div className="px-4 pb-4">{panel}</div>
          </section>
        </Karte>
      )}
    </div>
  );
}
