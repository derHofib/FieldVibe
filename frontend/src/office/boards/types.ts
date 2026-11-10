import type { Edge, Node } from "@xyflow/react";

/** Datenformen je Node-Typ -- werden 1:1 in Board.inhalt_json.nodes[].data
 * gespeichert (siehe office/boards/OfficeBoardPage.tsx fuer den Autosave).
 * Absichtlich lose/optional gehalten statt streng validiert: ein Board ist
 * Freitext-Inhalt, kein Formular. */

export type KlebezettelFarbe = "gelb" | "blau" | "gruen" | "rosa";

export interface KlebezettelDaten extends Record<string, unknown> {
  text: string;
  farbe: KlebezettelFarbe;
}

export interface FormDaten extends Record<string, unknown> {
  label: string;
  form: "rechteck" | "kreis";
}

export interface TextDaten extends Record<string, unknown> {
  text: string;
}

export interface RahmenDaten extends Record<string, unknown> {
  label: string;
}

export interface BildDaten extends Record<string, unknown> {
  url: string;
}

export interface VorgangKarteDaten extends Record<string, unknown> {
  vorgang_id: string;
}

export interface AnlagenPinDaten extends Record<string, unknown> {
  nummer: number;
  anlage_id: string | null;
}

export interface ProzessSchrittDaten extends Record<string, unknown> {
  label: string;
  sub?: string;
}

export interface ProzessEntscheidungDaten extends Record<string, unknown> {
  label: string;
}

export interface GrundrissDaten extends Record<string, unknown> {
  url: string;
}

export interface ChecklistePunkt {
  text: string;
  erledigt: boolean;
}

export interface ChecklisteDaten extends Record<string, unknown> {
  titel: string;
  punkte: ChecklistePunkt[];
}

export interface DateiAnhangDaten extends Record<string, unknown> {
  dateiname: string;
  object_key: string | null;
}

// Kuratierte Auswahl statt freier Icon-Eingabe -- siehe STICKER_ICONS in
// nodes/StickerNode.tsx fuer die Zuordnung Name -> lucide-Komponente.
export interface StickerDaten extends Record<string, unknown> {
  icon: string;
}

export type BoardNodeTyp =
  | "klebezettel"
  | "form"
  | "text"
  | "rahmen"
  | "bild"
  | "vorgang_karte"
  | "anlagen_pin"
  | "prozess_schritt"
  | "prozess_entscheidung"
  | "grundriss"
  | "checkliste"
  | "datei_anhang"
  | "sticker";

export type BoardNode = Node<Record<string, unknown>, BoardNodeTyp>;
export type BoardEdge = Edge;

export interface BoardInhalt extends Record<string, unknown> {
  nodes: BoardNode[];
  edges: BoardEdge[];
  viewport?: { x: number; y: number; zoom: number };
}

export function leeresInhalt(): BoardInhalt {
  return { nodes: [], edges: [] };
}
