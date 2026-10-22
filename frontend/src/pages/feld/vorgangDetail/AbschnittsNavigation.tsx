import { useNavigate } from "react-router-dom";
import { ABSCHNITT_ROUTE, ANCHOR_ABSCHNITTE } from "./konstanten";

interface AbschnittsNavigationProps {
  desktopTab: string;
  id: string | undefined;
  layout: "kompakt" | "dicht";
  setDesktopTab: (ziel: string) => void;
  verlaufSpalteBreit: boolean;
}

/** Tabs (dichtes Layout) bzw. Anker-Navigation (kompakt) zu den Abschnitten. */
export function AbschnittsNavigation({
  desktopTab, id, layout, setDesktopTab, verlaufSpalteBreit,
}: AbschnittsNavigationProps) {
  const navigate = useNavigate();
  return (
    <>
      {/* Kompakt (Feld-App, Office-SchmaleSpalte): Anker-Nav, springt zu den
       * Abschnitten weiter unten -- reine <a href="#..."> statt
       * scrollIntoView, bleibt so auch ohne JS-Handler funktionsfaehig.
       * Dicht (Office-Inspektor-Spalte): echte Tabs, ein Panel sichtbar,
       * role="tablist"/"tab" fuer Screenreader. */}
      {layout === "dicht" ? (
        <div
          role="tablist"
          aria-label="Vorgangs-Abschnitte"
          className="-mx-3 mb-3 flex gap-1 overflow-x-auto border-b border-sep px-3 pb-2 text-sm"
        >
          {ANCHOR_ABSCHNITTE
            // Verlauf ist im "breit"-Layout keine umschaltbare Tab-Seite
            // mehr, sondern eine staendig sichtbare zweite Spalte (siehe
            // verlaufSpalteBreit/dichtLinkeSpalteInhalt) -- als Tab-Pille
            // wuerde er nur verwirren, weil ein Klick nichts umschaltet.
            .filter((a) => !(verlaufSpalteBreit && a.ziel === "abschnitt-verlauf"))
            .map((a) => (
              <button
                key={a.ziel}
                type="button"
                role="tab"
                id={`tab-${a.ziel}`}
                aria-selected={desktopTab === a.ziel}
                aria-controls={a.ziel}
                onClick={() => setDesktopTab(a.ziel)}
                className={`shrink-0 rounded-[7px] px-2.5 py-1 font-medium whitespace-nowrap ${
                  desktopTab === a.ziel ? "bg-fill text-label" : "text-label2 hover:text-label"
                }`}
              >
                {a.label}
              </button>
            ))}
        </div>
      ) : (
        <nav aria-label="Vorgangs-Abschnitte" className="scrollbar-none -mx-3 flex gap-4 overflow-x-auto border-b border-sep px-3 pb-2 text-sm">
          {ANCHOR_ABSCHNITTE.map((a) => {
            // Abschnitte mit eigener Unterseite (siehe ArbeitszeitInhalt/
            // VerlaufInhalt/PositionenInhalt) navigieren dorthin statt zum Anker zu
            // springen -- alle anderen bleiben Sprungmarken auf der
            // durchlaufenden Seite.
            const eigeneSeite = ABSCHNITT_ROUTE[a.ziel];
            return eigeneSeite ? (
              <button
                key={a.ziel}
                type="button"
                onClick={() => navigate(`/vorgaenge/${id}/${eigeneSeite}`)}
                className="shrink-0 whitespace-nowrap font-medium text-label2 hover:text-label"
              >
                {a.label}
              </button>
            ) : (
              <a
                key={a.ziel}
                href={`#${a.ziel}`}
                className="shrink-0 whitespace-nowrap font-medium text-label2 hover:text-label"
              >
                {a.label}
              </a>
            );
          })}
        </nav>
      )}
    </>
  );
}
