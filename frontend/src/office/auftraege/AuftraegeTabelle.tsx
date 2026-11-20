import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import type { Auftrag, AuftragStatus } from "../../types";
import { projektLink } from "../../utils/verknuepfung";
import { Karte } from "../OfficeUi";

// "Industry"-Design (siehe docs/DESIGN.md): Rahmen-Tag statt gefuellter
// Pastell-Pille, gleiches Prinzip wie STATUS_BADGE in config/
// vorgangDarstellung.ts -- hier lokal, da Auftrag-Status nirgends sonst
// gebraucht wird.
export const AUFTRAG_STATUS_LABEL: Record<AuftragStatus, string> = {
  offen: "Offen",
  in_arbeit: "In Arbeit",
  abgeschlossen: "Abgeschlossen",
  storniert: "Storniert",
};

const AUFTRAG_STATUS_BADGE: Record<AuftragStatus, string> = {
  offen: "border rounded-[var(--radius-ap-pill)] border-blue-400 text-blue-700 dark:border-blue-600 dark:text-blue-300",
  in_arbeit: "border rounded-[var(--radius-ap-pill)] border-amber-400 text-amber-700 dark:border-amber-600 dark:text-amber-300",
  abgeschlossen: "border rounded-[var(--radius-ap-pill)] border-green-400 text-green-700 dark:border-green-600 dark:text-green-300",
  storniert: "border rounded-[var(--radius-ap-pill)] border-slate-300 text-slate-400 dark:border-stone-700 dark:text-stone-500",
};

const spalten = createColumnHelper<Auftrag>();

// Projektname bevorzugt vom Server (projekt_name), sonst aus der Projektliste der Seite.
function baueSpalten(projektNamen: Map<string, string> | undefined) {
  const projektName = (a: Auftrag) => a.projekt_name ?? (a.projekt_id ? projektNamen?.get(a.projekt_id) : undefined) ?? null;
  return [
    spalten.accessor("titel", { header: "Titel" }),
    spalten.accessor((a) => a.kunde_name ?? "—", {
      id: "kunde",
      header: "Kunde",
      cell: (info) => {
        const a = info.row.original;
        // Leistungsort unter dem Auftraggeber, damit sich viele Aufträge eines Kunden unterscheiden lassen.
        const ort = [a.standort?.bezeichnung, a.einheit].filter(Boolean).join(" · ");
        return (
          <>
            {info.getValue()}
            {ort && <span className="block text-sekundaer text-label2">{ort}</span>}
          </>
        );
      },
    }),
    spalten.accessor((a) => projektName(a) ?? "", {
      id: "projekt",
      header: "Projekt",
      cell: (info) => {
        const a = info.row.original;
        const name = projektName(a);
        if (!name || !a.projekt_id) return "—";
        return (
          // Zeilenklick öffnet das Auftrag-Panel, der Link darf es nicht mitauslösen.
          <Link to={projektLink(a.projekt_id)} onClick={(e) => e.stopPropagation()} className="text-tint-text hover:underline">
            {name}
          </Link>
        );
      },
    }),
    spalten.accessor("status", {
      header: "Status",
      cell: (info) => (
        <span className={`rounded-[var(--radius-ap-pill)] px-2 py-0.5 text-meta font-semibold ${AUFTRAG_STATUS_BADGE[info.getValue()]}`}>
          {AUFTRAG_STATUS_LABEL[info.getValue()]}
        </span>
      ),
    }),
    spalten.accessor("vorgaenge_gesamt", {
      header: "Vorgänge",
      cell: (info) => (info.getValue() ? `${info.row.original.vorgaenge_erledigt ?? 0} / ${info.getValue()}` : "—"),
    }),
    spalten.accessor("created_at", {
      header: "Erstellt am",
      cell: (info) => new Date(info.getValue()).toLocaleDateString("de-DE"),
    }),
  ];
}

/** Sortierbare Tabellen-Ansicht aller Auftraege -- gleiches Muster wie
 * VorgaengeTabelle.tsx. Zeilenklick oeffnet das Detail-Panel (siehe
 * OfficeAuftraegePage.tsx), noch keine serverseitigen Filter -- die Liste
 * ist bei der erwarteten Groessenordnung (deutlich weniger Auftraege als
 * Vorgaenge) bewusst ungefiltert. */
export function AuftraegeTabelle({
  auftraege,
  onZeileKlick,
  hervorgehoben,
  projektNamen,
}: {
  auftraege: Auftrag[];
  onZeileKlick: (auftrag: Auftrag) => void;
  /** Spalten-Ids, auf die gerade eine Filterbedingung wirkt. */
  hervorgehoben?: string[];
  /** Ersatz für projekt_name, solange der Server es nicht liefert. */
  projektNamen?: Map<string, string>;
}) {
  const SPALTEN = useMemo(() => baueSpalten(projektNamen), [projektNamen]);
  const [sorting, setSorting] = useState<SortingState>([]);

  const table = useReactTable({
    data: auftraege,
    columns: SPALTEN,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <Karte className="overflow-x-auto">
      <table className="w-full border-collapse text-fliess">
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id} className="border-b border-sepstrong">
              {headerGroup.headers.map((header) => {
                const sortiert = header.column.getIsSorted();
                return (
                  <th
                    key={header.id}
                    onClick={header.column.getToggleSortingHandler()}
                    className={`cursor-pointer px-3 py-2 text-left text-meta font-medium tracking-wide uppercase select-none hover:text-label ${
                      hervorgehoben?.includes(header.column.id) ? "text-tint-text" : "text-label2"
                    }`}
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
