import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../../api/client";
import { rechnungenApi } from "../../api/endpoints";
import type { RechnungPositionQuelle, RechnungPositionVorschlag } from "../../types";
import { formatStunden } from "../../utils/rechnungAbrechnung";
import { Sheet } from "../apple/Sheet";

const GRUPPEN: { titel: string; quellen: RechnungPositionQuelle[] }[] = [
  { titel: "Arbeitszeit", quellen: ["zeit"] },
  { titel: "Leistungen", quellen: ["leistung"] },
  { titel: "Fahrt", quellen: ["fahrzeit", "fahrtkosten"] },
  { titel: "Material", quellen: ["material"] },
];

function materialText(n: number): string {
  return `${n} ${n === 1 ? "Material" : "Materialien"}`;
}

/** Zweistufiger Dialog (Sheet: mobil von unten, Desktop zentriert): erst
 * Vorgang des Rechnungs-Kunden waehlen, dann die abrechenbaren Posten
 * einzeln abhaken. Die Auswahl wird gesammelt ueber vorgangUebernehmen
 * angelegt. */
export function VorgangHinzufuegen({
  rechnungId,
  kundeId,
  offen,
  onClose,
}: {
  rechnungId: string;
  kundeId: string;
  offen: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [vorgangId, setVorgangId] = useState<string | null>(null);
  const [abgewaehlt, setAbgewaehlt] = useState<Set<number>>(new Set());
  const [stundensatz, setStundensatz] = useState("");

  const { data: vorgaenge, isLoading: vorgaengeLaden } = useQuery({
    queryKey: ["rechnungen", "abrechenbare-vorgaenge", kundeId],
    queryFn: () => rechnungenApi.abrechenbareVorgaenge(kundeId),
    enabled: offen,
  });

  const { data: vorschlaege, isLoading: vorschlaegeLaden } = useQuery({
    queryKey: ["rechnung", rechnungId, "vorgang-vorschlaege", vorgangId],
    queryFn: () => rechnungenApi.vorgangVorschlaege(rechnungId, vorgangId!),
    enabled: offen && !!vorgangId,
  });

  const schliessen = () => {
    setVorgangId(null);
    setAbgewaehlt(new Set());
    setStundensatz("");
    uebernehmen.reset();
    onClose();
  };

  const liste: RechnungPositionVorschlag[] = vorschlaege ?? [];
  const gewaehlt = liste.filter((_, i) => !abgewaehlt.has(i));
  const zeitGewaehlt = gewaehlt.some((v) => v.quelle === "zeit");

  const uebernehmen = useMutation({
    mutationFn: () =>
      rechnungenApi.vorgangUebernehmen(rechnungId, {
        vorgang_id: vorgangId!,
        stundensatz: zeitGewaehlt && Number(stundensatz) > 0 ? stundensatz : "0",
        auswahl: gewaehlt.map((v) => ({
          quelle: v.quelle,
          lv_position_id: v.lv_position_id ?? null,
          material_id: v.material_id ?? null,
        })),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rechnung", rechnungId] });
      queryClient.invalidateQueries({ queryKey: ["rechnungen", "abrechenbare-vorgaenge"] });
      schliessen();
    },
  });

  const bestaetigen = () => {
    if (
      zeitGewaehlt &&
      !(Number(stundensatz) > 0) &&
      !window.confirm("Kein Stundensatz eingetragen. Mit 0 € übernehmen? Du kannst ihn später in der Rechnung eintragen.")
    ) {
      return;
    }
    uebernehmen.mutate();
  };

  const toggle = (i: number) =>
    setAbgewaehlt((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  const zurueck = () => {
    setVorgangId(null);
    setAbgewaehlt(new Set());
    setStundensatz("");
    uebernehmen.reset();
  };

  return (
    <Sheet
      offen={offen}
      onClose={schliessen}
      titel={vorgangId ? "Posten wählen" : "Vorgang hinzufügen"}
      links={
        <button onClick={vorgangId ? zurueck : schliessen} className="btn-touch text-[17px] text-tint-text">
          {vorgangId ? "Zurück" : "Abbrechen"}
        </button>
      }
    >
      <div className="space-y-3 p-4">
        {!vorgangId && (
          <>
            {vorgaengeLaden && <p className="text-sm text-label2">Lädt…</p>}
            {vorgaenge && vorgaenge.length === 0 && (
              <p className="text-sm text-label2">Keine abrechenbaren Vorgänge für diesen Kunden.</p>
            )}
            <div className="space-y-1.5">
              {(vorgaenge ?? []).map((v) => (
                <button
                  key={v.vorgang_id}
                  onClick={() => setVorgangId(v.vorgang_id)}
                  className="btn-touch block w-full rounded-md bg-fill p-2 text-left text-sm"
                >
                  <span className="block truncate text-label">
                    {v.vorgangsnummer} · {v.titel}
                  </span>
                  <span className="block text-xs text-label2">
                    {formatStunden(Number(v.stunden_ohne_svs) + Number(v.stunden_mit_svs))} ·{" "}
                    {materialText(v.material_offen)}
                  </span>
                </button>
              ))}
            </div>
          </>
        )}

        {vorgangId && (
          <>
            {vorschlaegeLaden && <p className="text-sm text-label2">Lädt…</p>}
            {vorschlaege && liste.length === 0 && (
              <p className="text-sm text-label2">Keine abrechenbaren Posten.</p>
            )}
            {GRUPPEN.map((g) => {
              const zeilen = liste
                .map((v, i) => ({ v, i }))
                .filter(({ v }) => g.quellen.includes(v.quelle));
              if (zeilen.length === 0) return null;
              return (
                <div key={g.titel}>
                  <p className="mb-1 text-xs font-semibold text-label2">{g.titel}</p>
                  <div className="space-y-1.5">
                    {zeilen.map(({ v, i }) => (
                      <label key={i} className="flex items-start gap-2 rounded-md bg-fill p-2 text-sm">
                        <input
                          type="checkbox"
                          checked={!abgewaehlt.has(i)}
                          onChange={() => toggle(i)}
                          className="mt-1 h-3.5 w-3.5"
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block text-label">{v.beschreibung}</span>
                          <span className="block text-xs text-label2">
                            {v.menge} {v.einheit} × {v.einzelpreis} €
                          </span>
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              );
            })}

            {zeitGewaehlt && (
              <div>
                <label className="mb-1 block text-xs font-medium text-label2">Stundensatz (€/Std)</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  placeholder="0,00"
                  value={stundensatz}
                  onChange={(e) => setStundensatz(e.target.value)}
                  className="field-ap"
                />
              </div>
            )}

            {uebernehmen.isError && (
              <p className="text-xs text-st-fehlt">
                {uebernehmen.error instanceof ApiError ? uebernehmen.error.message : "Übernahme fehlgeschlagen"}
              </p>
            )}

            <button
              disabled={gewaehlt.length === 0 || uebernehmen.isPending}
              onClick={bestaetigen}
              className="btn-touch btn-ap btn-ap-primary w-full px-4 py-2 text-sm font-medium disabled:opacity-50"
            >
              Übernehmen
            </button>
          </>
        )}
      </div>
    </Sheet>
  );
}
