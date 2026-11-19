import { Building2, CalendarClock, CircleDot, Flag, Folder, Layers, Lock, Rss, Users, Columns3, type LucideIcon } from "lucide-react";

import { tageZwischen } from "../../../utils/format";
import { isoDatum, normalisiere } from "../../../components/filter/auswerten";
import type { FilterFeld, FilterOption } from "../../../components/filter/typen";
import type { ProjektAufgabe, ProjektAufgabePrioritaet } from "../../../types";

export type Gruppierung = "faelligkeit" | "projekt" | "auftrag" | "kunde" | "prioritaet" | "quelle" | "keine";
export type Sortierung = "faelligkeit" | "prioritaet" | "titel" | "geaendert" | "angelegt";

export const STANDARD_GRUPPIERUNG: Gruppierung = "faelligkeit";
export const STANDARD_SORTIERUNG: Sortierung = "faelligkeit";

export const GRUPPIERUNGEN: { wert: Gruppierung; label: string; icon: LucideIcon }[] = [
  { wert: "faelligkeit", label: "Fälligkeit", icon: CalendarClock },
  { wert: "projekt", label: "Projekt", icon: Folder },
  { wert: "auftrag", label: "Auftrag", icon: Layers },
  { wert: "kunde", label: "Kunde", icon: Users },
  { wert: "prioritaet", label: "Priorität", icon: Flag },
  { wert: "quelle", label: "Quelle", icon: Lock },
];

export const SORTIERUNGEN: { wert: Sortierung; label: string }[] = [
  { wert: "faelligkeit", label: "Fälligkeit" },
  { wert: "prioritaet", label: "Priorität" },
  { wert: "titel", label: "Titel" },
  { wert: "geaendert", label: "Zuletzt geändert" },
  { wert: "angelegt", label: "Angelegt" },
];

export const PRIORITAET_LABEL: Record<ProjektAufgabePrioritaet, string> = {
  niedrig: "Niedrig",
  mittel: "Mittel",
  hoch: "Hoch",
};

const PRIORITAET_RANG: Record<ProjektAufgabePrioritaet, number> = { hoch: 0, mittel: 1, niedrig: 2 };

export function gruppierungAusUrl(roh: string | null): Gruppierung {
  if (roh === "keine" || GRUPPIERUNGEN.some((g) => g.wert === roh)) return roh as Gruppierung;
  return STANDARD_GRUPPIERUNG;
}

export function sortierungAusUrl(roh: string | null): Sortierung {
  return SORTIERUNGEN.some((s) => s.wert === roh) ? (roh as Sortierung) : STANDARD_SORTIERUNG;
}

/** Der Pfad (Projekt/Auftrag) kommt vom Server abgeleitet; die Rohfelder bleiben als Rückfall, falls er fehlt. */
export type PfadFelder = Pick<ProjektAufgabe, "projekt_id" | "auftrag_id"> &
  Partial<Pick<ProjektAufgabe, "projekt_name" | "pfad_projekt_id" | "pfad_projekt_name" | "pfad_auftrag_id">>;
export const projektIdVon = (a: PfadFelder) => a.pfad_projekt_id ?? a.projekt_id ?? null;
export const projektNameVon = (a: PfadFelder) => a.pfad_projekt_name ?? a.projekt_name ?? null;
export const auftragIdVon = (a: PfadFelder) => a.pfad_auftrag_id ?? a.auftrag_id ?? null;
export const kundeNameVon = (a: ProjektAufgabe) => a.kunde_name ?? a.vorgang_kunde_name ?? null;

/** Alle Wörter müssen vorkommen (Reihenfolge egal), "ae" findet "ä". */
export function suchtextVon(a: ProjektAufgabe): string {
  return [
    a.titel,
    a.beschreibung,
    projektNameVon(a),
    a.auftrag_titel,
    a.vorgang_vorgangsnummer,
    a.vorgang_titel,
    kundeNameVon(a),
    a.anlage_name,
  ]
    .filter(Boolean)
    .join(" ");
}

export function sucheAufgaben(aufgaben: ProjektAufgabe[], suche: string): ProjektAufgabe[] {
  const woerter = normalisiere(suche).split(/\s+/).filter(Boolean);
  if (woerter.length === 0) return aufgaben;
  return aufgaben.filter((a) => {
    const text = normalisiere(suchtextVon(a));
    return woerter.every((w) => text.includes(w));
  });
}

const collator = new Intl.Collator("de", { numeric: true, sensitivity: "base" });

export function sortiereAufgaben(aufgaben: ProjektAufgabe[], sortierung: Sortierung): ProjektAufgabe[] {
  const nachTitel = (a: ProjektAufgabe, b: ProjektAufgabe) => collator.compare(a.titel, b.titel);
  const vergleich: Record<Sortierung, (a: ProjektAufgabe, b: ProjektAufgabe) => number> = {
    // Ohne Termin ans Ende, auch wenn die Richtung aufsteigend ist.
    faelligkeit: (a, b) => {
      if (a.faelligkeit_am === b.faelligkeit_am) return nachTitel(a, b);
      if (!a.faelligkeit_am) return 1;
      if (!b.faelligkeit_am) return -1;
      return a.faelligkeit_am < b.faelligkeit_am ? -1 : 1;
    },
    prioritaet: (a, b) => PRIORITAET_RANG[a.prioritaet] - PRIORITAET_RANG[b.prioritaet] || nachTitel(a, b),
    titel: nachTitel,
    geaendert: (a, b) => (a.updated_at < b.updated_at ? 1 : a.updated_at > b.updated_at ? -1 : 0),
    angelegt: (a, b) => (a.created_at < b.created_at ? 1 : a.created_at > b.created_at ? -1 : 0),
  };
  return [...aufgaben].sort(vergleich[sortierung]);
}

export interface AufgabenGruppe {
  key: string;
  label: string;
  aufgaben: ProjektAufgabe[];
  /** Fälligkeits-Gruppe "Überfällig": Kopf in Warnfarbe. */
  warnung?: boolean;
}

type FaelligkeitsGruppe = "ueberfaellig" | "heute" | "woche" | "spaeter" | "ohne";

const FAELLIGKEIT_LABEL: Record<FaelligkeitsGruppe, string> = {
  ueberfaellig: "Überfällig",
  heute: "Heute",
  woche: "Diese Woche",
  spaeter: "Später",
  ohne: "Ohne Termin",
};
const FAELLIGKEIT_REIHENFOLGE: FaelligkeitsGruppe[] = ["ueberfaellig", "heute", "woche", "spaeter", "ohne"];

export function faelligkeitsGruppe(faelligkeitAm: string | null, heute: string, in7Tagen: string): FaelligkeitsGruppe {
  if (!faelligkeitAm) return "ohne";
  if (faelligkeitAm < heute) return "ueberfaellig";
  if (faelligkeitAm === heute) return "heute";
  if (faelligkeitAm <= in7Tagen) return "woche";
  return "spaeter";
}

function nachSchluessel(
  aufgaben: ProjektAufgabe[],
  schluessel: (a: ProjektAufgabe) => { key: string; label: string } | null,
  ohneLabel: string,
): AufgabenGruppe[] {
  const mit = new Map<string, AufgabenGruppe>();
  const ohne: ProjektAufgabe[] = [];
  for (const a of aufgaben) {
    const s = schluessel(a);
    if (!s) {
      ohne.push(a);
      continue;
    }
    const g = mit.get(s.key) ?? { key: s.key, label: s.label, aufgaben: [] };
    g.aufgaben.push(a);
    mit.set(s.key, g);
  }
  const gruppen = [...mit.values()].sort((a, b) => collator.compare(a.label, b.label));
  // "Ohne X" steht immer zuletzt, auch wenn es alphabetisch früher käme.
  if (ohne.length > 0) gruppen.push({ key: "ohne", label: ohneLabel, aufgaben: ohne });
  return gruppen;
}

/** Eine Ebene; die Reihenfolge der Aufgaben innerhalb einer Gruppe bleibt wie übergeben (vorher sortieren). */
export function gruppiereAufgaben(
  aufgaben: ProjektAufgabe[],
  gruppierung: Gruppierung,
  heute: string = isoDatum(new Date()),
): AufgabenGruppe[] {
  if (aufgaben.length === 0) return [];
  switch (gruppierung) {
    case "keine":
      return [{ key: "alle", label: "", aufgaben }];
    case "faelligkeit": {
      const [j, m, t] = heute.split("-").map(Number);
      const in7Tagen = isoDatum(new Date(j, m - 1, t + 7));
      const map = new Map<FaelligkeitsGruppe, ProjektAufgabe[]>();
      for (const a of aufgaben) {
        const g = faelligkeitsGruppe(a.faelligkeit_am, heute, in7Tagen);
        map.set(g, [...(map.get(g) ?? []), a]);
      }
      return FAELLIGKEIT_REIHENFOLGE.filter((g) => map.has(g)).map((g) => ({
        key: g,
        label: FAELLIGKEIT_LABEL[g],
        aufgaben: map.get(g)!,
        warnung: g === "ueberfaellig",
      }));
    }
    case "projekt":
      return nachSchluessel(
        aufgaben,
        (a) => {
          const name = projektNameVon(a);
          return name ? { key: projektIdVon(a) ?? name, label: name } : null;
        },
        "Ohne Projekt",
      );
    case "auftrag":
      return nachSchluessel(
        aufgaben,
        (a) => (a.auftrag_titel ? { key: auftragIdVon(a) ?? a.auftrag_titel, label: a.auftrag_titel } : null),
        "Ohne Auftrag",
      );
    case "kunde":
      return nachSchluessel(
        aufgaben,
        (a) => {
          const name = kundeNameVon(a);
          return name ? { key: name, label: name } : null;
        },
        "Ohne Kunde",
      );
    case "prioritaet": {
      const gruppen: AufgabenGruppe[] = [];
      for (const p of ["hoch", "mittel", "niedrig"] as const) {
        const treffer = aufgaben.filter((a) => a.prioritaet === p);
        if (treffer.length > 0) gruppen.push({ key: p, label: PRIORITAET_LABEL[p], aufgaben: treffer });
      }
      return gruppen;
    }
    case "quelle": {
      const privat = aufgaben.filter((a) => !a.projekt_id);
      const gruppen = nachSchluessel(
        aufgaben.filter((a) => a.projekt_id),
        (a) => ({ key: `spalte:${a.spalte_name ?? ""}`, label: a.spalte_name ?? "Projekt-Aufgabe" }),
        "",
      );
      return privat.length > 0 ? [{ key: "privat", label: "Privat", aufgaben: privat }, ...gruppen] : gruppen;
    }
  }
}

export function istUeberfaelligAm(a: ProjektAufgabe, heute: string): boolean {
  return !a.erledigt_am && !!a.faelligkeit_am && a.faelligkeit_am < heute;
}

export function kennzahlen(offene: ProjektAufgabe[], heute: string) {
  return { offen: offene.length, ueberfaellig: offene.filter((a) => istUeberfaelligAm(a, heute)).length };
}

function eindeutigeOptionen(aufgaben: ProjektAufgabe[], je: (a: ProjektAufgabe) => FilterOption | null): FilterOption[] {
  const map = new Map<string, FilterOption>();
  for (const a of aufgaben) {
    const o = je(a);
    if (o && !map.has(o.wert)) map.set(o.wert, o);
  }
  return [...map.values()].sort((a, b) => collator.compare(a.label, b.label));
}

/** Die Optionen der Verknüpfungs-Felder stammen aus den geladenen Aufgaben: die Liste ist klein und
 * ein Filter auf nicht vorkommende Werte wäre ohnehin leer. */
export function aufgabenFilterFelder(aufgaben: ProjektAufgabe[], erledigtSegment: boolean): FilterFeld<ProjektAufgabe>[] {
  const felder: FilterFeld<ProjektAufgabe>[] = [
    {
      key: "quelle",
      label: "Quelle",
      typ: "auswahl",
      icon: Lock,
      optionen: [
        { wert: "privat", label: "Privat" },
        { wert: "projekt", label: "Projekt-Aufgabe" },
      ],
      wert: (a) => (a.projekt_id ? "projekt" : "privat"),
    },
    {
      key: "projekt",
      label: "Projekt",
      typ: "verknuepfung",
      icon: Folder,
      optionen: eindeutigeOptionen(aufgaben, (a) => {
        const name = projektNameVon(a);
        return name ? { wert: projektIdVon(a) ?? name, label: name } : null;
      }),
      wert: (a) => (projektNameVon(a) ? (projektIdVon(a) ?? projektNameVon(a)) : null),
    },
    {
      key: "auftrag",
      label: "Auftrag",
      typ: "verknuepfung",
      icon: Layers,
      optionen: eindeutigeOptionen(aufgaben, (a) =>
        a.auftrag_titel ? { wert: auftragIdVon(a) ?? a.auftrag_titel, label: a.auftrag_titel } : null,
      ),
      wert: (a) => (a.auftrag_titel ? (auftragIdVon(a) ?? a.auftrag_titel) : null),
    },
    {
      key: "vorgang",
      label: "Vorgang",
      typ: "verknuepfung",
      icon: Rss,
      optionen: eindeutigeOptionen(aufgaben, (a) =>
        a.vorgang_id
          ? { wert: a.vorgang_id, label: [a.vorgang_vorgangsnummer, a.vorgang_titel].filter(Boolean).join(" · ") || "Vorgang" }
          : null,
      ),
      wert: (a) => a.vorgang_id,
    },
    {
      key: "kunde",
      label: "Kunde",
      typ: "verknuepfung",
      icon: Users,
      optionen: eindeutigeOptionen(aufgaben, (a) => {
        const name = kundeNameVon(a);
        return name ? { wert: name, label: name } : null;
      }),
      wert: (a) => kundeNameVon(a),
    },
    {
      key: "anlage",
      label: "Anlage",
      typ: "verknuepfung",
      icon: Building2,
      optionen: eindeutigeOptionen(aufgaben, (a) => (a.anlage_id ? { wert: a.anlage_id, label: a.anlage_name ?? "Anlage" } : null)),
      wert: (a) => a.anlage_id,
    },
    {
      key: "prioritaet",
      label: "Priorität",
      typ: "auswahl",
      icon: Flag,
      optionen: (["hoch", "mittel", "niedrig"] as const).map((p) => ({ wert: p, label: PRIORITAET_LABEL[p] })),
      wert: (a) => a.prioritaet,
    },
    {
      key: "faellig",
      label: "Fällig",
      typ: "datum",
      icon: CalendarClock,
      wert: (a) => a.faelligkeit_am,
    },
    {
      key: "spalte",
      label: "Kanban-Spalte",
      typ: "auswahl",
      icon: Columns3,
      optionen: eindeutigeOptionen(aufgaben, (a) => (a.spalte_name ? { wert: a.spalte_name, label: a.spalte_name } : null)),
      wert: (a) => a.spalte_name ?? null,
    },
  ];
  if (erledigtSegment) {
    felder.push({ key: "erledigt_am", label: "Erledigt am", typ: "datum", icon: CircleDot, wert: (a) => a.erledigt_am });
  }
  return felder;
}

const EINGEKLAPPT_PREFIX = "fieldvibe-aufgaben-eingeklappt-";

export function eingeklapptLesen(gruppierung: Gruppierung): string[] {
  try {
    const roh = localStorage.getItem(EINGEKLAPPT_PREFIX + gruppierung);
    const wert: unknown = roh ? JSON.parse(roh) : [];
    return Array.isArray(wert) ? wert.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export function eingeklapptSchreiben(gruppierung: Gruppierung, keys: string[]): void {
  try {
    localStorage.setItem(EINGEKLAPPT_PREFIX + gruppierung, JSON.stringify(keys));
  } catch {
    // privater Modus -- eingeklappt gilt dann nur für diese Sitzung
  }
}

const WOCHENTAG = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];

/** Fälligkeit für Zeilen und Karten: überfällig relativ ("vor 2 Tagen"), sonst Heute, in der Woche mit Wochentag
 * ("Fr 21.11."), weiter weg als Datum. */
export function faelligText(iso: string | null, heute: string): { text: string; ueberfaellig: boolean } | null {
  if (!iso) return null;
  const diff = tageZwischen(heute, iso);
  const [j, m, t] = iso.split("-").map(Number);
  if (diff < 0) return { text: diff === -1 ? "vor 1 Tag" : `vor ${-diff} Tagen`, ueberfaellig: true };
  if (diff === 0) return { text: "Heute", ueberfaellig: false };
  const tm = `${String(t).padStart(2, "0")}.${String(m).padStart(2, "0")}.`;
  if (diff <= 6) return { text: `${WOCHENTAG[new Date(j, m - 1, t).getDay()]} ${tm}`, ueberfaellig: false };
  return { text: `${tm}${j}`, ueberfaellig: false };
}
