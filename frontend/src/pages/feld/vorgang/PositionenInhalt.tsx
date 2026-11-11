import { ApiError } from "../../../api/client";
import { SymbolKachel } from "../../../components/apple/SymbolKachel";
import { SearchableSelect } from "../../../components/SearchableSelect";
import type { Angebot, Anlage, LeistungsverzeichnisPosition, LeistungsverzeichnisVerwendung, LeistungsverzeichnisVerwendungMitDetails, Lieferant, Material, MaterialBedarf, MaterialBedarfMitDetails, MaterialBedarfZweck, MaterialVerwendung, MaterialVerwendungMitDetails, Rechnung } from "../../../types";
import { NEU_MATERIAL } from "./konstanten";
import type { UseMutationResult } from "@tanstack/react-query";
import { Clock, Package } from "lucide-react";
import type { Dispatch, SetStateAction } from "react";
import { Select } from "../../../components/apple/Select";

export function PositionenInhalt({
  setShowBedarfForm,
  showBedarfForm,
  setShowMaterialForm,
  showMaterialForm,
  setShowLeistungForm,
  showLeistungForm,
  bedarfMaterialId,
  setBedarfMaterialId,
  materialListe,
  bedarfNeuBezeichnung,
  setBedarfNeuBezeichnung,
  bedarfNeuEinheit,
  setBedarfNeuEinheit,
  bedarfNeuEinzelpreis,
  setBedarfNeuEinzelpreis,
  bedarfNeuLieferantId,
  setBedarfNeuLieferantId,
  lieferantenFuerNeuesMaterial,
  bedarfMenge,
  setBedarfMenge,
  bedarfZweck,
  setBedarfZweck,
  bedarfNotiz,
  setBedarfNotiz,
  materialBedarfMutation,
  materialBedarfe,
  layout,
  bedarfEntfernenMutation,
  materialVerwendungen,
  lvVerwendungen,
  lvVerwendungEntfernenMutation,
  kannDisponieren,
  angebotAusVorgangMutation,
  rechnungAusVorgangMutation,
  materialId,
  setMaterialId,
  setMaterialLagerId,
  meinFahrzeug,
  materialLagerId,
  lagerorte,
  materialMenge,
  setMaterialMenge,
  materialVerwendenMutation,
  leistungsverzeichnis,
  lvPositionId,
  setLvPositionId,
  lvMenge,
  setLvMenge,
  leistungVerwendenMutation,
}: {
  setShowBedarfForm: Dispatch<SetStateAction<boolean>>;
  showBedarfForm: boolean;
  setShowMaterialForm: Dispatch<SetStateAction<boolean>>;
  showMaterialForm: boolean;
  setShowLeistungForm: Dispatch<SetStateAction<boolean>>;
  showLeistungForm: boolean;
  bedarfMaterialId: string;
  setBedarfMaterialId: Dispatch<SetStateAction<string>>;
  materialListe: Material[] | undefined;
  bedarfNeuBezeichnung: string;
  setBedarfNeuBezeichnung: Dispatch<SetStateAction<string>>;
  bedarfNeuEinheit: string;
  setBedarfNeuEinheit: Dispatch<SetStateAction<string>>;
  bedarfNeuEinzelpreis: string;
  setBedarfNeuEinzelpreis: Dispatch<SetStateAction<string>>;
  bedarfNeuLieferantId: string;
  setBedarfNeuLieferantId: Dispatch<SetStateAction<string>>;
  lieferantenFuerNeuesMaterial: Lieferant[] | undefined;
  bedarfMenge: string;
  setBedarfMenge: Dispatch<SetStateAction<string>>;
  bedarfZweck: MaterialBedarfZweck;
  setBedarfZweck: Dispatch<SetStateAction<MaterialBedarfZweck>>;
  bedarfNotiz: string;
  setBedarfNotiz: Dispatch<SetStateAction<string>>;
  materialBedarfMutation: UseMutationResult<MaterialBedarf, unknown, void, unknown>;
  materialBedarfe: MaterialBedarfMitDetails[] | undefined;
  layout: "kompakt" | "dicht";
  bedarfEntfernenMutation: UseMutationResult<void, unknown, string, unknown>;
  materialVerwendungen: MaterialVerwendungMitDetails[] | undefined;
  lvVerwendungen: LeistungsverzeichnisVerwendungMitDetails[] | undefined;
  lvVerwendungEntfernenMutation: UseMutationResult<void, unknown, string, unknown>;
  kannDisponieren: boolean;
  angebotAusVorgangMutation: UseMutationResult<Angebot, unknown, void, unknown>;
  rechnungAusVorgangMutation: UseMutationResult<Rechnung, unknown, void, unknown>;
  materialId: string;
  setMaterialId: Dispatch<SetStateAction<string>>;
  setMaterialLagerId: Dispatch<SetStateAction<string>>;
  meinFahrzeug: Anlage | null | undefined;
  materialLagerId: string;
  lagerorte: Anlage[];
  materialMenge: string;
  setMaterialMenge: Dispatch<SetStateAction<string>>;
  materialVerwendenMutation: UseMutationResult<MaterialVerwendung, unknown, void, unknown>;
  leistungsverzeichnis: LeistungsverzeichnisPosition[] | undefined;
  lvPositionId: string;
  setLvPositionId: Dispatch<SetStateAction<string>>;
  lvMenge: string;
  setLvMenge: Dispatch<SetStateAction<string>>;
  leistungVerwendenMutation: UseMutationResult<LeistungsverzeichnisVerwendung, unknown, void, unknown>;
}) {
  return (
    <>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-heading text-fliess font-semibold text-label">Positionen</h2>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => setShowBedarfForm((v) => !v)}
              className="btn-touch text-sekundaer font-medium text-tint-text"
            >
              {showBedarfForm ? "Abbrechen" : "+ Material bestellen"}
            </button>
            <button
              onClick={() => setShowMaterialForm((v) => !v)}
              className="btn-touch text-sekundaer font-medium text-tint-text"
            >
              {showMaterialForm ? "Abbrechen" : "+ Material verwenden"}
            </button>
            <button
              onClick={() => setShowLeistungForm((v) => !v)}
              className="btn-touch text-sekundaer font-medium text-tint-text"
            >
              {showLeistungForm ? "Abbrechen" : "+ Leistung verwenden"}
            </button>
          </div>
        </div>

        {showBedarfForm && (
          <div className="mb-2 space-y-2 border rounded-[var(--radius-ap-md)] border-sepstrong p-2">
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
              <div className="space-y-2 rounded-[var(--radius-ap-md)] bg-fill p-2">
                <input
                  type="text"
                  value={bedarfNeuBezeichnung}
                  onChange={(e) => setBedarfNeuBezeichnung(e.target.value)}
                  placeholder="Bezeichnung"
                  className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
                />
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={bedarfNeuEinheit}
                    onChange={(e) => setBedarfNeuEinheit(e.target.value)}
                    placeholder="Einheit"
                    className="w-20 border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
                  />
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={bedarfNeuEinzelpreis}
                    onChange={(e) => setBedarfNeuEinzelpreis(e.target.value)}
                    placeholder="Preis (optional)"
                    className="flex-1 border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
                  />
                </div>
                <Select
                  value={bedarfNeuLieferantId}
                  onChange={(e) => setBedarfNeuLieferantId(e.target.value)}
                >
                  <option value="">Kein Lieferant hinterlegt</option>
                  {(lieferantenFuerNeuesMaterial ?? []).map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                    </option>
                  ))}
                </Select>
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
                className="flex-1 border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
              />
              <Select
                className="w-auto"
                value={bedarfZweck}
                onChange={(e) => setBedarfZweck(e.target.value as MaterialBedarfZweck)}
                groesse="kompakt"
              >
                <option value="bestellung">Zur Bestellung</option>
                <option value="angebot">Für Angebot</option>
              </Select>
            </div>
            <input
              type="text"
              value={bedarfNotiz}
              onChange={(e) => setBedarfNotiz(e.target.value)}
              placeholder="Notiz (optional)"
              className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
            />
            <button
              disabled={
                !bedarfMaterialId ||
                !bedarfMenge ||
                (bedarfMaterialId === NEU_MATERIAL && !bedarfNeuBezeichnung.trim()) ||
                materialBedarfMutation.isPending
              }
              onClick={() => materialBedarfMutation.mutate()}
              className="btn-touch btn-ap-primary w-full px-3 py-1.5 text-sekundaer"
            >
              Vormerken
            </button>
            {materialBedarfMutation.isError && (
              <p className="text-sekundaer text-st-fehlt">
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
              <table className="w-full border-collapse text-fliess">
                <thead>
                  <tr className="text-left text-label2">
                    <th className="px-2 py-1 text-meta font-medium">Menge</th>
                    <th className="px-2 py-1 text-meta font-medium">Material</th>
                    <th className="px-2 py-1 text-meta font-medium">Zweck</th>
                    <th className="px-2 py-1 text-meta font-medium">Status</th>
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
                            className="btn-touch text-sekundaer text-st-fehlt"
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
                  className="flex items-center justify-between border rounded-[var(--radius-ap-md)] border-sepstrong px-2 py-1.5 text-fliess"
                >
                  <span className="text-label">
                    {b.menge}× {b.material_bezeichnung}
                    <span className="ml-1.5 border rounded-[var(--radius-ap-pill)] border-sep px-1.5 py-0.5 text-meta text-label">
                      {b.zweck === "angebot" ? "Angebot" : "Bestellung"} · {b.status}
                    </span>
                  </span>
                  {b.status === "offen" && (
                    <button
                      onClick={() => bedarfEntfernenMutation.mutate(b.id)}
                      className="btn-touch text-sekundaer text-st-fehlt"
                    >
                      Entfernen
                    </button>
                  )}
                </div>
              ))}
            </div>
          ))}

        {(materialVerwendungen ?? []).length > 0 || (lvVerwendungen ?? []).length > 0 ? (
          layout === "dicht" ? (
            <div className="mb-2 overflow-x-auto">
              <h3 className="px-1 pb-1 text-sekundaer font-medium text-label2">Verwendet</h3>
              <table className="w-full border-collapse text-fliess">
                <thead>
                  <tr className="text-left text-label2">
                    <th className="px-2 py-1 text-meta font-medium">Typ</th>
                    <th className="px-2 py-1 text-meta font-medium">Bezeichnung</th>
                    <th className="px-2 py-1 text-meta font-medium">Menge</th>
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
                          className="btn-touch text-sekundaer text-st-fehlt disabled:opacity-50"
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
              <h3 className="px-1 text-sekundaer font-medium text-label2">Verwendet</h3>
              {(materialVerwendungen ?? []).map((v) => (
                <div
                  key={`material-${v.id}`}
                  className="flex items-center justify-between gap-2 border rounded-[var(--radius-ap-md)] border-sepstrong px-2 py-1.5 text-fliess"
                >
                  <span className="flex min-w-0 items-center gap-2 text-label">
                    <SymbolKachel icon={Package} farbe="orange" groesse={24} />
                    <span className="truncate">
                      {v.menge}× {v.material_bezeichnung}
                      <span className="ml-1.5 border rounded-[var(--radius-ap-pill)] border-sep px-1.5 py-0.5 text-meta text-label">
                        {v.material_einheit}
                      </span>
                    </span>
                  </span>
                </div>
              ))}
              {(lvVerwendungen ?? []).map((v) => (
                <div
                  key={`lv-${v.id}`}
                  className="flex items-center justify-between gap-2 border rounded-[var(--radius-ap-md)] border-sepstrong px-2 py-1.5 text-fliess"
                >
                  <span className="flex min-w-0 items-center gap-2 text-label">
                    <SymbolKachel icon={Clock} farbe="blue" groesse={24} />
                    <span className="truncate">
                      {v.menge}× {v.lv_bezeichnung}
                      <span className="ml-1.5 border rounded-[var(--radius-ap-pill)] border-sep px-1.5 py-0.5 text-meta text-label">
                        {v.lv_einheit}
                      </span>
                    </span>
                  </span>
                  <button
                    onClick={() => lvVerwendungEntfernenMutation.mutate(v.id)}
                    disabled={lvVerwendungEntfernenMutation.isPending}
                    className="btn-touch shrink-0 text-sekundaer text-st-fehlt disabled:opacity-50"
                  >
                    Entfernen
                  </button>
                </div>
              ))}
            </div>
          )
        ) : null}

        {kannDisponieren && (
          <button
            onClick={() => angebotAusVorgangMutation.mutate()}
            disabled={angebotAusVorgangMutation.isPending}
            className="btn-touch mb-2 btn-ap w-full px-3 py-1.5 text-sekundaer"
          >
            + Angebot aus diesem Vorgang erstellen
          </button>
        )}

        {kannDisponieren && (
          <button
            onClick={() => rechnungAusVorgangMutation.mutate()}
            disabled={rechnungAusVorgangMutation.isPending}
            className="btn-touch mb-2 btn-ap w-full px-3 py-1.5 text-sekundaer"
          >
            + Rechnung aus diesem Vorgang erstellen
          </button>
        )}

        {showMaterialForm && (
          <div className="space-y-2 border rounded-[var(--radius-ap-md)] border-sepstrong p-2">
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
              <Select
                value={materialLagerId}
                onChange={(e) => setMaterialLagerId(e.target.value)}
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
              </Select>
            )}
            <div className="flex gap-2">
              <input
                type="number"
                step="0.01"
                min="0"
                value={materialMenge}
                onChange={(e) => setMaterialMenge(e.target.value)}
                placeholder="Menge"
                className="flex-1 border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
              />
              <button
                disabled={!materialId || !materialLagerId || !materialMenge || materialVerwendenMutation.isPending}
                onClick={() => materialVerwendenMutation.mutate()}
                className="btn-touch btn-ap-primary shrink-0 px-3 py-1.5 text-sekundaer"
              >
                Erfassen
              </button>
            </div>
            {materialVerwendenMutation.isError && (
              <p className="text-sekundaer text-st-fehlt">
                {materialVerwendenMutation.error instanceof ApiError
                  ? materialVerwendenMutation.error.message
                  : "Fehler beim Erfassen"}
              </p>
            )}
          </div>
        )}

        {showLeistungForm && (
          <div className="space-y-2 border rounded-[var(--radius-ap-md)] border-sepstrong p-2">
            {(leistungsverzeichnis ?? []).length === 0 ? (
              <p className="text-sekundaer text-label2">
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
                    className="flex-1 border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
                  />
                  <button
                    disabled={!lvPositionId || !lvMenge || leistungVerwendenMutation.isPending}
                    onClick={() => leistungVerwendenMutation.mutate()}
                    className="btn-touch btn-ap-primary shrink-0 px-3 py-1.5 text-sekundaer"
                  >
                    Erfassen
                  </button>
                </div>
                {leistungVerwendenMutation.isError && (
                  <p className="text-sekundaer text-st-fehlt">
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
