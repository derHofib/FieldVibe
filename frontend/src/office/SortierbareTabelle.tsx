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
      <table className="w-full border-collapse text-fliess">
        <thead className="border-b border-sepstrong text-sekundaer text-label2">
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
                  className={`px-3 py-2 text-meta font-medium tracking-wide uppercase ${spalte.align === "rechts" ? "text-right" : "text-left"}`}
                >
                  {spalte.sortWert ? (
                    <button
                      onClick={() => umschalten(spalte.key)}
                      className={`inline-flex items-center gap-1 rounded-sm tracking-wide uppercase hover:text-label ${
                        aktiv ? "text-label" : ""
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
                        <ChevronsUpDown size={12} strokeWidth={2} className="text-label3" />
                      )}
                    </button>
                  ) : (
                    spalte.label
                  )}
                </th>
              );
            })}
            {zeilenAktionen && (
              <th scope="col" className="w-10 px-2 py-2">
                <span className="sr-only">Aktionen</span>
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {sortiert.map((zeile) => {
            const key = zeilenKey(zeile);
            const ausgewaehlt = key === gewaehlt;
            return (
              <tr
                key={key}
                onClick={() => onWaehlen(zeile)}
                aria-selected={ausgewaehlt}
                className={`cursor-pointer border-b border-sep last:border-b-0 ${
                  ausgewaehlt ? "bg-tintbg" : "hover:bg-fill"
                }`}
              >
                {spalten.map((spalte) => (
                  <td
                    key={spalte.key}
                    className={`px-3 py-2 text-label ${
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
                        className="rounded-sm text-left font-semibold text-label"
                      >
                        {spalte.render(zeile)}
                      </button>
                    ) : (
                      spalte.render(zeile)
                    )}
                  </td>
                ))}
                {zeilenAktionen && (
                  <td className="px-2 py-1 text-right" onClick={(e) => e.stopPropagation()}>
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
