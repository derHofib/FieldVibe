import type { NodeTypes } from "@xyflow/react";

import { AnlagenPinNode } from "./AnlagenPinNode";
import { BildNode } from "./BildNode";
import { FormNode } from "./FormNode";
import { GrundrissNode } from "./GrundrissNode";
import { KlebezettelNode } from "./KlebezettelNode";
import { ProzessEntscheidungNode } from "./ProzessEntscheidungNode";
import { ProzessSchrittNode } from "./ProzessSchrittNode";
import { RahmenNode } from "./RahmenNode";
import { TextNode } from "./TextNode";
import { VorgangKarteNode } from "./VorgangKarteNode";

export const BOARD_NODE_TYPES: NodeTypes = {
  klebezettel: KlebezettelNode,
  form: FormNode,
  text: TextNode,
  rahmen: RahmenNode,
  bild: BildNode,
  vorgang_karte: VorgangKarteNode,
  anlagen_pin: AnlagenPinNode,
  prozess_schritt: ProzessSchrittNode,
  prozess_entscheidung: ProzessEntscheidungNode,
  grundriss: GrundrissNode,
};
