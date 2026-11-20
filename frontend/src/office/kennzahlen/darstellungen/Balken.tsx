import { formatWert } from "../format";
import { AKZENT, alterFarben, sortiert, zeilenFarbe, type DarstellungProps } from "./gemeinsam";

const MAX_ZEILEN = 8;

/** Waagerechte Rangliste: Top 8, der Rest als "Weitere" (nur bei summierbaren Kennzahlen -- eine Durchlaufzeit
 * oder Quote lässt sich nicht aufaddieren, dort bleibt der Rest weg). Eine Datenreihe = eine Farbe. */
export function Balken({ daten, statusFarben, summierbar, titel }: DarstellungProps) {
  const alle = sortiert(daten);
  const farbenAlter = daten.gruppierung === "alter" ? alterFarben(alle) : null;
  const sichtbar = alle.slice(0, MAX_ZEILEN).map((z, i) => ({
    schluessel: z.schluessel,
    label: z.label,
    wert: z.wert,
    farbe: farbenAlter?.[i] ?? zeilenFarbe(z, statusFarben),
  }));
  const rest = alle.slice(MAX_ZEILEN);
  if (rest.length > 0 && summierbar) {
    sichtbar.push({
      schluessel: "__weitere",
      label: `Weitere (${rest.length})`,
      wert: rest.reduce((summe, z) => summe + (z.wert ?? 0), 0),
      farbe: "var(--fill2)",
    });
  }
  const hoechster = Math.max(...sichtbar.map((z) => z.wert ?? 0), 0);

  return (
    <div role="img" aria-label={`Balkendiagramm: ${titel}, ${sichtbar.length} Einträge`} className="flex flex-col gap-2.5">
      {sichtbar.map((zeile) => (
        <div
          key={zeile.schluessel}
          className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)_auto] items-center gap-3"
          title={`${zeile.label}: ${formatWert(zeile.wert, daten.einheit)}`}
        >
          <span className="truncate text-sekundaer text-label">{zeile.label}</span>
          <span className="h-2.5 overflow-hidden rounded-full bg-fill">
            <span
              className="block h-full rounded-full"
              style={{ width: `${hoechster > 0 ? ((zeile.wert ?? 0) / hoechster) * 100 : 0}%`, background: zeile.farbe ?? AKZENT }}
            />
          </span>
          <span className="min-w-8 text-right text-sekundaer font-semibold tabular-nums text-label">
            {formatWert(zeile.wert, daten.einheit)}
          </span>
        </div>
      ))}
    </div>
  );
}
