import type { StatusKey } from "../components/apple/status";
import type { FormSchemaStatus, FormViewTyp, FormularfeldDatenquelle } from "../types";

export const LEISTUNGSTYP_LABEL: Record<string, string> = {
  installation: "Installation",
  pruefung: "Prüfung",
  wartung: "Wartung",
  stoerung: "Störung",
  beratung: "Beratung",
  planung: "Planung",
};

export const DATENQUELLE_LABEL: Record<FormularfeldDatenquelle, string> = {
  "vorgang.vorgangsnummer": "Vorgang → Nummer",
  "vorgang.titel": "Vorgang → Titel",
  "vorgang.beschreibung": "Vorgang → Beschreibung",
  "vorgang.leistungstyp": "Vorgang → Leistungstyp",
  "vorgang.faelligkeit_am": "Vorgang → Fälligkeit",
  "vorgang.adresse": "Vorgang → Adresse",
  "vorgang.zugewiesener_name": "Vorgang → Zugewiesener Techniker",
  "kunde.kundennummer": "Kunde → Kundennummer",
  "kunde.name": "Kunde → Name",
  "kunde.adresse": "Kunde → Adresse",
  "kunde.ansprechpartner": "Kunde → Ansprechpartner",
  "anlage.bezeichnung": "Anlage → Bezeichnung",
  "anlage.adresse": "Anlage → Adresse",
  "anlage.hersteller": "Anlage → Hersteller",
  "anlage.modell": "Anlage → Modell",
  "anlage.seriennummer": "Anlage → Seriennummer",
  "anlage.anlagentyp": "Anlage → Anlagentyp",
  "standort.bezeichnung": "Standort → Bezeichnung",
  "standort.adresse": "Standort → Adresse",
  "system.jetzt": "Automatisch → Heutiges Datum",
};

/** Grenzwert-Markierung eines Zahlenfeldes ("über 50" / "unter 2"), sonst null.
 * Reiner Hinweis (rot in der Zusammenfassung), blockiert nie das Speichern. */
export function grenzwertHinweis(validation: Record<string, unknown> | undefined, wert: unknown): string | null {
  if (wert === null || wert === undefined || wert === "") return null;
  const zahl = Number(wert);
  if (!Number.isFinite(zahl)) return null;
  const max = typeof validation?.warn_max === "number" ? validation.warn_max : null;
  const min = typeof validation?.warn_min === "number" ? validation.warn_min : null;
  if (max !== null && zahl > max) return `über ${max}`;
  if (min !== null && zahl < min) return `unter ${min}`;
  return null;
}

export const FORM_SCHEMA_STATUS_LABEL: Record<FormSchemaStatus, string> = {
  draft: "Entwurf",
  published: "Veröffentlicht",
  archived: "Archiviert",
};

export const FORM_SCHEMA_STATUS_TOKEN: Record<FormSchemaStatus, StatusKey> = {
  draft: "geplant",
  published: "erledigt",
  archived: "geplant",
};

// Verständliche Namen statt Typkürzeln (capture/print/...).
export const FORM_VIEW_TYP_LABEL: Record<FormViewTyp, string> = {
  capture: "Erfassung",
  summary: "Zusammenfassung",
  print: "Druck (A4)",
  table: "Tabelle",
  public: "Öffentlich",
};

export const FORM_VIEW_TYP_BESCHREIBUNG: Record<FormViewTyp, string> = {
  capture: "Feld-App, Schritt für Schritt",
  summary: "Vorgang, Kundenportal, Claude",
  print: "PDF und Ausdruck",
  table: "Listenansicht der Werte",
  public: "Link ohne Anmeldung",
};
