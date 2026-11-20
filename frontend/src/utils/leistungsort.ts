import type { Leistungsort } from "../types";

export interface LeistungsortFormular {
  bezeichnung: string;
  strasse: string;
  plz: string;
  ort: string;
}

export function leistungsortAlsFormular(l: Leistungsort | null | undefined): LeistungsortFormular {
  return {
    bezeichnung: l?.bezeichnung ?? "",
    strasse: l?.strasse ?? "",
    plz: l?.plz ?? "",
    ort: l?.ort ?? "",
  };
}

/** Leere Eingabe = kein Leistungsort (null), damit der Server nichts auf das PDF druckt. Das Land bleibt erhalten. */
export function baueLeistungsort(f: LeistungsortFormular, alt: Leistungsort | null | undefined): Leistungsort | null {
  const wert = {
    bezeichnung: f.bezeichnung.trim(),
    strasse: f.strasse.trim(),
    plz: f.plz.trim(),
    ort: f.ort.trim(),
  };
  if (!wert.bezeichnung && !wert.strasse && !wert.plz && !wert.ort) return null;
  return {
    bezeichnung: wert.bezeichnung || null,
    strasse: wert.strasse || null,
    plz: wert.plz || null,
    ort: wert.ort || null,
    land: alt?.land ?? null,
  };
}

/** "Moselstraße 14, 56068 Koblenz" */
export function leistungsortAdresse(l: Leistungsort | null | undefined): string {
  if (!l) return "";
  const ortZeile = [l.plz, l.ort].filter(Boolean).join(" ");
  return [l.strasse, ortZeile].filter(Boolean).join(", ");
}

export function leistungsortIstLeer(l: Leistungsort | null | undefined): boolean {
  return !l || (!l.bezeichnung && !leistungsortAdresse(l));
}
