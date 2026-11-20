import { ApiError } from "../../api/client";
import type { StatusKey } from "../../components/apple/status";
import type { KiAenderung, KiAktionStatus, KiObjektRef, KiRueckgaengigKonflikt } from "../../types/ki";

export const KI_STATUS_LABEL: Record<KiAktionStatus, string> = {
  ausgefuehrt: "Ausgeführt",
  vorgeschlagen: "Wartet auf Freigabe",
  abgelehnt: "Abgelehnt",
  verfallen: "Verfallen",
  fehlgeschlagen: "Fehlgeschlagen",
  rueckgaengig: "Rückgängig",
};

export const KI_STATUS_TON: Record<KiAktionStatus, StatusKey> = {
  ausgefuehrt: "erledigt",
  vorgeschlagen: "wartet",
  abgelehnt: "fehlt",
  verfallen: "geplant",
  fehlgeschlagen: "fehlt",
  rueckgaengig: "geplant",
};

/** Blau/Orange/Rot wie im Mockup: je höher die Stufe, desto folgenreicher die Aktion. */
export const KI_STUFE_TON: Record<1 | 2 | 3, StatusKey> = { 1: "neu", 2: "arbeit", 3: "fehlt" };
export const KI_STUFE_LABEL: Record<1 | 2 | 3, string> = {
  1: "Stufe 1: legt Neues an",
  2: "Stufe 2: ändert Bestehendes",
  3: "Stufe 3: folgenreich",
};

/** Office-Route je Objekttyp; Typen ohne eigene Seite (und unbekannte) bleiben ohne Link. */
export function objektLink(ref: KiObjektRef): string | null {
  const id = encodeURIComponent(ref.id);
  switch (ref.typ) {
    case "vorgang":
      return `/vorgaenge/${id}`;
    case "kunde":
      return `/kunden/${id}`;
    case "anlage":
      return `/anlagen/${id}`;
    case "standort":
      return `/standorte/${id}`;
    case "auftrag":
      return `/auftraege?auftrag=${id}`;
    case "projekt":
      return `/projekte?projekt=${id}`;
    case "aufgabe":
      return `/meine-aufgaben/${id}`;
    case "formular":
      return `/form-submissions/${id}`;
    default:
      return null;
  }
}

const TZ = "Europe/Berlin";
const tagSchluessel = (d: Date) => d.toLocaleDateString("de-DE", { timeZone: TZ });

/** Heute: nur die Uhrzeit, sonst das Datum. */
export function zeitKurz(iso: string, jetzt: Date = new Date()): string {
  const d = new Date(iso);
  if (tagSchluessel(d) === tagSchluessel(jetzt)) {
    return d.toLocaleTimeString("de-DE", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString("de-DE", { timeZone: TZ, day: "2-digit", month: "2-digit", year: "numeric" });
}

export function datumUhrzeit(iso: string): string {
  return new Date(iso).toLocaleString("de-DE", {
    timeZone: TZ,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Zweite Zeile der Tabelle: erzeugte und betroffene Objekte, ohne Dopplungen. */
export function objektZeile(ziele: KiObjektRef[], erzeugt: KiObjektRef[]): string {
  return [...new Set([...erzeugt, ...ziele].map((r) => r.label))].join(" · ");
}

export function gruppiereAenderungen(aenderungen: KiAenderung[]): { schluessel: string; label: string; zeilen: KiAenderung[] }[] {
  const gruppen = new Map<string, { schluessel: string; label: string; zeilen: KiAenderung[] }>();
  for (const a of aenderungen) {
    const schluessel = `${a.typ}:${a.id}`;
    const g = gruppen.get(schluessel) ?? { schluessel, label: a.label, zeilen: [] };
    g.zeilen.push(a);
    gruppen.set(schluessel, g);
  }
  return [...gruppen.values()];
}

export interface RueckgaengigKonflikt {
  meldung: string;
  konflikte: KiRueckgaengigKonflikt[];
}

/** Liest den strukturierten 409-Body (`detail: { meldung, konflikte }`); null bei jedem anderen Fehler. */
export function rueckgaengigKonflikt(err: unknown): RueckgaengigKonflikt | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null;
  const detail = (err.body as { detail?: unknown } | undefined)?.detail;
  if (!detail || typeof detail !== "object") return { meldung: err.message, konflikte: [] };
  const d = detail as { meldung?: unknown; konflikte?: unknown };
  return {
    meldung: typeof d.meldung === "string" ? d.meldung : "Das Zurücknehmen ist nicht mehr möglich.",
    konflikte: Array.isArray(d.konflikte) ? (d.konflikte as KiRueckgaengigKonflikt[]) : [],
  };
}
