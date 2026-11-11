import { datumZuIso } from "../../../utils/format";
import type {
  Adresse,
  Leistungstyp,
  MangelSchweregrad,
  MangelStatus,
  PartnerFreigabeStatus,
  TerminStatus,
  VorgangAbrechnungsart,
  VorgangStatus,
} from "../../../types";

export const SCHWEREGRAD_OPTIONEN: { value: MangelSchweregrad; label: string }[] = [
  { value: "niedrig", label: "Niedrig" },
  { value: "mittel", label: "Mittel" },
  { value: "hoch", label: "Hoch" },
  { value: "kritisch", label: "Kritisch" },
];

export const SCHWEREGRAD_LABEL: Record<MangelSchweregrad, string> = Object.fromEntries(
  SCHWEREGRAD_OPTIONEN.map((o) => [o.value, o.label]),
) as Record<MangelSchweregrad, string>;

// Hervorhebung bei kritisch/hoch statt neutralem border-sep -- sonst
// sieht ein kritischer Mangel unter Zeitdruck optisch identisch zu einem
// niedrigen aus (Status-Token st-arbeit/st-fehlt statt eigener Farben).
export const SCHWEREGRAD_BADGE: Record<MangelSchweregrad, string> = {
  niedrig: "border-sep text-label",
  mittel: "border-sep text-label",
  hoch: "border-st-arbeit text-st-arbeit",
  kritisch: "border-st-fehlt text-st-fehlt",
};

export const MANGEL_STATUS_LABEL: Record<MangelStatus, string> = {
  offen: "Offen",
  in_angebot: "Im Angebot",
  in_bearbeitung: "In Bearbeitung",
  behoben: "Behoben",
  abgelehnt: "Abgelehnt",
};

export const TERMIN_STATUS_LABEL: Record<TerminStatus, string> = {
  geplant: "Geplant",
  bestaetigt: "Bestätigt",
  abgeschlossen: "Abgeschlossen",
  abgesagt: "Abgesagt",
};

export const LEISTUNGSTYPEN: { value: Leistungstyp; label: string }[] = [
  { value: "stoerung", label: "Störung" },
  { value: "installation", label: "Installation" },
  { value: "wartung", label: "Wartung" },
  { value: "pruefung", label: "Prüfung" },
  { value: "beratung", label: "Beratung" },
  { value: "planung", label: "Planung" },
];

export const STATUS_LABEL: Record<VorgangStatus, string> = {
  neu: "Neu",
  geplant: "Geplant",
  in_arbeit: "In Arbeit",
  wartet_kunde: "Wartet auf Kunde",
  abgeschlossen: "Abgeschlossen",
  abgerechnet: "Abgerechnet",
  storniert: "Storniert",
};

// Fuer die Kurzuebersicht-Spalte im Desktop-Layout (layout="dicht") --
// Leistungstyp/Abrechnungsart stehen sonst nirgends auf dieser Seite.
export const LEISTUNGSTYP_LABEL: Record<Leistungstyp, string> = {
  stoerung: "Störung",
  installation: "Installation",
  wartung: "Wartung",
  pruefung: "Prüfung",
  beratung: "Beratung",
  planung: "Planung",
};

export const ABRECHNUNGSART_LABEL: Record<VorgangAbrechnungsart, string> = {
  pauschale: "Pauschale",
  aufwand: "Nach Aufwand",
  festpreis: "Festpreis",
  wartungsvertrag: "Wartungsvertrag",
  gewaehrleistung: "Gewährleistung",
};

// Spiegelt app/services/vorgang_completion_service.py:VORGANG_STATUS_GESCHLOSSEN
// -- "Vorgang übernehmen" ergibt fuer bereits geschlossene Vorgaenge keinen
// Sinn mehr (das Backend lehnt es dort ohnehin mit 409 ab).
export const VORGANG_STATUS_GESCHLOSSEN: VorgangStatus[] = ["abgeschlossen", "abgerechnet", "storniert"];

// Spiegelt app/api/routes/zeiterfassung.py:_VORGANG_STATUS_ZEIT_GESPERRT --
// enger als VORGANG_STATUS_GESCHLOSSEN: Zeit nachtragen/bearbeiten bleibt
// nach "abgeschlossen" bewusst moeglich, nur nach Abrechnung/Stornierung
// nicht mehr (das Backend lehnt es sonst ohnehin mit 409 ab).
export const VORGANG_STATUS_ZEIT_GESPERRT: VorgangStatus[] = ["abgerechnet", "storniert"];

export const PRIORITAET_OPTIONEN = [1, 2, 3, 4, 5];

export const FREIGABE_LABEL: Record<PartnerFreigabeStatus, string> = {
  vorgeschlagen: "Wartet auf Rückmeldung",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
};

export const FREIGABE_FARBE: Record<PartnerFreigabeStatus, string> = {
  vorgeschlagen: "bg-st-arbeit-bg text-st-arbeit",
  angenommen: "bg-st-erledigt-bg text-st-erledigt",
  abgelehnt: "bg-st-fehlt-bg text-st-fehlt",
};

export const EVENT_LABEL: Partial<Record<string, string>> = {
  status_change: "Status geändert",
  foto: "Foto hinzugefügt",
  dokument: "Dokument hinzugefügt",
  mangel: "Mangel erfasst",
  angebot: "Angebot aktualisiert",
  material: "Material erfasst",
  zeit_start: "Zeit gestartet",
  zeit_stop: "Zeit gestoppt",
  termin: "Termin",
  rechnung_status: "Rechnungsstatus aktualisiert",
  unterschrift: "Unterschrift erfasst",
  leistung: "Leistung erfasst",
};

export const NEU_MATERIAL = "__neu__";

export const ANCHOR_ABSCHNITTE: { ziel: string; label: string }[] = [
  { ziel: "abschnitt-uebersicht", label: "Übersicht" },
  { ziel: "abschnitt-zeit", label: "Zeit" },
  { ziel: "abschnitt-termine", label: "Termine" },
  { ziel: "abschnitt-maengel", label: "Mängel" },
  { ziel: "abschnitt-material", label: "Positionen" },
  { ziel: "abschnitt-verlauf", label: "Verlauf" },
];

// Abschnitte, die im "kompakt"-Layout als eigene Unterseite statt als Teil
// der durchlaufenden Seite existieren (siehe arbeitszeitInhalt/
// verlaufInhalt/positionenInhalt weiter unten) -- Wert ist das Route-Suffix
// hinter /vorgaenge/:id/.
export const ABSCHNITT_ROUTE: Record<string, string> = {
  "abschnitt-zeit": "zeit",
  "abschnitt-verlauf": "verlauf",
  "abschnitt-material": "positionen",
};

export function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// Fuer den Termine-Wochenkalender im Desktop-Layout (layout="dicht") --
// gleiche Rechenlogik wie office/DispoBoardPage.tsx, hier aber lokal
// kopiert statt importiert: dort ist es eine Seiten-lokale Hilfsfunktion,
// kein geteiltes Modul.
export const WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

export function startOfWoche(d: Date): Date {
  const date = new Date(d);
  const tag = date.getDay(); // 0 = Sonntag
  const diffZuMontag = tag === 0 ? -6 : 1 - tag;
  date.setHours(0, 0, 0, 0);
  date.setDate(date.getDate() + diffZuMontag);
  return date;
}

export function addTage(d: Date, n: number): Date {
  const date = new Date(d);
  date.setDate(date.getDate() + n);
  return date;
}

export function tagesSchluessel(d: Date): string {
  return datumZuIso(d);
}

export function leereAdresse(adresse: Adresse | null | undefined): { strasse: string; plz: string; ort: string } {
  return { strasse: adresse?.strasse ?? "", plz: adresse?.plz ?? "", ort: adresse?.ort ?? "" };
}

export function adresseAlsZeile(adresse: Adresse | null | undefined): string {
  return [adresse?.strasse, [adresse?.plz, adresse?.ort].filter(Boolean).join(" ")]
    .filter(Boolean)
    .join(", ");
}
