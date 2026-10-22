import { ApiError } from "../../../api/client";
import { SearchableSelect } from "../../../components/SearchableSelect";
import type { MaterialBedarfZweck } from "../../../types";
import { NEU_MATERIAL } from "./konstanten";
import type { PositionenDaten } from "./useVorgangPositionen";

interface BedarfBereichProps {
  layout: "kompakt" | "dicht";
  positionenDaten: PositionenDaten;
}

/** Material-Bedarf (Bestellung/Angebot) anlegen und auflisten. */
export function BedarfBereich({ layout, positionenDaten }: BedarfBereichProps) {
  const {
    bedarfEntfernenMutation, bedarfMaterialId, bedarfMenge, bedarfNeuBezeichnung, bedarfNeuEinheit,
    bedarfNeuEinzelpreis, bedarfNeuLieferantId, bedarfNotiz, bedarfZweck,
    lieferantenFuerNeuesMaterial, materialBedarfMutation, materialBedarfe, materialListe,
    setBedarfMaterialId, setBedarfMenge, setBedarfNeuBezeichnung, setBedarfNeuEinheit,
    setBedarfNeuEinzelpreis, setBedarfNeuLieferantId, setBedarfNotiz, setBedarfZweck,
    showBedarfForm,
  } = positionenDaten;
  return (
    <>
      {showBedarfForm && (
        <div className="mb-2 space-y-2 border border-sepstrong p-2">
          <SearchableSelect
            value={bedarfMaterialId}
            onChange={setBedarfMaterialId}
            placeholder="Material wählen…"
            options={[
              ...(materialListe ?? []).map((m) => ({ value: m.id, label: m.bezeichnung })),
              { value: NEU_MATERIAL, label: "+ Neues Material anlegen…" },
            ]}
          />

          {bedarfMaterialId === NEU_MATERIAL && (
            <div className="space-y-2 border border-dashed border-sepstrong p-2">
              <input
                type="text"
                value={bedarfNeuBezeichnung}
                onChange={(e) => setBedarfNeuBezeichnung(e.target.value)}
                placeholder="Bezeichnung"
                className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
              <div className="flex gap-2">
                <input
                  type="text"
                  value={bedarfNeuEinheit}
                  onChange={(e) => setBedarfNeuEinheit(e.target.value)}
                  placeholder="Einheit"
                  className="w-20 border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
                />
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={bedarfNeuEinzelpreis}
                  onChange={(e) => setBedarfNeuEinzelpreis(e.target.value)}
                  placeholder="Preis (optional)"
                  className="flex-1 border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
                />
              </div>
              <select
                value={bedarfNeuLieferantId}
                onChange={(e) => setBedarfNeuLieferantId(e.target.value)}
                className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              >
                <option value="">Kein Lieferant hinterlegt</option>
                {(lieferantenFuerNeuesMaterial ?? []).map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="flex gap-2">
            <input
              type="number"
              step="0.01"
              min="0"
              value={bedarfMenge}
              onChange={(e) => setBedarfMenge(e.target.value)}
              placeholder="Menge"
              className="flex-1 border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
            <select
              value={bedarfZweck}
              onChange={(e) => setBedarfZweck(e.target.value as MaterialBedarfZweck)}
              className="border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            >
              <option value="bestellung">Zur Bestellung</option>
              <option value="angebot">Für Angebot</option>
            </select>
          </div>
          <input
            type="text"
            value={bedarfNotiz}
            onChange={(e) => setBedarfNotiz(e.target.value)}
            placeholder="Notiz (optional)"
            className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
          />
          <button
            disabled={
              !bedarfMaterialId ||
              !bedarfMenge ||
              (bedarfMaterialId === NEU_MATERIAL && !bedarfNeuBezeichnung.trim()) ||
              materialBedarfMutation.isPending
            }
            onClick={() => materialBedarfMutation.mutate()}
            className="btn-touch btn-ap-primary w-full px-3 py-1.5 text-sm"
          >
            Vormerken
          </button>
          {materialBedarfMutation.isError && (
            <p className="text-xs text-st-fehlt">
              {materialBedarfMutation.error instanceof ApiError
                ? materialBedarfMutation.error.message
                : "Fehler beim Vormerken"}
            </p>
          )}
        </div>
      )}

      {(materialBedarfe ?? []).length > 0 &&
        (layout === "dicht" ? (
          <div className="mb-2 overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-label2">
                  <th className="px-2 py-1 text-xs font-medium">Menge</th>
                  <th className="px-2 py-1 text-xs font-medium">Material</th>
                  <th className="px-2 py-1 text-xs font-medium">Zweck</th>
                  <th className="px-2 py-1 text-xs font-medium">Status</th>
                  <th className="px-2 py-1"></th>
                </tr>
              </thead>
              <tbody>
                {materialBedarfe!.map((b) => (
                  <tr key={b.id} className="border-t border-sep">
                    <td className="px-2 py-1.5 tabular-nums text-label">{b.menge}×</td>
                    <td className="px-2 py-1.5 text-label">{b.material_bezeichnung}</td>
                    <td className="px-2 py-1.5 text-label2">{b.zweck === "angebot" ? "Angebot" : "Bestellung"}</td>
                    <td className="px-2 py-1.5 text-label2">{b.status}</td>
                    <td className="px-2 py-1.5 text-right">
                      {b.status === "offen" && (
                        <button
                          onClick={() => bedarfEntfernenMutation.mutate(b.id)}
                          className="btn-touch text-xs text-st-fehlt"
                        >
                          Entfernen
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="mb-2 space-y-1">
            {materialBedarfe!.map((b) => (
              <div
                key={b.id}
                className="flex items-center justify-between border border-sepstrong px-2 py-1.5 text-sm"
              >
                <span className="text-label">
                  {b.menge}× {b.material_bezeichnung}
                  <span className="ml-1.5 border border-sep px-1.5 py-0.5 text-xs text-label">
                    {b.zweck === "angebot" ? "Angebot" : "Bestellung"} · {b.status}
                  </span>
                </span>
                {b.status === "offen" && (
                  <button
                    onClick={() => bedarfEntfernenMutation.mutate(b.id)}
                    className="btn-touch text-xs text-st-fehlt"
                  >
                    Entfernen
                  </button>
                )}
              </div>
            ))}
          </div>
        ))}

    </>
  );
}
