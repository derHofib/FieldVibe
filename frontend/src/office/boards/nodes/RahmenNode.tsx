import { NodeResizer } from "@xyflow/react";
import { useReactFlow, type NodeProps } from "@xyflow/react";

import type { BoardNode, RahmenDaten } from "../types";

/** Rein visuelle Gruppierung -- bewusst kein echtes React-Flow-Parent/Child-
 * Nesting in v1 (das braeuchte eigene Drag-in/Drag-out-Logik). Ein Rahmen ist
 * ein groBer, weit hinten liegender Kasten; Notizen "drinnen" sind normale,
 * unabhaengige Nodes, die zufaellig darueber positioniert sind. */
export function RahmenNode({ id, data, selected }: NodeProps<BoardNode>) {
  const { updateNodeData } = useReactFlow();
  const { label } = data as RahmenDaten;
  return (
    <div className="h-full w-full rounded-xl border-2 border-dashed border-slate-300 bg-slate-50/40 dark:border-stone-700 dark:bg-stone-800/20">
      <NodeResizer isVisible={selected} minWidth={160} minHeight={120} lineClassName="!border-blue-500" handleClassName="!bg-blue-500" />
      <input
        value={label}
        onChange={(e) => updateNodeData(id, { label: e.target.value })}
        placeholder="Rahmen-Beschriftung…"
        className="nodrag m-2 rounded-md bg-transparent px-1 text-xs font-bold tracking-wide text-slate-500 uppercase outline-none placeholder:text-slate-300 dark:text-stone-400"
      />
    </div>
  );
}
