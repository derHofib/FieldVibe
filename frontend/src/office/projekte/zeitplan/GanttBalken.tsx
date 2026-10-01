import type { PointerEvent as ReactPointerEvent, KeyboardEvent as ReactKeyboardEvent } from "react";

import type { ZeitplanElement } from "../../../types";
import { formatBereich, formatKurz, formatTag, type BalkenRechteck, type Zeitraum, type ZiehArt } from "./zeitplanLogik";

const TYP_LABEL = { phase: "Phase", schritt: "Schritt", meilenstein: "Meilenstein" } as const;

export function balkenBeschreibung(e: ZeitplanElement, z: Zeitraum): string {
  const bereich = e.typ === "meilenstein" ? formatKurz(z.start) : formatBereich(formatTag(z.start), formatTag(z.ende));
  return `${TYP_LABEL[e.typ]} ${e.titel}, ${bereich}${e.erledigt ? ", erledigt" : ""}`;
}

/** Ein Balken (Schritt), Sammelbalken (Phase) oder eine Raute (Meilenstein)
 * in der Zeitleiste. Ziehen/Resize/Verbinden laufen ueber Pointer-Events,
 * die der Tab auf window verfolgt (siehe ZeitplanTab.tsx); die Tastatur
 * nutzt dieselbe PATCH-Logik. */
export function GanttBalken({
  element,
  zeitraum,
  rechteck,
  aktiv,
  verbindenAktiv,
  istZiel,
  onZiehStart,
  onVerbindenStart,
  onTaste,
}: {
  element: ZeitplanElement;
  zeitraum: Zeitraum;
  rechteck: BalkenRechteck;
  aktiv: boolean;
  verbindenAktiv: boolean;
  istZiel: boolean;
  onZiehStart: (e: ReactPointerEvent, art: ZiehArt) => void;
  onVerbindenStart: (e: ReactPointerEvent) => void;
  onTaste: (e: ReactKeyboardEvent) => void;
}) {
  const { x, y, w, h, cy, rechts } = rechteck;
  const istPhase = element.typ === "phase";
  const istMeilenstein = element.typ === "meilenstein";
  const fortschritt = Math.min(100, Math.max(0, element.fortschritt));
  const clipId = `gantt-clip-${element.id}`;

  // Titel im Balken, wenn er (grob geschaetzt, 6.3 px je Zeichen bei 11 px) hineinpasst.
  const titelBreite = element.titel.length * 6.3 + 14;
  const imBalken = element.typ === "schritt" && w >= titelBreite;
  const titelDaneben = !imBalken;
  const labelX = rechts + (istMeilenstein || istPhase ? 14 : 16);

  return (
    <g
      className="group outline-none"
      role="button"
      tabIndex={0}
      aria-label={balkenBeschreibung(element, zeitraum)}
      aria-description="Pfeiltasten links und rechts verschieben um einen Tag, mit Umschalt um eine Woche, mit Umschalt und Alt wird die Dauer geändert."
      onKeyDown={onTaste}
      opacity={element.erledigt ? 0.55 : 1}
      style={{ touchAction: "none" }}
    >
      {/* Fokusring: stroke statt outline, SVG-Elemente bekommen keinen CSS-Outline-Ring. */}
      <rect
        x={x - 3}
        y={y - 3}
        width={w + 6}
        height={h + 6}
        rx={istMeilenstein ? 4 : 9}
        className="fill-none stroke-tint opacity-0 group-focus-visible:opacity-100"
        strokeWidth={2}
        pointerEvents="none"
      />

      {istPhase ? (
        <>
          <rect
            x={x}
            y={cy - 6}
            width={w}
            height={7}
            rx={2}
            className="cursor-grab fill-tone-indigo"
            onPointerDown={(e) => onZiehStart(e, "verschieben")}
          />
          <polygon points={`${x},${cy + 1} ${x + 8},${cy + 1} ${x},${cy + 8}`} className="fill-tone-indigo" pointerEvents="none" />
          <polygon points={`${x + w},${cy + 1} ${x + w - 8},${cy + 1} ${x + w},${cy + 8}`} className="fill-tone-indigo" pointerEvents="none" />
        </>
      ) : istMeilenstein ? (
        <polygon
          points={`${x + w / 2},${y} ${x + w},${cy} ${x + w / 2},${y + h} ${x},${cy}`}
          className={`cursor-grab ${istZiel ? "fill-tone-amber stroke-tint" : "fill-tone-amber"}`}
          strokeWidth={istZiel ? 2 : 0}
          onPointerDown={(e) => onZiehStart(e, "verschieben")}
        />
      ) : (
        <>
          <clipPath id={clipId}>
            <rect x={x} y={y} width={w} height={h} rx={6} />
          </clipPath>
          <rect
            x={x}
            y={y}
            width={w}
            height={h}
            rx={6}
            className={`cursor-grab fill-tint-solid ${istZiel ? "stroke-label" : ""}`}
            strokeWidth={istZiel ? 2 : 0}
            onPointerDown={(e) => onZiehStart(e, "verschieben")}
          />
          {fortschritt > 0 && (
            <rect x={x} y={y} width={(w * fortschritt) / 100} height={h} fill="#000" fillOpacity={0.28} clipPath={`url(#${clipId})`} pointerEvents="none" />
          )}
          {imBalken && (
            <text x={x + 8} y={cy + 4} fontSize={11} fontWeight={600} className="fill-white" pointerEvents="none">
              {element.erledigt ? "✓ " : ""}
              {element.titel}
            </text>
          )}
          {/* Greifer am rechten Rand: Dauer aendern (min. 1 Tag). */}
          <rect
            x={x + w - 6}
            y={y}
            width={6}
            height={h}
            className="cursor-ew-resize fill-transparent"
            onPointerDown={(e) => onZiehStart(e, "dauer")}
          />
        </>
      )}

      {titelDaneben && (
        <text
          x={labelX}
          y={cy + 4}
          fontSize={11}
          fontWeight={istPhase ? 700 : 500}
          className="fill-label"
          pointerEvents="none"
          textDecoration={element.erledigt ? "line-through" : undefined}
        >
          {element.erledigt ? "✓ " : ""}
          {element.titel}
        </text>
      )}

      {!istPhase && (
        <circle
          cx={rechts + 5}
          cy={cy}
          r={5}
          strokeWidth={2}
          className={`cursor-crosshair fill-card stroke-tint ${
            verbindenAktiv || aktiv ? "opacity-100" : "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"
          }`}
          onPointerDown={onVerbindenStart}
        >
          <title>Zum Verbinden auf einen anderen Schritt oder Meilenstein ziehen</title>
        </circle>
      )}
    </g>
  );
}
