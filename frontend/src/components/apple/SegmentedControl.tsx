/** Segmented Control (Abschnitt 4.2). Generisch ueber den Wertetyp, damit
 * sowohl "Alle/Einzelauftraege/Aus Projekten" als auch "Liste/Kacheln" o.ae.
 * darueber laufen koennen. */
export function SegmentedControl<T extends string>({
  ariaLabel,
  optionen,
  wert,
  onChange,
  groesse = "desktop",
  volleBreite = false,
}: {
  ariaLabel: string;
  optionen: { wert: T; label: string }[];
  wert: T;
  onChange: (wert: T) => void;
  groesse?: "desktop" | "mobil";
  volleBreite?: boolean;
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={`inline-flex rounded-[9px] bg-fill p-0.5 ${volleBreite ? "w-full" : ""}`}
    >
      {optionen.map((opt) => {
        const aktiv = opt.wert === wert;
        return (
          <button
            key={opt.wert}
            type="button"
            aria-pressed={aktiv}
            onClick={() => onChange(opt.wert)}
            className={`rounded-[7px] px-3 text-[13px] transition-colors ${
              volleBreite ? "flex-1" : ""
            } ${groesse === "mobil" ? "h-7" : "h-6"} ${
              // text-label statt text-label2 im inaktiven Zustand: echte
              // iOS-Segmented-Controls unterscheiden aktiv/inaktiv ueber
              // Gewicht + Pille, nicht ueber Textfarbe -- text-label2 fiel
              // hier zudem unter 4.5:1 Kontrast (axe-core, Phase D).
              aktiv ? "bg-thumb font-semibold text-label shadow-[0_1px_3px_rgba(0,0,0,.14)]" : "font-medium text-label"
            }`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
