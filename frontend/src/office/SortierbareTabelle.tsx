import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { TabellenRahmen } from "./OfficeUi";

export interface Spalte<T> {
  key: string;
  label: string;
  render: (zeile: T) => ReactNode;
  /** Ohne sortWert ist die Spalte nicht sortierbar. */
  sortWert?: (zeile: T) => string | number;
  align?: "links" | "rechts";
  /** Die Hauptspalte bekommt den fokussierbaren Auswahl-Button. */
  haupt?: boolean;
}

const collator = new Intl.Collator("de", { numeric: true, sensitivity: "base" });

function vergleiche(a: string | number, b: string | number): number {
  if (typeof a === "number" && typeof b === "number") return a - b;
  return collator.compare(String(a), String(b));
}

/** Tabelle mit sortierbaren Spalten und wählbarer Zeile (Listenseite mit
 * Detailpanel). Sortierung liegt im Client: die Listen sind komplett geladen
 * (Kunden/Material kommen ohne Paginierung aus der API). */
export function SortierbareTabelle<T>({
  zeilen,
  spalten,
  zeilenKey,
  gewaehlt,
  onWaehlen,
  startSortierung,
  zeilenAktionen,
}: {
  zeilen: T[];
  spalten: Spalte<T>[];
  zeilenKey: (zeile: T) => string;
  gewaehlt?: string | null;
  onWaehlen: (zeile: T) => void;
  startSortierung?: { key: string; absteigend?: boolean };
  /** Zusätzliche letzte Spalte (z. B. AktionsMenue). */
  zeilenAktionen?: (zeile: T) => ReactNode;
}) {
  const [sortierung, setSortierung] = useState(startSortierung ?? null);

  const sortiert = useMemo(() => {
    const spalte = spalten.find((s) => s.key === sortierung?.key);
    if (!spalte?.sortWert) return zeilen;
    const wert = spalte.sortWert;
    const richtung = sortierung?.absteigend ? -1 : 1;
    return [...zeilen].sort((a, b) => richtung * vergleiche(wert(a), wert(b)));
  }, [zeilen, spalten, sortierung]);

  const umschalten = (key: string) =>
    setSortierung((alt) =>
      alt?.key === key ? { key, absteigend: !alt.absteigend } : { key, absteigend: false },
    );

  return (
    <TabellenRahmen>
      <table className="w-full text-left text-[13px]">
        <thead className="bg-slate-50 text-xs text-slate-500 dark:bg-stone-800/60 dark:text-stone-400">
          <tr>
            {spalten.map((spalte) => {
              const aktiv = sortierung?.key === spalte.key;
              return (
                <th
                  key={spalte.key}
                  scope="col"
                  aria-sort={
                    aktiv ? (sortierung?.absteigend ? "descending" : "ascending") : undefined
                  }
                  className={`px-3 py-2.5 font-semibold ${spalte.align === "rechts" ? "text-right" : ""}`}
                >
                  {spalte.sortWert ? (
                    <button
                      onClick={() => umschalten(spalte.key)}
                      className={`inline-flex items-center gap-1 rounded-sm hover:text-slate-800 dark:hover:text-stone-100 ${
                        aktiv ? "text-slate-800 dark:text-stone-100" : ""
                      }`}
                    >
                      {spalte.label}
                      {aktiv ? (
                        sortierung?.absteigend ? (
                          <ArrowDown size={12} strokeWidth={2.5} />
                        ) : (
                          <ArrowUp size={12} strokeWidth={2.5} />
                        )
                      ) : (
                        <ChevronsUpDown size={12} strokeWidth={2} className="opacity-50" />
                      )}
                    </button>
                  ) : (
                    spalte.label
                  )}
                </th>
              );
            })}
            {zeilenAktionen && (
              <th scope="col" className="w-10 px-2 py-2.5">
                <span className="sr-only">Aktionen</span>
              </th>
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-stone-800">
          {sortiert.map((zeile) => {
            const key = zeilenKey(zeile);
            const ausgewaehlt = key === gewaehlt;
            return (
              <tr
                key={key}
                onClick={() => onWaehlen(zeile)}
                aria-selected={ausgewaehlt}
                className={`cursor-pointer ${
                  ausgewaehlt
                    ? "bg-blue-50/70 dark:bg-blue-500/10"
                    : "hover:bg-slate-50 dark:hover:bg-stone-800/50"
                }`}
              >
                {spalten.map((spalte) => (
                  <td
                    key={spalte.key}
                    className={`px-3 py-2.5 text-slate-600 dark:text-stone-300 ${
                      spalte.align === "rechts" ? "text-right tabular-nums" : ""
                    }`}
                  >
                    {spalte.haupt ? (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onWaehlen(zeile);
                        }}
                        aria-current={ausgewaehlt ? "true" : undefined}
                        className="rounded-sm text-left font-semibold text-slate-800 dark:text-stone-100"
                      >
                        {spalte.render(zeile)}
                      </button>
                    ) : (
                      spalte.render(zeile)
                    )}
                  </td>
                ))}
                {zeilenAktionen && (
                  <td className="px-2 py-1.5 text-right" onClick={(e) => e.stopPropagation()}>
                    {zeilenAktionen(zeile)}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </TabellenRahmen>
  );
}
