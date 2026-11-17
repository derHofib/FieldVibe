import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { gespeicherteFilterApi } from "../../api/endpoints";
import type { GespeicherterFilterEntitaet } from "../../types";
import { useBestaetigung } from "../ConfirmDialog";
import { bedingungenGleich } from "./auswerten";
import { OPERATOR_LABEL, operatorenFuer, type FilterBedingung, type FilterFeld, type FilterOperator } from "./typen";
import type { FilterZustand } from "./useFilterZustand";
import { wertGueltig } from "./url";

export interface Ansicht {
  id: string;
  name: string;
  istStandard: boolean;
  bedingungen: FilterBedingung[];
}

function bereinige<T>(roh: unknown, felder: FilterFeld<T>[]): FilterBedingung[] {
  if (!Array.isArray(roh)) return [];
  const nachKey = new Map(felder.map((f) => [f.key, f]));
  const ergebnis: FilterBedingung[] = [];
  for (const b of roh) {
    if (!b || typeof b !== "object") continue;
    const { feld, op, wert } = b as { feld?: unknown; op?: unknown; wert?: unknown };
    if (typeof feld !== "string" || typeof op !== "string" || !(op in OPERATOR_LABEL)) continue;
    const f = nachKey.get(feld);
    if (!f || !operatorenFuer(f).includes(op as FilterOperator)) continue;
    if (wert !== undefined && !wertGueltig(wert)) continue;
    ergebnis.push(wert === undefined ? { feld, op: op as FilterOperator } : { feld, op: op as FilterOperator, wert });
  }
  return ergebnis;
}

/** Logik der gespeicherten Ansichten (Filterkombinationen ohne Suche). Format: `filter_json = { v: 2, bedingungen }`;
 * ältere flache Vorlagen werden beim Lesen über `alteVorlageUmrechnen` umgerechnet, ohne Umrechnung ausgeblendet. */
export function useAnsichten<T>(opts: {
  entitaet?: GespeicherterFilterEntitaet;
  zustand: FilterZustand;
  felder: FilterFeld<T>[];
  alteVorlageUmrechnen?: (alt: Record<string, string>) => FilterBedingung[];
}) {
  const { entitaet, zustand, felder, alteVorlageUmrechnen } = opts;
  const bestaetigen = useBestaetigung();
  const queryClient = useQueryClient();
  const standardAngewendet = useRef(false);
  const [gewaehltId, setGewaehltId] = useState<string | null>(null);
  const [speichernOffen, setSpeichernOffen] = useState(false);

  const { data } = useQuery({
    queryKey: ["gespeicherte-filter", entitaet],
    queryFn: () => gespeicherteFilterApi.list(entitaet!),
    enabled: !!entitaet,
  });

  const ansichten: Ansicht[] = (data ?? []).flatMap((v) => {
    const fj = v.filter_json ?? {};
    let bedingungen: FilterBedingung[] | null = null;
    if (fj.v === 2) bedingungen = bereinige(fj.bedingungen, felder);
    else if (alteVorlageUmrechnen) bedingungen = bereinige(alteVorlageUmrechnen(fj as Record<string, string>), felder);
    return bedingungen ? [{ id: v.id, name: v.name, istStandard: v.ist_standard, bedingungen }] : [];
  });

  useEffect(() => {
    if (standardAngewendet.current || !data) return;
    standardAngewendet.current = true;
    const standard = ansichten.find((a) => a.istStandard);
    // Link oder Zurück-Taste mit eigenen Filtern gewinnt gegen die Standard-Ansicht.
    if (standard && zustand.bedingungen.length === 0) {
      zustand.setBedingungen(standard.bedingungen);
      setGewaehltId(standard.id);
    }
    // Nur beim ersten Laden der Liste anwenden.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const aktive = ansichten.find((a) => bedingungenGleich(a.bedingungen, zustand.bedingungen)) ?? null;
  const gewaehlte =
    zustand.bedingungen.length > 0 ? (aktive ?? ansichten.find((a) => a.id === gewaehltId) ?? null) : null;
  const weichtAb = !!gewaehlte && !bedingungenGleich(gewaehlte.bedingungen, zustand.bedingungen);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["gespeicherte-filter", entitaet] });

  const erstellen = useMutation({
    meta: { erfolg: "Ansicht gespeichert" },
    mutationFn: (v: { name: string; alsStandard: boolean }) =>
      gespeicherteFilterApi.create({
        entitaet: entitaet!,
        name: v.name,
        filter_json: { v: 2, bedingungen: zustand.bedingungen },
        ist_standard: v.alsStandard,
      }),
    onSuccess: (neu) => {
      invalidate();
      setGewaehltId(neu.id);
      setSpeichernOffen(false);
    },
  });

  const uebernehmenMut = useMutation({
    meta: { erfolg: "Ansicht aktualisiert" },
    mutationFn: (a: Ansicht) =>
      gespeicherteFilterApi.update(a.id, { filter_json: { v: 2, bedingungen: zustand.bedingungen } }),
    onSuccess: invalidate,
  });

  const standardMut = useMutation({
    meta: { erfolg: "Standard gesetzt" },
    mutationFn: (a: Ansicht) => gespeicherteFilterApi.update(a.id, { ist_standard: true }),
    onSuccess: invalidate,
  });

  const loeschenMut = useMutation({
    meta: { erfolg: "Ansicht gelöscht" },
    mutationFn: (a: Ansicht) => gespeicherteFilterApi.remove(a.id),
    onSuccess: invalidate,
  });

  return {
    verfuegbar: !!entitaet,
    ansichten,
    aktive,
    gewaehlte,
    weichtAb,
    speichernOffen,
    setSpeichernOffen,
    speichernLaeuft: erstellen.isPending,
    anwenden: (a: Ansicht) => {
      zustand.setBedingungen(a.bedingungen);
      setGewaehltId(a.id);
    },
    speichern: (name: string, alsStandard: boolean) => erstellen.mutate({ name, alsStandard }),
    aenderungenUebernehmen: (a: Ansicht) => uebernehmenMut.mutate(a),
    alsStandardSetzen: (a: Ansicht) => standardMut.mutate(a),
    loeschen: async (a: Ansicht) => {
      if (!(await bestaetigen({ titel: `Ansicht „${a.name}“ löschen?`, bestaetigenLabel: "Löschen" }))) return;
      loeschenMut.mutate(a);
    },
  };
}

export type AnsichtenZustand = ReturnType<typeof useAnsichten>;
