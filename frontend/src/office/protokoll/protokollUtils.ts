export interface ProtokollEintrag {
  id: number;
  zeit: string;
  akteur_typ: "user" | "portal" | "system" | "partner";
  actor_user_id: string | null;
  actor_name: string | null;
  aktion: string;
  entity_type: string | null;
  entity_id: string | null;
  payload: Record<string, unknown>;
  request_id: string | null;
  ip: string | null;
}

export interface ProtokollListe {
  eintraege: ProtokollEintrag[];
  gesamt: number;
}

export interface ProtokollFilter {
  von?: string;
  bis?: string;
  aktion?: string;
  entity_type?: string;
  akteur_typ?: string;
}

export interface KettenFehler {
  seq: number | null;
  audit_log_id: number | null;
  grund: string;
}

export interface KettenPruefung {
  ok: boolean;
  geprueft: number;
  kopf_seq: number | null;
  kopf_hash: string | null;
  ohne_siegel: number;
  legacy_eintraege: number;
  fehler: KettenFehler[];
}

export const AKTEUR_LABEL: Record<ProtokollEintrag["akteur_typ"], string> = {
  user: "Mitarbeiter",
  portal: "Kundenportal",
  system: "System",
  partner: "Partner",
};

// Bekannte Aktionen mit lesbarem Namen; alles andere wird aus dem Schluessel abgeleitet.
const AKTION_LABEL: Record<string, string> = {
  login: "Anmeldung",
  login_fehlgeschlagen: "Anmeldung fehlgeschlagen",
  logout: "Abmeldung",
  logout_alle_geraete: "Überall abgemeldet",
  passwort_geaendert: "Passwort geändert",
  passwort_zurueckgesetzt: "Passwort zurückgesetzt",
  mfa_aktiviert: "MFA aktiviert",
  mfa_deaktiviert: "MFA deaktiviert",
  mfa_zurueckgesetzt: "MFA zurückgesetzt",
  user_erstellt: "Nutzer angelegt",
  user_geaendert: "Nutzer geändert",
  user_rolle_geaendert: "Rolle/Rechte geändert",
  user_anonymisiert: "Nutzer anonymisiert",
  user_geloescht: "Nutzer gelöscht",
  rechnung_erstellt: "Rechnung erstellt",
  rechnung_versendet: "Rechnung versendet",
  rechnung_email_versendet: "Rechnung per E-Mail gesendet",
  rechnung_storniert: "Rechnung storniert",
  rechnung_als_bezahlt_markiert: "Rechnung als bezahlt markiert",
  rechnung_entwurf_geloescht: "Rechnungsentwurf gelöscht",
  gutschrift_erstellt: "Gutschrift erstellt",
  abschlaege_angerechnet: "Abschläge angerechnet",
  zahlung_gebucht: "Zahlung gebucht",
  zahlung_storniert: "Zahlung storniert",
  angebot_versendet: "Angebot versendet",
  angebot_angenommen: "Angebot angenommen",
  angebot_abgelehnt: "Angebot abgelehnt",
  angebot_annahme: "Angebot im Portal angenommen",
  angebot_ablehnung: "Angebot im Portal abgelehnt",
  angebot_widerruf: "Angebot widerrufen",
  steuerdaten_geaendert: "Steuerdaten geändert",
  papierkorb_endgueltig_geloescht: "Endgültig gelöscht",
  datenimport_ausgefuehrt: "Datenimport ausgeführt",
  datenimport_rueckgaengig: "Datenimport rückgängig",
  export_audit_csv: "Export: Protokoll (CSV)",
  export_csv: "Export: CSV",
  export_datev: "Export: DATEV",
  export_ustva: "Auswertung: UStVA",
  export_z3: "Export: Z3 (Datenträgerüberlassung)",
  export_vollexport: "Export: Vollexport",
};

export function aktionLabel(aktion: string): string {
  const bekannt = AKTION_LABEL[aktion];
  if (bekannt) return bekannt;
  const text = aktion.replace(/[._]+/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function filterQuery(filter: ProtokollFilter, extra: Record<string, string | number> = {}): string {
  const eintraege = Object.entries({ ...filter, ...extra }).filter(([, v]) => v !== undefined && v !== "");
  return new URLSearchParams(eintraege.map(([k, v]) => [k, String(v)])).toString();
}

export function zeitText(iso: string): string {
  return new Date(iso).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "medium" });
}

/** Kurzfassung der Details fuer die Tabelle: "schluessel: wert" je Eintrag, lange Werte gekuerzt. */
export function detailsText(payload: Record<string, unknown>, maxZeichen = 120): string {
  const teile = Object.entries(payload).map(([k, v]) => {
    const wert = typeof v === "object" && v !== null ? JSON.stringify(v) : String(v);
    return `${k}: ${wert}`;
  });
  const text = teile.join(" · ");
  return text.length > maxZeichen ? `${text.slice(0, maxZeichen - 1)}…` : text;
}

export function seitenText(offset: number, anzahl: number, gesamt: number): string {
  if (gesamt === 0) return "Keine Einträge";
  return `${offset + 1}–${offset + anzahl} von ${gesamt.toLocaleString("de-DE")}`;
}
