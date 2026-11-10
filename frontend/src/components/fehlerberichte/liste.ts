import { fehlerberichteApi } from "../../api/endpoints";
import type { FehlerberichtArt, FehlerberichtListItem, FehlerberichtSchweregrad, FehlerberichtStatus } from "../../types";
import { OFFENE_STATUS } from "./darstellung";

export type StatusFilter = FehlerberichtStatus | "offen" | "alle";
export type Zeitraum = "" | "24h" | "7d" | "30d";

/** Reiter der Liste; "alle" lädt ohne art-Filter. */
export type ArtReiter = FehlerberichtArt | "alle";

export interface ListenFilter {
  art: ArtReiter;
  status: StatusFilter;
  schweregrad: FehlerberichtSchweregrad | "";
  mandantId: string;
  q: string;
  zeitraum: Zeitraum;
}

export const STANDARD_FILTER: ListenFilter = { art: "fehler", status: "offen", schweregrad: "", mandantId: "", q: "", zeitraum: "" };

const ZEITRAUM_STUNDEN: Record<Exclude<Zeitraum, "">, number> = { "24h": 24, "7d": 24 * 7, "30d": 24 * 30 };
const SEITENGROESSE = 100;

function seitIso(zeitraum: Zeitraum): string | undefined {
  if (!zeitraum) return undefined;
  return new Date(Date.now() - ZEITRAUM_STUNDEN[zeitraum] * 3_600_000).toISOString();
}

/** Das Backend kennt nur EINEN Status je Abfrage -- "offen" (neu/gesichtet/
 * in_arbeit) wird deshalb als parallele Mehrfachabfrage geladen und
 * clientseitig nach Datum zusammengefuehrt. */
export async function ladeBerichte(filter: ListenFilter): Promise<FehlerberichtListItem[]> {
  const basis = {
    art: filter.art === "alle" ? undefined : filter.art,
    schweregrad: filter.schweregrad || undefined,
    mandant_id: filter.mandantId || undefined,
    q: filter.q.trim() || undefined,
    seit: seitIso(filter.zeitraum),
    limit: SEITENGROESSE,
  };
  if (filter.status === "offen") {
    const teile = await Promise.all(OFFENE_STATUS.map((status) => fehlerberichteApi.liste({ ...basis, status })));
    return teile
      .flat()
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .slice(0, SEITENGROESSE);
  }
  return fehlerberichteApi.liste({ ...basis, status: filter.status === "alle" ? undefined : filter.status });
}
