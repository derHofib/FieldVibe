import {
  BarChart3,
  Bell,
  Briefcase,
  CalendarDays,
  ClipboardList,
  Clock,
  Gauge,
  Inbox,
  type LucideIcon,
  Mail,
  Plug,
  Receipt,
  Rss,
  Star,
  StickyNote,
  Tags,
  Timer,
  Trash2,
  TrendingUp,
  User,
  UserCog,
  Users,
  Wrench,
} from "lucide-react";

import type { IconTone } from "../components/IconBadge";
import { istModulAktiv } from "../utils/module";
import type { CurrentUser, RechteAktion, RechteBereich } from "../types";

// Einzige Quelle der Wahrheit fuer jede Seite, die ein Nutzer sich in die
// individualisierbare Bottom-Nav legen kann (siehe components/BottomNav.tsx
// + pages/feld/BottomNavSettingsPage.tsx). "sichtbar" spiegelt exakt dieselben
// Rechte-/Modul-Gates, die die jeweilige Seite bzw. ihr bisheriger Einstiegs-
// punkt (GeschaeftPage/DispoBoardPage/FeedPage/ProfilePage/SettingsPage)
// schon vorher verwendet hat -- keine neuen Berechtigungen, nur ein neuer,
// zentraler Ort dafuer.
export type NavKategorie = "Arbeit" | "Finanzen" | "Kommunikation" | "Verwaltung";

// Reihenfolge der Gruppen in der Office-Seitenleiste (office/OfficeLayout.tsx):
// taegliche Arbeit oben, Verwaltung als Selteneres unten.
export const NAV_KATEGORIE_REIHENFOLGE: NavKategorie[] = [
  "Arbeit",
  "Finanzen",
  "Kommunikation",
  "Verwaltung",
];

export interface NavSeite {
  key: string;
  label: string;
  icon: LucideIcon;
  tone: IconTone;
  route: string;
  kategorie: NavKategorie;
  sichtbar: (ctx: {
    currentUser: CurrentUser | undefined;
    hatRecht: (bereich: RechteBereich, aktion: RechteAktion) => boolean;
  }) => boolean;
  // Nur in der Office-Seitenleiste anwaehlbar, nie in der mobilen Bottom-Nav
  // (weder als fester Link noch in der Rotunde) -- siehe BottomNav.tsx.
  nurOffice?: boolean;
}

export const NAV_SEITEN: NavSeite[] = [
  {
    key: "feed",
    label: "Feed",
    icon: Rss,
    tone: "sky",
    route: "/feed",
    kategorie: "Kommunikation",
    sichtbar: () => true,
  },
  {
    key: "profil",
    label: "Profil",
    icon: User,
    tone: "violet",
    route: "/profil",
    kategorie: "Verwaltung",
    sichtbar: () => true,
  },
  {
    key: "boards",
    label: "Boards",
    icon: StickyNote,
    tone: "indigo",
    route: "/boards",
    kategorie: "Arbeit",
    sichtbar: () => true,
  },
  {
    key: "dispo",
    label: "Dispo",
    icon: CalendarDays,
    tone: "amber",
    route: "/dispo",
    kategorie: "Arbeit",
    sichtbar: ({ currentUser, hatRecht }) =>
      hatRecht("dispo", "sehen") && istModulAktiv(currentUser, "dispo"),
  },
  {
    key: "geschaeft",
    label: "Geschäft",
    icon: Briefcase,
    tone: "emerald",
    route: "/geschaeft",
    kategorie: "Arbeit",
    sichtbar: ({ currentUser, hatRecht }) =>
      (hatRecht("kunden", "sehen") && istModulAktiv(currentUser, "kundenverwaltung")) ||
      (hatRecht("abrechnung", "sehen") && istModulAktiv(currentUser, "abrechnung")) ||
      (hatRecht("material", "sehen") && istModulAktiv(currentUser, "material")),
  },
  {
    key: "zeiterfassung",
    label: "Zeiterfassung",
    icon: Timer,
    tone: "cyan",
    route: "/statistik",
    kategorie: "Arbeit",
    sichtbar: ({ currentUser }) => istModulAktiv(currentUser, "statistik"),
  },
  {
    key: "pruefmittel",
    label: "Prüfmittel",
    icon: Gauge,
    tone: "sky",
    route: "/pruefmittel",
    kategorie: "Arbeit",
    sichtbar: ({ currentUser }) => istModulAktiv(currentUser, "pruefzyklen"),
  },
  {
    key: "anfragen",
    label: "Auftragsanfragen",
    icon: Inbox,
    tone: "amber",
    route: "/anfragen",
    kategorie: "Arbeit",
    sichtbar: ({ currentUser }) => istModulAktiv(currentUser, "kundenportal"),
  },
  {
    key: "rechnungen",
    label: "Rechnungen",
    icon: Receipt,
    tone: "cyan",
    route: "/rechnungen",
    kategorie: "Finanzen",
    sichtbar: ({ currentUser, hatRecht }) =>
      hatRecht("abrechnung", "sehen") && istModulAktiv(currentUser, "abrechnung"),
  },
  {
    key: "rechnungseingang",
    label: "Rechnungseingang",
    icon: Inbox,
    tone: "cyan",
    route: "/rechnungseingang",
    kategorie: "Finanzen",
    sichtbar: ({ currentUser, hatRecht }) =>
      hatRecht("abrechnung", "sehen") && istModulAktiv(currentUser, "abrechnung"),
  },
  {
    key: "buchhaltung",
    label: "Buchhaltung",
    icon: BarChart3,
    tone: "indigo",
    route: "/auswertung",
    kategorie: "Finanzen",
    sichtbar: ({ currentUser, hatRecht }) =>
      hatRecht("abrechnung", "sehen") && istModulAktiv(currentUser, "abrechnung"),
  },
  {
    key: "kennzahlen",
    label: "Kennzahlen",
    icon: TrendingUp,
    tone: "sky",
    route: "/insights",
    kategorie: "Finanzen",
    sichtbar: ({ currentUser }) => istModulAktiv(currentUser, "statistik"),
  },
  {
    key: "meldungen",
    label: "Meldungen",
    icon: Bell,
    tone: "rose",
    route: "/benachrichtigungen",
    kategorie: "Kommunikation",
    sichtbar: ({ currentUser }) => currentUser?.role !== "loesch_ansicht",
  },
  {
    key: "postfach",
    label: "Postfach",
    icon: Mail,
    tone: "teal",
    route: "/postfach",
    kategorie: "Kommunikation",
    // Kein Rechte-Check wie bei den Business-Bereichen -- das eigene
    // Postfach ist persoenlich, nicht rollenabhaengig (nur der
    // Modul-Schalter des Mandanten kann es fuer alle abschalten).
    sichtbar: ({ currentUser }) => istModulAktiv(currentUser, "postfach"),
  },
  {
    key: "highlights",
    label: "Highlights",
    icon: Star,
    tone: "violet",
    route: "/highlights",
    kategorie: "Kommunikation",
    sichtbar: ({ currentUser }) => istModulAktiv(currentUser, "highlights"),
  },
  {
    key: "nutzer",
    label: "Nutzer verwalten",
    icon: Users,
    tone: "amber",
    route: "/accounts",
    kategorie: "Verwaltung",
    sichtbar: () => true,
  },
  {
    key: "account_typen",
    label: "Account-Typen & Rechte",
    icon: UserCog,
    tone: "violet",
    route: "/account-typen",
    kategorie: "Verwaltung",
    sichtbar: () => true,
  },
  {
    key: "techniker_zuweisungen",
    label: "Techniker-Zuweisungen",
    icon: Wrench,
    tone: "emerald",
    route: "/techniker-zuweisungen",
    kategorie: "Verwaltung",
    sichtbar: ({ hatRecht }) => hatRecht("dispo", "bearbeiten"),
  },
  {
    key: "team_zeiten",
    label: "Team-Zeiten",
    icon: Clock,
    tone: "cyan",
    route: "/team-zeiten",
    kategorie: "Verwaltung",
    sichtbar: ({ hatRecht }) => hatRecht("mitarbeiterverwaltung", "bearbeiten"),
  },
  {
    key: "anlagen_felder",
    label: "Anlagen-Zusatzfelder",
    icon: Tags,
    tone: "rose",
    route: "/anlagen-felder",
    kategorie: "Verwaltung",
    sichtbar: () => true,
  },
  {
    key: "formulare",
    label: "Formulare",
    icon: ClipboardList,
    tone: "violet",
    route: "/formulare",
    kategorie: "Verwaltung",
    sichtbar: ({ hatRecht }) => hatRecht("formulare", "sehen"),
  },
  {
    key: "integrationen",
    label: "Firmendaten & Integrationen",
    icon: Plug,
    tone: "indigo",
    route: "/integrationen",
    kategorie: "Verwaltung",
    sichtbar: () => true,
  },
  {
    key: "papierkorb",
    label: "Papierkorb",
    icon: Trash2,
    tone: "slate",
    route: "/papierkorb",
    kategorie: "Verwaltung",
    sichtbar: ({ currentUser }) =>
      currentUser?.role === "loesch_ansicht" || currentUser?.role === "loesch_operativ",
  },
];

// Bottom-Nav-Layout (siehe components/BottomNav.tsx): links vom Neu-Button
// eine feste, nicht wischbare Zone mit genau LINKS_SLOT_ANZAHL Seiten,
// rechts vom Neu-Button eine wischbare "Rotunde" beliebiger Laenge (das
// zentrierte Icon gross, die Nachbarn kleiner). Beide Zonen sind frei
// konfigurierbar (siehe pages/feld/BottomNavSettingsPage.tsx).
export const LINKS_SLOT_ANZAHL = 2;

// Standardbelegung fuer Nutzer ohne eigene Praeferenz (bottom_nav_items ===
// null) -- entspricht dem bisherigen Verhalten: Feed/Profil fest, der Rest
// wie im vormaligen "Mehr"-Menue.
export const STANDARD_LINKS = ["feed", "profil"];
export const STANDARD_ROTUNDE = [
  "meldungen",
  "dispo",
  "geschaeft",
  "rechnungen",
  "rechnungseingang",
  "buchhaltung",
  "papierkorb",
];

export function sichtbareNavSeiten(
  currentUser: CurrentUser | undefined,
  hatRecht: (bereich: RechteBereich, aktion: RechteAktion) => boolean,
): NavSeite[] {
  return NAV_SEITEN.filter((seite) => seite.sichtbar({ currentUser, hatRecht }));
}

// Gemeinsam von BottomNav.tsx und BottomNavSettingsPage.tsx genutzt, damit
// beide garantiert dieselbe feste Zone berechnen. Filtert auf gerade
// sichtbare Seiten, kappt auf LINKS_SLOT_ANZAHL und fuellt bei Bedarf (leere
// oder zu kurze gespeicherte Auswahl, aeltere Daten) aus STANDARD_LINKS auf,
// damit die feste Zone nie eine kaputte Luecke zeigt.
export function effektiveLinks(
  gespeichert: string[] | null | undefined,
  sichtbareSeiten: NavSeite[],
): string[] {
  const sichtbareKeys = new Set(sichtbareSeiten.map((seite) => seite.key));
  const basis = (gespeichert ?? STANDARD_LINKS)
    .filter((key) => sichtbareKeys.has(key))
    .slice(0, LINKS_SLOT_ANZAHL);
  if (basis.length >= LINKS_SLOT_ANZAHL) return basis;
  const auffuellen = STANDARD_LINKS.filter(
    (key) => sichtbareKeys.has(key) && !basis.includes(key),
  );
  return [...basis, ...auffuellen].slice(0, LINKS_SLOT_ANZAHL);
}

// Analog fuer die wischbare Rotunde rechts -- keine Mindestlaenge, keine
// Pflicht-Keys (Feed/Profil leben jetzt ausschliesslich in effektiveLinks).
export function effektiveRotunde(
  gespeichert: string[] | null | undefined,
  sichtbareSeiten: NavSeite[],
): string[] {
  const sichtbareKeys = new Set(sichtbareSeiten.map((seite) => seite.key));
  return (gespeichert ?? STANDARD_ROTUNDE).filter((key) => sichtbareKeys.has(key));
}
