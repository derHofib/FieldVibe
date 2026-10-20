import type { MandantFirmendaten } from "../types";
import { istHttpUrl } from "./rechtliches";

export type VerbraucherschutzModus = "aus" | "nur_privatkunden";

export const MODUS_OPTIONEN: { wert: VerbraucherschutzModus; label: string; hinweis: string }[] = [
  {
    wert: "aus",
    label: "Aus",
    hinweis: "Kunden nehmen Angebote wie bisher mit einem Klick an.",
  },
  {
    wert: "nur_privatkunden",
    label: "Nur für Privatkunden",
    hinweis:
      "Bei Kunden vom Typ „Privat“: Button „Zahlungspflichtig beauftragen“, Widerrufsbelehrung, Bestätigungsmail und Widerrufsbutton.",
  },
];

/** Fehlender oder unbekannter Wert (Bestandsmandant) = "aus", wie im Backend. */
export function modusAusFirmendaten(fd: MandantFirmendaten): VerbraucherschutzModus {
  return fd.portal_verbraucherschutz === "nur_privatkunden" ? "nur_privatkunden" : "aus";
}

export function hatBelehrungstext(text: string | undefined): boolean {
  return !!text && text.trim().length > 0;
}

/** Schutz aktiv, aber kein eigener Belehrungstext: Kunden sehen den Platzhalter. */
export function zeigtPlatzhalterBelehrung(modus: VerbraucherschutzModus, text: string | undefined): boolean {
  return modus === "nur_privatkunden" && !hatBelehrungstext(text);
}

export interface PortalFormular {
  modus: VerbraucherschutzModus;
  belehrungText: string;
  belehrungVersion: string;
  barrierefreiheitEmail: string;
  barrierefreiheitStand: string;
  barrierefreiheitUrl: string;
}

export function formularAusFirmendaten(fd: MandantFirmendaten): PortalFormular {
  return {
    modus: modusAusFirmendaten(fd),
    belehrungText: fd.widerrufsbelehrung_text ?? "",
    belehrungVersion: fd.widerrufsbelehrung_version ?? "",
    barrierefreiheitEmail: fd.barrierefreiheit_kontakt_email ?? "",
    barrierefreiheitStand: fd.barrierefreiheit_stand ?? "",
    barrierefreiheitUrl: fd.barrierefreiheit_url ?? "",
  };
}

/** Nur die Portal-Schluessel: das Backend mergt Firmendaten auf oberster Ebene,
 * andere Formulare bleiben unberuehrt. */
export function firmendatenAusFormular(f: PortalFormular): MandantFirmendaten {
  return {
    portal_verbraucherschutz: f.modus,
    widerrufsbelehrung_text: f.belehrungText.trim(),
    widerrufsbelehrung_version: f.belehrungVersion.trim(),
    barrierefreiheit_kontakt_email: f.barrierefreiheitEmail.trim(),
    barrierefreiheit_stand: f.barrierefreiheitStand.trim(),
    barrierefreiheit_url: f.barrierefreiheitUrl.trim(),
  };
}

export function portalFormularFehler(f: PortalFormular): Partial<Record<keyof PortalFormular, string>> {
  const fehler: Partial<Record<keyof PortalFormular, string>> = {};
  const email = f.barrierefreiheitEmail.trim();
  if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) fehler.barrierefreiheitEmail = "Bitte eine gültige E-Mail-Adresse eingeben";
  const url = f.barrierefreiheitUrl.trim();
  if (url && !istHttpUrl(url)) fehler.barrierefreiheitUrl = "Bitte eine http(s)-Adresse eingeben";
  if (f.belehrungText.trim().length > 20000) fehler.belehrungText = "Höchstens 20.000 Zeichen";
  return fehler;
}
