import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { STATUS_BADGE, STATUS_LABEL, istUeberfaellig } from "../../config/vorgangDarstellung";
import type { FeedCard } from "../../types";
import { Karte } from "../OfficeUi";

const spalten = createColumnHelper<FeedCard>();

const SPALTEN = [
  spalten.accessor("vorgangsnummer", { header: "Nr." }),
  spalten.accessor("titel", { header: "Titel" }),
  spalten.accessor("kunde_name", { header: "Kunde" }),
  spalten.accessor((v) => v.anlage_bezeichnung ?? v.standort_bezeichnung ?? "—", {
    id: "anlage",
    header: "Anlage",
  }),
  spalten.accessor("status", {
    header: "Status",
    cell: (info) => (
      <span className={`inline-block px-2 py-0.5 text-[10px] font-semibold ${STATUS_BADGE[info.getValue()]}`}>
        {STATUS_LABEL[info.getValue()]}
      </span>
    ),
  }),
  spalten.accessor("prioritaet", { header: "Prio." }),
  spalten.accessor("faelligkeit_am", {
    header: "Fällig",
    cell: (info) => {
      const wert = info.getValue();
      if (!wert) return <span className="text-ind-ink-3">—</span>;
      const ueberfaellig = istUeberfaellig(wert);
      return (
        <span className={ueberfaellig ? "font-semibold text-rose-600 dark:text-rose-300" : undefined}>
          {new Date(wert).toLocaleDateString("de-DE")}
        </span>
      );
    },
  }),
  spalten.accessor((v) => v.zugewiesener_name ?? "—", { id: "zugewiesen", header: "Zugewiesen" }),
];

/** Sortierbare, filterbare Tabellen-Ansicht der Vorgaenge -- die Filter
 * (Kunde/Anlage/Projekt/Status/...) laufen serverseitig ueber dieselbe
 * Filterleiste wie Liste/Kanban/Raster (siehe OfficeVorgaengePage.tsx),
 * hier nur noch Spalten-Sortierung on top. */
export function VorgaengeTabelle({ vorgaenge }: { vorgaenge: FeedCard[] }) {
  const navigate = useNavigate();
  const [sorting, setSorting] = useState<SortingState>([]);

  const table = useReactTable({
    data: vorgaenge,
    columns: SPALTEN,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <Karte className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id} className="border-b border-ind-line-2">
              {headerGroup.headers.map((header) => {
                const sortiert = header.column.getIsSorted();
                return (
                  <th
                    key={header.id}
                    onClick={header.column.getToggleSortingHandler()}
                    className="cursor-pointer px-3 py-2 text-left text-xs font-medium tracking-wide text-ind-ink-3 uppercase select-none hover:text-ind-ink-2"
                  >
                    <span className="flex items-center gap-1">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {sortiert === "asc" ? (
                        <ArrowUp size={12} strokeWidth={2.5} />
                      ) : sortiert === "desc" ? (
                        <ArrowDown size={12} strokeWidth={2.5} />
                      ) : (
                        <ArrowUpDown size={11} strokeWidth={2} className="text-ind-ink-3/50" />
                      )}
                    </span>
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              onClick={() => navigate(`/vorgaenge/${row.original.id}`)}
              className="cursor-pointer border-b border-ind-line last:border-b-0 hover:bg-slate-50 dark:hover:bg-stone-800/50"
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-3 py-2 text-ind-ink">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </Karte>
  );
}
