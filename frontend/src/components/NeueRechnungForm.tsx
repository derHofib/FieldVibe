import { useMutation, useQuery } from "@tanstack/react-query";
import { ListChecks } from "lucide-react";
import { useState } from "react";

import { kundenApi, rechnungenApi } from "../api/endpoints";
import { SearchableSelect } from "./SearchableSelect";

type Modus = "pauschal" | "einzelposten";

/** Gemeinsame Rechnung-Anlage fuer Mobile (RechnungenPage) und Desktop
 * (OfficeRechnungenPage) -- ersetzt die vormalige Schnellanlage in der
 * inzwischen aufgeteilten GeschaeftPage, die immer einen Gesamtbetrag
 * verlangte. "Einzelposten" legt die Rechnung leer an (wie beim Angebot
 * schon laenger ueblich) und der Aufrufer navigiert danach zur Detailseite,
 * wo Positionen erfasst werden -- "Pauschalbetrag" bleibt fuer die schnelle
 * Ein-Zeilen-Rechnung erhalten. */
export function NeueRechnungForm({
  onAbbrechen,
  onErfolg,
}: {
  onAbbrechen: () => void;
  onErfolg: (rechnungId: string) => void;
}) {
  const [modus, setModus] = useState<Modus>("einzelposten");
  const [kundeId, setKundeId] = useState("");
  const [betragNetto, setBetragNetto] = useState("");
  const [leistungsdatum, setLeistungsdatum] = useState("");

  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list() });

  const erstellen = useMutation({
    mutationFn: () =>
      rechnungenApi.create({
        kunde_id: kundeId,
        betrag_netto: modus === "pauschal" ? betragNetto : undefined,
        leistungsdatum: leistungsdatum || undefined,
      }),
    onSuccess: (rechnung) => onErfolg(rechnung.id),
  });

  return (
    <div className="space-y-3 rounded-lg bg-white p-4 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
      <div className="flex rounded-full bg-slate-100 p-1 dark:bg-stone-800">
        {(["pauschal", "einzelposten"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setModus(m)}
            className={`flex-1 rounded-full py-1.5 text-xs font-semibold ${
              modus === m
                ? "btn-clay bg-linear-to-r from-cyan-500 to-blue-600 text-white"
                : "text-slate-500 dark:text-stone-400"
            }`}
          >
            {m === "pauschal" ? "Pauschalbetrag" : "Einzelposten"}
          </button>
        ))}
      </div>

      <div>
        <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-stone-400">Kunde</label>
        <SearchableSelect
          value={kundeId}
          onChange={setKundeId}
          placeholder="Kunde wählen…"
          options={(kunden ?? []).map((k) => ({ value: k.id, label: `${k.name} (${k.kundennummer})` }))}
        />
      </div>

      {modus === "pauschal" ? (
        <>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-stone-400">
              Betrag netto (EUR)
            </label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={betragNetto}
              onChange={(e) => setBetragNetto(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-stone-400">
              Leistungsdatum (optional)
            </label>
            <input
              type="date"
              value={leistungsdatum}
              onChange={(e) => setLeistungsdatum(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
            <p className="mt-1 text-xs text-slate-400 dark:text-stone-500">
              Nur nötig, wenn abweichend vom Rechnungsdatum.
            </p>
          </div>
        </>
      ) : (
        <div className="flex items-start gap-2 rounded-lg border border-dashed border-cyan-200 bg-cyan-50/60 p-3 dark:border-cyan-500/30 dark:bg-cyan-500/10">
          <ListChecks size={16} strokeWidth={2} className="mt-0.5 shrink-0 text-cyan-700 dark:text-cyan-300" />
          <p className="text-xs text-cyan-800 dark:text-cyan-200">
            Positionen werden nach dem Anlegen erfasst — Material und Arbeitszeit einzeln.
          </p>
        </div>
      )}

      <div className="flex items-center gap-2">
        <button
          disabled={!kundeId || (modus === "pauschal" && !betragNetto) || erstellen.isPending}
          onClick={() => erstellen.mutate()}
          className="btn-touch flex-1 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Rechnung anlegen
        </button>
        <button onClick={onAbbrechen} className="btn-touch px-2 text-sm font-medium text-slate-500 dark:text-stone-400">
          Abbrechen
        </button>
      </div>
    </div>
  );
}
