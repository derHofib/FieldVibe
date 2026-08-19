import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** Kleine, geteilte Bausteine der Desktop-Oberflaeche. Bewusst hier gebuendelt
 * statt in components/: sie setzen eine breite Flaeche voraus und waeren in
 * der Handy-App fehl am Platz. Farben/Toene kommen weiterhin aus dem
 * bestehenden System (siehe docs/DESIGN.md). */

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
      <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">
        {titel}
        {anzahl !== undefined && (
          <span className="ml-2 text-sm font-medium text-slate-400 dark:text-stone-500">
            {anzahl}
          </span>
        )}
      </h1>
      <div className="flex items-center gap-2">{children}</div>
    </div>
  );
}

/** Umschalter fuer gleichrangige Ansichten (Liste/Kanban/Raster,
 * Rechnungen/Angebote, Uebersicht/Editor). */
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
    <div className="flex gap-0.5 rounded-lg border border-slate-200 bg-slate-100 p-0.5 dark:border-stone-700 dark:bg-stone-800">
      {optionen.map((option) => {
        const Icon = option.icon;
        const aktiv = option.wert === wert;
        return (
          <button
            key={option.wert}
            onClick={() => onWechsel(option.wert)}
            aria-pressed={aktiv}
            className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-semibold ${
              aktiv
                ? "bg-white text-slate-800 shadow-xs dark:bg-stone-900 dark:text-stone-100"
                : "text-slate-500 hover:text-slate-700 dark:text-stone-400 dark:hover:text-stone-200"
            }`}
          >
            <Icon size={13} strokeWidth={2} />
            {option.label}
          </button>
        );
      })}
    </div>
  );
}


export function Karte({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-xl border border-slate-200 bg-white dark:border-stone-800 dark:bg-stone-900 ${className}`}
    >
      {children}
    </div>
  );
}

/** Kennzahl-Kachel (Buchhaltung). `ton` faerbt nur den Zusatztext, nicht die
 * Flaeche -- kraeftige Farbflaechen sind laut docs/DESIGN.md bewusst
 * vermieden. */
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
      ? "text-rose-600 font-semibold dark:text-rose-300"
      : ton === "gut"
        ? "text-emerald-600 font-semibold dark:text-emerald-300"
        : "text-slate-400 dark:text-stone-500";

  return (
    <Karte className="p-4">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-slate-500 dark:text-stone-400">
        {Icon && <Icon size={13} strokeWidth={2} />}
        {label}
      </p>
      <p className="text-xl font-bold tabular-nums text-slate-800 dark:text-stone-100">{wert}</p>
      {zusatz && <p className={`mt-1 text-xs ${zusatzKlasse}`}>{zusatz}</p>}
    </Karte>
  );
}

/** Waagerecht scrollbarer Rahmen fuer Tabellen -- ohne ihn schiebt eine breite
 * Tabelle die ganze Seite seitlich weg. */
export function TabellenRahmen({ children }: { children: ReactNode }) {
  return (
    <Karte className="overflow-hidden">
      <div className="overflow-x-auto">{children}</div>
    </Karte>
  );
}
