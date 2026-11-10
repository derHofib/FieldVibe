import { ShieldOff } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { IconBadge } from "./IconBadge";

/** Einheitliche Sperrseite des Routen-Guards (components/RouteGuard.tsx).
 * `alsH1`: im Office traegt sonst jede Seite ihren eigenen SeitenKopf-h1, hier
 * gibt es keinen; die Feld-App hat den h1 schon im FeldLayout. */
export function KeinZugriff({ startRoute, alsH1 = false }: { startRoute: string; alsH1?: boolean }) {
  const navigate = useNavigate();
  const Titel = alsH1 ? "h1" : "h2";
  // react-router legt in history.state.idx die Position im App-Verlauf ab;
  // bei einem Deep-Link ohne Vorgaenger gaebe navigate(-1) sonst eine leere Seite.
  const hatVerlauf = ((window.history.state as { idx?: number } | null)?.idx ?? 0) > 0;

  return (
    <div className="mx-auto flex max-w-sm flex-col items-center gap-3 py-12 text-center">
      <IconBadge icon={ShieldOff} tone="slate" />
      <Titel className="text-[17px] font-semibold text-label">Kein Zugriff</Titel>
      <p className="text-sm text-label2">
        Für diesen Bereich fehlt dir das Recht. Wende dich an deinen Administrator, wenn du ihn brauchst.
      </p>
      <div className="mt-2 flex flex-wrap justify-center gap-2">
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
      </div>
    </div>
  );
}
