
import type { MaengelDaten } from "./useVorgangMaengel";

interface VerknuepfteAufgabenProps {
  maengelDaten: MaengelDaten;
}

/** Rein anzeigende Liste der mit dem Vorgang verknüpften Projektaufgaben. */
export function VerknuepfteAufgaben({ maengelDaten }: VerknuepfteAufgabenProps) {
  const { verknuepfteAufgaben } = maengelDaten;
  return (
    <div className="scroll-mt-4 card-ap p-3">
      <h2 className="font-heading mb-2 text-sm font-semibold uppercase tracking-wide text-label">Verknüpfte Aufgaben</h2>
      {/* Rein anzeigend: Bearbeitung nur ueber das Projekte-Kanban in der
          Office-Oberflaeche, kein Statusabgleich zurueck zum Vorgang. */}
      <div className="space-y-1.5">
        {verknuepfteAufgaben!.map((a) => (
          <div key={a.id} className="border border-sepstrong p-2 text-sm">
            <div className="flex items-start justify-between gap-2">
              <p className="text-label">{a.titel}</p>
              <span className="shrink-0 border border-sep px-2 py-0.5 text-xs font-medium text-label">
                {a.prioritaet}
              </span>
            </div>
            <div className="mt-1 flex items-center justify-between text-xs text-label2">
              <span>
                {a.checkliste.length > 0
                  ? `${a.checkliste.filter((p) => p.erledigt).length}/${a.checkliste.length} erledigt`
                  : a.zugewiesener_name || "Nicht zugewiesen"}
              </span>
              {a.faelligkeit_am && <span>fällig {a.faelligkeit_am}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
