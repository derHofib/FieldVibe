import { Handle, Position, useReactFlow, type NodeProps } from "@xyflow/react";

import type { BoardNode, FormDaten } from "../types";

export function FormNode({ id, data, selected }: NodeProps<BoardNode>) {
  const { updateNodeData } = useReactFlow();
  const { label, form } = data as FormDaten;
  return (
    <div
      className={`flex h-[76px] w-[150px] items-center justify-center bg-violet-100 p-2 text-center text-xs font-semibold text-violet-800 shadow-md ${
        form === "kreis" ? "rounded-full" : "rounded-xl"
      } ${selected ? "ring-2 ring-blue-500" : ""}`}
    >
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !border-none !bg-slate-300 dark:!bg-stone-600" />
      <input
        value={label}
        onChange={(e) => updateNodeData(id, { label: e.target.value })}
        placeholder="Beschriftung…"
        className="nodrag w-full bg-transparent text-center text-xs font-semibold outline-none placeholder:text-violet-400"
      />
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !border-none !bg-slate-300 dark:!bg-stone-600" />
    </div>
  );
}
