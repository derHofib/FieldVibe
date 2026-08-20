import { Handle, Position, useReactFlow, type NodeProps } from "@xyflow/react";

import type { BoardNode, TextDaten } from "../types";

export function TextNode({ id, data, selected }: NodeProps<BoardNode>) {
  const { updateNodeData } = useReactFlow();
  const { text } = data as TextDaten;
  return (
    <div className={`w-[180px] ${selected ? "ring-2 ring-blue-500" : ""}`}>
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !border-none !bg-slate-300 dark:!bg-stone-600" />
      <textarea
        value={text}
        onChange={(e) => updateNodeData(id, { text: e.target.value })}
        rows={2}
        placeholder="Text…"
        className="nodrag w-full resize-none bg-transparent text-sm font-semibold text-slate-700 outline-none placeholder:text-slate-300 dark:text-stone-200"
      />
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !border-none !bg-slate-300 dark:!bg-stone-600" />
    </div>
  );
}
