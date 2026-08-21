import { useMutation } from "@tanstack/react-query";
import { Handle, Position, useReactFlow, type NodeProps } from "@xyflow/react";
import { FileText, Paperclip, Upload, X } from "lucide-react";
import { useRef } from "react";
import { useParams } from "react-router-dom";

import { boardsApi } from "../../../api/endpoints";
import type { BoardNode, DateiAnhangDaten } from "../types";

/** boardId kommt bewusst per useParams statt als Prop -- der Node sitzt
 * immer unter der Route /boards/:id (siehe OfficeBoardPage.tsx), genau wie
 * VorgangKarteNode sich seinen useNavigate() selbst holt statt ihn
 * durchgereicht zu bekommen. */
export function DateiAnhangNode({ id, data, selected }: NodeProps<BoardNode>) {
  const { id: routenId } = useParams<{ id: string }>();
  const board_id = routenId ?? "";
  const { updateNodeData } = useReactFlow();
  const { dateiname, object_key } = data as DateiAnhangDaten;
  const inputRef = useRef<HTMLInputElement>(null);

  const hochladen = useMutation({
    mutationFn: (file: File) => boardsApi.anhangUpload(board_id, file),
    onSuccess: (ergebnis) => updateNodeData(id, { dateiname: ergebnis.dateiname, object_key: ergebnis.object_key }),
  });

  const oeffnen = useMutation({
    mutationFn: () => boardsApi.anhangUrl(board_id, object_key!),
    onSuccess: (ergebnis) => window.open(ergebnis.url, "_blank", "noopener,noreferrer"),
  });

  const entfernen = useMutation({
    mutationFn: () => boardsApi.anhangRemove(board_id, object_key!),
    onSuccess: () => updateNodeData(id, { dateiname: "", object_key: null }),
  });

  return (
    <div
      className={`w-[190px] rounded-xl bg-white p-3 shadow-lg dark:bg-stone-900 ${
        selected ? "ring-2 ring-blue-500" : ""
      }`}
    >
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !border-none !bg-slate-300 dark:!bg-stone-600" />
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) hochladen.mutate(file);
          e.target.value = "";
        }}
      />
      {object_key ? (
        <div className="nodrag flex items-start gap-2">
          <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-cyan-100 text-cyan-700 dark:bg-cyan-500/15 dark:text-cyan-300">
            <FileText size={14} strokeWidth={2} />
          </span>
          <div className="min-w-0 flex-1">
            <button
              onClick={() => oeffnen.mutate()}
              className="block truncate text-left text-[11.5px] font-semibold text-slate-700 hover:underline dark:text-stone-200"
              title={dateiname}
            >
              {dateiname}
            </button>
            <button
              onClick={() => entfernen.mutate()}
              className="mt-0.5 text-[10px] font-medium text-slate-400 hover:text-red-500 dark:text-stone-500"
            >
              Entfernen
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => inputRef.current?.click()}
          disabled={hochladen.isPending}
          className="nodrag flex w-full flex-col items-center gap-1.5 rounded-lg border-2 border-dashed border-slate-200 py-3 text-slate-400 disabled:opacity-50 dark:border-stone-700 dark:text-stone-500"
        >
          {hochladen.isPending ? (
            <Upload size={16} strokeWidth={2} className="animate-pulse" />
          ) : (
            <Paperclip size={16} strokeWidth={2} />
          )}
          <span className="text-[11px] font-semibold">{hochladen.isPending ? "Lädt hoch…" : "Datei anhängen"}</span>
        </button>
      )}
      {hochladen.isError && (
        <p className="nodrag mt-1.5 flex items-center gap-1 text-[10px] text-red-600 dark:text-red-400">
          <X size={10} strokeWidth={2.5} /> Upload fehlgeschlagen
        </p>
      )}
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !border-none !bg-slate-300 dark:!bg-stone-600" />
    </div>
  );
}
