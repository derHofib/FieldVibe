import { ApiError } from "../../../api/client";
import { SearchableSelect } from "../../../components/SearchableSelect";
import type { PositionenDaten } from "./useVorgangPositionen";

interface VerwendenFormulareProps {
  positionenDaten: PositionenDaten;
}

/** Formulare für Material- und Leistungsverwendung. */
export function VerwendenFormulare({ positionenDaten }: VerwendenFormulareProps) {
  const {
    lagerorte, leistungVerwendenMutation, leistungsverzeichnis, lvMenge, lvPositionId, materialId,
    materialLagerId, materialListe, materialMenge, materialVerwendenMutation, meinFahrzeug,
    setLvMenge, setLvPositionId, setMaterialId, setMaterialLagerId, setMaterialMenge,
    showLeistungForm, showMaterialForm,
  } = positionenDaten;
  return (
    <>
      {showMaterialForm && (
        <div className="space-y-2 border border-sepstrong p-2">
          <SearchableSelect
            value={materialId}
            onChange={(v) => {
              setMaterialId(v);
              // Fuer Techniker das eigene zugewiesene Fahrzeug als
              // Standard-Lagerort vorschlagen (siehe Techniker-
              // Zuweisungen-Seite) -- spart bei jedem Materialverbrauch
              // aus dem eigenen Fahrzeug den manuellen Auswahlschritt.
              setMaterialLagerId(meinFahrzeug?.id ?? "");
            }}
            placeholder="Material wählen…"
            options={(materialListe ?? []).map((m) => ({
              value: m.id,
              label: m.bezeichnung,
              sublabel: `(${m.bestand_gesamt} ${m.einheit} gesamt verfügbar)`,
            }))}
          />
          {materialId && (
            <select
              value={materialLagerId}
              onChange={(e) => setMaterialLagerId(e.target.value)}
              className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            >
              <option value="">Lagerort wählen…</option>
              {(materialListe?.find((m) => m.id === materialId)?.bestaende ?? []).map((b) => (
                <option key={b.lager_id} value={b.lager_id}>
                  {b.lager_bezeichnung} ({b.menge} verfügbar)
                </option>
              ))}
              {lagerorte
                .filter(
                  (l) => !materialListe?.find((m) => m.id === materialId)?.bestaende.some((b) => b.lager_id === l.id)
                )
                .map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.bezeichnung} (0 verfügbar)
                  </option>
                ))}
            </select>
          )}
          <div className="flex gap-2">
            <input
              type="number"
              step="0.01"
              min="0"
              value={materialMenge}
              onChange={(e) => setMaterialMenge(e.target.value)}
              placeholder="Menge"
              className="flex-1 border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
            <button
              disabled={!materialId || !materialLagerId || !materialMenge || materialVerwendenMutation.isPending}
              onClick={() => materialVerwendenMutation.mutate()}
              className="btn-touch btn-ap-primary shrink-0 px-3 py-1.5 text-sm"
            >
              Erfassen
            </button>
          </div>
          {materialVerwendenMutation.isError && (
            <p className="text-xs text-st-fehlt">
              {materialVerwendenMutation.error instanceof ApiError
                ? materialVerwendenMutation.error.message
                : "Fehler beim Erfassen"}
            </p>
          )}
        </div>
      )}

      {showLeistungForm && (
        <div className="space-y-2 border border-sepstrong p-2">
          {(leistungsverzeichnis ?? []).length === 0 ? (
            <p className="text-xs text-label2">
              Für diesen Kunden ist kein Leistungsverzeichnis hinterlegt.
            </p>
          ) : (
            <>
              <SearchableSelect
                value={lvPositionId}
                onChange={setLvPositionId}
                placeholder="Position wählen…"
                options={(leistungsverzeichnis ?? []).map((p) => ({
                  value: p.id,
                  label: p.bezeichnung,
                  sublabel: `${p.einzelpreis} €/${p.einheit}`,
                }))}
              />
              <div className="flex gap-2">
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={lvMenge}
                  onChange={(e) => setLvMenge(e.target.value)}
                  placeholder="Menge"
                  className="flex-1 border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
                />
                <button
                  disabled={!lvPositionId || !lvMenge || leistungVerwendenMutation.isPending}
                  onClick={() => leistungVerwendenMutation.mutate()}
                  className="btn-touch btn-ap-primary shrink-0 px-3 py-1.5 text-sm"
                >
                  Erfassen
                </button>
              </div>
              {leistungVerwendenMutation.isError && (
                <p className="text-xs text-st-fehlt">
                  {leistungVerwendenMutation.error instanceof ApiError
                    ? leistungVerwendenMutation.error.message
                    : "Fehler beim Erfassen"}
                </p>
              )}
            </>
          )}
        </div>
      )}
    </>
  );
}
