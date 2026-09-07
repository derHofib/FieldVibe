import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Compass, LayoutGrid, Plus, StickyNote, Trash2, Workflow } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { boardsApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import type { BoardTyp } from "../../types";
import { Karte, SeitenKopf } from "../OfficeUi";

const TYP_ICON: Record<BoardTyp, typeof LayoutGrid> = {
  frei: LayoutGrid,
  bauplanung: Compass,
  prozess: Workflow,
};

const TYP_LABEL: Record<BoardTyp, string> = {
  frei: "Freies Board",
  bauplanung: "Bauplanung",
  prozess: "Prozess",
};

const TYP_TON: Record<BoardTyp, string> = {
  frei: "bg-indigo-100 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-300",
  bauplanung: "bg-amber-100 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300",
  prozess: "bg-emerald-100 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300",
};

function relativeZeit(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diffMs / 60_000);
  if (min < 60) return min <= 1 ? "gerade eben" : `vor ${min} Min.`;
  const std = Math.floor(min / 60);
  if (std < 24) return `vor ${std} Std.`;
  const tage = Math.floor(std / 24);
  return tage === 1 ? "vor 1 Tag" : `vor ${tage} Tagen`;
}

export function OfficeBoardsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [zeigeNeu, setZeigeNeu] = useState(false);
  const [name, setName] = useState("");
  const [typ, setTyp] = useState<BoardTyp>("frei");

  const { data: boards, isLoading } = useQuery({ queryKey: ["boards"], queryFn: () => boardsApi.list() });

  const erstellen = useMutation({
    mutationFn: () => boardsApi.create({ name: name.trim(), board_typ: typ }),
    onSuccess: (board) => navigate(`/boards/${board.id}`),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["boards"] }),
  });

  const loeschen = useMutation({
    mutationFn: (id: string) => boardsApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["boards"] }),
  });

  return (
    <div>
      <SeitenKopf titel="Boards" anzahl={boards?.length}>
        <button
          onClick={() => setZeigeNeu(true)}
          className="btn-clay flex items-center gap-1.5 rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-2 text-xs font-semibold text-white"
        >
          <Plus size={14} strokeWidth={2.5} />
          Neues Board
        </button>
      </SeitenKopf>

      {zeigeNeu && (
        <Karte className="mb-4 p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[220px] flex-1">
              <label className="mb-1 block text-xs font-medium text-ind-ink-3">Name</label>
              <input
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="z. B. Projektplanung Rheinblick"
                className="w-full border border-ind-line bg-transparent px-3 py-2 text-sm text-ind-ink"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-ind-ink-3">Art</label>
              <select
                value={typ}
                onChange={(e) => setTyp(e.target.value as BoardTyp)}
                className="border border-ind-line bg-transparent px-3 py-2 text-sm text-ind-ink"
              >
                {(Object.keys(TYP_LABEL) as BoardTyp[]).map((t) => (
                  <option key={t} value={t}>
                    {TYP_LABEL[t]}
                  </option>
                ))}
              </select>
            </div>
            <button
              onClick={() => erstellen.mutate()}
              disabled={!name.trim() || erstellen.isPending}
              className="btn-clay rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 px-4 py-2 text-xs font-semibold text-white disabled:opacity-40"
            >
              Anlegen
            </button>
            <button
              onClick={() => setZeigeNeu(false)}
              className="rounded-lg px-3 py-2 text-xs font-medium text-ind-ink-3"
            >
              Abbrechen
            </button>
          </div>
        </Karte>
      )}

      {isLoading ? (
        <p className="py-10 text-center text-sm text-ind-ink-3">Lädt…</p>
      ) : !boards || boards.length === 0 ? (
        <EmptyState icon={StickyNote} text="Noch keine Boards angelegt." />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {boards.map((b) => {
            const Icon = TYP_ICON[b.board_typ];
            return (
              <button key={b.id} onClick={() => navigate(`/boards/${b.id}`)} className="text-left">
                <Karte className="overflow-hidden transition-shadow hover:shadow-md">
                  <div
                    className="relative flex h-24 items-center justify-center bg-slate-50 dark:bg-stone-800/40"
                    style={{ backgroundImage: "radial-gradient(#cbd5e1 1px, transparent 1px)", backgroundSize: "16px 16px" }}
                  >
                    <span className={`flex h-11 w-11 items-center justify-center rounded-xl ${TYP_TON[b.board_typ]}`}>
                      <Icon size={20} strokeWidth={2} />
                    </span>
                    <span
                      role="button"
                      tabIndex={0}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (window.confirm(`Board "${b.name}" wirklich löschen?`)) loeschen.mutate(b.id);
                      }}
                      className="absolute top-2 right-2 flex h-7 w-7 items-center justify-center rounded-lg bg-white/90 text-slate-400 hover:text-red-600 dark:bg-stone-900/80 dark:text-stone-500 dark:hover:text-red-400"
                    >
                      <Trash2 size={14} strokeWidth={2} />
                    </span>
                  </div>
                  <div className="p-3.5">
                    <p className="truncate text-sm font-bold text-ind-ink">{b.name}</p>
                    <div className="mt-1 flex items-center justify-between gap-2">
                      <span className="text-[11px] font-medium text-ind-ink-3">
                        {TYP_LABEL[b.board_typ]}
                      </span>
                      <span className="text-[11px] text-ind-ink-3">
                        {relativeZeit(b.updated_at)}
                      </span>
                    </div>
                  </div>
                </Karte>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
