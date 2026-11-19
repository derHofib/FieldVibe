import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { ApiError } from "../api/client";
import { kundenApi, telefonateApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { queueTelefonat } from "../offline/outbox";
import type { Telefonat, TelefonatCreate, TelefonatFilter, TelefonatUpdate } from "../types";

/** Nach Anlegen/Ändern/Löschen: Verlauf des Vorgangs, Listen, Kontaktverlauf, Menü-Zähler und
 * die Zeiterfassung (gebuchte Arbeitszeit wird mit angelegt, gezogen oder gelöscht). */
export function invalidiereTelefonate(queryClient: QueryClient) {
  for (const key of [
    ["vorgang-events"],
    ["telefonate"],
    ["kontaktverlauf"],
    ["telefonate-anzahl-offen"],
    ["zeiterfassung"],
    ["outbox"],
  ]) {
    queryClient.invalidateQueries({ queryKey: key });
  }
}

export function useTelefonateListe(filter: TelefonatFilter, enabled = true) {
  return useQuery({
    queryKey: ["telefonate", "liste", filter],
    queryFn: () => telefonateApi.list(filter),
    enabled,
  });
}

export function useKontaktverlauf(kundeId: string | undefined, limit = 50) {
  return useQuery({
    queryKey: ["kontaktverlauf", kundeId, limit],
    queryFn: () => kundenApi.kontaktverlauf(kundeId!, limit),
    enabled: !!kundeId,
  });
}

/** Offene Rückrufe des angemeldeten Nutzers -- Zahl am Menüpunkt "Telefonate" (Office). */
export function useAnzahlOffeneRueckrufe(aktiv = true): number | undefined {
  const { currentUser } = useAuth();
  const { data } = useQuery({
    queryKey: ["telefonate-anzahl-offen"],
    queryFn: telefonateApi.anzahlOffeneRueckrufe,
    enabled: aktiv && !!currentUser,
    refetchInterval: 60_000,
  });
  return data?.anzahl;
}

/** Anlegen mit Offline-Fallback wie bei Kommentaren: bei Netzwerkfehler (kein ApiError) landet der
 * Eintrag mit derselben client_uuid in der Outbox, Ergebnis ist dann null. */
export function useTelefonatAnlegen(opts?: { onFertig?: (t: Telefonat | null) => void }) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: TelefonatCreate): Promise<Telefonat | null> => {
      const mitUuid = { ...body, client_uuid: body.client_uuid ?? crypto.randomUUID() };
      try {
        return await telefonateApi.create(mitUuid);
      } catch (err) {
        if (err instanceof ApiError) throw err;
        await queueTelefonat(mitUuid);
        return null;
      }
    },
    onSuccess: (t) => {
      invalidiereTelefonate(queryClient);
      opts?.onFertig?.(t);
    },
  });
}

export function useTelefonatAendern(opts?: { onFertig?: (t: Telefonat) => void }) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: TelefonatUpdate }) => telefonateApi.update(id, body),
    onSuccess: (t) => {
      invalidiereTelefonate(queryClient);
      opts?.onFertig?.(t);
    },
  });
}

export function useTelefonatLoeschen(opts?: { onFertig?: () => void }) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => telefonateApi.remove(id),
    onSuccess: () => {
      invalidiereTelefonate(queryClient);
      opts?.onFertig?.();
    },
  });
}
