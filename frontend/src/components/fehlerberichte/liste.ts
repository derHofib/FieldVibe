import { fehlerberichteApi } from "../../api/endpoints";
import type { FehlerberichtArt, FehlerberichtListItem, FehlerberichtSchweregrad, FehlerberichtStatus } from "../../types";
import { OFFENE_STATUS } from "./darstellung";

export type StatusFilter = FehlerberichtStatus | "offen" | "alle";

/** Reiter der Liste; "alle" lädt ohne art-Filter. */
export type ArtReiter = FehlerberichtArt | "alle";

export interface ListenFilter {
  art: ArtReiter;
  status: StatusFilter;
  schweregrad: FehlerberichtSchweregrad | "";
  mandantId: string;
  q: string;
  /** Untergrenze der Meldezeit als ISO-Zeitstempel; leer = kein Zeitfilter. */
  seit: string;
}

export const STANDARD_FILTER: ListenFilter = { art: "fehler", status: "offen", schweregrad: "", mandantId: "", q: "", seit: "" };

const SEITENGROESSE = 100;

/** Das Backend kennt nur EINEN Status je Abfrage -- "offen" (neu/gesichtet/
 * in_arbeit) wird deshalb als parallele Mehrfachabfrage geladen und
 * clientseitig nach Datum zusammengefuehrt. */
export async function ladeBerichte(filter: ListenFilter): Promise<FehlerberichtListItem[]> {
  const basis = {
    art: filter.art === "alle" ? undefined : filter.art,
    schweregrad: filter.schweregrad || undefined,
    mandant_id: filter.mandantId || undefined,
    q: filter.q.trim() || undefined,
    seit: filter.seit || undefined,
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
