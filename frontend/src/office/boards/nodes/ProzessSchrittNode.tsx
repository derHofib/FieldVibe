import { Handle, Position, useReactFlow, type NodeProps } from "@xyflow/react";

import type { BoardNode, ProzessSchrittDaten } from "../types";

export function ProzessSchrittNode({ id, data, selected }: NodeProps<BoardNode>) {
  const { updateNodeData } = useReactFlow();
  const { label, sub } = data as ProzessSchrittDaten;
  return (
    <div
      className={`w-[160px] rounded-xl border-[1.5px] border-sep bg-white p-3 shadow-sm dark:bg-stone-900 ${
        selected ? "ring-2 ring-tint" : ""
      }`}
    >
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-none !bg-slate-300 dark:!bg-stone-600" />
      <input
        value={label}
        onChange={(e) => updateNodeData(id, { label: e.target.value })}
        placeholder="Prozessschritt…"
        className="nodrag w-full bg-transparent text-[12.5px] font-bold text-label outline-none placeholder:text-label3 "
      />
      <input
        value={sub ?? ""}
        onChange={(e) => updateNodeData(id, { sub: e.target.value })}
        placeholder="Zusatz…"
        className="nodrag mt-0.5 w-full bg-transparent text-[10.5px] text-label2 outline-none placeholder:text-label3 0"
      />
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-none !bg-slate-300 dark:!bg-stone-600" />
    </div>
  );
}
