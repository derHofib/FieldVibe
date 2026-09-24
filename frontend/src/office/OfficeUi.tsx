import type { LucideIcon } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";

/** Kleine, geteilte Bausteine der Desktop-Oberflaeche (Abschnitt 5, Toolbar/
 * Werkzeugleiste). Bewusst hier gebuendelt statt in components/apple/: sie
 * setzen eine breite Flaeche voraus und waeren in der Handy-App fehl am
 * Platz. Farben/Toene kommen ausschliesslich aus den Apple-Design-Token
 * (siehe index.css), keine Tailwind-Palettenfarben mehr. */

export function SeitenKopf({
  titel,
  anzahl,
  children,
}: {
  titel: string;
  anzahl?: number;
  children?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <h1 className="ap-heading text-2xl font-semibold text-label">
        {titel}
        {anzahl !== undefined && <span className="ml-2 text-sm font-medium text-label2">{anzahl}</span>}
      </h1>
      <div className="flex items-center gap-2">{children}</div>
    </div>
  );
}

/** Umschalter fuer gleichrangige Ansichten (Liste/Kanban/Raster,
 * Rechnungen/Angebote, Uebersicht/Editor) -- optisch dasselbe Segmented-
 * Control-Muster wie components/apple/SegmentedControl.tsx, hier aber mit
 * Symbolen statt nur Text (die Ansichten sind sonst schwer auseinander-
 * zuhalten) und deshalb als eigene Variante statt geteilter Komponente. */
export function AnsichtUmschalter<T extends string>({
  wert,
  optionen,
  onWechsel,
}: {
  wert: T;
  optionen: { wert: T; label: string; icon: LucideIcon }[];
  onWechsel: (wert: T) => void;
}) {
  return (
    <div role="group" aria-label="Ansicht" className="inline-flex rounded-[9px] bg-fill p-0.5">
      {optionen.map((option) => {
        const Icon = option.icon;
        const aktiv = option.wert === wert;
        return (
          <button
            key={option.wert}
            type="button"
            onClick={() => onWechsel(option.wert)}
            aria-pressed={aktiv}
            title={option.label}
            className={`flex h-6 items-center gap-1.5 rounded-[7px] px-2.5 text-xs font-semibold transition-colors ${
              aktiv ? "bg-thumb text-label shadow-[0_1px_3px_rgba(0,0,0,.14)]" : "text-label2"
            }`}
          >
            <Icon size={13} strokeWidth={2} aria-hidden="true" />
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export function Karte({
  children,
  className = "",
  style,
}: {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div className={`card-ap ${className}`} style={style}>
      {children}
    </div>
  );
}

/** Kennzahl-Kachel (Buchhaltung). `ton` faerbt nur den Zusatztext, nicht die
 * Flaeche -- kraeftige Farbflaechen sind laut Abschnitt 3 bewusst vermieden,
 * die Status-Token uebernehmen die Rolle der frueheren rose/emerald-Toene. */
export function KennzahlKarte({
  label,
  wert,
  zusatz,
  ton = "neutral",
  icon: Icon,
}: {
  label: string;
  wert: string;
  zusatz?: string;
  ton?: "neutral" | "warnung" | "gut";
  icon?: LucideIcon;
}) {
  const zusatzKlasse =
    ton === "warnung"
      ? "text-st-fehlt font-semibold"
      : ton === "gut"
        ? "text-st-erledigt font-semibold"
        : "text-label2";

  return (
    <Karte className="p-4">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-label2">
        {Icon && <Icon size={13} strokeWidth={2} aria-hidden="true" />}
        {label}
      </p>
      <p className="ap-heading text-2xl font-semibold tabular-nums text-label">{wert}</p>
      {zusatz && <p className={`mt-1 text-xs ${zusatzKlasse}`}>{zusatz}</p>}
    </Karte>
  );
}

/** Waagerecht scrollbarer Rahmen fuer Tabellen -- ohne ihn schiebt eine breite
 * Tabelle die ganze Seite seitlich weg. */
export function TabellenRahmen({ children }: { children: ReactNode }) {
  return (
    <Karte className="overflow-hidden p-0">
      <div className="overflow-x-auto">{children}</div>
    </Karte>
  );
}
