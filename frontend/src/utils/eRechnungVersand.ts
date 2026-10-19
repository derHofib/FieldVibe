// Versand von E-Rechnungen: Modus je Mandant, Leitweg-ID und Profil (XRechnung/ZUGFeRD).
// Gegenstück zu backend/app/services/e_invoice_service.py und leitweg_id.py.

import type { MandantFirmendaten } from "../types";

export type ERechnungModus = "aus" | "b2b" | "alle";
export type ERechnungFormat = "zugferd" | "xrechnung";
export type ERechnungProfil = "en16931" | "xrechnung";

export const E_RECHNUNG_MODI: { wert: ERechnungModus; label: string; hinweis: string }[] = [
  { wert: "aus", label: "Aus", hinweis: "Rechnungen werden immer als normales PDF versendet." },
  {
    wert: "b2b",
    label: "Nur für gewerbliche Kunden",
    hinweis:
      "Kunden mit Typ Gewerbe, Öffentlich oder Hausverwaltung, mit USt-IdNr. oder mit Leitweg-ID bekommen eine E-Rechnung; Privatkunden ein normales PDF.",
  },
  {
    wert: "alle",
    label: "Für alle Kunden",
    hinweis: "Auch Privatkunden bekommen eine E-Rechnung – fehlen Pflichtangaben, ist der Versand gesperrt.",
  },
];

/** Wirksamer Modus: der gespeicherte, sonst abgeleitet aus dem älteren e_rechnung_aktiv. */
export function eRechnungModus(fd: Pick<MandantFirmendaten, "e_rechnung_modus" | "e_rechnung_aktiv">): ERechnungModus {
  const modus = fd.e_rechnung_modus;
  if (modus === "aus" || modus === "b2b" || modus === "alle") return modus;
  return fd.e_rechnung_aktiv ? "alle" : "aus";
}

export const E_RECHNUNG_FORMAT_OPTIONEN: { wert: ERechnungFormat | ""; label: string }[] = [
  { wert: "", label: "Automatisch (mit Leitweg-ID XRechnung, sonst ZUGFeRD)" },
  { wert: "zugferd", label: "ZUGFeRD (PDF mit eingebetteter XML)" },
  { wert: "xrechnung", label: "XRechnung (für Behörden)" },
];

export const E_RECHNUNG_FORMAT_KURZ: Record<ERechnungFormat, string> = {
  zugferd: "ZUGFeRD",
  xrechnung: "XRechnung",
};

export const LEITWEG_ID_FORMAT_HINWEIS =
  "Format: Grobadressierung (2–12 Ziffern), optional -Feinadressierung, -Prüfziffer (2 Ziffern), z. B. 04011000-1234512345-06";

const LEITWEG_MUSTER = /^(\d{2,12})(?:-([A-Z0-9]{1,30}))?-(\d{2})$/;

/** ISO 7064 MOD 97-10 über Grob- und Feinadressierung (Buchstaben A=10 … Z=35). */
export function leitwegPruefziffer(grobUndFein: string): string {
  let rest = 0;
  for (const zeichen of grobUndFein + "00") {
    const wert = parseInt(zeichen, 36);
    rest = (wert >= 10 ? rest * 100 + wert : rest * 10 + wert) % 97;
  }
  return String(98 - rest).padStart(2, "0");
}

/** Fehlermeldung zur Eingabe, null = leer oder gültig. Das Backend prüft verbindlich nochmals. */
export function leitwegIdFehler(eingabe: string): string | null {
  const wert = eingabe.replace(/\s+/g, "").toUpperCase();
  if (!wert) return null;
  const treffer = LEITWEG_MUSTER.exec(wert);
  if (!treffer) return `Ungültiges Format. ${LEITWEG_ID_FORMAT_HINWEIS}`;
  const [, grob, fein, ziffern] = treffer;
  if (leitwegPruefziffer(grob + (fein ?? "")) !== ziffern) {
    return "Die Prüfziffer der Leitweg-ID stimmt nicht – bitte Tippfehler prüfen.";
  }
  return null;
}

/** Hinweis in der Rechnungsdetail-Ansicht; null ohne E-Rechnung. */
export function eRechnungPruefHinweis(profil: ERechnungProfil | null | undefined, leitwegId?: string | null): string | null {
  if (!profil) return null;
  const name = profil === "xrechnung" ? "XRechnung" : "ZUGFeRD";
  const leitweg = profil === "xrechnung" && leitwegId ? ` Leitweg-ID: ${leitwegId}.` : "";
  return `E-Rechnung (${name}) – interne Pflichtfeldprüfung bestanden.${leitweg}`;
}
