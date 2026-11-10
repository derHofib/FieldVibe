import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { rechtlichesApi } from "../api/endpoints";
import { PORTAL_SLUG_QUERY } from "../utils/rechtliches";

/** Portal-Slug aus ?portal_slug=..., damit Platzhalter-Seiten und Links den
 * Mandanten des Kunden-Logins ueber Seitenwechsel hinweg beibehalten. */
export function usePortalSlugAusUrl(): string | undefined {
  const [params] = useSearchParams();
  return params.get(PORTAL_SLUG_QUERY)?.trim() || undefined;
}

/** Oeffentliche Firmenangaben fuer Impressum/Datenschutz. Blockiert nie: bei
 * Fehler/Laden ist data undefined, die Links nutzen dann ihren Fallback. */
export function useRechtliches(portalSlug?: string) {
  return useQuery({
    queryKey: ["public-rechtliches", portalSlug ?? null],
    queryFn: async () => {
      if (!portalSlug) return rechtlichesApi.get();
      try {
        return await rechtlichesApi.get(portalSlug);
      } catch (err) {
        // Veralteter/ungueltiger Slug: wie ohne Kontext weitermachen.
        if (err instanceof ApiError && err.status === 404) return rechtlichesApi.get();
        throw err;
      }
    },
    staleTime: 10 * 60 * 1000,
    retry: false,
  });
}
