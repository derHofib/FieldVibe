import type { ZeitplanAbhaengigkeit } from "../../../types";
import { ART_LABEL, pfeilZeigtNachLinks, verbindungsAnker, verbindungsPfad, type BalkenRechteck } from "./zeitplanLogik";

/** Verbindungslinien (je Art Ende -> Anfang, Anfang -> Anfang, Ende -> Ende) mit Pfeilspitze am Ziel. Die breite,
 * unsichtbare Linie darunter macht die duenne Linie treffbar; Hover und
 * Auswahl heben sie in --tint hervor. */
export function GanttVerbindungen({
  abhaengigkeiten,
  geometrie,
  ausgewaehltId,
  kritischModus,
  onKlick,
}: {
  abhaengigkeiten: ZeitplanAbhaengigkeit[];
  geometrie: Map<string, BalkenRechteck>;
  ausgewaehltId: string | null;
  kritischModus: boolean;
  /** Position in Viewport-Koordinaten (Klickpunkt bzw. Mitte bei Tastatur). */
  onKlick: (dep: ZeitplanAbhaengigkeit, position: { x: number; y: number }) => void;
}) {
  return (
    <g>
      {abhaengigkeiten.map((d) => {
        const v = geometrie.get(d.vorgaenger_id);
        const n = geometrie.get(d.nachfolger_id);
        if (!v || !n) return null;
        const art = d.art ?? "ende_anfang";
        const { von, nach } = verbindungsAnker(art, v, n);
        const pfad = verbindungsPfad(von, nach, art);
        const dx = pfeilZeigtNachLinks(art) ? 6 : -6;
        const gewaehlt = d.id === ausgewaehltId;
        const kritischHervor = kritischModus && d.kritisch;
        const farbe = gewaehlt ? "stroke-tint" : kritischHervor ? "stroke-st-fehlt-dot" : "stroke-label2 group-hover:stroke-tint";
        const pfeilFarbe = gewaehlt ? "fill-tint" : kritischHervor ? "fill-st-fehlt-dot" : "fill-label2 group-hover:fill-tint";
        return (
          <g
            key={d.id}
            className="group cursor-pointer"
            opacity={kritischModus && !d.kritisch ? 0.45 : 1}
            role="button"
            tabIndex={0}
            aria-label={`Verbindung bearbeiten, ${ART_LABEL[art]}, Versatz ${d.versatz_tage} Tage`}
            onClick={(e) => onKlick(d, { x: e.clientX, y: e.clientY })}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                const r = e.currentTarget.getBoundingClientRect();
                onKlick(d, { x: r.left + r.width / 2, y: r.top + r.height / 2 });
              }
            }}
          >
            <path d={pfad} fill="none" stroke="transparent" strokeWidth={10} />
            <path d={pfad} fill="none" strokeWidth={gewaehlt || kritischHervor ? 2 : 1.5} className={farbe} />
            <polygon
              points={`${nach.x},${nach.y} ${nach.x + dx},${nach.y - 3.5} ${nach.x + dx},${nach.y + 3.5}`}
              className={pfeilFarbe}
            />
          </g>
        );
      })}
    </g>
  );
}
