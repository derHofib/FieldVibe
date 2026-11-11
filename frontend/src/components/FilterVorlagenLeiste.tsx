import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { gespeicherteFilterApi } from "../api/endpoints";
import { ApiError } from "../api/client";
import type { GespeicherterFilter, GespeicherterFilterEntitaet } from "../types";
import { MoreHorizontal } from "lucide-react";
import { PulldownMenu, type PulldownItem } from "./apple/PulldownMenu";
import { useBestaetigung } from "./ConfirmDialog";

function filtersEqual(a: Record<string, string>, b: Record<string, string>): boolean {
  const aKeys = Object.keys(a).filter((k) => a[k]);
  const bKeys = Object.keys(b).filter((k) => b[k]);
  if (aKeys.length !== bKeys.length) return false;
  return aKeys.every((k) => a[k] === b[k]);
}

interface FilterVorlagenProps {
  entitaet: GespeicherterFilterEntitaet;
  filter: Record<string, string>;
  onApply: (filterJson: Record<string, string>) => void;
}

export type FilterVorlagenState = ReturnType<typeof useFilterVorlagen>;

/** Wiederverwendbare Leiste fuer benannte Filter-Vorlagen (Standort, Kunde,
 * Assets, Aufträge...): laedt/wendet gespeicherte Filter-Sets an, erlaubt
 * das Speichern des aktuell aktiven Filters unter einem Namen sowie das
 * Markieren einer Vorlage als Standard -- die dann beim naechsten Aufruf der
 * jeweiligen Liste automatisch angewendet wird. */
export function useFilterVorlagen({ entitaet, filter, onApply }: FilterVorlagenProps) {
  const bestaetigen = useBestaetigung();
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
    meta: { erfolg: "Angelegt" },
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
    meta: { erfolg: "Gespeichert" },
    mutationFn: (v: GespeicherterFilter) => gespeicherteFilterApi.update(v.id, { ist_standard: !v.ist_standard }),
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    meta: { erfolg: "Gelöscht" },
    mutationFn: (id: string) => gespeicherteFilterApi.remove(id),
    onSuccess: invalidate,
  });

  const hatAktivenFilter = Object.values(filter).some((v) => !!v);

  return {
    vorlagen, filter, onApply, hatAktivenFilter, zeigeSpeichern, setZeigeSpeichern, name, setName,
    alsStandard, setAlsStandard, error, createMutation, standardMutation, deleteMutation, bestaetigen,
  };
}

function VorlagenChips({ v: h }: { v: FilterVorlagenState }) {
  const { vorlagen, filter, onApply, standardMutation, deleteMutation, bestaetigen } = h;
  return (
    <>
      {(vorlagen ?? []).length > 0 && (
        <div className="-mx-3 flex gap-2 overflow-x-auto px-3 py-0.5">
          {vorlagen!.map((v) => {
            const aktiv = filtersEqual(filter, v.filter_json);
            return (
              <div
                key={v.id}
                className={`flex h-[26px] shrink-0 items-stretch rounded-[13px] pl-2.5 pr-0.5 text-xs font-medium ${
                  aktiv ? "bg-tint-solid text-white" : "bg-fill text-label"
                }`}
              >
                {/* Gleiche Masse wie FilterChip statt btn-touch: sonst waechst der Chip je
                    nach Zustand unterschiedlich und die Leiste springt. */}
                <button onClick={() => onApply(v.filter_json)} className="whitespace-nowrap pr-1">
                  {v.ist_standard && "★ "}
                  {v.name}
                </button>
                <button
                  onClick={() => standardMutation.mutate(v)}
                  title={v.ist_standard ? "Als Standard entfernen" : "Als Standard setzen"}
                  className={`px-1.5 ${aktiv ? "text-white/80" : "text-label2"}`}
                >
                  {v.ist_standard ? "★" : "☆"}
                </button>
                <button
                  onClick={async () => {
                    if (await bestaetigen({ titel: `Filter-Vorlage "${v.name}" löschen?`, bestaetigenLabel: "Löschen" })) deleteMutation.mutate(v.id);
                  }}
                  className={`px-1.5 ${aktiv ? "text-white/80" : "text-label2"}`}
                >
                  ×
                </button>
              </div>
            );
          })}
        </div>
      )}

    </>
  );
}

function SpeichernForm({ v: h }: { v: FilterVorlagenState }) {
  const { zeigeSpeichern, name, setName, alsStandard, setAlsStandard, createMutation, error } = h;
  return (
    <>
      {zeigeSpeichern && (
        <div className="flex flex-wrap items-center gap-2 border border-sepstrong p-2">
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name der Vorlage"
            className="btn-touch min-w-0 flex-1 border border-sep bg-transparent px-3 py-1.5 text-sm text-label"
          />
          <label className="flex shrink-0 items-center gap-1 text-xs text-label">
            <input type="checkbox" checked={alsStandard} onChange={(e) => setAlsStandard(e.target.checked)} />
            Als Standard
          </label>
          <button
            disabled={!name.trim() || createMutation.isPending}
            onClick={() => createMutation.mutate()}
            className="btn-touch shrink-0 rounded-md btn-ap-primary px-3 py-1.5 text-xs font-medium disabled:opacity-50"
          >
            Speichern
          </button>
        </div>
      )}
      {error && <p className="text-xs text-st-fehlt ">{error}</p>}
    </>
  );
}

/** Office: Leiste mit Vorlagen-Chips, Zuruecksetzen und Speichern-Link. */
export function FilterVorlagenLeiste(props: FilterVorlagenProps) {
  const h = useFilterVorlagen(props);
  const { onApply, hatAktivenFilter, zeigeSpeichern, setZeigeSpeichern } = h;
  return (
    <div className="space-y-2">
      <VorlagenChips v={h} />
      <div className="flex flex-wrap items-center gap-3">
        {hatAktivenFilter && (
          <button
            onClick={() => onApply({})}
            className="btn-touch text-xs text-label2 "
          >
            Filter zurücksetzen
          </button>
        )}
        <button
          onClick={() => setZeigeSpeichern((v) => !v)}
          disabled={!hatAktivenFilter}
          className="btn-touch text-xs text-tint-text disabled:opacity-40 hover:underline"
        >
          {zeigeSpeichern ? "Abbrechen" : "Aktuellen Filter als Vorlage speichern…"}
        </button>
      </div>

      <SpeichernForm v={h} />
    </div>
  );
}

/** Feld-App: Vorlagen-Aktionen im Filter-Menue statt als eigene Zeilen im Seitenkopf.
 * Chips (Standard setzen/Loeschen) und Speichern-Formular erscheinen erst, wenn
 * die Seite das Filterpanel oeffnet bzw. "Speichern" gewaehlt wurde. */
export function FilterVorlagenMenue({ v: h }: { v: FilterVorlagenState }) {
  const { vorlagen, onApply, hatAktivenFilter, setZeigeSpeichern } = h;
  const items: PulldownItem[] = [
    ...(vorlagen ?? []).map((vl) => ({
      label: `${vl.ist_standard ? "★ " : ""}${vl.name}`,
      onSelect: () => onApply(vl.filter_json),
    })),
    ...((vorlagen ?? []).length > 0 ? (["trenner"] as PulldownItem[]) : []),
    { label: "Filter zurücksetzen", disabled: !hatAktivenFilter, onSelect: () => onApply({}) },
    { label: "Aktuellen Filter als Vorlage speichern…", disabled: !hatAktivenFilter, onSelect: () => setZeigeSpeichern(true) },
  ];
  return (
    <PulldownMenu
      ariaLabel="Filter-Vorlagen"
      items={items}
      trigger={({ toggeln, triggerRef, offen }) => (
        <button
          ref={triggerRef}
          type="button"
          onClick={toggeln}
          aria-haspopup="menu"
          aria-expanded={offen}
          aria-label="Filter-Vorlagen"
          title="Filter-Vorlagen"
          className="btn-ap-toolbar"
        >
          <MoreHorizontal size={16} strokeWidth={2} aria-hidden="true" />
        </button>
      )}
    />
  );
}

export function FilterVorlagenVerwaltung({ v: h, chipsZeigen }: { v: FilterVorlagenState; chipsZeigen: boolean }) {
  return (
    <div className="space-y-2">
      {chipsZeigen && <VorlagenChips v={h} />}
      <SpeichernForm v={h} />
    </div>
  );
}
