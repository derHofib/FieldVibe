import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { gespeicherteFilterApi } from "../api/endpoints";
import { ApiError } from "../api/client";
import type { GespeicherterFilter, GespeicherterFilterEntitaet } from "../types";

function filtersEqual(a: Record<string, string>, b: Record<string, string>): boolean {
  const aKeys = Object.keys(a).filter((k) => a[k]);
  const bKeys = Object.keys(b).filter((k) => b[k]);
  if (aKeys.length !== bKeys.length) return false;
  return aKeys.every((k) => a[k] === b[k]);
}

/** Wiederverwendbare Leiste fuer benannte Filter-Vorlagen (Standort, Kunde,
 * Assets, Aufträge...): laedt/wendet gespeicherte Filter-Sets an, erlaubt
 * das Speichern des aktuell aktiven Filters unter einem Namen sowie das
 * Markieren einer Vorlage als Standard -- die dann beim naechsten Aufruf der
 * jeweiligen Liste automatisch angewendet wird. */
export function FilterVorlagenLeiste({
  entitaet,
  filter,
  onApply,
}: {
  entitaet: GespeicherterFilterEntitaet;
  filter: Record<string, string>;
  onApply: (filterJson: Record<string, string>) => void;
}) {
  const queryClient = useQueryClient();
  const appliedDefault = useRef(false);
  const [zeigeSpeichern, setZeigeSpeichern] = useState(false);
  const [name, setName] = useState("");
  const [alsStandard, setAlsStandard] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: vorlagen } = useQuery({
    queryKey: ["gespeicherte-filter", entitaet],
    queryFn: () => gespeicherteFilterApi.list(entitaet),
  });

  useEffect(() => {
    if (appliedDefault.current || !vorlagen) return;
    appliedDefault.current = true;
    const standard = vorlagen.find((v) => v.ist_standard);
    if (standard) onApply(standard.filter_json);
    // onApply kommt vom Elternteil neu bei jedem Render -- nur beim ersten
    // Laden der Vorlagen soll automatisch angewendet werden.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vorlagen]);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["gespeicherte-filter", entitaet] });

  const createMutation = useMutation({
    mutationFn: () =>
      gespeicherteFilterApi.create({ entitaet, name, filter_json: filter, ist_standard: alsStandard }),
    onSuccess: () => {
      invalidate();
      setZeigeSpeichern(false);
      setName("");
      setAlsStandard(false);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Vorlage konnte nicht gespeichert werden"),
  });

  const standardMutation = useMutation({
    mutationFn: (v: GespeicherterFilter) => gespeicherteFilterApi.update(v.id, { ist_standard: !v.ist_standard }),
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => gespeicherteFilterApi.remove(id),
    onSuccess: invalidate,
  });

  const hatAktivenFilter = Object.values(filter).some((v) => !!v);

  return (
    <div className="space-y-2">
      {(vorlagen ?? []).length > 0 && (
        <div className="-mx-3 flex gap-2 overflow-x-auto px-3 pb-1">
          {vorlagen!.map((v) => {
            const aktiv = filtersEqual(filter, v.filter_json);
            return (
              <div
                key={v.id}
                className={`flex shrink-0 items-center gap-1 rounded-full py-1.5 pl-3 pr-1.5 text-xs font-medium ${
                  aktiv
                    ? "bg-gradient-to-r from-cyan-500 to-blue-600 text-white"
                    : "bg-white text-slate-600 shadow-sm dark:bg-slate-900 dark:text-slate-300 dark:shadow-none dark:ring-1 dark:ring-slate-800"
                }`}
              >
                <button onClick={() => onApply(v.filter_json)} className="btn-touch whitespace-nowrap">
                  {v.ist_standard && "★ "}
                  {v.name}
                </button>
                <button
                  onClick={() => standardMutation.mutate(v)}
                  title={v.ist_standard ? "Als Standard entfernen" : "Als Standard setzen"}
                  className={`btn-touch px-1 ${aktiv ? "text-white/80" : "text-slate-400 dark:text-slate-500"}`}
                >
                  {v.ist_standard ? "★" : "☆"}
                </button>
                <button
                  onClick={() => {
                    if (window.confirm(`Filter-Vorlage "${v.name}" löschen?`)) deleteMutation.mutate(v.id);
                  }}
                  className={`btn-touch px-1 ${aktiv ? "text-white/80" : "text-slate-400 dark:text-slate-500"}`}
                >
                  ×
                </button>
              </div>
            );
          })}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        {hatAktivenFilter && (
          <button
            onClick={() => onApply({})}
            className="btn-touch text-xs text-slate-500 underline dark:text-slate-400"
          >
            Filter zurücksetzen
          </button>
        )}
        <button
          onClick={() => setZeigeSpeichern((v) => !v)}
          disabled={!hatAktivenFilter}
          className="btn-touch text-xs text-blue-700 underline disabled:opacity-40 dark:text-blue-400"
        >
          {zeigeSpeichern ? "Abbrechen" : "Aktuellen Filter als Vorlage speichern…"}
        </button>
      </div>

      {zeigeSpeichern && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg bg-slate-50 p-2 dark:bg-slate-800/60">
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name der Vorlage"
            className="btn-touch min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          />
          <label className="flex shrink-0 items-center gap-1 text-xs text-slate-600 dark:text-slate-300">
            <input type="checkbox" checked={alsStandard} onChange={(e) => setAlsStandard(e.target.checked)} />
            Als Standard
          </label>
          <button
            disabled={!name.trim() || createMutation.isPending}
            onClick={() => createMutation.mutate()}
            className="btn-touch shrink-0 rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
          >
            Speichern
          </button>
        </div>
      )}
      {error && <p className="text-xs text-red-700 dark:text-red-400">{error}</p>}
    </div>
  );
}
