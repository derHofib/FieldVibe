import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ListChecks } from "lucide-react";
import { useState } from "react";

import { ApiError } from "../api/client";
import { kundenApi, rechnungenApi } from "../api/endpoints";
import { formatStunden, zaehleFehlendeSaetze } from "../utils/rechnungAbrechnung";
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
  const [ausgewaehlt, setAusgewaehlt] = useState<Set<string>>(new Set());
  const [saetze, setSaetze] = useState<Record<string, string>>({});
  const queryClient = useQueryClient();

  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list() });

  const { data: vorgaenge, isLoading: vorgaengeLaden } = useQuery({
    queryKey: ["rechnungen", "abrechenbare-vorgaenge", kundeId],
    queryFn: () => rechnungenApi.abrechenbareVorgaenge(kundeId),
    enabled: modus === "einzelposten" && !!kundeId,
  });

  const waehleKunde = (id: string) => {
    setKundeId(id);
    setAusgewaehlt(new Set());
    setSaetze({});
  };

  const toggle = (id: string) =>
    setAusgewaehlt((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const auswahl = modus === "einzelposten" ? (vorgaenge ?? []).filter((v) => ausgewaehlt.has(v.vorgang_id)) : [];

  const erstellen = useMutation({
    mutationFn: () =>
      rechnungenApi.create({
        kunde_id: kundeId,
        betrag_netto: modus === "pauschal" ? betragNetto : undefined,
        leistungsdatum: leistungsdatum || undefined,
        vorgaenge:
          auswahl.length > 0
            ? auswahl.map((v) => ({ vorgang_id: v.vorgang_id, stundensatz: saetze[v.vorgang_id] || "0" }))
            : undefined,
      }),
    onSuccess: (rechnung) => {
      queryClient.invalidateQueries({ queryKey: ["rechnungen", "abrechenbare-vorgaenge"] });
      onErfolg(rechnung.id);
    },
  });

  const anlegen = () => {
    const fehlend = zaehleFehlendeSaetze(auswahl, ausgewaehlt, saetze);
    if (
      fehlend > 0 &&
      !window.confirm(
        `Für ${fehlend} ${fehlend === 1 ? "Vorgang" : "Vorgänge"} ist kein Stundensatz hinterlegt. Mit 0 € anlegen? Den Satz kannst du später in der Rechnung eintragen.`,
      )
    ) {
      return;
    }
    erstellen.mutate();
  };

  return (
    <div className="space-y-3 card-ap p-4">
      <div className="flex rounded-full bg-fill p-1">
        {(["pauschal", "einzelposten"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setModus(m)}
            className={`flex-1 rounded-full py-1.5 text-xs font-semibold ${
              modus === m
                ? "btn-ap-primary text-white"
                : "text-label2"
            }`}
          >
            {m === "pauschal" ? "Pauschalbetrag" : "Einzelposten"}
          </button>
        ))}
      </div>

      <div>
        <label className="mb-1 block text-xs font-medium text-label2">Kunde</label>
        <SearchableSelect
          value={kundeId}
          onChange={waehleKunde}
          placeholder="Kunde wählen…"
          options={(kunden ?? []).map((k) => ({ value: k.id, label: `${k.name} (${k.kundennummer})` }))}
        />
      </div>

      {modus === "pauschal" ? (
        <>
          <div>
            <label className="mb-1 block text-xs font-medium text-label2">
              Betrag netto (EUR)
            </label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={betragNetto}
              onChange={(e) => setBetragNetto(e.target.value)}
              className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-label2">
              Leistungsdatum (optional)
            </label>
            <input
              type="date"
              value={leistungsdatum}
              onChange={(e) => setLeistungsdatum(e.target.value)}
              className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
            <p className="mt-1 text-xs text-label2">
              Nur nötig, wenn abweichend vom Rechnungsdatum.
            </p>
          </div>
        </>
      ) : (
        <>
          {kundeId && vorgaengeLaden && <p className="text-xs text-label2">Lädt offene Stunden…</p>}
          {kundeId && vorgaenge && vorgaenge.length === 0 && (
            <p className="text-xs text-label2">Keine offenen abrechenbaren Stunden für diesen Kunden.</p>
          )}
          {vorgaenge && vorgaenge.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-label2">Vorgänge mit offenen Stunden</p>
              {vorgaenge.map((v) => {
                const gewaehlt = ausgewaehlt.has(v.vorgang_id);
                return (
                  <div key={v.vorgang_id} className="rounded-md bg-fill px-2 py-1.5 text-sm">
                    <label className="flex items-start gap-2">
                      <input
                        type="checkbox"
                        checked={gewaehlt}
                        onChange={() => toggle(v.vorgang_id)}
                        className="mt-1 h-3.5 w-3.5"
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-label">
                          {v.vorgangsnummer} · {v.titel}
                        </span>
                        <span className="block text-xs text-label2">
                          {formatStunden(Number(v.stunden_ohne_svs) + Number(v.stunden_mit_svs))}
                          {Number(v.stunden_mit_svs) > 0 && ` · davon ${formatStunden(v.stunden_mit_svs)} mit SVS`}
                        </span>
                      </span>
                    </label>
                    {gewaehlt && Number(v.stunden_ohne_svs) > 0 && (
                      <div className="mt-1.5 pl-6">
                        <label className="mb-1 block text-xs font-medium text-label2">Stundensatz (€/Std)</label>
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          placeholder="0,00"
                          value={saetze[v.vorgang_id] ?? ""}
                          onChange={(e) => setSaetze((prev) => ({ ...prev, [v.vorgang_id]: e.target.value }))}
                          className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
                        />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          {ausgewaehlt.size === 0 && (
            <div className="flex items-start gap-2 rounded-lg border border-dashed border-cyan-200 bg-cyan-50/60 p-3 dark:border-cyan-500/30 dark:bg-cyan-500/10">
              <ListChecks size={16} strokeWidth={2} className="mt-0.5 shrink-0 text-cyan-700 dark:text-cyan-300" />
              <p className="text-xs text-cyan-800 dark:text-cyan-200">
                Ohne Auswahl werden die Positionen nach dem Anlegen erfasst — Material und Arbeitszeit einzeln.
              </p>
            </div>
          )}
        </>
      )}

      {erstellen.isError && (
        <p className="text-xs text-st-fehlt">
          {erstellen.error instanceof ApiError ? erstellen.error.message : "Rechnung konnte nicht angelegt werden"}
        </p>
      )}

      <div className="flex items-center gap-2">
        <button
          disabled={!kundeId || (modus === "pauschal" && !betragNetto) || erstellen.isPending}
          onClick={anlegen}
          className="btn-touch flex-1 rounded-md btn-ap-primary px-4 py-2 text-sm font-medium disabled:opacity-50"
        >
          Rechnung anlegen
        </button>
        <button onClick={onAbbrechen} className="btn-touch px-2 text-sm font-medium text-label2">
          Abbrechen
        </button>
      </div>
    </div>
  );
}
