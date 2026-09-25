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

import type { Projekt } from "../../types";
import { Karte } from "../OfficeUi";

const spalten = createColumnHelper<Projekt>();

const SPALTEN = [
  spalten.accessor("name", { header: "Name" }),
  spalten.accessor("archiviert", {
    header: "Status",
    cell: (info) =>
      info.getValue() ? (
        <span className="rounded-[var(--radius-ap-pill)] border border-slate-300 px-2 py-0.5 text-xs font-semibold text-slate-400 dark:border-stone-700 dark:text-stone-500">
          Archiviert
        </span>
      ) : (
        <span className="rounded-[var(--radius-ap-pill)] border border-blue-400 px-2 py-0.5 text-xs font-semibold text-blue-700 dark:border-blue-600 dark:text-blue-300">
          Aktiv
        </span>
      ),
  }),
  spalten.accessor("created_at", {
    header: "Erstellt am",
    cell: (info) => new Date(info.getValue()).toLocaleDateString("de-DE"),
  }),
];

/** Sortierbare Tabellen-Ansicht aller Projekte -- neuer Standard-Einstieg
 * in OfficeProjektePage.tsx (siehe dort): zeigt alle Projekte statt nur
 * das eine per Dropdown ausgewaehlte, Zeilenklick oeffnet das rechte
 * Detail-Panel (ProjektDetailPanel.tsx). Gleiches Muster wie
 * VorgaengeTabelle.tsx/AuftraegeTabelle.tsx. */
export function ProjekteTabelle({
  projekte,
  onZeileKlick,
}: {
  projekte: Projekt[];
  onZeileKlick: (projekt: Projekt) => void;
}) {
  const [sorting, setSorting] = useState<SortingState>([]);

  const table = useReactTable({
    data: projekte,
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
              onClick={() => onZeileKlick(row.original)}
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
