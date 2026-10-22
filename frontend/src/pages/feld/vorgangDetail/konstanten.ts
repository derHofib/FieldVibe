import type {
  Leistungstyp, MangelSchweregrad, MangelStatus, PartnerFreigabeStatus, TerminStatus,
  VorgangAbrechnungsart, VorgangStatus,
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

export const STATUS_OPTIONS: VorgangStatus[] = [
  "neu",
  "geplant",
  "in_arbeit",
  "wartet_kunde",
  "abgeschlossen",
  "abgerechnet",
  "storniert",
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
// -- "Ticket übernehmen" ergibt fuer bereits geschlossene Vorgaenge keinen
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
// der durchlaufenden Seite existieren (siehe ArbeitszeitInhalt/
// VerlaufInhalt/PositionenInhalt) -- Wert ist das Route-Suffix
// hinter /vorgaenge/:id/.
export const ABSCHNITT_ROUTE: Record<string, string> = {
  "abschnitt-zeit": "zeit",
  "abschnitt-verlauf": "verlauf",
  "abschnitt-material": "positionen",
};
