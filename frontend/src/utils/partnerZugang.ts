import type { Einladung, PartnerZugang } from "../types";

export type PortalZugangStatus =
  | { art: "aktiv"; zugang: PartnerZugang }
  | { art: "gesperrt"; zugang: PartnerZugang }
  | { art: "offen"; einladung: Einladung }
  | { art: "abgelaufen"; einladung: Einladung }
  | { art: "keiner" };

/** Ein vorhandener Zugang schlägt jede Einladung (die angenommene bleibt in
 * der Liste stehen); sonst zählt nur die jüngste noch offene Einladung. */
export function portalZugangStatus(zugaenge: PartnerZugang[], einladungen: Einladung[]): PortalZugangStatus {
  const zugang = [...zugaenge].sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  if (zugang) return zugang.aktiv ? { art: "aktiv", zugang } : { art: "gesperrt", zugang };
  const offen = einladungen
    .filter((e) => e.status === "offen")
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  if (offen) return offen.abgelaufen ? { art: "abgelaufen", einladung: offen } : { art: "offen", einladung: offen };
  return { art: "keiner" };
}

export function partnerPortalLink(origin: string): string {
  return `${origin.replace(/\/$/, "")}/partnerportal`;
}

/** Backend-Meldungen (409 E-Mail vergeben/Einladung offen) sind schon
 * verständlich; 403/422 bekommen einen klaren Text statt der Rohmeldung. */
export function einladungFehlerText(status: number | null, message: string): string {
  if (status === 403) return "Das Modul „Nachunternehmer“ ist nicht freigeschaltet oder Ihnen fehlt das Recht dazu.";
  if (status === 422) return "Bitte eine gültige E-Mail-Adresse eingeben.";
  if (status === 409) return message;
  return message || "Aktion fehlgeschlagen. Bitte erneut versuchen.";
}
