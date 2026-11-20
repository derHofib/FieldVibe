import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { mandantEinstellungenApi, vorOrtApi } from "../api/endpoints";
import { STANDARD_ANONYMISIERUNG_MONATE } from "../utils/vorOrt";
import type { VorOrtKontaktCreate, VorOrtKontaktFilter, VorOrtKontaktUpdate, VorOrtZiel, VorOrtZuordnungCreate } from "../types";

/** Alles, was Kontakte vor Ort anzeigt: Ziel-Listen, Kunden-Liste, Vorgang-Detail (enthält die geerbten), Feed. */
function useInvalidiereVorOrt() {
  const queryClient = useQueryClient();
  return () => {
    for (const key of [["vor-ort"], ["vorgang"], ["vorgaenge"], ["feed"], ["auftraege"], ["projekte"]]) {
      void queryClient.invalidateQueries({ queryKey: key });
    }
  };
}

export function useVorOrtKontakteFuerZiel(ziel: VorOrtZiel, zielId: string, enabled = true) {
  return useQuery({
    queryKey: ["vor-ort", "ziel", ziel, zielId],
    queryFn: () => vorOrtApi.listeFuerZiel(ziel, zielId),
    enabled,
  });
}

export function useVorOrtKontakteFuerKunde(kundeId: string | null, filter: VorOrtKontaktFilter = {}, enabled = true) {
  return useQuery({
    queryKey: ["vor-ort", "kunde", kundeId, filter],
    queryFn: () => vorOrtApi.listeFuerKunde(kundeId!, filter),
    enabled: enabled && !!kundeId,
  });
}

export function useVorOrtZuordnen(ziel: VorOrtZiel, zielId: string) {
  const invalidieren = useInvalidiereVorOrt();
  return useMutation({
    meta: { erfolg: "Kontakt hinzugefügt" },
    mutationFn: (body: VorOrtZuordnungCreate) => vorOrtApi.zuordnen(ziel, zielId, body),
    onSuccess: invalidieren,
  });
}

export function useVorOrtHauptkontakt() {
  const invalidieren = useInvalidiereVorOrt();
  return useMutation({
    meta: { erfolg: "Gespeichert" },
    mutationFn: ({ zuordnungId, haupt }: { zuordnungId: string; haupt: boolean }) =>
      vorOrtApi.hauptkontaktSetzen(zuordnungId, haupt),
    onSuccess: invalidieren,
  });
}

export function useVorOrtEntfernen() {
  const invalidieren = useInvalidiereVorOrt();
  return useMutation({
    meta: { erfolg: "Kontakt entfernt" },
    mutationFn: (zuordnungId: string) => vorOrtApi.zuordnungEntfernen(zuordnungId),
    onSuccess: invalidieren,
  });
}

export function useVorOrtKontaktAendern() {
  const invalidieren = useInvalidiereVorOrt();
  return useMutation({
    meta: { erfolg: "Gespeichert" },
    mutationFn: ({ id, body }: { id: string; body: VorOrtKontaktUpdate }) => vorOrtApi.aendern(id, body),
    onSuccess: invalidieren,
  });
}

export function useVorOrtKontaktAnlegen(kundeId: string) {
  const invalidieren = useInvalidiereVorOrt();
  return useMutation({
    meta: { erfolg: "Kontakt angelegt" },
    mutationFn: (body: VorOrtKontaktCreate) => vorOrtApi.anlegen(kundeId, body),
    onSuccess: invalidieren,
  });
}

export function useVorOrtKontaktLoeschen() {
  const invalidieren = useInvalidiereVorOrt();
  return useMutation({
    meta: { erfolg: "Gelöscht" },
    mutationFn: (id: string) => vorOrtApi.loeschen(id),
    onSuccess: invalidieren,
  });
}

export function useVorOrtAnonymisieren() {
  const invalidieren = useInvalidiereVorOrt();
  return useMutation({
    meta: { erfolg: "Anonymisiert" },
    mutationFn: (id: string) => vorOrtApi.anonymisieren(id),
    onSuccess: invalidieren,
  });
}

/** Frist der Anonymisierung in Monaten; ohne Recht auf die Mandanten-Einstellungen gilt der Standard. */
export function useAnonymisierungMonate(): number {
  const { data } = useQuery({
    queryKey: ["mandant-einstellungen"],
    queryFn: mandantEinstellungenApi.get,
    retry: false,
  });
  return data?.vor_ort_kontakte_anonymisieren_monate ?? STANDARD_ANONYMISIERUNG_MONATE;
}
