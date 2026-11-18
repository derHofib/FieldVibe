/** Tab-Leiste der Office-Ansicht (role=tablist): Unterstrich in Tint für den
 * aktiven Tab, damit Tabs und Eckdaten-Chips nicht gleich aussehen. Der Zähler
 * erscheint nur, wenn der Tab Inhalt hat; Warnungen (offene Mängel) sind rot. */
export function VorgangTabLeiste({
  abschnitte,
  aktiv,
  onWaehle,
  zaehler,
}: {
  abschnitte: { ziel: string; label: string }[];
  aktiv: string;
  onWaehle: (ziel: string) => void;
  zaehler: Record<string, { text: string; warnung?: boolean } | undefined>;
}) {
  return (
    <div
      role="tablist"
      aria-label="Vorgangs-Abschnitte"
      className="scrollbar-none -mx-3 flex gap-4 overflow-x-auto border-b-[0.5px] border-sep px-3 text-fliess"
    >
      {abschnitte.map((a) => {
        const z = zaehler[a.ziel];
        return (
          <button
            key={a.ziel}
            type="button"
            role="tab"
            id={`tab-${a.ziel}`}
            aria-selected={aktiv === a.ziel}
            aria-controls={a.ziel}
            onClick={() => onWaehle(a.ziel)}
            className={`-mb-px inline-flex shrink-0 items-center gap-1.5 border-b-2 py-2 font-medium whitespace-nowrap ${
              aktiv === a.ziel ? "border-tint text-label" : "border-transparent text-label2 hover:text-label"
            }`}
          >
            {a.label}
            {z && (
              <span
                className={`rounded-[var(--radius-ap-pill)] px-1.5 text-meta font-medium ${
                  z.warnung ? "bg-st-fehlt-bg text-st-fehlt" : "bg-fill text-label2"
                }`}
              >
                <span className="sr-only">: </span>
                {z.text}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
