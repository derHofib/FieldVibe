import { Handle, Position as HandlePosition, type Node, type NodeProps } from "@xyflow/react";
import { Building2, ChevronDown, ChevronRight, MoreHorizontal, UserRound } from "lucide-react";
import { createContext, useContext } from "react";

import type { Position } from "../../types/organigramm";
import { besetzungText, istUnterbesetzt, knotenDarstellung, sollIst } from "./darstellung";
import { STANDARD_MASSE } from "./layout";

export interface DiagrammKontextWert {
  ausgewaehltId: string | null;
  dropZielId: string | null;
  onWaehlen: (id: string) => void;
  // umschalten: Klick auf den "..."-Button schliesst ein bereits offenes Menue derselben Position
  onMenue: (position: Position, anker: { x: number; y: number }, umschalten?: boolean) => void;
  onUmschalten: (id: string) => void;
}

export const DiagrammKontext = createContext<DiagrammKontextWert>({
  ausgewaehltId: null,
  dropZielId: null,
  onWaehlen: () => {},
  onMenue: () => {},
  onUmschalten: () => {},
});

export interface PositionKnotenDaten extends Record<string, unknown> {
  position: Position;
  kinder: number;
  zugeklappt: boolean;
  // Filter aktiv und der Knoten gehoert nur als Pfad zu einem Treffer dazu
  gedimmt: boolean;
}

export type PositionKnotenTyp = Node<PositionKnotenDaten, "position">;

const UNSICHTBAR = { opacity: 0, pointerEvents: "none" as const };

export function PositionKnoten({ data, draggable }: NodeProps<PositionKnotenTyp>) {
  const { ausgewaehltId, dropZielId, onWaehlen, onMenue, onUmschalten } = useContext(DiagrammKontext);
  const { position: p, kinder, zugeklappt, gedimmt } = data;
  const d = knotenDarstellung(p);
  const kontext = d.variante === "kontext";
  const ausgewaehlt = ausgewaehltId === p.id;
  const dropZiel = dropZielId === p.id;

  // Rand/Schatten kommen aus .card-ap ausserhalb jedes Layers: Abweichungen nur per Inline-Style (siehe DESIGN.md).
  const stil: React.CSSProperties = {
    width: STANDARD_MASSE.knotenBreite,
    height: STANDARD_MASSE.knotenHoehe,
    ...(d.gestrichelt ? { borderStyle: "dashed", borderWidth: 1.5, borderColor: "var(--st-arbeit-dot)" } : {}),
    ...(ausgewaehlt ? { boxShadow: "0 0 0 2px var(--tint)" } : {}),
    ...(dropZiel ? { boxShadow: "0 0 0 3px var(--st-erledigt-dot)" } : {}),
  };
  const deckkraft = kontext ? "opacity-50" : d.blass || gedimmt ? "opacity-60" : "";

  return (
    <div className="relative">
      <Handle id="t" type="target" position={HandlePosition.Top} style={UNSICHTBAR} isConnectable={false} />
      <Handle id="l" type="target" position={HandlePosition.Left} style={UNSICHTBAR} isConnectable={false} />
      <Handle id="b" type="source" position={HandlePosition.Bottom} style={UNSICHTBAR} isConnectable={false} />
      <Handle id="r" type="source" position={HandlePosition.Right} style={UNSICHTBAR} isConnectable={false} />

      <div
        className={`card-ap flex flex-col justify-between px-3 py-2 ${deckkraft} ${kontext ? "grayscale" : ""} ${draggable ? "cursor-grab active:cursor-grabbing" : ""}`}
        style={stil}
        data-testid={`org-knoten-${p.id}`}
      >
        <div className="flex items-start gap-1">
          {kontext ? (
            <span className="min-w-0 flex-1 truncate text-[14px] font-semibold text-label2">{p.titel}</span>
          ) : (
            <button
              type="button"
              onClick={() => onWaehlen(p.id)}
              className="nopan min-w-0 flex-1 truncate text-left text-[14px] font-semibold text-label hover:underline focus-visible:outline-2 focus-visible:outline-tint"
              title={p.titel}
            >
              {p.titel}
            </button>
          )}
          {!kontext && (
            <button
              type="button"
              aria-label={`Aktionen für ${p.titel}`}
              aria-haspopup="menu"
              data-menue-ausloeser
              onClick={(e) => {
                const r = e.currentTarget.getBoundingClientRect();
                onMenue(p, { x: r.left, y: r.bottom + 4 }, true);
              }}
              className="nodrag nopan -mt-0.5 -mr-1 shrink-0 rounded-full p-1 text-label2 hover:bg-fill hover:text-label"
            >
              <MoreHorizontal size={16} strokeWidth={2} aria-hidden="true" />
            </button>
          )}
        </div>

        {kontext ? (
          <span className="text-[11px] text-label3">Pfad zur Wurzel (ohne Details)</span>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-1">
              {p.account_typ && (
                <span className="max-w-[120px] truncate rounded-full bg-fill px-2 py-0.5 text-[11px] font-medium text-label">
                  {p.account_typ.name}
                </span>
              )}
              {d.stab && (
                <span className="rounded-full bg-tintbg px-2 py-0.5 text-[11px] font-semibold text-tint-text">Stab</span>
              )}
              {p.status === "geplant" && (
                <span className="rounded-full bg-st-geplant-bg px-2 py-0.5 text-[11px] font-semibold text-st-geplant">
                  Platzhalter
                </span>
              )}
            </div>
            <p className="flex items-center gap-1 truncate text-[11px] text-label2" title={p.org_einheit?.name}>
              <Building2 size={11} strokeWidth={2} className="shrink-0" aria-hidden="true" />
              <span className="truncate">{p.org_einheit?.name ?? "Keine Einheit"}</span>
            </p>
            <div className="flex items-center gap-1 text-[12px]">
              <UserRound size={12} strokeWidth={2} className="shrink-0 text-label2" aria-hidden="true" />
              <span
                className={`min-w-0 flex-1 truncate ${p.status === "vakant" ? "font-semibold text-st-arbeit" : "text-label"}`}
                title={besetzungText(p)}
              >
                {besetzungText(p)}
              </span>
              <span
                className={`shrink-0 tabular-nums ${istUnterbesetzt(p) ? "font-semibold text-st-arbeit" : "text-label2"}`}
                title="Ist/Soll-Besetzung"
              >
                {sollIst(p)}
              </span>
            </div>
          </>
        )}
      </div>

      {kinder > 0 && (
        <button
          type="button"
          onClick={() => onUmschalten(p.id)}
          aria-expanded={!zugeklappt}
          aria-label={`${zugeklappt ? "Aufklappen" : "Zuklappen"}: ${p.titel} (${kinder} direkte Unterposition${kinder === 1 ? "" : "en"})`}
          className="nodrag nopan absolute -bottom-3 left-1/2 z-10 flex h-6 -translate-x-1/2 items-center gap-0.5 rounded-full border-[0.5px] border-sepstrong bg-card px-1.5 text-[11px] font-medium tabular-nums text-label shadow-sm hover:bg-fill"
        >
          {zugeklappt ? <ChevronRight size={12} strokeWidth={2.5} aria-hidden="true" /> : <ChevronDown size={12} strokeWidth={2.5} aria-hidden="true" />}
          {kinder}
        </button>
      )}
    </div>
  );
}
