import type { KundeTyp } from "../types";

export const KUNDE_TYP_LABEL: Record<KundeTyp, string> = {
  privat: "Privat",
  gewerbe: "Gewerbe",
  oeffentlich: "Öffentlich",
  hausverwaltung: "Hausverwaltung",
};

/** Kundentyp ist im Backend ein Literal, kommt aber als string an -- unbekannte
 * Werte werden unverändert gezeigt statt zu verschwinden. */
export function kundeTypLabel(typ: string): string {
  return (KUNDE_TYP_LABEL as Record<string, string>)[typ] ?? typ;
}
