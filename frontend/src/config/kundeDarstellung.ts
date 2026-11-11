import type { KundeTyp } from "../types";
import { lesbarerWert } from "../utils/anzeigeNamen";

export const KUNDE_TYP_LABEL: Record<KundeTyp, string> = {
  privat: "Privat",
  gewerbe: "Gewerbe",
  oeffentlich: "Öffentlich",
  hausverwaltung: "Hausverwaltung",
};

/** Kundentyp ist im Backend ein Literal, kommt aber als string an – unbekannte
 * Werte werden lesbar gemacht (Unterstriche, Großschreibung). */
export function kundeTypLabel(typ: string): string {
  return (KUNDE_TYP_LABEL as Record<string, string>)[typ] ?? lesbarerWert(typ);
}
