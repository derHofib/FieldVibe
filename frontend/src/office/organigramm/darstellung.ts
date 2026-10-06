import { ApiError } from "../../api/client";
import type { StatusKey } from "../../components/apple/status";
import type { RechteScope } from "../../types";
import type { Besetzung, Position, PositionCreate, PositionStatus } from "../../types/organigramm";

export const POSITION_STATUS_LABEL: Record<PositionStatus, string> = {
  besetzt: "Besetzt",
  vakant: "Vakant",
  // Fachlich "geplant" (Flag), in der Oberflaeche als Platzhalter bezeichnet
  geplant: "Platzhalter",
};

// Vakant bekommt den Warnton (orange), nicht Rot: es ist ein Handlungsbedarf, kein Fehler.
export const POSITION_STATUS_TOKEN: Record<PositionStatus, StatusKey> = {
  besetzt: "erledigt",
  vakant: "arbeit",
  geplant: "geplant",
};

export const SCOPE_LABEL: Record<RechteScope, string> = {
  eigene: "Eigene",
  team: "Team",
  teilbaum: "Teilbaum",
  bereich: "Bereich",
  mandant: "Mandant",
};

export const AKTION_LABEL: Record<string, string> = {
  sehen: "Sehen",
  erstellen: "Erstellen",
  bearbeiten: "Bearbeiten",
  loeschen: "Löschen",
  exportieren: "Exportieren",
  freigeben: "Freigeben",
  rechte_verwalten: "Rechte verwalten",
  zeitplan_sehen: "Zeitplan sehen",
  zeitplan_beantragen: "Zeitplan beantragen",
};

export function aktionLabel(aktion: string): string {
  return AKTION_LABEL[aktion] ?? aktion;
}

export function scopeLabel(scope: string | null | undefined): string {
  return scope ? (SCOPE_LABEL[scope as RechteScope] ?? scope) : "–";
}

export type KnotenVariante = "kontext" | "besetzt" | "vakant" | "geplant";

export interface KnotenDarstellung {
  variante: KnotenVariante;
  stab: boolean;
  gestrichelt: boolean;
  blass: boolean;
  statusLabel: string | null;
}

/** Welche visuelle Variante ein Knoten bekommt; unabhaengig von React, damit testbar. */
export function knotenDarstellung(p: Position): KnotenDarstellung {
  const stab = p.typ === "stabsstelle";
  if (p.kontext || !p.status) {
    return { variante: "kontext", stab, gestrichelt: false, blass: true, statusLabel: null };
  }
  return {
    variante: p.status,
    stab,
    gestrichelt: p.status === "vakant",
    blass: p.status === "geplant",
    statusLabel: POSITION_STATUS_LABEL[p.status],
  };
}

/** Besetzungsanzeige: Namen, sonst "vakant"/"Platzhalter"; ohne Namensrecht (DSGVO) nur die Anzahl. */
export function besetzungText(p: Position): string {
  const aktive = p.besetzungen ?? [];
  if (aktive.length === 0) return p.status === "geplant" ? "Platzhalter" : "vakant";
  const namen = aktive.map((b) => b.name).filter((n): n is string => !!n);
  if (namen.length === aktive.length) return namen.join(", ");
  if (namen.length === 0) return aktive.length === 1 ? "1 Person" : `${aktive.length} Personen`;
  return `${namen.join(", ")} +${aktive.length - namen.length}`;
}

export function sollIst(p: Position): string {
  return `${p.ist_besetzung ?? 0}/${p.soll_besetzung ?? 0}`;
}

export function istUnterbesetzt(p: Position): boolean {
  return !p.kontext && !p.geplant && (p.ist_besetzung ?? 0) < (p.soll_besetzung ?? 0);
}

export type KontextAktion =
  | "details"
  | "darunter"
  | "platzhalter"
  | "stabsstelle"
  | "duplizieren"
  | "rechte"
  | "anzeigen_als"
  | "archivieren"
  | "loeschen";

/**
 * Aktionen im Kontextmenue eines Knotens. `darf` fragt ein Organigramm-Recht ab
 * (sehen/erstellen/bearbeiten/loeschen/rechte_verwalten). Das Backend erzwingt die
 * Rechte ohnehin -- hier wird nur nichts angeboten, was sicher scheitern wuerde.
 */
export function kontextAktionen(p: Position, darf: (aktion: string) => boolean, kinderAnzahl: number): KontextAktion[] {
  if (p.kontext) return [];
  const aktionen: KontextAktion[] = ["details"];
  if (p.archiviert_am) return aktionen;
  const istWurzel = p.parent_id === null;
  if (darf("erstellen")) {
    aktionen.push("darunter", "platzhalter", "stabsstelle");
    if (!istWurzel) aktionen.push("duplizieren");
  }
  if (darf("rechte_verwalten")) aktionen.push("rechte");
  aktionen.push("anzeigen_als");
  if (darf("loeschen") && !istWurzel) {
    aktionen.push("archivieren");
    // Loeschen geht nur ohne Unterpositionen und ohne jemals besetzt gewesen zu sein;
    // die Besetzungshistorie kennt die Liste nicht, das Backend antwortet sonst mit 409.
    if (kinderAnzahl === 0 && (p.besetzungen ?? []).length === 0) aktionen.push("loeschen");
  }
  return aktionen;
}

export interface MenueZustand {
  position: Position;
  anker: { x: number; y: number };
}

/** Neuer Menuezustand beim Klick auf "...": derselbe Knoten schliesst (umschalten), ein anderer wechselt. */
export function menueNachOeffnen(
  alt: MenueZustand | null,
  position: Position,
  anker: { x: number; y: number },
  umschalten = false,
): MenueZustand | null {
  return umschalten && alt?.position.id === position.id ? null : { position, anker };
}

export const KONTEXT_AKTION_LABEL: Record<KontextAktion, string> = {
  details: "Details öffnen",
  darunter: "Position darunter anlegen",
  platzhalter: "Platzhalter anlegen",
  stabsstelle: "Stabsstelle anlegen",
  duplizieren: "Duplizieren",
  rechte: "Rechte bearbeiten",
  anzeigen_als: "Anzeigen als …",
  archivieren: "Archivieren",
  loeschen: "Löschen",
};

/** Backend-Fehler als Satz fuer die Anzeige; 403/409 bekommen eine Einordnung. */
export function verstaendlicherFehler(err: unknown, fallback = "Aktion fehlgeschlagen"): string {
  if (!(err instanceof ApiError)) return err instanceof Error && err.message ? err.message : fallback;
  switch (err.status) {
    case 403:
      return `Nicht erlaubt (Eskalationsschutz): ${err.message} – es kann nur vergeben werden, was Sie selbst besitzen, und nur in Ihrem Verantwortungsbereich.`;
    case 409:
      return `Nicht möglich: ${err.message}`;
    case 404:
      return `Nicht gefunden: ${err.message}`;
    default:
      return err.message || fallback;
  }
}

export function besetzungZeitraum(b: Besetzung, jetzt: Date = new Date()): string {
  const datum = (iso: string) => new Date(iso).toLocaleDateString("de-DE");
  if (b.gueltig_bis) return `${datum(b.gueltig_von)} – ${datum(b.gueltig_bis)}`;
  return new Date(b.gueltig_von) > jetzt ? `ab ${datum(b.gueltig_von)}` : `seit ${datum(b.gueltig_von)}`;
}

/** Aktiv = gestartet und nicht beendet. Zukuenftige Besetzungen zaehlen noch nicht. */
export function besetzungAktiv(b: Besetzung, jetzt: Date = new Date()): boolean {
  return new Date(b.gueltig_von) <= jetzt && (b.gueltig_bis === null || new Date(b.gueltig_bis) > jetzt);
}

export type AnlegeModus = "darunter" | "platzhalter" | "stabsstelle";

export const ANLEGE_MODUS_TITEL: Record<AnlegeModus, string> = {
  darunter: "Position darunter anlegen",
  platzhalter: "Platzhalter anlegen",
  stabsstelle: "Stabsstelle anlegen",
};

/** Body fuer POST /positionen je Menueeintrag; leere Auswahlfelder werden weggelassen. */
export function neuePositionBody(
  modus: AnlegeModus,
  parentId: string,
  felder: { titel: string; orgEinheitId?: string; accountTypId?: string; sollBesetzung?: number },
): PositionCreate {
  const body: PositionCreate = {
    parent_id: parentId,
    typ: modus === "stabsstelle" ? "stabsstelle" : "linie",
    titel: felder.titel.trim(),
    geplant: modus === "platzhalter",
    soll_besetzung: felder.sollBesetzung ?? 1,
  };
  if (felder.orgEinheitId) body.org_einheit_id = felder.orgEinheitId;
  if (felder.accountTypId) body.account_typ_id = felder.accountTypId;
  return body;
}
