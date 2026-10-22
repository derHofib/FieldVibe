import { useNavigate } from "react-router-dom";
import type { MaengelDaten } from "./useVorgangMaengel";
import type { PositionenDaten } from "./useVorgangPositionen";
import type { TermineDaten } from "./useVorgangTermine";
import type { VerlaufDaten } from "./useVorgangVerlauf";
import type { ZeitDaten } from "./useVorgangZeit";

interface KennzahlenZeileProps {
  ansicht: "voll" | "zeit" | "verlauf" | "positionen";
  id: string | undefined;
  layout: "kompakt" | "dicht";
  maengelDaten: MaengelDaten;
  positionenDaten: PositionenDaten;
  termineDaten: TermineDaten;
  verlaufDaten: VerlaufDaten;
  zeitDaten: ZeitDaten;
}

/** Kennzahlen je Abschnitt auf der kompakten Hauptseite. */
export function KennzahlenZeile({
  ansicht, id, layout, maengelDaten, positionenDaten, termineDaten, verlaufDaten, zeitDaten,
}: KennzahlenZeileProps) {
  const { offeneMaengelAnzahl } = maengelDaten;
  const { positionenAnzahl } = positionenDaten;
  const { naechsterTermin } = termineDaten;
  const { verlaufEintraege } = verlaufDaten;
  const { gesamtKm, gesamtStunden } = zeitDaten;
  const navigate = useNavigate();
  return (
    <>
      {/* Kennzahlen-Zeile: auf einen Blick, ob in den anderen Abschnitten
       * ueberhaupt etwas wartet, statt jeden einzeln aufklappen zu muessen
       * -- Zeit/Positionen/Verlauf verlinken zur eigenen Unterseite,
       * Termine/Maengel springen zum Abschnitt weiter unten. Nur im
       * "kompakt"-Layout auf der Hauptseite (die eigenen Unterseiten
       * brauchen sie nicht, "dicht" hat dafuer die echten Tabs). */}
      {layout !== "dicht" && ansicht === "voll" && (
        <div className="scrollbar-none -mx-3 flex gap-2 overflow-x-auto px-3 pb-1">
          <button
            type="button"
            onClick={() => navigate(`/vorgaenge/${id}/zeit`)}
            className="btn-touch flex shrink-0 flex-col items-start gap-0.5 border border-sep px-3 py-2 text-left hover:bg-fill"
          >
            <span className="text-[11px] text-label2">Zeit</span>
            <span className="text-sm font-semibold text-label">
              {gesamtStunden} Std.{gesamtKm > 0 && ` · ${gesamtKm.toFixed(1)} km`}
            </span>
          </button>
          <a
            href="#abschnitt-termine"
            className="btn-touch flex shrink-0 flex-col items-start gap-0.5 border border-sep px-3 py-2 text-left hover:bg-fill"
          >
            <span className="text-[11px] text-label2">Nächster Termin</span>
            <span className="text-sm font-semibold text-label">
              {naechsterTermin
                ? new Date(naechsterTermin.start_at).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })
                : "—"}
            </span>
          </a>
          <a
            href="#abschnitt-maengel"
            className="btn-touch flex shrink-0 flex-col items-start gap-0.5 border border-sep px-3 py-2 text-left hover:bg-fill"
          >
            <span className="text-[11px] text-label2">Mängel</span>
            <span className={`text-sm font-semibold ${offeneMaengelAnzahl > 0 ? "text-st-fehlt" : "text-label"}`}>
              {offeneMaengelAnzahl} offen
            </span>
          </a>
          <button
            type="button"
            onClick={() => navigate(`/vorgaenge/${id}/positionen`)}
            className="btn-touch flex shrink-0 flex-col items-start gap-0.5 border border-sep px-3 py-2 text-left hover:bg-fill"
          >
            <span className="text-[11px] text-label2">Positionen</span>
            <span className="text-sm font-semibold text-label">{positionenAnzahl}</span>
          </button>
          <button
            type="button"
            onClick={() => navigate(`/vorgaenge/${id}/verlauf`)}
            className="btn-touch flex shrink-0 flex-col items-start gap-0.5 border border-sep px-3 py-2 text-left hover:bg-fill"
          >
            <span className="text-[11px] text-label2">Verlauf</span>
            <span className="text-sm font-semibold text-label">{verlaufEintraege.length} Einträge</span>
          </button>
        </div>
      )}
    </>
  );
}
