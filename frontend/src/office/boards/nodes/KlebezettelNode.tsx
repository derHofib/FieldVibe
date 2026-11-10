import { Handle, Position, useReactFlow, type NodeProps } from "@xyflow/react";

import type { BoardNode, KlebezettelDaten, KlebezettelFarbe } from "../types";

const FARB_KLASSEN: Record<KlebezettelFarbe, string> = {
  gelb: "bg-st-arbeit-bg text-st-arbeit",
  blau: "bg-tintbg text-tint",
  gruen: "bg-st-erledigt-bg text-st-erledigt",
  rosa: "bg-st-fehlt-bg text-st-fehlt",
};

const FARB_SWATCH: Record<KlebezettelFarbe, string> = {
  gelb: "bg-st-arbeit-bg",
  blau: "bg-tintbg",
  gruen: "bg-st-erledigt-bg",
  rosa: "bg-st-fehlt-bg",
};

const KLEBEZETTEL_FARBEN: KlebezettelFarbe[] = ["gelb", "blau", "gruen", "rosa"];

export function KlebezettelNode({ id, data, selected }: NodeProps<BoardNode>) {
  const { updateNodeData } = useReactFlow();
  const { text, farbe } = data as KlebezettelDaten;
  return (
    <div
      className={`w-[170px] rounded-lg p-3 text-xs font-medium shadow-md ${FARB_KLASSEN[farbe] ?? FARB_KLASSEN.gelb} ${
        selected ? "ring-2 ring-tint" : ""
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
                farbe === f ? "ring-2 ring-offset-1 ring-sep " : ""
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
