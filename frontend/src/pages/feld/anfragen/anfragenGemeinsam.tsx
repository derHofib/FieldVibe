import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, CalendarDays, CircleDot, Type, Wrench } from "lucide-react";
import { useMemo } from "react";

import { ApiError } from "../../../api/client";
import { vorgangAnfragenApi } from "../../../api/endpoints";
import type { FilterFeld } from "../../../components/filter/typen";
import type { Kunde, Leistungstyp, VorgangAbrechnungsart, VorgangAnfrage } from "../../../types";

export const LEISTUNGSTYP_LABEL: Record<Leistungstyp, string> = {
  installation: "Installation",
  pruefung: "Prüfung",
  wartung: "Wartung",
  stoerung: "Störung",
  beratung: "Beratung",
  planung: "Planung",
};

export const ABRECHNUNGSARTEN: { value: VorgangAbrechnungsart; label: string }[] = [
  { value: "aufwand", label: "Nach Aufwand" },
  { value: "pauschale", label: "Pauschale" },
  { value: "festpreis", label: "Festpreis" },
  { value: "wartungsvertrag", label: "Wartungsvertrag" },
  { value: "gewaehrleistung", label: "Gewährleistung" },
];

// Beschriftung wie im Formular "Neuer Vorgang"
export const PRIORITAETEN = [
  { value: 1, label: "1 – Niedrig" },
  { value: 2, label: "2" },
  { value: 3, label: "3 – Normal" },
  { value: 4, label: "4" },
  { value: 5, label: "5 – Hoch" },
];

export const STATUS_LABEL = { offen: "Offen", angenommen: "Angenommen", abgelehnt: "Abgelehnt" } as const;

/** Filterfelder der Anfragenliste; das Kundenfeld gibt es nur, wenn die Kundenliste geladen werden durfte. */
export function useAnfragenFilterFelder(kunden: Kunde[] | undefined): FilterFeld<VorgangAnfrage>[] {
  return useMemo<FilterFeld<VorgangAnfrage>[]>(
    () => [
      { key: "titel", label: "Titel", typ: "text", icon: Type, wert: (a) => a.titel },
      {
        key: "status",
        label: "Status",
        typ: "auswahl",
        icon: CircleDot,
        wert: (a) => a.status,
        optionen: Object.entries(STATUS_LABEL).map(([wert, label]) => ({ wert, label })),
      },
      {
        key: "leistungstyp",
        label: "Leistungstyp",
        typ: "auswahl",
        icon: Wrench,
        wert: (a) => a.leistungstyp,
        optionen: Object.entries(LEISTUNGSTYP_LABEL).map(([wert, label]) => ({ wert, label })),
      },
      ...(kunden
        ? [
            {
              key: "kunde",
              label: "Kunde",
              typ: "verknuepfung" as const,
              icon: Building2,
              wert: (a: VorgangAnfrage) => a.kunde_id,
              optionen: kunden.map((k) => ({ wert: k.id, label: k.name })),
            },
          ]
        : []),
      { key: "eingegangen", label: "Eingegangen", typ: "datum", icon: CalendarDays, wert: (a) => a.created_at.slice(0, 10) },
    ],
    [kunden],
  );
}

/** Annehmen/Ablehnen einer Anfrage; Fehlertext der letzten Mutation in `fehler`. */
export function useAnfrageAktionen(anfrage: VorgangAnfrage) {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["vorgang-anfragen"] });

  const annehmen = useMutation({
    meta: { erfolg: "Angenommen" },
    mutationFn: (v: { abrechnungsart: VorgangAbrechnungsart; prioritaet: number }) =>
      vorgangAnfragenApi.annehmen(anfrage.id, v),
    onSuccess: invalidate,
  });
  const ablehnen = useMutation({
    meta: { erfolg: "Abgelehnt" },
    mutationFn: (grund?: string) => vorgangAnfragenApi.ablehnen(anfrage.id, grund || undefined),
    onSuccess: invalidate,
  });

  const fehler = (m: typeof annehmen | typeof ablehnen, standard: string) =>
    m.error ? (m.error instanceof ApiError ? m.error.message : standard) : null;

  return {
    annehmen,
    ablehnen,
    fehler: fehler(annehmen, "Fehler beim Annehmen") ?? fehler(ablehnen, "Fehler beim Ablehnen"),
    laeuft: annehmen.isPending || ablehnen.isPending,
  };
}

/** Relative Angabe für die Eingangsspalte ("vor 2 Std.", "gestern", "vor 4 Tagen"). */
export function eingangRelativ(iso: string, jetzt: number = Date.now()): string {
  const min = Math.floor((jetzt - new Date(iso).getTime()) / 60_000);
  if (min < 60) return min <= 1 ? "gerade eben" : `vor ${min} Min.`;
  const std = Math.floor(min / 60);
  if (std < 24) return `vor ${std} Std.`;
  const tage = Math.floor(std / 24);
  return tage === 1 ? "gestern" : `vor ${tage} Tagen`;
}

export const datumUhrzeit = (iso: string) =>
  new Date(iso).toLocaleString("de-DE", { timeZone: "Europe/Berlin", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

export const nurDatum = (iso: string) =>
  new Date(iso).toLocaleDateString("de-DE", { timeZone: "Europe/Berlin", day: "2-digit", month: "2-digit", year: "numeric" });
