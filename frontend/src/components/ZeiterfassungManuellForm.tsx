import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { ApiError } from "../api/client";
import { leistungsverzeichnisApi, vorgaengeApi, zeiterfassungApi } from "../api/endpoints";
import type { ZeiterfassungKategorie } from "../types";
import { SearchableSelect } from "./SearchableSelect";

const KATEGORIE_OPTIONEN: { value: ZeiterfassungKategorie; label: string }[] = [
  { value: "verwaltung", label: "Verwaltung" },
  { value: "fahrzeit", label: "Fahrzeit" },
  { value: "schulung", label: "Schulung" },
  { value: "pause", label: "Pause" },
  { value: "urlaub", label: "Urlaub" },
  { value: "krankheit", label: "Krankheit" },
  { value: "sonstiges", label: "Sonstiges" },
  { value: "auftrag", label: "Auftrag (nachgetragen)" },
];

function heuteAlsInput(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Datum + lokale Uhrzeit (aus <input type="time">) zu einem UTC-ISO-String --
 * new Date("YYYY-MM-DDTHH:mm") interpretiert ohne Zeitzonen-Suffix immer die
 * Browser-Ortszeit, .toISOString() liefert dann automatisch das passende UTC. */
function alsIso(datum: string, uhrzeit: string): string {
  return new Date(`${datum}T${uhrzeit}`).toISOString();
}

export function ZeiterfassungManuellForm({
  onClose,
  onGespeichert,
}: {
  onClose: () => void;
  onGespeichert: () => void;
}) {
  const [datum, setDatum] = useState(heuteAlsInput());
  const [startZeit, setStartZeit] = useState("08:00");
  const [endeZeit, setEndeZeit] = useState("16:00");
  const [kategorie, setKategorie] = useState<ZeiterfassungKategorie>("verwaltung");
  const [vorgangId, setVorgangId] = useState("");
  const [taetigkeit, setTaetigkeit] = useState("");
  const [abrechenbar, setAbrechenbar] = useState(false);
  const [lvPositionId, setLvPositionId] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);

  const { data: vorgaenge } = useQuery({
    queryKey: ["vorgaenge-fuer-zeiterfassung"],
    queryFn: () => vorgaengeApi.list(),
    enabled: kategorie === "auftrag",
  });

  const ausgewaehlterVorgang = (vorgaenge ?? []).find((v) => v.id === vorgangId);

  // SVS-Kopplung: der Stundenverrechnungssatz kommt aus dem Leistungs-
  // verzeichnis des Kunden des gewaehlten Vorgangs -- nur relevant, wenn
  // diese Zeit ueberhaupt abrechenbar ist.
  const { data: stundensaetze } = useQuery({
    queryKey: ["leistungsverzeichnis", ausgewaehlterVorgang?.kunde_id, "stundensaetze"],
    queryFn: () => leistungsverzeichnisApi.list(ausgewaehlterVorgang!.kunde_id, true),
    enabled: kategorie === "auftrag" && abrechenbar && !!ausgewaehlterVorgang,
  });

  const mutation = useMutation({
    mutationFn: () =>
      zeiterfassungApi.manuellErfassen({
        start_at: alsIso(datum, startZeit),
        ende_at: alsIso(datum, endeZeit),
        kategorie,
        vorgang_id: kategorie === "auftrag" ? vorgangId || undefined : undefined,
        taetigkeit: taetigkeit || undefined,
        abrechenbar: kategorie === "auftrag" ? abrechenbar : false,
        lv_position_id: kategorie === "auftrag" && abrechenbar ? lvPositionId || undefined : undefined,
      }),
    onSuccess: onGespeichert,
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Speichern fehlgeschlagen"),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    setFehler(null);
    if (kategorie === "auftrag" && !vorgangId) {
      setFehler("Bitte einen Vorgang auswählen");
      return;
    }
    if (alsIso(datum, endeZeit) <= alsIso(datum, startZeit)) {
      setFehler("Ende muss nach dem Start liegen");
      return;
    }
    mutation.mutate();
  }

  return (
    <form
      onSubmit={submit}
      className="space-y-3 border border-ind-line bg-ind-bg p-4"
    >
      <div className="grid grid-cols-3 gap-2">
        <div className="col-span-3 sm:col-span-1">
          <label className="mb-1 block text-xs font-medium text-ind-ink-2">
            Datum
          </label>
          <input
            type="date"
            value={datum}
            onChange={(e) => setDatum(e.target.value)}
            required
            className="btn-touch w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-ind-ink-2">
            Von
          </label>
          <input
            type="time"
            value={startZeit}
            onChange={(e) => setStartZeit(e.target.value)}
            required
            className="btn-touch w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-ind-ink-2">
            Bis
          </label>
          <input
            type="time"
            value={endeZeit}
            onChange={(e) => setEndeZeit(e.target.value)}
            required
            className="btn-touch w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
          />
        </div>
      </div>

      <div>
        <label className="mb-1 block text-xs font-medium text-ind-ink-2">
          Kategorie
        </label>
        <select
          value={kategorie}
          onChange={(e) => setKategorie(e.target.value as ZeiterfassungKategorie)}
          className="btn-touch w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
        >
          {KATEGORIE_OPTIONEN.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {kategorie === "auftrag" && (
        <div>
          <label className="mb-1 block text-xs font-medium text-ind-ink-2">
            Vorgang
          </label>
          <SearchableSelect
            options={(vorgaenge ?? []).map((v) => ({
              value: v.id,
              label: `${v.vorgangsnummer} – ${v.titel}`,
            }))}
            value={vorgangId}
            onChange={setVorgangId}
            placeholder="Vorgang suchen…"
          />
          <label className="mt-2 flex items-center gap-1.5 text-sm text-ind-ink-2">
            <input
              type="checkbox"
              checked={abrechenbar}
              onChange={(e) => setAbrechenbar(e.target.checked)}
              className="h-4 w-4 rounded-xs border-slate-300 dark:border-stone-600"
            />
            Abrechenbar
          </label>
          {abrechenbar && (stundensaetze ?? []).length > 0 && (
            <div className="mt-2">
              <label className="mb-1 block text-xs font-medium text-ind-ink-2">
                Stundenverrechnungssatz (optional)
              </label>
              <SearchableSelect
                options={(stundensaetze ?? []).map((s) => ({
                  value: s.id,
                  label: `${s.bezeichnung} – ${s.einzelpreis} €/${s.einheit}`,
                }))}
                value={lvPositionId}
                onChange={setLvPositionId}
                placeholder="Kein Stundensatz"
              />
            </div>
          )}
        </div>
      )}

      <div>
        <label className="mb-1 block text-xs font-medium text-ind-ink-2">
          Notiz (optional)
        </label>
        <input
          type="text"
          value={taetigkeit}
          onChange={(e) => setTaetigkeit(e.target.value)}
          placeholder="z.B. Materialbestellung, Ersatzteile abholen…"
          className="btn-touch w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
        />
      </div>

      {fehler && <p className="text-sm text-red-600 dark:text-red-400">{fehler}</p>}

      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm text-slate-600 dark:bg-stone-800 dark:text-stone-300"
        >
          Abbrechen
        </button>
        <button
          type="submit"
          disabled={mutation.isPending}
          className="btn-touch btn-clay rounded-md bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          Speichern
        </button>
      </div>
    </form>
  );
}
