import { useNavigate } from "react-router-dom";

import { GesperrtZustand } from "./EmptyState";

/** Einheitliche Sperrseite des Routen-Guards (components/RouteGuard.tsx).
 * `alsH1`: im Office traegt sonst jede Seite ihren eigenen SeitenKopf-h1, hier
 * gibt es keinen; die Feld-App hat den h1 schon im FeldLayout. */
export function KeinZugriff({ startRoute, alsH1 = false }: { startRoute: string; alsH1?: boolean }) {
  const navigate = useNavigate();
  // react-router legt in history.state.idx die Position im App-Verlauf ab;
  // bei einem Deep-Link ohne Vorgaenger gaebe navigate(-1) sonst eine leere Seite.
  const hatVerlauf = ((window.history.state as { idx?: number } | null)?.idx ?? 0) > 0;

  return (
    <GesperrtZustand
      alsH1={alsH1}
      text="Für diesen Bereich fehlt dir das Recht. Wende dich an deinen Administrator, wenn du ihn brauchst."
      action={
        <>
          <button
            type="button"
            className="btn-touch btn-ap px-4"
            onClick={() => (hatVerlauf ? navigate(-1) : navigate(startRoute, { replace: true }))}
          >
            Zurück
          </button>
          <button
            type="button"
            className="btn-touch btn-ap btn-ap-primary px-4"
            onClick={() => navigate(startRoute, { replace: true })}
          >
            Zur Startseite
          </button>
        </>
      }
    />
  );
}
