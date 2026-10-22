import {
  Archive,
  BarChart3,
  Bell,
  CalendarCheck,
  CalendarDays,
  CalendarRange,
  ClipboardList,
  Clock,
  FileUp,
  Gauge,
  HardHat,
  Hourglass,
  Inbox,
  KanbanSquare,
  Layers,
  ListChecks,
  type LucideIcon,
  Mail,
  Network,
  Package,
  Plug,
  Receipt,
  Rss,
  ScrollText,
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
import type { CurrentUser, NavKategorienRead, RechteAktion, RechteBereich } from "../types";

// Einzige Quelle der Wahrheit fuer jede Seite in der Office-Seitenleiste
// (office/OfficeLayout.tsx) und im "Mehr"-Tab der Feld-App
// (pages/feld/MehrPage.tsx). "sichtbar" spiegelt exakt dieselben Rechte-/
// Modul-Gates, die die jeweilige Seite bzw. ihr bisheriger Einstiegspunkt
// (GeschaeftPage/DispoBoardPage/FeedPage/ProfilePage/SettingsPage) schon
// vorher verwendet hat -- keine neuen Berechtigungen, nur ein neuer,
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

// mandant_admin und loesch_operativ: das Backend laesst loesch_operativ ueberall durch,
// wo require_roles("mandant_admin") steht (app/api/deps.py). nur_mandant_admin
// (Protokoll, Export) schliesst es dagegen aus.
function istAdmin(currentUser: CurrentUser | undefined): boolean {
  return currentUser?.role === "mandant_admin" || currentUser?.role === "loesch_operativ";
}

// loesch_ansicht sieht im Backend ausschliesslich den Papierkorb. Seine Rechte-Matrix ist
// trotzdem voll (alle Nicht-custom-Rollen), die rechtebasierten Gates liessen sonst jede
// Seite durch, die dann nur 403 liefert.
const SEITEN_LOESCH_ANSICHT = new Set(["papierkorb", "profil"]);

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
  // Nur in der Office-Seitenleiste anwaehlbar, taucht im "Mehr"-Tab der
  // Feld-App nicht auf -- siehe pages/feld/MehrPage.tsx.
  nurOffice?: boolean;
  // Gegenstueck: nur im "Mehr"-Tab der Feld-App, nicht in der Office-Seitenleiste
  // (dort fuehrt /projekte auf das Kanban, das ein Nutzer ohne projekte.sehen nicht oeffnen darf).
  nurFeld?: boolean;
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
    key: "projekte",
    label: "Projekte",
    icon: KanbanSquare,
    tone: "amber",
    route: "/projekte",
    kategorie: "Arbeit",
    // Kanban mit Drag&Drop ist am Desktop gebaut, nicht fuer die schmale
    // Feld-App-Spalte -- siehe office/OfficeProjektePage.tsx.
    nurOffice: true,
    sichtbar: ({ hatRecht }) => hatRecht("projekte", "sehen"),
  },
  {
    key: "zeitplaene",
    label: "Zeitpläne",
    icon: CalendarRange,
    tone: "amber",
    route: "/projekte",
    kategorie: "Arbeit",
    // Techniker ohne projekte.sehen: die Projekte-Seite der Feld-App zeigt dann
    // "Meine Zeitpläne" statt der Projektliste (pages/feld/ProjektePageMobil.tsx).
    nurFeld: true,
    sichtbar: ({ hatRecht }) => hatRecht("projekte", "zeitplan_sehen") && !hatRecht("projekte", "sehen"),
  },
  {
    key: "auftraege",
    label: "Aufträge",
    icon: Layers,
    tone: "teal",
    route: "/auftraege",
    kategorie: "Arbeit",
    // Tabellen-Ansicht mit Sortierung -- wie "projekte" am Desktop gebaut,
    // nutzt denselben Rechte-Bereich (siehe app/models/auftrag.py).
    nurOffice: true,
    sichtbar: ({ hatRecht }) => hatRecht("projekte", "sehen"),
  },
  {
    key: "meine-aufgaben",
    label: "Meine Aufgaben",
    icon: ListChecks,
    tone: "violet",
    route: "/meine-aufgaben",
    kategorie: "Arbeit",
    // Bewusst KEIN Rechte-Gate: private Aufgaben (Projekt-Aufgaben ohne
    // Projekt) sind fuer jeden Nutzer nutzbar, unabhaengig vom Rechte-
    // Bereich "projekte" (der nur das Kanban-Board schuetzt). Reine Liste,
    // kein Drag&Drop -- deshalb anders als "projekte" auch in der Feld-App.
    sichtbar: () => true,
  },
  {
    key: "kunden",
    label: "Kundenverwaltung",
    icon: Users,
    tone: "emerald",
    route: "/kunden",
    kategorie: "Arbeit",
    sichtbar: ({ currentUser, hatRecht }) =>
      hatRecht("kunden", "sehen") && istModulAktiv(currentUser, "kundenverwaltung"),
  },
  {
    key: "partner",
    label: "Partner & Nachunternehmer",
    icon: HardHat,
    tone: "amber",
    route: "/partner",
    kategorie: "Arbeit",
    sichtbar: ({ currentUser, hatRecht }) =>
      istModulAktiv(currentUser, "nachunternehmer") && hatRecht("partner", "sehen"),
  },
  {
    key: "material",
    label: "Material",
    icon: Package,
    tone: "amber",
    route: "/material",
    kategorie: "Arbeit",
    sichtbar: ({ currentUser, hatRecht }) =>
      hatRecht("material", "sehen") && istModulAktiv(currentUser, "material"),
  },
  {
    key: "zeiterfassung",
    label: "Zeiterfassung",
    icon: Timer,
    tone: "cyan",
    route: "/statistik",
    kategorie: "Arbeit",
    sichtbar: ({ currentUser }) => istModulAktiv(currentUser, "zeiterfassung"),
  },
  {
    key: "zeiten_buchen",
    label: "Zeiten buchen",
    icon: Hourglass,
    tone: "cyan",
    route: "/zeiten-buchen",
    kategorie: "Arbeit",
    // Nur fuer Buchungsberechtigte (Konzept 7.3) -- ohne das Recht gibt es
    // dort nichts zu tun (kein Techniker vermerkt/bucht fuer sich selbst).
    sichtbar: ({ currentUser }) =>
      !!currentUser?.darf_zeiten_buchen && istModulAktiv(currentUser, "zeiterfassung"),
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
    label: "Vorgangsanfragen",
    icon: Inbox,
    tone: "amber",
    route: "/anfragen",
    kategorie: "Arbeit",
    // /api/vorgang-anfragen verlangt vorgaenge.bearbeiten.
    sichtbar: ({ currentUser, hatRecht }) =>
      hatRecht("vorgaenge", "bearbeiten") && istModulAktiv(currentUser, "kundenportal"),
  },
  {
    key: "rechnungen",
    label: "Rechnungen & Angebote",
    icon: Receipt,
    tone: "cyan",
    route: "/rechnungen",
    kategorie: "Finanzen",
    sichtbar: ({ currentUser, hatRecht }) =>
      hatRecht("abrechnung", "sehen") && istModulAktiv(currentUser, "abrechnung"),
  },
  {
    key: "leistungsverzeichnis",
    label: "Leistungsverzeichnis",
    icon: ClipboardList,
    tone: "cyan",
    route: "/leistungsverzeichnis",
    kategorie: "Finanzen",
    // Gleiches Recht wie der Endpunkt selbst (haengt fachlich am Kunden,
    // siehe app/api/routes/leistungsverzeichnis.py).
    sichtbar: ({ hatRecht }) => hatRecht("kunden", "sehen"),
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
    // Das Backend sperrt /api/auswertung fuer Nutzer mit Kundeneinschraenkung
    // komplett (403) -- Menuepunkt gar nicht erst anbieten.
    sichtbar: ({ currentUser, hatRecht }) =>
      hatRecht("abrechnung", "sehen") &&
      istModulAktiv(currentUser, "abrechnung") &&
      !currentUser?.nur_zugewiesene_kunden,
  },
  {
    key: "kennzahlen",
    label: "Kennzahlen",
    icon: TrendingUp,
    tone: "sky",
    route: "/insights",
    kategorie: "Finanzen",
    // /api/insights: nur Admin-Rollen, zusaetzlich Modul "statistik".
    sichtbar: ({ currentUser }) => istAdmin(currentUser) && istModulAktiv(currentUser, "statistik"),
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
    sichtbar: ({ currentUser, hatRecht }) =>
      hatRecht("vorgaenge", "sehen") && istModulAktiv(currentUser, "highlights"),
  },
  {
    key: "nutzer",
    label: "Nutzer verwalten",
    icon: Users,
    tone: "amber",
    route: "/accounts",
    kategorie: "Verwaltung",
    // GET /api/users: mandant_admin bzw. custom mit mitarbeiterverwaltung.sehen.
    sichtbar: ({ hatRecht }) => hatRecht("mitarbeiterverwaltung", "sehen"),
  },
  {
    key: "account_typen",
    label: "Account-Typen & Rechte",
    icon: UserCog,
    tone: "violet",
    route: "/account-typen",
    kategorie: "Verwaltung",
    // Backend (_verwalter): Admin oder rechte_verwalten im Organigramm bzw. der Mitarbeiterverwaltung.
    sichtbar: ({ currentUser, hatRecht }) =>
      istAdmin(currentUser) ||
      hatRecht("organigramm", "rechte_verwalten") ||
      hatRecht("mitarbeiterverwaltung", "rechte_verwalten"),
  },
  {
    key: "organigramm",
    label: "Organigramm",
    icon: Network,
    tone: "indigo",
    route: "/organigramm",
    kategorie: "Verwaltung",
    // Diagramm mit Drag&Drop und breiter Rechte-Matrix: nur am Desktop (Office).
    nurOffice: true,
    sichtbar: ({ hatRecht }) => hatRecht("organigramm", "sehen"),
  },
  {
    key: "techniker_zuweisungen",
    label: "Techniker-Zuweisungen",
    icon: Wrench,
    tone: "emerald",
    route: "/techniker-zuweisungen",
    kategorie: "Verwaltung",
    // /api/techniker-zuweisungen verlangt kunden.bearbeiten (nicht dispo.bearbeiten).
    sichtbar: ({ hatRecht }) => hatRecht("kunden", "bearbeiten"),
  },
  {
    key: "abwesenheiten",
    label: "Abwesenheiten",
    icon: CalendarCheck,
    tone: "cyan",
    route: "/abwesenheiten",
    kategorie: "Verwaltung",
    sichtbar: ({ currentUser }) =>
      !!currentUser?.darf_abwesenheiten_verwalten && istModulAktiv(currentUser, "zeiterfassung"),
  },
  {
    key: "team_zeiten",
    label: "Team-Zeiten",
    icon: Clock,
    tone: "cyan",
    route: "/team-zeiten",
    kategorie: "Verwaltung",
    sichtbar: ({ hatRecht, currentUser }) =>
      hatRecht("mitarbeiterverwaltung", "bearbeiten") && istModulAktiv(currentUser, "zeiterfassung"),
  },
  {
    key: "anlagen_felder",
    label: "Anlagen-Zusatzfelder",
    icon: Tags,
    tone: "rose",
    route: "/anlagen-felder",
    kategorie: "Verwaltung",
    sichtbar: ({ hatRecht }) => hatRecht("kunden", "sehen"),
  },
  {
    key: "formulare",
    label: "Formulare",
    icon: ClipboardList,
    tone: "violet",
    route: "/form-schemas",
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
    sichtbar: ({ currentUser }) => istAdmin(currentUser),
  },
  {
    key: "protokoll",
    label: "Protokoll",
    icon: ScrollText,
    tone: "slate",
    route: "/protokoll",
    kategorie: "Verwaltung",
    // Tabelle mit Details und Integritaetspruefung: nur am Desktop; Backend: require_roles("mandant_admin").
    nurOffice: true,
    sichtbar: ({ currentUser }) => currentUser?.role === "mandant_admin",
  },
  {
    key: "datenimport",
    label: "Datenimport",
    icon: FileUp,
    tone: "teal",
    route: "/datenimport",
    kategorie: "Verwaltung",
    // Assistent mit breiten Tabellen (Zuordnung, Probelauf): nur am Desktop; Backend:
    // require_roles("mandant_admin"), also inkl. loesch_operativ.
    nurOffice: true,
    sichtbar: ({ currentUser }) => istAdmin(currentUser),
  },
  {
    key: "export",
    label: "Daten exportieren",
    icon: Archive,
    tone: "teal",
    route: "/einstellungen/export",
    kategorie: "Verwaltung",
    // Breite Tabelle, nur am Desktop; Backend: nur_mandant_admin (schliesst loesch_operativ aus).
    nurOffice: true,
    sichtbar: ({ currentUser }) => currentUser?.role === "mandant_admin",
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

export function sichtbareNavSeiten(
  currentUser: CurrentUser | undefined,
  hatRecht: (bereich: RechteBereich, aktion: RechteAktion) => boolean,
  oberflaeche: "office" | "feld" = "office",
): NavSeite[] {
  return NAV_SEITEN.filter(
    (seite) =>
      (oberflaeche === "feld" || !seite.nurFeld) &&
      (currentUser?.role !== "loesch_ansicht" || SEITEN_LOESCH_ANSICHT.has(seite.key)) &&
      seite.sichtbar({ currentUser, hatRecht }),
  );
}

export interface NavGruppe {
  name: string;
  seiten: NavSeite[];
}

// Gruppierung fuer die Office-Seitenleiste (siehe office/OfficeLayout.tsx).
// custom === undefined oder custom.kategorien leer -> der Mandant hat die
// Menue-Kategorien noch nie angepasst, dann gelten unveraendert die vier
// hart codierten Standardkategorien. Sobald custom.kategorien etwas
// enthaelt, ersetzt das komplett: Reihenfolge/Namen kommen aus custom,
// jede sichtbare Seite ohne (noch) passende Zuordnung -- z.B. ein erst
// nach dem letzten Speichern neu hinzugekommener Menuepunkt -- landet
// gesammelt in einer angehaengten "Weitere"-Gruppe, statt zu verschwinden.
export function effektiveNavGruppen(
  angezeigt: NavSeite[],
  custom: NavKategorienRead | undefined,
): NavGruppe[] {
  if (!custom || custom.kategorien.length === 0) {
    return NAV_KATEGORIE_REIHENFOLGE.map((kategorie) => ({
      name: kategorie as string,
      seiten: angezeigt.filter((seite) => seite.kategorie === kategorie),
    })).filter((gruppe) => gruppe.seiten.length > 0);
  }

  const gruppen: NavGruppe[] = [...custom.kategorien]
    .sort((a, b) => a.reihenfolge - b.reihenfolge)
    .map((k) => ({ name: k.name, seiten: [] }));
  const gruppeNachName = new Map(gruppen.map((g) => [g.name, g]));
  const weitere: NavSeite[] = [];

  for (const seite of angezeigt) {
    const kategorieName = custom.zuordnungen[seite.key];
    const ziel = kategorieName ? gruppeNachName.get(kategorieName) : undefined;
    if (ziel) ziel.seiten.push(seite);
    else weitere.push(seite);
  }

  const ergebnis = gruppen.filter((g) => g.seiten.length > 0);
  if (weitere.length > 0) ergebnis.push({ name: "Weitere", seiten: weitere });
  return ergebnis;
}
