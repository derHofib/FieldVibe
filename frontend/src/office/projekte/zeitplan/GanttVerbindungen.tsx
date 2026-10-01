import type { ZeitplanAbhaengigkeit } from "../../../types";
import { verbindungsPfad, type BalkenRechteck } from "./zeitplanLogik";

/** Verbindungslinien (Ende -> Anfang) mit Pfeilspitze. Die breite,
 * unsichtbare Linie darunter macht die duenne Linie treffbar; Hover und
 * Auswahl heben sie in --tint hervor. */
export function GanttVerbindungen({
  abhaengigkeiten,
  geometrie,
  ausgewaehltId,
  onKlick,
}: {
  abhaengigkeiten: ZeitplanAbhaengigkeit[];
  geometrie: Map<string, BalkenRechteck>;
  ausgewaehltId: string | null;
  /** Position in Viewport-Koordinaten (Klickpunkt bzw. Mitte bei Tastatur). */
  onKlick: (dep: ZeitplanAbhaengigkeit, position: { x: number; y: number }) => void;
}) {
  return (
    <g>
      {abhaengigkeiten.map((d) => {
        const v = geometrie.get(d.vorgaenger_id);
        const n = geometrie.get(d.nachfolger_id);
        if (!v || !n) return null;
        const von = { x: v.rechts, y: v.cy };
        const nach = { x: n.links, y: n.cy };
        const gewaehlt = d.id === ausgewaehltId;
        const farbe = gewaehlt ? "stroke-tint" : "stroke-label2 group-hover:stroke-tint";
        return (
          <g
            key={d.id}
            className="group cursor-pointer"
            role="button"
            tabIndex={0}
            aria-label={`Verbindung bearbeiten, Versatz ${d.versatz_tage} Tage`}
            onClick={(e) => onKlick(d, { x: e.clientX, y: e.clientY })}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                const r = e.currentTarget.getBoundingClientRect();
                onKlick(d, { x: r.left + r.width / 2, y: r.top + r.height / 2 });
              }
            }}
          >
            <path d={verbindungsPfad(von, nach)} fill="none" stroke="transparent" strokeWidth={10} />
            <path d={verbindungsPfad(von, nach)} fill="none" strokeWidth={gewaehlt ? 2 : 1.5} className={farbe} />
            <polygon
              points={`${nach.x},${nach.y} ${nach.x - 6},${nach.y - 3.5} ${nach.x - 6},${nach.y + 3.5}`}
              className={gewaehlt ? "fill-tint" : "fill-label2 group-hover:fill-tint"}
            />
          </g>
        );
      })}
    </g>
  );
}
