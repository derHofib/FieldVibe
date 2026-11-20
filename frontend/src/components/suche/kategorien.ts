import {
  ArrowRight,
  FileText,
  Hash,
  KanbanSquare,
  Layers,
  type LucideIcon,
  Phone,
  Receipt,
  Rss,
  Users,
  Wrench,
} from "lucide-react";

import { NAV_SEITEN, type NavSeite } from "../../config/navSeiten";
import type { CurrentUser, RechteAktion, RechteBereich, SearchHit, SearchKategorie } from "../../types";
import { formatEuro } from "../../utils/format";
import { RECHNUNG_STATUS_LABEL } from "../../utils/buchhaltung";
import { ANGEBOT_STATUS_LABEL } from "../rechnung/rechnungenFilter";
import type { KachelFarbe } from "../apple/SymbolKachel";
import { type StatusKey, VORGANG_STATUS_LABEL, vorgangStatusZuToken } from "../apple/status";
import { bedingungenZuJson } from "../filter/url";
import type { ZuletztEintrag } from "./zuletztGeoeffnet";

export type SucheOberflaeche = "office" | "feld";
export type EintragKategorie = SearchKategorie | "seite";

/** Feste Reihenfolge der Gruppen und der Kategorie-Pillen ohne Trefferlage. */
export const KATEGORIE_REIHENFOLGE: SearchKategorie[] = [
  "vorgang",
  "kunde",
  "anlage",
  "rechnung",
  "angebot",
  "auftrag",
  "projekt",
  "telefonat",
  "tag",
];

interface KategorieInfo {
  plural: string;
  singular: string;
  icon: LucideIcon;
  farbe: KachelFarbe;
}

export const KATEGORIE_INFO: Record<EintragKategorie, KategorieInfo> = {
  vorgang: { plural: "Vorgänge", singular: "Vorgang", icon: Rss, farbe: "blue" },
  kunde: { plural: "Kunden", singular: "Kunde", icon: Users, farbe: "indigo" },
  anlage: { plural: "Anlagen", singular: "Anlage", icon: Wrench, farbe: "orange" },
  rechnung: { plural: "Rechnungen", singular: "Rechnung", icon: Receipt, farbe: "green" },
  angebot: { plural: "Angebote", singular: "Angebot", icon: FileText, farbe: "green" },
  auftrag: { plural: "Aufträge", singular: "Auftrag", icon: Layers, farbe: "indigo" },
  projekt: { plural: "Projekte", singular: "Projekt", icon: KanbanSquare, farbe: "indigo" },
  telefonat: { plural: "Telefonate", singular: "Telefonat", icon: Phone, farbe: "gray" },
  tag: { plural: "Tags", singular: "Tag", icon: Hash, farbe: "gray" },
  seite: { plural: "Seiten", singular: "Seite", icon: ArrowRight, farbe: "gray" },
};

// Die Feld-App hat für Aufträge, Projekte (nur Kanban am Desktop) und Telefonate
// keine Detailroute -- dort würden Treffer ins Leere führen.
const NUR_OFFICE: SearchKategorie[] = ["auftrag", "projekt", "telefonat"];

export function kategorieErreichbar(kategorie: SearchKategorie, oberflaeche: SucheOberflaeche): boolean {
  return oberflaeche === "office" || !NUR_OFFICE.includes(kategorie);
}

/** Ziel eines Treffers. Tags navigieren nicht, sie setzen die Suche (`null`). */
export function zielPfad(
  kategorie: SearchKategorie,
  id: string,
  titel: string,
  oberflaeche: SucheOberflaeche,
): string | null {
  if (!kategorieErreichbar(kategorie, oberflaeche)) return null;
  switch (kategorie) {
    case "vorgang":
      return `/vorgaenge/${id}`;
    case "kunde":
      return `/kunden/${id}`;
    case "anlage":
      return `/anlagen/${id}`;
    case "rechnung":
      return `/rechnungen/${id}`;
    case "angebot":
      return `/angebote/${id}`;
    case "auftrag":
      return `/auftraege?auftrag=${encodeURIComponent(id)}`;
    case "projekt":
      return `/projekte?projekt=${encodeURIComponent(id)}`;
    // Die Telefonate-Liste kennt keinen Öffnen-Parameter, nur die Suche über `q`.
    case "telefonat":
      return `/telefonate?q=${encodeURIComponent(titel)}`;
    case "tag":
      return null;
  }
}

const LISTEN_PFAD: Partial<Record<SearchKategorie, string>> = {
  vorgang: "/vorgaenge",
  kunde: "/kunden",
  rechnung: "/rechnungen",
  angebot: "/angebote",
  auftrag: "/auftraege",
  projekt: "/projekte",
  telefonat: "/telefonate",
};

// Nur die Vorgangsliste hat ein Status-Feld mit "ist nicht" (useVorgaengeFilter).
const ERLEDIGT_VORGANG = ["abgeschlossen", "abgerechnet", "storniert"];

/** Liste für „Alle N in …" (Office). `null`, wo es keine eigene Liste gibt (Anlagen, Tags). */
export function listenPfad(kategorie: SearchKategorie, begriff: string, nurOffen: boolean): string | null {
  const basis = LISTEN_PFAD[kategorie];
  if (!basis) return null;
  const params = new URLSearchParams({ q: begriff });
  if (nurOffen && kategorie === "vorgang") {
    params.set("f", bedingungenZuJson([{ feld: "status", op: "ist_nicht", wert: ERLEDIGT_VORGANG }]));
  }
  return `${basis}?${params.toString()}`;
}

export interface StatusAnzeige {
  token: StatusKey;
  label: string;
}

const RECHNUNG_TOKEN: Record<string, StatusKey> = {
  entwurf: "neu",
  versendet: "geplant",
  teilweise_bezahlt: "arbeit",
  bezahlt: "erledigt",
  storniert: "fehlt",
};

const ANGEBOT_TOKEN: Record<string, StatusKey> = {
  entwurf: "neu",
  versendet: "geplant",
  angenommen: "erledigt",
  abgelehnt: "fehlt",
  widerrufen: "arbeit",
};

const AUFTRAG_STATUS: Record<string, StatusAnzeige> = {
  offen: { token: "neu", label: "Offen" },
  in_arbeit: { token: "arbeit", label: "In Arbeit" },
  abgeschlossen: { token: "erledigt", label: "Abgeschlossen" },
  storniert: { token: "geplant", label: "Storniert" },
};

function humanisiert(status: string): string {
  const text = status.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Roher Backend-Status → Pille. Unbekannte Werte bleiben lesbar (neutral), statt zu verschwinden. */
export function statusAnzeige(kategorie: EintragKategorie, status: string | null | undefined): StatusAnzeige | null {
  if (!status) return null;
  switch (kategorie) {
    case "vorgang":
      if (status in VORGANG_STATUS_LABEL) {
        const s = status as keyof typeof VORGANG_STATUS_LABEL;
        return { token: vorgangStatusZuToken(s), label: VORGANG_STATUS_LABEL[s] };
      }
      break;
    case "rechnung":
      if (status in RECHNUNG_TOKEN) {
        return {
          token: RECHNUNG_TOKEN[status],
          label: RECHNUNG_STATUS_LABEL[status as keyof typeof RECHNUNG_STATUS_LABEL],
        };
      }
      break;
    case "angebot":
      if (status in ANGEBOT_TOKEN) {
        return {
          token: ANGEBOT_TOKEN[status],
          label: ANGEBOT_STATUS_LABEL[status as keyof typeof ANGEBOT_STATUS_LABEL],
        };
      }
      break;
    case "auftrag":
      if (status in AUFTRAG_STATUS) return AUFTRAG_STATUS[status];
      break;
    default:
      break;
  }
  return { token: "geplant", label: humanisiert(status) };
}

function formatTag(datum: string): string {
  const iso = datum.slice(0, 10);
  const [j, m, t] = iso.split("-");
  return j && m && t ? `${t}.${m}.${j}` : datum;
}

/** Titel für die Anzeige: Vorgangstitel kommen als „V-…: Titel". */
export function anzeigeTitel(hit: Pick<SearchHit, "kategorie" | "titel">): string {
  return hit.kategorie === "vorgang" ? hit.titel.replace(": ", " · ") : hit.titel;
}

/** Untertitel aus den strukturierten Feldern; ohne diese der Rohtext des Backends. */
export function anzeigeUntertitel(hit: SearchHit): string {
  const titel = hit.titel.toLowerCase();
  const teile: string[] = [];
  // Die Nummer steht bei Vorgängen/Rechnungen schon im Titel.
  if (hit.nummer && !titel.includes(hit.nummer.toLowerCase())) teile.push(hit.nummer);
  if (hit.kunde_name) teile.push(hit.kunde_name);
  if (hit.zusatz && hit.zusatz !== hit.kunde_name) teile.push(hit.zusatz);
  if (hit.betrag !== null && hit.betrag !== undefined && hit.betrag !== "") teile.push(formatEuro(hit.betrag));
  if (hit.datum) teile.push(formatTag(hit.datum));
  if (teile.length === 0) return hit.subtitel ?? "";
  return teile.join(" · ");
}

export interface SucheEintrag {
  key: string;
  kategorie: EintragKategorie;
  id: string;
  titel: string;
  untertitel: string;
  status: StatusAnzeige | null;
  /** Roher Backend-Status, für den Verlauf „Zuletzt geöffnet". */
  statusRoh: string | null;
  /** Pfad zum Öffnen; `tag` = Suche auf „#tag" setzen. */
  ziel: { pfad: string } | { tag: string };
}

export function trefferZuEintrag(hit: SearchHit, oberflaeche: SucheOberflaeche): SucheEintrag | null {
  if (hit.kategorie === "tag") {
    return {
      key: `tag-${hit.id}`,
      kategorie: "tag",
      id: hit.id,
      titel: hit.titel,
      untertitel: hit.subtitel ?? "",
      status: null,
      statusRoh: null,
      ziel: { tag: hit.titel.replace(/^#/, "") },
    };
  }
  const pfad = zielPfad(hit.kategorie, hit.id, hit.titel, oberflaeche);
  if (!pfad) return null;
  return {
    key: `${hit.kategorie}-${hit.id}`,
    kategorie: hit.kategorie,
    id: hit.id,
    titel: anzeigeTitel(hit),
    untertitel: anzeigeUntertitel(hit),
    status: statusAnzeige(hit.kategorie, hit.status),
    statusRoh: hit.status ?? null,
    ziel: { pfad },
  };
}

export function verlaufZuEintrag(e: ZuletztEintrag, oberflaeche: SucheOberflaeche): SucheEintrag | null {
  const pfad = zielPfad(e.kategorie, e.id, e.titel, oberflaeche);
  if (!pfad) return null;
  return {
    key: `zuletzt-${e.kategorie}-${e.id}`,
    kategorie: e.kategorie,
    id: e.id,
    titel: e.titel,
    untertitel: e.untertitel,
    status: statusAnzeige(e.kategorie, e.status),
    statusRoh: e.status ?? null,
    ziel: { pfad },
  };
}

export function seiteZuEintrag(seite: NavSeite): SucheEintrag {
  return {
    key: `seite-${seite.key}`,
    kategorie: "seite",
    id: seite.key,
    titel: seite.label,
    untertitel: seite.kategorie,
    status: null,
    statusRoh: null,
    ziel: { pfad: seite.route },
  };
}

/** "99+" ab 100 (das Backend deckelt bei 100). */
export function formatAnzahl(n: number): string {
  return n > 99 ? "99+" : String(n);
}

// Seitenleisten-Eintrag, dessen Sichtbarkeitsregel auch für die Suchkategorie gilt.
const NAV_KEY: Partial<Record<SearchKategorie, string>> = {
  kunde: "kunden",
  anlage: "kunden",
  rechnung: "rechnungen",
  angebot: "rechnungen",
  auftrag: "auftraege",
  projekt: "projekte",
  telefonat: "telefonate",
};

/** Ohne Suchbegriff liefert das Backend keine Zahlen -- dann entscheiden dieselben Rechte wie bei der Navigation. */
export function kategorieDarf(
  kategorie: SearchKategorie,
  currentUser: CurrentUser | undefined,
  hatRecht: (bereich: RechteBereich, aktion: RechteAktion) => boolean,
): boolean {
  if (kategorie === "tag") return true;
  if (kategorie === "vorgang") return hatRecht("vorgaenge", "sehen");
  const seite = NAV_SEITEN.find((s) => s.key === NAV_KEY[kategorie]);
  return seite ? seite.sichtbar({ currentUser, hatRecht }) : false;
}

export interface KategorieLeiste {
  sichtbar: SearchKategorie[];
  mehr: SearchKategorie[];
}

const SICHTBAR_MAX = 4;

/** „Alle" + die vier Kategorien mit den meisten Treffern, Rest unter „Mehr".
 * Ohne Zahlen (kein Suchbegriff) feste Reihenfolge. Die gewählte Kategorie bleibt immer sichtbar. */
export function kategorienLeiste(opts: {
  /** Zahlen der aktuellen Suche; `undefined` = kein Suchbegriff bzw. noch nichts geladen. */
  anzahl: Partial<Record<SearchKategorie, number>> | undefined;
  /** Kategorien, die der Nutzer sehen darf und die auf dieser Oberfläche erreichbar sind. */
  erlaubt: SearchKategorie[];
  gewaehlt: SearchKategorie | "alle";
}): KategorieLeiste {
  const { anzahl, erlaubt, gewaehlt } = opts;
  let kandidaten: SearchKategorie[];
  if (anzahl) {
    kandidaten = KATEGORIE_REIHENFOLGE.filter((k) => anzahl[k] !== undefined && erlaubt.includes(k));
    // Stabil: bei gleicher Zahl bleibt die feste Reihenfolge.
    kandidaten = kandidaten
      .map((k, i) => ({ k, i }))
      .sort((a, b) => (anzahl[b.k] ?? 0) - (anzahl[a.k] ?? 0) || a.i - b.i)
      .map((x) => x.k)
      .filter((k) => (anzahl[k] ?? 0) > 0 || k === gewaehlt);
  } else {
    kandidaten = KATEGORIE_REIHENFOLGE.filter((k) => k !== "tag" && erlaubt.includes(k));
  }
  let sichtbar = kandidaten.slice(0, SICHTBAR_MAX);
  if (gewaehlt !== "alle" && kandidaten.includes(gewaehlt) && !sichtbar.includes(gewaehlt)) {
    sichtbar = [...sichtbar.slice(0, SICHTBAR_MAX - 1), gewaehlt];
  }
  return { sichtbar, mehr: kandidaten.filter((k) => !sichtbar.includes(k)) };
}

/** Kategorien für die Pillen: mit Zahlen gilt, was das Backend liefert (Rechte), sonst die Navigationsrechte. */
export function erlaubteKategorien(
  anzahl: Partial<Record<SearchKategorie, number>> | undefined,
  currentUser: CurrentUser | undefined,
  hatRecht: (bereich: RechteBereich, aktion: RechteAktion) => boolean,
  oberflaeche: SucheOberflaeche,
): SearchKategorie[] {
  return KATEGORIE_REIHENFOLGE.filter(
    (k) => kategorieErreichbar(k, oberflaeche) && (anzahl ? true : kategorieDarf(k, currentUser, hatRecht)),
  );
}
