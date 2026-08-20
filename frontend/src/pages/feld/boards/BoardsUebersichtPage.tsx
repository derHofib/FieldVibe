import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Compass, LayoutGrid, Plus, StickyNote, Workflow } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { boardsApi } from "../../../api/endpoints";
import { EmptyState } from "../../../components/EmptyState";
import type { BoardTyp } from "../../../types";

const TYP_ICON: Record<BoardTyp, typeof LayoutGrid> = {
  frei: LayoutGrid,
  bauplanung: Compass,
  prozess: Workflow,
};

const TYP_LABEL: Record<BoardTyp, string> = {
  frei: "Frei",
  bauplanung: "Bauplanung",
  prozess: "Prozess",
};

const TYP_TON: Record<BoardTyp, string> = {
  frei: "bg-indigo-100 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-300",
  bauplanung: "bg-amber-100 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300",
  prozess: "bg-emerald-100 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300",
};

const FILTER_OPTIONEN: { key: "alle" | BoardTyp; label: string }[] = [
  { key: "alle", label: "Alle" },
  { key: "frei", label: "Frei" },
  { key: "bauplanung", label: "Bauplanung" },
  { key: "prozess", label: "Prozess" },
];

function relativeZeit(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diffMs / 60_000);
  if (min < 60) return min <= 1 ? "gerade eben" : `vor ${min} Min.`;
  const std = Math.floor(min / 60);
  if (std < 24) return `vor ${std} Std.`;
  const tage = Math.floor(std / 24);
  return tage === 1 ? "vor 1 Tag" : `vor ${tage} Tagen`;
}

/** Mobiles Gegenstueck zu office/boards/OfficeBoardsPage.tsx -- Liste statt
 * Karten-Raster (schmaler Bildschirm), sonst dieselbe Datenquelle
 * (boardsApi). Das Anlegen bleibt bewusst simpel (nur Name + Art), volles
 * Bearbeiten/Werkzeuge gibt es erst nach dem Oeffnen. */
export function BoardsUebersichtPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<"alle" | BoardTyp>("alle");
  const [zeigeNeu, setZeigeNeu] = useState(false);
  const [name, setName] = useState("");
  const [typ, setTyp] = useState<BoardTyp>("frei");

  const { data: boards, isLoading } = useQuery({ queryKey: ["boards"], queryFn: () => boardsApi.list() });

  const erstellen = useMutation({
    mutationFn: () => boardsApi.create({ name: name.trim(), board_typ: typ }),
    onSuccess: (board) => navigate(`/boards/${board.id}`),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["boards"] }),
  });

  const gefiltert = (boards ?? []).filter((b) => filter === "alle" || b.board_typ === filter);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-2">
          <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">Boards</h1>
          <span className="text-sm font-medium text-slate-400 dark:text-stone-500">{boards?.length ?? 0}</span>
        </div>
        <button
          onClick={() => setZeigeNeu((v) => !v)}
          aria-label="Neues Board"
          className="btn-touch flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 dark:text-stone-400 dark:hover:bg-stone-800"
        >
          <Plus size={19} strokeWidth={2.25} />
        </button>
      </div>

      {zeigeNeu && (
        <div className="space-y-2.5 rounded-xl bg-white p-3.5 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="z. B. Projektplanung Rheinblick"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
          <select
            value={typ}
            onChange={(e) => setTyp(e.target.value as BoardTyp)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          >
            {(Object.keys(TYP_LABEL) as BoardTyp[]).map((t) => (
              <option key={t} value={t}>
                {TYP_LABEL[t]}
              </option>
            ))}
          </select>
          <div className="flex items-center gap-3">
            <button
              onClick={() => erstellen.mutate()}
              disabled={!name.trim() || erstellen.isPending}
              className="btn-clay flex-1 rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 py-2 text-sm font-semibold text-white disabled:opacity-40"
            >
              Anlegen
            </button>
            <button
              onClick={() => setZeigeNeu(false)}
              className="text-sm font-medium text-slate-500 dark:text-stone-400"
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}

      <div className="flex gap-2 overflow-x-auto pb-1">
        {FILTER_OPTIONEN.map((o) => (
          <button
            key={o.key}
            onClick={() => setFilter(o.key)}
            className={`btn-touch shrink-0 rounded-full px-3.5 py-1.5 text-xs font-semibold whitespace-nowrap ${
              filter === o.key
                ? "bg-slate-800 text-white dark:bg-stone-100 dark:text-stone-900"
                : "bg-white text-slate-600 shadow-xs dark:bg-stone-900 dark:text-stone-300 dark:shadow-none dark:ring-1 dark:ring-stone-800"
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <p className="py-8 text-center text-sm text-slate-400 dark:text-stone-500">Lädt…</p>
      ) : gefiltert.length === 0 ? (
        <EmptyState icon={StickyNote} text="Noch keine Boards angelegt." />
      ) : (
        <div className="space-y-2.5">
          {gefiltert.map((b) => {
            const Icon = TYP_ICON[b.board_typ];
            return (
              <button
                key={b.id}
                onClick={() => navigate(`/boards/${b.id}`)}
                className="card-interactive btn-touch flex w-full items-center gap-3 rounded-2xl bg-white p-3 text-left shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800"
              >
                <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${TYP_TON[b.board_typ]}`}>
                  <Icon size={19} strokeWidth={2} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[14.5px] font-bold text-slate-800 dark:text-stone-100">{b.name}</p>
                  <p className="mt-0.5 text-xs text-slate-400 dark:text-stone-500">
                    {TYP_LABEL[b.board_typ]} &middot; {relativeZeit(b.updated_at)}
                  </p>
                </div>
                <ChevronRight size={16} className="shrink-0 text-slate-300 dark:text-stone-600" />
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
