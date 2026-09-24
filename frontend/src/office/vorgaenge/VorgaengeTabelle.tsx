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

import { StatusPille } from "../../components/apple/StatusPille";
import { vorgangStatusZuToken } from "../../components/apple/status";
import { STATUS_LABEL, istUeberfaellig } from "../../config/vorgangDarstellung";
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
    cell: (info) => <StatusPille status={vorgangStatusZuToken(info.getValue())} label={STATUS_LABEL[info.getValue()]} />,
  }),
  spalten.accessor("prioritaet", { header: "Prio." }),
  spalten.accessor("faelligkeit_am", {
    header: "Fällig",
    cell: (info) => {
      const wert = info.getValue();
      if (!wert) return <span className="text-label2">—</span>;
      const ueberfaellig = istUeberfaellig(wert);
      return (
        <span className={ueberfaellig ? "font-semibold text-st-fehlt" : undefined}>
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
            <tr key={headerGroup.id} className="border-b border-sepstrong">
              {headerGroup.headers.map((header) => {
                const sortiert = header.column.getIsSorted();
                return (
                  <th
                    key={header.id}
                    onClick={header.column.getToggleSortingHandler()}
                    className="cursor-pointer px-3 py-2 text-left text-xs font-medium tracking-wide text-label2 uppercase select-none hover:text-label"
                  >
                    <span className="flex items-center gap-1">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {sortiert === "asc" ? (
                        <ArrowUp size={12} strokeWidth={2.5} />
                      ) : sortiert === "desc" ? (
                        <ArrowDown size={12} strokeWidth={2.5} />
                      ) : (
                        <ArrowUpDown size={11} strokeWidth={2} className="text-label3" />
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
              className="cursor-pointer border-b border-sep last:border-b-0 hover:bg-fill"
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-3 py-2 text-label">
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
