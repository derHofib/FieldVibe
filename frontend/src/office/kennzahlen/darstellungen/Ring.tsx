import { formatWert } from "../format";
import { sortiert, statusFarbe, type DarstellungProps } from "./gemeinsam";

const RADIUS = 42;
const UMFANG = 2 * Math.PI * RADIUS;
// Abstufungen der Akzentfarbe statt bunter Palette: eine Reihe = eine Farbe (Konzept, Entscheidung 6).
const DECKKRAFT = [1, 0.75, 0.55, 0.4, 0.28];
const MAX_TEILE = 6;

interface Teil {
  schluessel: string;
  label: string;
  wert: number;
  farbe: string;
  deckkraft: number;
}

/** Donut mit Gesamtwert in der Mitte und Legende. Höchstens sechs Teile; der Rest wird zu einem grauen "Weitere". */
export function Ring({ daten, statusFarben, titel }: DarstellungProps) {
  const mitWert = sortiert(daten).filter((z) => (z.wert ?? 0) > 0);
  const teile: Teil[] = mitWert.slice(0, MAX_TEILE - 1).map((z, i) => ({
    schluessel: z.schluessel,
    label: z.label,
    wert: z.wert ?? 0,
    farbe: (statusFarben ? statusFarbe(z.schluessel) : null) ?? "var(--tint)",
    deckkraft: statusFarben && statusFarbe(z.schluessel) ? 1 : DECKKRAFT[i],
  }));
  const rest = mitWert.slice(MAX_TEILE - 1);
  if (rest.length === 1 && mitWert.length === MAX_TEILE) {
    // Genau ein Teil über der Grenze: lieber zeigen als hinter "Weitere (1)" verstecken.
    const z = rest[0];
    teile.push({ schluessel: z.schluessel, label: z.label, wert: z.wert ?? 0, farbe: "var(--fill2)", deckkraft: 1 });
  } else if (rest.length > 0) {
    teile.push({
      schluessel: "__weitere",
      label: `Weitere (${rest.length})`,
      wert: rest.reduce((summe, z) => summe + (z.wert ?? 0), 0),
      farbe: "var(--fill2)",
      deckkraft: 1,
    });
  }

  const summe = teile.reduce((s, t) => s + t.wert, 0);
  const mitte = daten.gesamt ?? summe;
  // Startposition je Segment vorab berechnen statt beim Rendern zu summieren.
  const segmente = teile.map((teil, i) => ({
    teil,
    laenge: summe > 0 ? (teil.wert / summe) * UMFANG : 0,
    start: summe > 0 ? (teile.slice(0, i).reduce((s, t) => s + t.wert, 0) / summe) * UMFANG : 0,
  }));

  return (
    <div
      role="img"
      aria-label={`Ringdiagramm: ${titel}, ${teile.length} Anteile, Gesamt ${formatWert(mitte, daten.einheit)}`}
      className="flex flex-wrap items-center gap-x-6 gap-y-3"
    >
      <div className="relative h-36 w-36 shrink-0">
        <svg viewBox="0 0 120 120" className="h-full w-full">
          <circle cx="60" cy="60" r={RADIUS} fill="none" stroke="var(--fill)" strokeWidth={14} />
          {segmente.map(({ teil, laenge, start }) => (
            <circle
              key={teil.schluessel}
              cx="60"
              cy="60"
              r={RADIUS}
              fill="none"
              stroke={teil.farbe}
              strokeOpacity={teil.deckkraft}
              strokeWidth={14}
              strokeDasharray={`${laenge} ${UMFANG - laenge}`}
              strokeDashoffset={-start}
              transform="rotate(-90 60 60)"
            >
              <title>{`${teil.label}: ${formatWert(teil.wert, daten.einheit)}`}</title>
            </circle>
          ))}
        </svg>
        <span className="absolute inset-0 flex items-center justify-center px-6 text-center text-fliess font-semibold tabular-nums text-label">
          {formatWert(mitte, daten.einheit)}
        </span>
      </div>

      <ul className="min-w-40 flex-1 space-y-1.5">
        {teile.map((teil) => (
          <li key={teil.schluessel} className="flex items-center gap-2 text-sekundaer">
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ background: teil.farbe, opacity: teil.deckkraft }}
              aria-hidden="true"
            />
            <span className="min-w-0 flex-1 truncate text-label">{teil.label}</span>
            <span className="font-semibold tabular-nums text-label">{formatWert(teil.wert, daten.einheit)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
