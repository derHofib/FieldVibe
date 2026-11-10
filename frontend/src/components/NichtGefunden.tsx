import { Compass } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { IconBadge } from "./IconBadge";

/** Echte 404-Seite fuer unbekannte Pfade innerhalb einer Shell (statt stillem Redirect
 * auf die Startseite, bei dem Tippfehler in Links unbemerkt bleiben). */
export function NichtGefunden({
  startRoute,
  startLabel = "Zur Startseite",
  alsH1 = false,
}: {
  startRoute: string;
  startLabel?: string;
  /** Office/Super-Admin: kein h1 im Layout, die Seite traegt ihn selbst. */
  alsH1?: boolean;
}) {
  const navigate = useNavigate();
  const Titel = alsH1 ? "h1" : "h2";
  // react-router legt in history.state.idx die Position im App-Verlauf ab;
  // bei einem Deep-Link ohne Vorgaenger gaebe navigate(-1) sonst eine leere Seite.
  const hatVerlauf = ((window.history.state as { idx?: number } | null)?.idx ?? 0) > 0;

  return (
    <div className="mx-auto flex max-w-sm flex-col items-center gap-3 py-12 text-center">
      <IconBadge icon={Compass} tone="slate" />
      <Titel className="text-[17px] font-semibold text-label">Seite nicht gefunden</Titel>
      <p className="text-sm text-label2">Diese Adresse gibt es nicht. Vielleicht wurde die Seite verschoben oder der Link ist veraltet.</p>
      <div className="mt-2 flex flex-wrap justify-center gap-2">
        {hatVerlauf && (
          <button type="button" className="btn-touch btn-ap px-4" onClick={() => navigate(-1)}>
            Zurück
          </button>
        )}
        <button
          type="button"
          className="btn-touch btn-ap btn-ap-primary px-4"
          onClick={() => navigate(startRoute, { replace: true })}
        >
          {startLabel}
        </button>
      </div>
    </div>
  );
}
