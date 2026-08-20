import { Handle, Position, type NodeProps } from "@xyflow/react";

import type { BildDaten, BoardNode } from "../types";

export function BildNode({ data, selected }: NodeProps<BoardNode>) {
  const { url } = data as BildDaten;
  return (
    <div className={`w-[200px] overflow-hidden rounded-lg shadow-md ${selected ? "ring-2 ring-blue-500" : ""}`}>
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !border-none !bg-slate-300 dark:!bg-stone-600" />
      {url ? (
        <img src={url} alt="" className="block w-full" draggable={false} />
      ) : (
        <div className="flex h-24 items-center justify-center bg-slate-100 text-xs text-slate-400 dark:bg-stone-800 dark:text-stone-500">
          Kein Bild
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !border-none !bg-slate-300 dark:!bg-stone-600" />
    </div>
  );
}
