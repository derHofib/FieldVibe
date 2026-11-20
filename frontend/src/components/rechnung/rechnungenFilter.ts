import { CalendarCheck, CalendarClock, CalendarDays, CircleDot, Euro, Hash, Layers, Tag, Truck, UserRound } from "lucide-react";

import type {
  Angebot,
  AngebotStatus,
  Eingangsrechnung,
  EingangsrechnungKategorie,
  EingangsrechnungStatus,
  RechnungenFilter,
  RechnungStatus,
  Rechnungsart,
} from "../../types";
import type { StatusKey } from "../apple/status";
import { RECHNUNG_STATUS_LABEL } from "../../utils/buchhaltung";
import { RECHNUNGSART_FILTER, RECHNUNGSART_LABEL } from "../../utils/rechnungsart";
import { auswahlKomplement, isoDatum, parseDeutscheZahl, zeitraumAufloesen } from "../filter/auswerten";
import type { FilterBedingung, FilterFeld, FilterOption } from "../filter/typen";

export const RECHNUNG_STATUS_ALLE: RechnungStatus[] = ["entwurf", "versendet", "teilweise_bezahlt", "bezahlt", "storniert"];

export const ANGEBOT_STATUS_LABEL: Record<AngebotStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
  widerrufen: "Widerrufen",
};

export const EINGANG_STATUS_LABEL: Record<EingangsrechnungStatus, string> = {
  entwurf: "Entwurf",
  offen: "Offen",
  bezahlt: "Bezahlt",
  storniert: "Storniert",
};

export const EINGANG_KATEGORIE_LABEL: Record<EingangsrechnungKategorie, string> = {
  wareneinkauf: "Wareneinkauf",
  betriebskosten: "Betriebskosten",
  miete: "Miete",
  personal: "Personal",
  fahrzeug: "Fahrzeug",
  versicherung: "Versicherung",
  sonstiges: "Sonstiges",
};

const RECHNUNG_STATUS_OPTIONEN: FilterOption[] = [
  { wert: "entwurf", label: RECHNUNG_STATUS_LABEL.entwurf, status: "neu" },
  { wert: "versendet", label: RECHNUNG_STATUS_LABEL.versendet, status: "geplant" },
  { wert: "teilweise_bezahlt", label: RECHNUNG_STATUS_LABEL.teilweise_bezahlt, status: "arbeit" },
  { wert: "bezahlt", label: RECHNUNG_STATUS_LABEL.bezahlt, status: "erledigt" },
  { wert: "storniert", label: RECHNUNG_STATUS_LABEL.storniert, status: "fehlt" },
];

const ANGEBOT_STATUS_OPTIONEN: FilterOption[] = [
  { wert: "entwurf", label: ANGEBOT_STATUS_LABEL.entwurf, status: "neu" },
  { wert: "versendet", label: ANGEBOT_STATUS_LABEL.versendet, status: "geplant" },
  { wert: "angenommen", label: ANGEBOT_STATUS_LABEL.angenommen, status: "erledigt" },
  { wert: "abgelehnt", label: ANGEBOT_STATUS_LABEL.abgelehnt, status: "fehlt" },
  { wert: "widerrufen", label: ANGEBOT_STATUS_LABEL.widerrufen, status: "arbeit" },
];

const EINGANG_STATUS_OPTIONEN: FilterOption[] = [
  { wert: "entwurf", label: EINGANG_STATUS_LABEL.entwurf, status: "neu" },
  { wert: "offen", label: EINGANG_STATUS_LABEL.offen, status: "arbeit" },
  { wert: "bezahlt", label: EINGANG_STATUS_LABEL.bezahlt, status: "erledigt" },
  { wert: "storniert", label: EINGANG_STATUS_LABEL.storniert, status: "fehlt" },
];

/** Status-Token je Eingangsrechnungs-Status, einzige Zuordnung für Filterpillen und Tabellen-Status. */
export function eingangStatusToken(status: EingangsrechnungStatus): StatusKey | undefined {
  return EINGANG_STATUS_OPTIONEN.find((o) => o.wert === status)?.status;
}

const DATUM_SERVER_OPERATOREN = ["am", "vor", "nach", "zwischen", "relativ"] as const;
const BETRAG_SERVER_OPERATOREN = ["gte", "lte", "zwischen"] as const;

/** Rechnungen werden serverseitig gefiltert: nur Operatoren, die das Backend (von/bis, betrag_von/bis, status in …) kann. */
export function rechnungFelder(kunden: FilterOption[] | undefined): FilterFeld<unknown>[] {
  const felder: FilterFeld<unknown>[] = [
    { key: "status", label: "Status", typ: "auswahl", icon: CircleDot, optionen: RECHNUNG_STATUS_OPTIONEN },
  ];
  if (kunden) {
    felder.push({
      key: "kunde",
      label: "Kunde",
      typ: "verknuepfung",
      icon: UserRound,
      optionen: kunden,
      operatoren: ["ist"],
      einzelwert: true,
    });
  }
  felder.push(
    { key: "rechnungsdatum", label: "Erstellt am", typ: "datum", icon: CalendarDays, operatoren: [...DATUM_SERVER_OPERATOREN] },
    { key: "faellig", label: "Fällig", typ: "datum", icon: CalendarClock, operatoren: [...DATUM_SERVER_OPERATOREN] },
    { key: "betrag", label: "Betrag brutto", typ: "betrag", icon: Euro, operatoren: [...BETRAG_SERVER_OPERATOREN] },
    {
      key: "art",
      label: "Art",
      typ: "auswahl",
      icon: Layers,
      optionen: RECHNUNGSART_FILTER.map((a) => ({ wert: a, label: RECHNUNGSART_LABEL[a] })),
      operatoren: ["ist"],
      einzelwert: true,
    },
  );
  return felder;
}

function liste(b: FilterBedingung): string[] {
  if (Array.isArray(b.wert)) return b.wert;
  return typeof b.wert === "string" ? [b.wert] : [];
}

function tagVerschoben(iso: string, delta: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  return isoDatum(new Date(y, m - 1, d + delta));
}

function datumBereich(b: FilterBedingung): { von?: string; bis?: string } {
  const w = b.wert;
  if (b.op === "relativ" && w && typeof w === "object" && "relativ" in w) return zeitraumAufloesen(w.relativ);
  if (b.op === "zwischen" && w && typeof w === "object" && !Array.isArray(w) && !("relativ" in w)) {
    return { von: w.von || undefined, bis: w.bis || undefined };
  }
  if (typeof w !== "string" || !w) return {};
  if (b.op === "am") return { von: w, bis: w };
  if (b.op === "vor") return { bis: tagVerschoben(w, -1) };
  if (b.op === "nach") return { von: tagVerschoben(w, 1) };
  return {};
}

function ohneLeer(o: Record<string, string | undefined>): Record<string, string> {
  return Object.fromEntries(Object.entries(o).filter(([, v]) => v)) as Record<string, string>;
}

function betragNachServer(zahl: string | undefined): string | undefined {
  if (!zahl) return undefined;
  const n = parseDeutscheZahl(zahl);
  return n === null ? undefined : String(n);
}

/** Bedingungen → API-Parameter. "Überfällig" beim Fälligkeitsdatum ist ein eigener Schalter (`nur_ueberfaellig`),
 * weil das Backend dort zusätzlich auf offene Rechnungen einschränkt. */
export function rechnungServerParameter(bedingungen: FilterBedingung[]): RechnungenFilter {
  const roh: Record<string, string> = {};
  for (const b of bedingungen) {
    if (b.feld === "status") {
      const gewaehlt = liste(b);
      const status = b.op === "ist_nicht" ? auswahlKomplement(gewaehlt, RECHNUNG_STATUS_ALLE) : gewaehlt;
      if (status.length > 0) roh.status = status.join(",");
    } else if (b.feld === "kunde" && b.op === "ist") {
      const id = liste(b)[0];
      if (id) roh.kunde_id = id;
    } else if (b.feld === "art" && b.op === "ist") {
      const art = liste(b)[0];
      if (art) roh.rechnungsart = art;
    } else if (b.feld === "rechnungsdatum") {
      const { von, bis } = datumBereich(b);
      Object.assign(roh, ohneLeer({ von, bis }));
    } else if (b.feld === "faellig") {
      if (b.op === "relativ" && b.wert && typeof b.wert === "object" && "relativ" in b.wert && b.wert.relativ === "ueberfaellig") {
        roh.nur_ueberfaellig = "true";
      } else {
        const { von, bis } = datumBereich(b);
        Object.assign(roh, ohneLeer({ faellig_von: von, faellig_bis: bis }));
      }
    } else if (b.feld === "betrag") {
      const w = b.wert;
      if (b.op === "gte" && typeof w === "string") Object.assign(roh, ohneLeer({ betrag_von: betragNachServer(w) }));
      else if (b.op === "lte" && typeof w === "string") Object.assign(roh, ohneLeer({ betrag_bis: betragNachServer(w) }));
      else if (b.op === "zwischen" && w && typeof w === "object" && !Array.isArray(w) && !("relativ" in w)) {
        Object.assign(roh, ohneLeer({ betrag_von: betragNachServer(w.von), betrag_bis: betragNachServer(w.bis) }));
      }
    }
  }
  const { status, nur_ueberfaellig, rechnungsart, ...rest } = roh;
  return {
    ...rest,
    status: status ? (status.split(",") as RechnungStatus[]) : undefined,
    rechnungsart: rechnungsart as Rechnungsart | undefined,
    nur_ueberfaellig: nur_ueberfaellig ? true : undefined,
  };
}

/** Clientseitig gefilterte Angebote; der Kundenname kommt nicht im Angebot, daher nur die Kunden-ID als Wert. */
export function angebotFelder(kunden: FilterOption[] | undefined): FilterFeld<Angebot>[] {
  const felder: FilterFeld<Angebot>[] = [
    { key: "nummer", label: "Nummer", typ: "text", icon: Hash, wert: (a) => a.angebotsnummer },
  ];
  if (kunden) {
    felder.push({ key: "kunde", label: "Kunde", typ: "verknuepfung", icon: UserRound, wert: (a) => a.kunde_id, optionen: kunden });
  }
  felder.push(
    { key: "status", label: "Status", typ: "auswahl", icon: CircleDot, wert: (a) => a.status, optionen: ANGEBOT_STATUS_OPTIONEN },
    { key: "erstellt", label: "Erstellt", typ: "datum", icon: CalendarDays, wert: (a) => a.created_at },
    { key: "gueltig_bis", label: "Gültig bis", typ: "datum", icon: CalendarCheck, wert: (a) => a.gueltig_bis },
    // Decimal-String mit Punkt: als Zahl übergeben, sonst liest parseDeutscheZahl den Punkt als Tausendertrenner.
    { key: "betrag", label: "Betrag brutto", typ: "betrag", icon: Euro, wert: (a) => Number(a.gesamt_brutto) },
  );
  return felder;
}

export function eingangsrechnungFelder(): FilterFeld<Eingangsrechnung>[] {
  return [
    { key: "lieferant", label: "Lieferant", typ: "text", icon: Truck, wert: (e) => e.lieferant_name },
    { key: "status", label: "Status", typ: "auswahl", icon: CircleDot, wert: (e) => e.status, optionen: EINGANG_STATUS_OPTIONEN },
    {
      key: "kategorie",
      label: "Kategorie",
      typ: "auswahl",
      icon: Tag,
      wert: (e) => e.kategorie,
      optionen: Object.entries(EINGANG_KATEGORIE_LABEL).map(([wert, label]) => ({ wert, label })),
    },
    { key: "rechnungsdatum", label: "Rechnungsdatum", typ: "datum", icon: CalendarDays, wert: (e) => e.rechnungsdatum },
    { key: "faellig", label: "Fällig", typ: "datum", icon: CalendarClock, wert: (e) => e.faellig_am },
    { key: "betrag", label: "Betrag brutto", typ: "betrag", icon: Euro, wert: (e) => Number(e.betrag_brutto) },
    { key: "nummer", label: "Rechnungsnummer", typ: "text", icon: Hash, wert: (e) => e.rechnungsnummer_lieferant },
  ];
}

export function kundenOptionen(kunden: { id: string; name: string; kundennummer: string }[] | undefined): FilterOption[] | undefined {
  return kunden?.map((k) => ({ wert: k.id, label: `${k.name} (${k.kundennummer})` }));
}
