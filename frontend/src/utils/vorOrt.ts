import type {
  VorOrtKontakt,
  VorOrtKontaktCreate,
  VorOrtKontaktZugeordnet,
  VorOrtZiel,
} from "../types";
import { VOR_ORT_ROLLE_LABEL } from "../types";

export const ANONYMISIERT_TEXT = "Kontakt anonymisiert";
export const STANDARD_ANONYMISIERUNG_MONATE = 12;

export function istAnonymisiert(k: Pick<VorOrtKontakt, "anonymisiert_am">): boolean {
  return k.anonymisiert_am != null;
}

/** Name, sonst (nur Telefon erfasst) die Nummer, sonst die Rolle; anonymisiert immer der feste Text. */
export function kontaktAnzeigename(k: Pick<VorOrtKontakt, "name" | "telefon" | "rolle" | "anonymisiert_am">): string {
  if (istAnonymisiert(k)) return ANONYMISIERT_TEXT;
  return k.name?.trim() || k.telefon?.trim() || VOR_ORT_ROLLE_LABEL[k.rolle];
}

/** `tel:`-Ziel ohne Leer-/Trennzeichen; "+" bleibt erhalten. */
export function telHref(telefon: string): string {
  return `tel:${telefon.replace(/[^\d+]/g, "")}`;
}

/** "Whg. 3 · nachmittags" -- leere Teile entfallen. */
export function kontaktUnterzeile(k: Pick<VorOrtKontakt, "einheit" | "erreichbarkeit">): string {
  return [k.einheit, k.erreichbarkeit].filter((t) => t && t.trim()).join(" · ");
}

/** MM/YYYY für "zuletzt", null ohne Datum. */
export function monatJahr(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return `${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
}

/** Unterzeile in der Auswahl bekannter Kontakte: "Whg. 3 · zuletzt 03/2026". */
export function bekanntUnterzeile(k: Pick<VorOrtKontakt, "einheit" | "letzter_einsatz_am">): string {
  const zuletzt = monatJahr(k.letzter_einsatz_am);
  return [k.einheit, zuletzt ? `zuletzt ${zuletzt}` : null].filter(Boolean).join(" · ");
}

/** Herkunft eines geerbten Eintrags ("vom Auftrag ‚Heizung‘"); eigene Einträge haben keine. */
export function herkunftText(z: Pick<VorOrtKontaktZugeordnet, "herkunft" | "herkunft_titel">, ziel: VorOrtZiel): string | null {
  if (z.herkunft === ziel) return null;
  const art = z.herkunft === "auftrag" ? "Auftrag" : z.herkunft === "projekt" ? "Projekt" : "Vorgang";
  return `vom ${art} ‚${z.herkunft_titel}‘`;
}

export interface KontaktFormWerte {
  /** Nur im Formular mit Standort-Auswahl relevant ("" = kein Standort). */
  standortId: string;
  name: string;
  rolle: VorOrtKontaktCreate["rolle"];
  telefon: string;
  email: string;
  einheit: string;
  erreichbarkeit: string;
  hinweis: string;
}

export function leereKontaktForm(): KontaktFormWerte {
  return { standortId: "", name: "", rolle: "mieter", telefon: "", email: "", einheit: "", erreichbarkeit: "", hinweis: "" };
}

export function kontaktFormAus(k: VorOrtKontakt): KontaktFormWerte {
  return {
    standortId: k.standort_id ?? "",
    name: k.name ?? "",
    rolle: k.rolle,
    telefon: k.telefon ?? "",
    email: k.email ?? "",
    einheit: k.einheit ?? "",
    erreichbarkeit: k.erreichbarkeit ?? "",
    hinweis: k.hinweis ?? "",
  };
}

/** Clientseitige Pflichtprüfung, spiegelt die Server-Regel "Name oder Telefon". */
export function pruefeKontaktForm(w: KontaktFormWerte): string | null {
  if (!w.name.trim() && !w.telefon.trim()) return "Name oder Telefon angeben";
  return null;
}

/** Leere Felder werden als null gesendet (beim Ändern löscht das den Wert). Der Standort wird nur mit
 * `mitStandort` gesendet; sonst setzt der Server beim Zuordnen den Standort des Ziels. */
export function kontaktFormZuBody(w: KontaktFormWerte, mitStandort = false): VorOrtKontaktCreate {
  const leerNull = (t: string) => t.trim() || null;
  return {
    ...(mitStandort ? { standort_id: w.standortId || null } : {}),
    name: leerNull(w.name),
    rolle: w.rolle,
    telefon: leerNull(w.telefon),
    email: leerNull(w.email),
    einheit: leerNull(w.einheit),
    erreichbarkeit: leerNull(w.erreichbarkeit),
    hinweis: leerNull(w.hinweis),
  };
}

/** Sind alle Einträge vom Auftrag/Projekt geerbt, nennt die Fußnote deren Herkunft. */
export function geerbtFussnote(liste: VorOrtKontaktZugeordnet[], ziel: VorOrtZiel): string | null {
  if (liste.length === 0 || liste.some((z) => z.herkunft === ziel)) return null;
  const quellen = [...new Set(liste.map((z) => (z.herkunft === "auftrag" ? "Auftrag" : "Projekt")))];
  const titel = [...new Set(liste.map((z) => z.herkunft_titel))];
  return `Vom ${quellen.join(" und vom ")} ${titel.map((t) => `‚${t}‘`).join(", ")} übernommen.`;
}

/** Auswahl bekannter Kontakte: zuerst die des Ziel-Standorts, dann der Rest; bereits zugeordnete und anonymisierte entfallen. */
export function auswahlGruppen(
  kontakte: VorOrtKontakt[],
  standortId: string | null,
  schonZugeordnet: Set<string>,
): { titel: string | null; kontakte: VorOrtKontakt[] }[] {
  const frei = kontakte.filter((k) => !schonZugeordnet.has(k.id) && !istAnonymisiert(k));
  const amStandort = standortId ? frei.filter((k) => k.standort_id === standortId) : [];
  const rest = frei.filter((k) => !amStandort.includes(k));
  const gruppen: { titel: string | null; kontakte: VorOrtKontakt[] }[] = [];
  if (amStandort.length > 0) {
    gruppen.push({ titel: `Bekannt in ${amStandort[0].standort_bezeichnung ?? "diesem Standort"}`, kontakte: amStandort });
  }
  if (rest.length > 0) gruppen.push({ titel: amStandort.length > 0 ? "Weitere Kontakte des Kunden" : null, kontakte: rest });
  return gruppen;
}

export interface KontaktStandortGruppe {
  standortId: string | null;
  titel: string | null;
  kontakte: VorOrtKontakt[];
}

/** Gruppierung der Kunden-Liste nach Standort; "Ohne …" steht zuletzt. */
export function nachStandortGruppieren(kontakte: VorOrtKontakt[]): KontaktStandortGruppe[] {
  const map = new Map<string | null, KontaktStandortGruppe>();
  for (const k of kontakte) {
    const key = k.standort_id;
    const g = map.get(key) ?? { standortId: key, titel: k.standort_bezeichnung, kontakte: [] };
    g.kontakte.push(k);
    map.set(key, g);
  }
  return [...map.values()].sort((a, b) => {
    if ((a.standortId === null) !== (b.standortId === null)) return a.standortId === null ? 1 : -1;
    return (a.titel ?? "").localeCompare(b.titel ?? "", "de");
  });
}

/** Bei Hausverwaltungen heißen Standorte "Liegenschaft" (nur Beschriftung). */
export function standortBegriff(kundeTyp: string | null | undefined): "Standort" | "Liegenschaft" {
  return kundeTyp === "hausverwaltung" ? "Liegenschaft" : "Standort";
}
