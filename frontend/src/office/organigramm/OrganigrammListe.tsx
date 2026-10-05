import { ArrowDown, ArrowUp, ArrowUpDown, MoreHorizontal } from "lucide-react";
import { useEffect } from "react";
import { createPortal } from "react-dom";

import { StatusPille } from "../../components/apple/StatusPille";
import { TabellenRahmen } from "../OfficeUi";
import type { Position } from "../../types/organigramm";
import {
  besetzungText,
  istUnterbesetzt,
  POSITION_STATUS_LABEL,
  POSITION_STATUS_TOKEN,
  sollIst,
} from "./darstellung";
import type { ListenZeile, SortRichtung, SortSchluessel } from "./liste";

const SPALTEN: { key: SortSchluessel; label: string }[] = [
  { key: "baum", label: "Position" },
  { key: "typ", label: "Typ" },
  { key: "org_einheit", label: "Organisationseinheit" },
  { key: "account_typ", label: "Account-Typ" },
  { key: "status", label: "Status" },
  { key: "sollist", label: "Ist/Soll" },
];

function typText(p: Position): string {
  return p.typ === "stabsstelle" ? "Stabsstelle" : "Linie";
}

export function OrganigrammListe({
  zeilen,
  sortierung,
  richtung,
  onSortieren,
  onWaehlen,
  onMenue,
  ausgewaehltId,
}: {
  zeilen: ListenZeile[];
  sortierung: SortSchluessel;
  richtung: SortRichtung;
  onSortieren: (schluessel: SortSchluessel) => void;
  onWaehlen: (id: string) => void;
  onMenue: (position: Position, anker: { x: number; y: number }) => void;
  ausgewaehltId: string | null;
}) {
  return (
    <TabellenRahmen>
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Positionen des Organigramms, sortierbar</caption>
        <thead className="bg-fill text-xs text-label2">
          <tr>
            {SPALTEN.map((s) => {
              const aktiv = sortierung === s.key;
              const Icon = !aktiv ? ArrowUpDown : richtung === "auf" ? ArrowUp : ArrowDown;
              return (
                <th
                  key={s.key}
                  scope="col"
                  aria-sort={aktiv ? (richtung === "auf" ? "ascending" : "descending") : "none"}
                  className="px-3 py-2 font-semibold"
                >
                  <button type="button" onClick={() => onSortieren(s.key)} className="inline-flex items-center gap-1 hover:text-label focus-visible:outline-2 focus-visible:outline-tint">
                    {s.label}
                    <Icon size={12} strokeWidth={2} aria-hidden="true" />
                  </button>
                </th>
              );
            })}
            <th scope="col" className="px-3 py-2 font-semibold">
              Besetzung
            </th>
            <th scope="col" className="w-10 px-2 py-2">
              <span className="sr-only">Aktionen</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-sep">
          {zeilen.length === 0 && (
            <tr>
              <td colSpan={SPALTEN.length + 2} className="px-3 py-6 text-center text-label2">
                Keine Positionen gefunden.
              </td>
            </tr>
          )}
          {zeilen.map(({ position: p, tiefe, pfad }) => {
            const kontext = !!p.kontext;
            const eingerueckt = sortierung === "baum";
            return (
              <tr key={p.id} className={`${ausgewaehltId === p.id ? "bg-tintbg" : "hover:bg-fill"} ${kontext ? "text-label3" : ""}`}>
                <th scope="row" className="px-3 py-2 text-left font-normal">
                  <div style={{ paddingLeft: eingerueckt ? tiefe * 18 : 0 }}>
                    {kontext ? (
                      <span>{p.titel}</span>
                    ) : (
                      <button type="button" onClick={() => onWaehlen(p.id)} className="text-left font-medium text-label hover:underline focus-visible:outline-2 focus-visible:outline-tint">
                        {p.titel}
                      </button>
                    )}
                    {!eingerueckt && <span className="block text-xs text-label2">{pfad}</span>}
                  </div>
                </th>
                <td className="px-3 py-2">{kontext ? "" : typText(p)}</td>
                <td className="px-3 py-2">{p.org_einheit?.name ?? ""}</td>
                <td className="px-3 py-2">{p.account_typ?.name ?? ""}</td>
                <td className="px-3 py-2">
                  {p.status ? <StatusPille status={POSITION_STATUS_TOKEN[p.status]} label={POSITION_STATUS_LABEL[p.status]} /> : kontext ? "Pfad" : ""}
                </td>
                <td className={`px-3 py-2 tabular-nums ${istUnterbesetzt(p) ? "font-semibold text-st-arbeit" : ""}`}>{kontext ? "" : sollIst(p)}</td>
                <td className="px-3 py-2">{kontext ? "" : (p.besetzungen ?? []).length > 0 ? besetzungText(p) : ""}</td>
                <td className="px-2 py-2">
                  {!kontext && (
                    <button
                      type="button"
                      aria-label={`Aktionen für ${p.titel}`}
                      aria-haspopup="menu"
                      onClick={(e) => {
                        const r = e.currentTarget.getBoundingClientRect();
                        onMenue(p, { x: r.left - 200, y: r.bottom + 4 });
                      }}
                      className="rounded-full p-1 text-label2 hover:bg-fill2 hover:text-label"
                    >
                      <MoreHorizontal size={16} strokeWidth={2} aria-hidden="true" />
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </TabellenRahmen>
  );
}

/**
 * PDF-Export ueber die Druckansicht des Browsers ("Als PDF speichern"): eine eigene, schlichte Tabelle
 * wird per Portal angehaengt, die App-Oberflaeche (#root) ist nur im Druck ausgeblendet. Funktioniert
 * ohne Backend und ohne zusaetzliche Bibliothek.
 */
export function OrganigrammDruck({ zeilen, onFertig }: { zeilen: ListenZeile[]; onFertig: () => void }) {
  useEffect(() => {
    window.addEventListener("afterprint", onFertig);
    const timer = window.setTimeout(() => window.print(), 80);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("afterprint", onFertig);
    };
  }, [onFertig]);

  const zelle: React.CSSProperties = { border: "1px solid #999", padding: "3px 6px", textAlign: "left", verticalAlign: "top" };
  return createPortal(
    <div id="org-druck" style={{ color: "#000", background: "#fff", fontFamily: "sans-serif", fontSize: 11, padding: 16 }}>
      <style>{`
        #org-druck { display: none; }
        @media print {
          #root { display: none !important; }
          #org-druck { display: block !important; position: absolute; top: 0; left: 0; width: 100%; }
          @page { size: A4 landscape; margin: 12mm; }
        }
      `}</style>
      <h1 style={{ fontSize: 16, margin: "0 0 8px" }}>Organigramm – {new Date().toLocaleDateString("de-DE")}</h1>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr>
            {["Position", "Typ", "Organisationseinheit", "Account-Typ", "Status", "Ist/Soll", "Besetzung"].map((h) => (
              <th key={h} style={{ ...zelle, background: "#eee" }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {zeilen
            .filter((z) => !z.position.kontext)
            .map(({ position: p, tiefe }) => (
              <tr key={p.id}>
                <td style={{ ...zelle, paddingLeft: 6 + tiefe * 14 }}>{p.titel}</td>
                <td style={zelle}>{typText(p)}</td>
                <td style={zelle}>{p.org_einheit?.name ?? ""}</td>
                <td style={zelle}>{p.account_typ?.name ?? ""}</td>
                <td style={zelle}>{p.status ? POSITION_STATUS_LABEL[p.status] : ""}</td>
                <td style={zelle}>{sollIst(p)}</td>
                <td style={zelle}>{(p.besetzungen ?? []).length > 0 ? besetzungText(p) : ""}</td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>,
    document.body,
  );
}
