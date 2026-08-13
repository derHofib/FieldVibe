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
  Plug,
  Receipt,
  Rss,
  Star,
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
}

// Feed und Profil sind Pflichtbestandteile der Leiste (siehe MANDATORY_KEYS
// weiter unten) -- sie tauchen deshalb nie in der "Weitere Seiten"-Auswahl
// der Einstellungen auf (immer schon in gewaehlteKeys enthalten), lassen
// sich dort aber wie jeder andere Punkt per Pfeiltasten verschieben.
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

// Feed (Start) und Profil (eigener Account) sind nie abwaehlbar -- ohne Feed
// gaebe es keinen erreichbaren Startpunkt mehr, ohne Profil kein Logout.
// Beide duerfen aber frei ihre Position wechseln (siehe effektiveNavKeys).
export const MANDATORY_KEYS = ["feed", "profil"];

// Bisheriges "Mehr"-Menue plus die vormals fest verdrahteten Feed/Profil-
// Positionen, 1:1 als Standardauswahl fuer Nutzer ohne eigene Praeferenz
// (bottom_nav_items === null) -- siehe vormals BottomNav.tsx mehrItems.
// Reihenfolge bewusst beibehalten (Feed zuerst, Profil zuletzt).
export const STANDARD_BOTTOM_NAV_KEYS = [
  "feed",
  "meldungen",
  "dispo",
  "geschaeft",
  "rechnungen",
  "rechnungseingang",
  "buchhaltung",
  "papierkorb",
  "profil",
];

export function sichtbareNavSeiten(
  currentUser: CurrentUser | undefined,
  hatRecht: (bereich: RechteBereich, aktion: RechteAktion) => boolean,
): NavSeite[] {
  return NAV_SEITEN.filter((seite) => seite.sichtbar({ currentUser, hatRecht }));
}

// Gemeinsam von BottomNav.tsx und BottomNavSettingsPage.tsx genutzt, damit
// beide garantiert dieselbe Reihenfolge/Zusammensetzung berechnen. Filtert
// auf gerade sichtbare Seiten und stellt sicher, dass Feed/Profil auch dann
// enthalten sind, wenn eine gespeicherte Auswahl (aeltere Daten, direkter
// API-Zugriff) sie ausnahmsweise nicht enthaelt.
export function effektiveNavKeys(
  gespeichert: string[] | null,
  sichtbareSeiten: NavSeite[],
): string[] {
  const sichtbareKeys = new Set(sichtbareSeiten.map((seite) => seite.key));
  const basis = gespeichert ?? STANDARD_BOTTOM_NAV_KEYS;
  const ergebnis = basis.filter((key) => sichtbareKeys.has(key));
  for (const key of MANDATORY_KEYS) {
    if (!sichtbareKeys.has(key) || ergebnis.includes(key)) continue;
    if (key === "feed") ergebnis.unshift(key);
    else ergebnis.push(key);
  }
  return ergebnis;
}
