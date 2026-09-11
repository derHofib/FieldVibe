// Katalog der verfuegbaren Feldtypen, in Kategorien sortiert -- das ist die
// Kaestchen-Liste, aus der ein neues Feld in den Formular-Editor gezogen
// wird (siehe FormBuilderCanvas.tsx). Reihenfolge/Kategorisierung ist eine
// Vereinfachung fuer den Einstieg; welche FELD_TYPEN es ueberhaupt geben
// soll, ist ein eigenes, spaeteres Thema. Eigene Datei statt Teil der
// Editor-Seite, weil sowohl die Seite als auch der Canvas/die Palette ihn
// brauchen.
import {
  AlignLeft,
  Calendar,
  Camera,
  Euro,
  Hash,
  Home,
  List,
  ListChecks,
  Mail,
  MapPin,
  Paperclip,
  PenLine,
  Phone,
  ScanLine,
  Star,
  ToggleLeft,
  Type,
  type LucideIcon,
} from "lucide-react";

import type { FormFeldTyp } from "../types";

export const FELD_TYP_KATALOG: { name: string; typen: { typ: FormFeldTyp; label: string; icon: LucideIcon }[] }[] = [
  {
    name: "Text & Zahlen",
    typen: [
      { typ: "text", label: "Text (einzeilig)", icon: Type },
      { typ: "textarea", label: "Text (mehrzeilig)", icon: AlignLeft },
      { typ: "zahl", label: "Zahl", icon: Hash },
      { typ: "betrag", label: "Betrag (€)", icon: Euro },
      { typ: "datum", label: "Datum", icon: Calendar },
      { typ: "email", label: "E-Mail", icon: Mail },
      { typ: "telefon", label: "Telefon", icon: Phone },
      { typ: "adresse", label: "Adresse", icon: Home },
    ],
  },
  {
    name: "Auswahl",
    typen: [
      { typ: "dropdown", label: "Dropdown", icon: List },
      { typ: "mehrfachauswahl", label: "Mehrfachauswahl", icon: ListChecks },
      { typ: "ja_nein", label: "Ja / Nein", icon: ToggleLeft },
      { typ: "bewertung", label: "Bewertung (Skala)", icon: Star },
    ],
  },
  {
    name: "Erfassung vor Ort",
    typen: [
      { typ: "foto", label: "Foto", icon: Camera },
      { typ: "datei", label: "Datei (Bild/PDF)", icon: Paperclip },
      { typ: "unterschrift", label: "Unterschrift", icon: PenLine },
      { typ: "gps", label: "GPS-Standort", icon: MapPin },
      { typ: "qr_scan", label: "QR-/Barcode-Scan", icon: ScanLine },
    ],
  },
];

export const FELD_TYP_LABEL = Object.fromEntries(
  FELD_TYP_KATALOG.flatMap((k) => k.typen.map((t) => [t.typ, t.label])),
) as Record<FormFeldTyp, string>;
