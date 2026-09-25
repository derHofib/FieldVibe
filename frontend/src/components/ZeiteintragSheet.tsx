import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { ApiError } from "../api/client";
import { zeiterfassungApi } from "../api/endpoints";
import type { Zeiterfassung, ZeiterfassungKategorie } from "../types";
import { Sheet } from "./apple/Sheet";

// Lokale Kopie von toLocalInputValue aus VorgangDetailPage.tsx -- dort eine
// seiten-lokale Hilfsfunktion, kein geteiltes Modul (siehe dortiger
// Kommentar zu WOCHENTAGE fuer dasselbe Vorgehen).
function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// "auftrag" bewusst mit eigenem Label hier (anders als
// ZEITERFASSUNG_KATEGORIE_LABEL in utils/zeiterfassung.ts, das dafuer
// bewusst kein Label hat -- dort steht sonst die Vorgangsnummer). In diesem
// Sheet befinden wir uns immer schon im Kontext eines Vorgangs.
const KATEGORIE_OPTIONEN: { wert: ZeiterfassungKategorie; label: string }[] = [
  { wert: "auftrag", label: "Auftrag (dieser Vorgang)" },
  { wert: "fahrzeit", label: "Fahrzeit" },
  { wert: "verwaltung", label: "Verwaltung" },
  { wert: "schulung", label: "Schulung" },
  { wert: "pause", label: "Pause" },
  { wert: "urlaub", label: "Urlaub" },
  { wert: "krankheit", label: "Krankheit" },
  { wert: "sonstiges", label: "Sonstiges" },
];

const FORM_ID = "zeiteintrag-formular";

/** Sheet zum Anlegen ("+ Zeit nachtragen") oder Bearbeiten eines bereits
 * beendeten Zeiterfassungs-Eintrags an einem Vorgang (Stufe 1, siehe
 * docs/konzepte/ZEITERFASSUNG.md). Laufende Timer laufen nie hier durch --
 * die Zeit-Tab-Liste zeigt ohnehin nur Eintraege mit gesetztem ende_at. */
export function ZeiteintragSheet({
  offen,
  onClose,
  vorgangId,
  eintrag,
  onGespeichert,
}: {
  offen: boolean;
  onClose: () => void;
  vorgangId: string;
  eintrag?: Zeiterfassung | null;
  onGespeichert: () => void;
}) {
  const queryClient = useQueryClient();
  const istBearbeiten = !!eintrag;

  const jetzt = new Date();
  const vorEinerStunde = new Date(jetzt.getTime() - 60 * 60 * 1000);

  const [kategorie, setKategorie] = useState<ZeiterfassungKategorie>(eintrag?.kategorie ?? "auftrag");
  const [taetigkeit, setTaetigkeit] = useState(eintrag?.taetigkeit ?? "");
  const [startAt, setStartAt] = useState(
    toLocalInputValue(eintrag ? new Date(eintrag.start_at) : vorEinerStunde),
  );
  const [endeAt, setEndeAt] = useState(
    toLocalInputValue(eintrag?.ende_at ? new Date(eintrag.ende_at) : jetzt),
  );
  const [abrechenbar, setAbrechenbar] = useState(
    eintrag?.abrechenbar ?? kategorie === "auftrag",
  );
  const [error, setError] = useState<string | null>(null);

  function invalidateUndSchliessen() {
    queryClient.invalidateQueries({ queryKey: ["zeiterfassung", vorgangId] });
    queryClient.invalidateQueries({ queryKey: ["zeiterfassung-laufend"] });
    onGespeichert();
    onClose();
  }

  const anlegenMutation = useMutation({
    mutationFn: () =>
      zeiterfassungApi.manuellErfassen({
        vorgang_id: vorgangId,
        kategorie,
        start_at: new Date(startAt).toISOString(),
        ende_at: new Date(endeAt).toISOString(),
        taetigkeit,
        abrechenbar,
      }),
    onSuccess: invalidateUndSchliessen,
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen."),
  });

  const aktualisierenMutation = useMutation({
    mutationFn: () =>
      zeiterfassungApi.aktualisieren(eintrag!.id, {
        kategorie,
        start_at: new Date(startAt).toISOString(),
        ende_at: new Date(endeAt).toISOString(),
        taetigkeit,
        abrechenbar,
      }),
    onSuccess: invalidateUndSchliessen,
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen."),
  });

  const loeschenMutation = useMutation({
    mutationFn: () => zeiterfassungApi.loeschen(eintrag!.id),
    onSuccess: invalidateUndSchliessen,
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen."),
  });

  const speichertGerade = anlegenMutation.isPending || aktualisierenMutation.isPending;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (new Date(endeAt) <= new Date(startAt)) {
      setError("Ende muss nach dem Start liegen");
      return;
    }
    if (istBearbeiten) {
      aktualisierenMutation.mutate();
    } else {
      anlegenMutation.mutate();
    }
  }

  return (
    <Sheet
      offen={offen}
      onClose={onClose}
      titel={istBearbeiten ? "Zeit bearbeiten" : "Zeit nachtragen"}
      links={
        <button type="button" onClick={onClose} className="text-[17px] text-tint">
          Abbrechen
        </button>
      }
      rechts={
        <button
          type="submit"
          form={FORM_ID}
          disabled={speichertGerade}
          className="text-[17px] font-semibold text-tint disabled:opacity-40"
        >
          Speichern
        </button>
      }
    >
      <form id={FORM_ID} onSubmit={handleSubmit} className="space-y-4 p-4">
        {error && <p className="text-sm text-st-fehlt">{error}</p>}

        <div>
          <label className="mb-1 block text-xs font-medium text-label2">Kategorie</label>
          <select
            value={kategorie}
            onChange={(e) => setKategorie(e.target.value as ZeiterfassungKategorie)}
            className="field-ap"
          >
            {KATEGORIE_OPTIONEN.map((opt) => (
              <option key={opt.wert} value={opt.wert}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-label2">Tätigkeit</label>
          <input
            value={taetigkeit}
            onChange={(e) => setTaetigkeit(e.target.value)}
            placeholder="Was wurde gemacht?"
            className="field-ap"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-label2">Start</label>
            <input
              type="datetime-local"
              value={startAt}
              onChange={(e) => setStartAt(e.target.value)}
              className="field-ap"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-label2">Ende</label>
            <input
              type="datetime-local"
              value={endeAt}
              onChange={(e) => setEndeAt(e.target.value)}
              className="field-ap"
              required
            />
          </div>
        </div>

        <label className="flex items-center gap-2 text-sm text-label">
          <input
            type="checkbox"
            checked={abrechenbar}
            onChange={(e) => setAbrechenbar(e.target.checked)}
            className="h-4 w-4"
          />
          Abrechenbar
        </label>

        {istBearbeiten && (
          <button
            type="button"
            onClick={() => {
              if (window.confirm("Zeiteintrag wirklich löschen?")) {
                loeschenMutation.mutate();
              }
            }}
            disabled={loeschenMutation.isPending}
            className="btn-touch text-sm font-medium text-st-fehlt disabled:opacity-50"
          >
            Eintrag löschen
          </button>
        )}
      </form>
    </Sheet>
  );
}
