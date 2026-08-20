import { Handle, Position, useReactFlow, type NodeProps } from "@xyflow/react";

import type { BoardNode, ProzessEntscheidungDaten } from "../types";

export function ProzessEntscheidungNode({ id, data, selected }: NodeProps<BoardNode>) {
  const { updateNodeData } = useReactFlow();
  const { label } = data as ProzessEntscheidungDaten;
  return (
    <div className="relative flex h-[120px] w-[120px] items-center justify-center">
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-none !bg-slate-300 dark:!bg-stone-600" />
      <div
        className={`absolute inset-0 rotate-45 rounded-2xl border-[1.5px] border-amber-300 bg-amber-50 dark:border-amber-500/40 dark:bg-amber-500/10 ${
          selected ? "ring-2 ring-blue-500" : ""
        }`}
      />
      <input
        value={label}
        onChange={(e) => updateNodeData(id, { label: e.target.value })}
        placeholder="Entscheidung?"
        className="nodrag relative z-10 w-20 bg-transparent text-center text-[11px] font-bold text-amber-800 outline-none placeholder:text-amber-300 dark:text-amber-200"
      />
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-none !bg-slate-300 dark:!bg-stone-600" />
      <Handle type="source" id="unten" position={Position.Bottom} className="!h-2 !w-2 !border-none !bg-slate-300 dark:!bg-stone-600" />
    </div>
  );
}
