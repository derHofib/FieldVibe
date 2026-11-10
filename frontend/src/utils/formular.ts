import type { FormularfeldDatenquelle } from "../types";

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
