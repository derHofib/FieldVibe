import type { PortalVorOrtKontaktEingabe, VorOrtRolle } from "../types";

export const PORTAL_MAX_KONTAKTE = 5;
/** Das Portal kennt die Mandanten-Einstellung nicht; der Hinweis nennt den Standardwert. */
export const PORTAL_ANONYMISIERUNG_MONATE = 12;

export interface PortalKontaktFormular {
  name: string;
  rolle: VorOrtRolle;
  telefon: string;
  erreichbarkeit: string;
  hinweis: string;
}

export function leererPortalKontakt(): PortalKontaktFormular {
  return { name: "", rolle: "mieter", telefon: "", erreichbarkeit: "", hinweis: "" };
}

function istLeer(k: PortalKontaktFormular): boolean {
  return !k.name.trim() && !k.telefon.trim() && !k.erreichbarkeit.trim() && !k.hinweis.trim();
}

/** Fehlertext je Zeilenindex; komplett leere Zeilen werden beim Senden ignoriert. */
export function validierePortalKontakte(liste: PortalKontaktFormular[]): Record<number, string> {
  const fehler: Record<number, string> = {};
  liste.forEach((k, i) => {
    if (!istLeer(k) && !k.name.trim() && !k.telefon.trim()) fehler[i] = "Bitte Name oder Telefon angeben.";
  });
  return fehler;
}

export function baueKontakteBody(liste: PortalKontaktFormular[]): PortalVorOrtKontaktEingabe[] {
  return liste
    .filter((k) => !istLeer(k))
    .slice(0, PORTAL_MAX_KONTAKTE)
    .map((k) => ({
      name: k.name.trim() || null,
      rolle: k.rolle,
      telefon: k.telefon.trim() || null,
      erreichbarkeit: k.erreichbarkeit.trim() || null,
      hinweis: k.hinweis.trim() || null,
    }));
}
