import { Handle, Position, useReactFlow, type NodeProps } from "@xyflow/react";

import type { BoardNode, KlebezettelDaten, KlebezettelFarbe } from "../types";

const FARB_KLASSEN: Record<KlebezettelFarbe, string> = {
  gelb: "bg-amber-100 text-amber-900",
  blau: "bg-blue-100 text-blue-900",
  gruen: "bg-emerald-100 text-emerald-900",
  rosa: "bg-rose-100 text-rose-900",
};

const FARB_SWATCH: Record<KlebezettelFarbe, string> = {
  gelb: "bg-amber-300",
  blau: "bg-blue-300",
  gruen: "bg-emerald-300",
  rosa: "bg-rose-300",
};

const KLEBEZETTEL_FARBEN: KlebezettelFarbe[] = ["gelb", "blau", "gruen", "rosa"];

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
      {/* Nur bei Auswahl sichtbar, sonst wuerde jeder Klebezettel dauerhaft
          vier Punkte mitschleppen -- analog zum Resize-Handle bei RahmenNode. */}
      {selected && (
        <div className="nodrag mb-2 flex items-center gap-1.5">
          {KLEBEZETTEL_FARBEN.map((f) => (
            <button
              key={f}
              onClick={() => updateNodeData(id, { farbe: f })}
              aria-label={`Farbe ${f}`}
              className={`h-4 w-4 rounded-full ${FARB_SWATCH[f]} ${
                farbe === f ? "ring-2 ring-offset-1 ring-slate-600 dark:ring-stone-300" : ""
              }`}
            />
          ))}
        </div>
      )}
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
