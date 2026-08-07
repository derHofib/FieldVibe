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

import type { FormularfeldTyp } from "../types";

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
