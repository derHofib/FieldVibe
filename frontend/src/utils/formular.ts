import {
  AlignLeft,
  Calendar,
  Camera,
  CheckSquare,
  Hash,
  Heading,
  ListChecks,
  MapPin,
  PenLine,
  ScanLine,
  Star,
  ToggleLeft,
  Type,
  type LucideIcon,
} from "lucide-react";

import type { FormularfeldDatenquelle, FormularfeldTyp } from "../types";

export const FORMULARFELD_TYP_LABEL: Record<FormularfeldTyp, string> = {
  text: "Text (einzeilig)",
  textarea: "Text (mehrzeilig)",
  zahl: "Zahl",
  datum: "Datum",
  dropdown: "Auswahl (Dropdown)",
  mehrfachauswahl: "Mehrfachauswahl",
  ja_nein: "Ja/Nein",
  bewertung: "Bewertung",
  foto: "Foto",
  unterschrift: "Unterschrift",
  gps: "GPS-Standort",
  qr_scan: "Barcode/QR-Scan",
  abschnitt: "Abschnitts-Überschrift",
};

export const FORMULARFELD_TYP_ICON: Record<FormularfeldTyp, LucideIcon> = {
  text: Type,
  textarea: AlignLeft,
  zahl: Hash,
  datum: Calendar,
  dropdown: ListChecks,
  mehrfachauswahl: CheckSquare,
  ja_nein: ToggleLeft,
  bewertung: Star,
  foto: Camera,
  unterschrift: PenLine,
  gps: MapPin,
  qr_scan: ScanLine,
  abschnitt: Heading,
};

export const LEISTUNGSTYP_LABEL: Record<string, string> = {
  installation: "Installation",
  pruefung: "Prüfung",
  wartung: "Wartung",
  stoerung: "Störung",
  beratung: "Beratung",
  planung: "Planung",
};

// Feldtypen, die eine Datenquellen-Bindung (Auto-Fill aus dem Vorgang)
// unterstuetzen -- siehe FORMULARFELD_TYPEN_MIT_DATENQUELLE in
// backend/app/models/formular.py. dropdown ist bewusst ausgeschlossen, da
// ein aufgeloester Wert nicht zwingend in den definierten Auswahlwerten
// enthalten ist.
export const FORMULARFELD_TYPEN_MIT_DATENQUELLE: FormularfeldTyp[] = ["text", "textarea", "zahl", "datum"];

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
};
