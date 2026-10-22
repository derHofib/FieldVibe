import { Clock, Package } from "lucide-react";
import { SymbolKachel } from "../../../components/apple/SymbolKachel";
import type { PositionenDaten } from "./useVorgangPositionen";

interface VerwendungenListeProps {
  layout: "kompakt" | "dicht";
  positionenDaten: PositionenDaten;
}

/** Verwendetes Material und Leistungen aus dem Leistungsverzeichnis. */
export function VerwendungenListe({ layout, positionenDaten }: VerwendungenListeProps) {
  const { lvVerwendungEntfernenMutation, lvVerwendungen, materialVerwendungen } = positionenDaten;
  return (
    <>
      {(materialVerwendungen ?? []).length > 0 || (lvVerwendungen ?? []).length > 0 ? (
        layout === "dicht" ? (
          <div className="mb-2 overflow-x-auto">
            <h3 className="px-1 pb-1 text-xs font-medium text-label2">Verwendet</h3>
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-label2">
                  <th className="px-2 py-1 text-xs font-medium">Typ</th>
                  <th className="px-2 py-1 text-xs font-medium">Bezeichnung</th>
                  <th className="px-2 py-1 text-xs font-medium">Menge</th>
                  <th className="px-2 py-1"></th>
                </tr>
              </thead>
              <tbody>
                {(materialVerwendungen ?? []).map((v) => (
                  <tr key={`material-${v.id}`} className="border-t border-sep">
                    <td className="px-2 py-1.5">
                      <SymbolKachel icon={Package} farbe="orange" groesse={20} />
                    </td>
                    <td className="px-2 py-1.5 text-label">{v.material_bezeichnung}</td>
                    <td className="px-2 py-1.5 tabular-nums text-label2">
                      {v.menge} {v.material_einheit}
                    </td>
                    <td className="px-2 py-1.5"></td>
                  </tr>
                ))}
                {(lvVerwendungen ?? []).map((v) => (
                  <tr key={`lv-${v.id}`} className="border-t border-sep">
                    <td className="px-2 py-1.5">
                      <SymbolKachel icon={Clock} farbe="blue" groesse={20} />
                    </td>
                    <td className="px-2 py-1.5 text-label">{v.lv_bezeichnung}</td>
                    <td className="px-2 py-1.5 tabular-nums text-label2">
                      {v.menge} {v.lv_einheit}
                    </td>
                    <td className="px-2 py-1.5 text-right">
                      <button
                        onClick={() => lvVerwendungEntfernenMutation.mutate(v.id)}
                        disabled={lvVerwendungEntfernenMutation.isPending}
                        className="btn-touch text-xs text-st-fehlt disabled:opacity-50"
                      >
                        Entfernen
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="mb-2 space-y-1">
            <h3 className="px-1 text-xs font-medium text-label2">Verwendet</h3>
            {(materialVerwendungen ?? []).map((v) => (
              <div
                key={`material-${v.id}`}
                className="flex items-center justify-between gap-2 border border-sepstrong px-2 py-1.5 text-sm"
              >
                <span className="flex min-w-0 items-center gap-2 text-label">
                  <SymbolKachel icon={Package} farbe="orange" groesse={24} />
                  <span className="truncate">
                    {v.menge}× {v.material_bezeichnung}
                    <span className="ml-1.5 border border-sep px-1.5 py-0.5 text-xs text-label">
                      {v.material_einheit}
                    </span>
                  </span>
                </span>
              </div>
            ))}
            {(lvVerwendungen ?? []).map((v) => (
              <div
                key={`lv-${v.id}`}
                className="flex items-center justify-between gap-2 border border-sepstrong px-2 py-1.5 text-sm"
              >
                <span className="flex min-w-0 items-center gap-2 text-label">
                  <SymbolKachel icon={Clock} farbe="blue" groesse={24} />
                  <span className="truncate">
                    {v.menge}× {v.lv_bezeichnung}
                    <span className="ml-1.5 border border-sep px-1.5 py-0.5 text-xs text-label">
                      {v.lv_einheit}
                    </span>
                  </span>
                </span>
                <button
                  onClick={() => lvVerwendungEntfernenMutation.mutate(v.id)}
                  disabled={lvVerwendungEntfernenMutation.isPending}
                  className="btn-touch shrink-0 text-xs text-st-fehlt disabled:opacity-50"
                >
                  Entfernen
                </button>
              </div>
            ))}
          </div>
        )
      ) : null}

    </>
  );
}
