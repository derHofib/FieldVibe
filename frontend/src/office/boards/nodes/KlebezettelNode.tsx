import { Handle, Position, useReactFlow, type NodeProps } from "@xyflow/react";

import type { BoardNode, KlebezettelDaten, KlebezettelFarbe } from "../types";

const FARB_KLASSEN: Record<KlebezettelFarbe, string> = {
  gelb: "bg-amber-100 text-amber-900",
  blau: "bg-blue-100 text-blue-900",
  gruen: "bg-emerald-100 text-emerald-900",
  rosa: "bg-rose-100 text-rose-900",
};

export function KlebezettelNode({ id, data, selected }: NodeProps<BoardNode>) {
  const { updateNodeData } = useReactFlow();
  const { text, farbe } = data as KlebezettelDaten;
  return (
    <div
      className={`w-[170px] rounded-lg p-3 text-xs font-medium shadow-md ${FARB_KLASSEN[farbe] ?? FARB_KLASSEN.gelb} ${
        selected ? "ring-2 ring-blue-500" : ""
      }`}
    >
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !border-none !bg-slate-300 dark:!bg-stone-600" />
      <textarea
        value={text}
        onChange={(e) => updateNodeData(id, { text: e.target.value })}
        rows={3}
        placeholder="Notiz…"
        className="nodrag w-full resize-none bg-transparent text-xs font-medium outline-none placeholder:text-current placeholder:opacity-50"
      />
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !border-none !bg-slate-300 dark:!bg-stone-600" />
    </div>
  );
}
