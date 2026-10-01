import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent, RefObject } from "react";
import { useMemo } from "react";

import type { ZeitplanAbhaengigkeit } from "../../../types";
import { GanttBalken } from "./GanttBalken";
import { GanttVerbindungen } from "./GanttVerbindungen";
import {
  PX_PRO_TAG,
  ZEILEN_HOEHE,
  balkenRechteck,
  istWochenende,
  kopfSegmente,
  tagZuX,
  type BalkenRechteck,
  type Zeile,
  type Zeitbereich,
  type Zeitraum,
  type Zoom,
  type ZiehArt,
} from "./zeitplanLogik";

export const KOPF_ZEILE_HOEHE = 20;
export const KOPF_HOEHE = KOPF_ZEILE_HOEHE * 2;

export interface GanttZiehAnzeige {
  /** Gezogenes Element (Balken/Phase) bzw. Quelle der Verbindung. */
  id: string;
  art: ZiehArt | "verbinden";
  /** Infozeile ueber dem Balken, z. B. "12.10. – 15.10. (4 Tage)". */
  info: string | null;
  /** Nur Verbinden: Zeigerposition in Zeitleisten-Koordinaten und gueltiges Ziel. */
  zeigerX?: number;
  zeigerY?: number;
  zielId?: string | null;
}

/** Zeitleiste: sticky Kopf (Monate/KW/Tage je Zoom) und der SVG-Koerper mit
 * Wochenenden, Heute-Linie, Verbindungen und Balken. Die Zeilen sind exakt
 * so hoch wie in der Liste links (ZEILEN_HOEHE) -- beide Spalten liegen im
 * selben Scroll-Container, daher gemeinsames vertikales Scrollen. */
export function GanttZeitleiste({
  zeilen,
  positionen,
  abhaengigkeiten,
  zoom,
  bereich,
  heute,
  zieh,
  ausgewaehltDepId,
  svgRef,
  onZiehStart,
  onVerbindenStart,
  onTaste,
  onDepKlick,
}: {
  zeilen: Zeile[];
  positionen: Map<string, Zeitraum>;
  abhaengigkeiten: ZeitplanAbhaengigkeit[];
  zoom: Zoom;
  bereich: Zeitbereich;
  heute: number;
  zieh: GanttZiehAnzeige | null;
  ausgewaehltDepId: string | null;
  svgRef: RefObject<SVGSVGElement | null>;
  onZiehStart: (e: ReactPointerEvent, id: string, art: ZiehArt) => void;
  onVerbindenStart: (e: ReactPointerEvent, id: string) => void;
  onTaste: (e: ReactKeyboardEvent, id: string) => void;
  onDepKlick: (dep: ZeitplanAbhaengigkeit, position: { x: number; y: number }) => void;
}) {
  const px = PX_PRO_TAG[zoom];
  const breite = bereich.anzahlTage * px;
  const hoehe = Math.max(zeilen.length * ZEILEN_HOEHE, ZEILEN_HOEHE);
  const kopf = useMemo(() => kopfSegmente(bereich.ursprung, bereich.anzahlTage, zoom), [bereich, zoom]);
  const heuteX = tagZuX(heute, bereich.ursprung, zoom) + px / 2;
  const heuteSichtbar = heute >= bereich.ursprung && heute < bereich.ursprung + bereich.anzahlTage;

  const wochenenden = useMemo(() => {
    if (zoom === "monat") return [];
    const out: number[] = [];
    for (let t = bereich.ursprung; t < bereich.ursprung + bereich.anzahlTage; t++) if (istWochenende(t)) out.push(t);
    return out;
  }, [bereich, zoom]);

  const geometrie = useMemo(() => {
    const m = new Map<string, BalkenRechteck>();
    zeilen.forEach((z, i) => {
      if (z.art !== "element") return;
      const pos = positionen.get(z.element.id);
      if (pos) m.set(z.element.id, balkenRechteck(z.element.typ, pos, i, zoom, bereich.ursprung));
    });
    return m;
  }, [zeilen, positionen, zoom, bereich.ursprung]);

  const ziehGeo = zieh ? geometrie.get(zieh.id) : undefined;
  const zielGeo = zieh?.zielId ? geometrie.get(zieh.zielId) : undefined;
  // Erste Zeile: kein Platz ueber dem Balken (Kopf), Infozeile darunter.
  const infoY = ziehGeo ? (ziehGeo.y - 26 < 2 ? ziehGeo.y + ziehGeo.h + 4 : ziehGeo.y - 26) : 0;
  const infoBreite = zieh?.info ? zieh.info.length * 6.4 + 16 : 0;

  return (
    <div className="relative" style={{ width: breite }}>
      <div className="sticky top-0 z-10 bg-card" style={{ height: KOPF_HOEHE }} aria-hidden="true">
        <div className="relative" style={{ height: KOPF_ZEILE_HOEHE }}>
          {kopf.oben.map((s) => (
            <div
              key={s.von}
              className="absolute top-0.5 truncate rounded-[5px] bg-fill px-2 text-[11px] leading-4 font-semibold text-label"
              style={{ left: (s.von - bereich.ursprung) * px + 1, width: (s.bis - s.von) * px - 2, height: KOPF_ZEILE_HOEHE - 4 }}
            >
              {s.label}
            </div>
          ))}
        </div>
        <div className="relative" style={{ height: KOPF_ZEILE_HOEHE }}>
          {kopf.unten.map((s) => {
            const wochenendTag = zoom === "tag" && istWochenende(s.von);
            const istHeute = zoom === "tag" && s.von === heute;
            return (
              <div
                key={s.von}
                className={`absolute top-0 flex items-center justify-center text-[11px] tabular-nums ${wochenendTag ? "text-label3" : "text-label2"}`}
                style={{ left: (s.von - bereich.ursprung) * px, width: (s.bis - s.von) * px, height: KOPF_ZEILE_HOEHE }}
              >
                {istHeute ? <span className="rounded-full bg-tint-solid px-1.5 leading-[16px] font-semibold text-white">{s.label}</span> : s.label}
              </div>
            );
          })}
        </div>
      </div>

      <svg
        ref={svgRef}
        width={breite}
        height={hoehe}
        className="block select-none"
        role="group"
        aria-label="Zeitleiste"
        style={{ cursor: zieh?.art === "verbinden" ? "crosshair" : undefined }}
      >
        {wochenenden.map((t) => (
          <rect key={t} x={tagZuX(t, bereich.ursprung, zoom)} y={0} width={px} height={hoehe} className="fill-fill" opacity={0.7} />
        ))}

        {zeilen.map((z, i) =>
          z.art === "element" && z.element.typ === "phase" ? (
            <rect key={z.element.id} x={0} y={i * ZEILEN_HOEHE} width={breite} height={ZEILEN_HOEHE} className="fill-fill" />
          ) : null,
        )}

        {heuteSichtbar && <line x1={heuteX} x2={heuteX} y1={0} y2={hoehe} className="stroke-tint" strokeWidth={1.5} pointerEvents="none" />}

        <GanttVerbindungen abhaengigkeiten={abhaengigkeiten} geometrie={geometrie} ausgewaehltId={ausgewaehltDepId} onKlick={onDepKlick} />

        {zeilen.map((z) => {
          if (z.art !== "element") return null;
          const pos = positionen.get(z.element.id);
          const rechteck = geometrie.get(z.element.id);
          if (!pos || !rechteck) return null;
          const verbinden = zieh?.art === "verbinden";
          return (
            <GanttBalken
              key={z.element.id}
              element={z.element}
              zeitraum={pos}
              rechteck={rechteck}
              aktiv={zieh?.id === z.element.id}
              verbindenAktiv={verbinden && zieh?.id === z.element.id}
              istZiel={verbinden && zieh?.zielId === z.element.id}
              onZiehStart={(e, art) => onZiehStart(e, z.element.id, art)}
              onVerbindenStart={(e) => onVerbindenStart(e, z.element.id)}
              onTaste={(e) => onTaste(e, z.element.id)}
            />
          );
        })}

        {zieh?.art === "verbinden" && ziehGeo && zieh.zeigerX !== undefined && zieh.zeigerY !== undefined && (
          <g pointerEvents="none">
            <line
              x1={ziehGeo.rechts}
              y1={ziehGeo.cy}
              x2={zielGeo ? zielGeo.links : zieh.zeigerX}
              y2={zielGeo ? zielGeo.cy : zieh.zeigerY}
              className="stroke-tint"
              strokeWidth={2}
              strokeDasharray={zielGeo ? undefined : "4 3"}
            />
            <circle cx={zielGeo ? zielGeo.links : zieh.zeigerX} cy={zielGeo ? zielGeo.cy : zieh.zeigerY} r={3.5} className="fill-tint" />
          </g>
        )}

        {zieh?.info && ziehGeo && (
          <g pointerEvents="none">
            <rect
              x={Math.max(2, Math.min(ziehGeo.x, breite - infoBreite - 2))}
              y={infoY}
              width={infoBreite}
              height={20}
              rx={6}
              fill="#1c1c1e"
              fillOpacity={0.92}
            />
            <text x={Math.max(2, Math.min(ziehGeo.x, breite - infoBreite - 2)) + 8} y={infoY + 14} fontSize={11} fontWeight={600} fill="#fff">
              {zieh.info}
            </text>
          </g>
        )}
      </svg>
    </div>
  );
}
