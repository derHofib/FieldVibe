import type { NodeProps } from "@xyflow/react";

import type { BoardNode, GrundrissDaten } from "../types";

/** Hintergrundbild fuer Bauplanung-Boards -- nicht ueber Handles verbindbar,
 * bewusst nicht selektierbar/loeschbar wie ein normales Element (siehe
 * office/boards/OfficeBoardPage.tsx, nodesDraggable/nodesConnectable je
 * Node einzeln gesteuert). */
export function GrundrissNode({ data }: NodeProps<BoardNode>) {
  const { url } = data as GrundrissDaten;
  if (!url) return null;
  return <img src={url} alt="Grundriss" className="block max-w-none select-none" draggable={false} />;
}
