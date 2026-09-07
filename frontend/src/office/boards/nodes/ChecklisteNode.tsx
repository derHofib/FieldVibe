import { Handle, Position, useReactFlow, type NodeProps } from "@xyflow/react";
import { Plus, X } from "lucide-react";

import type { BoardNode, ChecklisteDaten, ChecklistePunkt } from "../types";

export function ChecklisteNode({ id, data, selected }: NodeProps<BoardNode>) {
  const { updateNodeData } = useReactFlow();
  const { titel, punkte } = data as ChecklisteDaten;

  const punkteSetzen = (naechste: ChecklistePunkt[]) => updateNodeData(id, { punkte: naechste });

  return (
    <div
      className={`w-[210px] rounded-xl bg-white p-3 shadow-lg dark:bg-stone-900 ${
        selected ? "ring-2 ring-blue-500" : ""
      }`}
    >
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !border-none !bg-slate-300 dark:!bg-stone-600" />
      <input
        value={titel}
        onChange={(e) => updateNodeData(id, { titel: e.target.value })}
        placeholder="Checkliste…"
        className="nodrag w-full bg-transparent text-xs font-bold text-slate-700 outline-none placeholder:text-slate-300 dark:text-stone-200 dark:placeholder:text-stone-600"
      />
      <div className="mt-2 space-y-1.5">
        {punkte.map((punkt, i) => (
          <div key={i} className="nodrag flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={punkt.erledigt}
              onChange={(e) =>
                punkteSetzen(punkte.map((p, pi) => (pi === i ? { ...p, erledigt: e.target.checked } : p)))
              }
              className="h-3.5 w-3.5 shrink-0 accent-blue-600"
            />
            <input
              value={punkt.text}
              onChange={(e) => punkteSetzen(punkte.map((p, pi) => (pi === i ? { ...p, text: e.target.value } : p)))}
              placeholder="Punkt…"
              className={`min-w-0 flex-1 bg-transparent text-[11.5px] outline-none placeholder:text-slate-300 dark:placeholder:text-stone-600 ${
                punkt.erledigt ? "text-slate-400 line-through dark:text-stone-500" : "text-ind-ink"
              }`}
            />
            <button
              onClick={() => punkteSetzen(punkte.filter((_, pi) => pi !== i))}
              aria-label="Punkt entfernen"
              className="shrink-0 text-slate-300 hover:text-red-500 dark:text-stone-600"
            >
              <X size={11} strokeWidth={2.5} />
            </button>
          </div>
        ))}
      </div>
      <button
        onClick={() => punkteSetzen([...punkte, { text: "", erledigt: false }])}
        className="nodrag mt-2 flex items-center gap-1 text-[11px] font-semibold text-blue-700 dark:text-blue-400"
      >
        <Plus size={12} strokeWidth={2.5} /> Punkt
      </button>
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !border-none !bg-slate-300 dark:!bg-stone-600" />
    </div>
  );
}
