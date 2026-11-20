import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { kiApi } from "../api/endpoints";
import type { KiAktion, KiAktionenFilter } from "../types/ki";

export function useKiAktionenListe(filter: KiAktionenFilter, limit: number, offset: number, enabled = true) {
  return useQuery({
    queryKey: ["ki", "aktionen", filter, limit, offset],
    queryFn: () => kiApi.aktionen(filter, limit, offset),
    placeholderData: keepPreviousData,
    enabled,
  });
}

/** Detail einer Aktion; die Zeile aus der Liste dient als Startwert, damit das Panel ohne Flackern aufgeht. */
export function useKiAktion(id: string | null, startwert?: KiAktion) {
  return useQuery({
    queryKey: ["ki", "aktion", id],
    queryFn: () => kiApi.aktion(id!),
    enabled: id !== null,
    initialData: startwert,
    // Startwert aus der Liste gilt als veraltet: Frist und Rückgängig-Zustand werden beim Öffnen frisch geholt.
    initialDataUpdatedAt: 0,
  });
}

/** `stumm`: den 409 (Konflikte) zeigt das Panel selbst als Hinweisbox, kein globaler Fehler-Toast. */
export function useKiRueckgaengig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => kiApi.rueckgaengig(id),
    meta: { stumm: true },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["ki", "aktionen"] });
      void queryClient.invalidateQueries({ queryKey: ["ki", "aktion"] });
    },
  });
}
