import type { FormField, FormSchema, FormSchemaDetail, FormSubmissionUebersicht, FormView } from "../../types";

export const schema = (teil: Partial<FormSchema> & { id: string; name: string }): FormSchema => ({
  beschreibung: null,
  version: 1,
  status: "published",
  vorgaenger_id: null,
  erstellt_von: "u1",
  erstellt_via: "app",
  erstellt_von_name: "D. Hofmann",
  felder_anzahl: 3,
  leistungstypen: [],
  ausgefuellt_anzahl: 0,
  created_at: "2026-11-18T08:00:00Z",
  updated_at: "2026-11-18T08:00:00Z",
  ...teil,
});

export const feld = (key: string, feld_typ: FormField["feld_typ"], validation: Record<string, unknown> = {}): FormField => ({
  id: key,
  key,
  feld_typ,
  label: { de: key },
  hilfetext: null,
  pflichtfeld: false,
  validation,
  default_value: null,
  optionen: {},
  group_key: null,
  datenquelle: null,
  reihenfolge: 0,
});

export const detail = (s: FormSchema, felder: FormField[] = [feld("co", "zahl", { warn_max: 50 })]): FormSchemaDetail => ({
  ...s,
  groups: [],
  fields: felder,
  zuordnungen: [],
});

export const view = (id: string, type: FormView["type"]): FormView => ({
  id,
  schema_id: "s1",
  type,
  name: type,
  konfiguration: {},
  erstellt_von: null,
  created_at: "2026-11-18T08:00:00Z",
  updated_at: "2026-11-18T08:00:00Z",
});

export const uebersicht = (teil: Partial<FormSubmissionUebersicht> & { id: string }): FormSubmissionUebersicht => ({
  schema_id: "s1",
  schema_name: "Pre Check",
  schema_version: 1,
  vorgang_id: "v1",
  vorgangsnummer: "V-00040",
  vorgang_titel: "Störung Heizung Kita",
  kunde_name: "Gemeinde Rosenau",
  status: "abgeschlossen",
  erstellt_via: "app",
  ausgefuellt_von_name: "T. Becker",
  kundensichtbar: false,
  created_at: "2026-11-18T07:00:00Z",
  abgeschlossen_am: "2026-11-18T09:40:00Z",
  ...teil,
});
