import { TriangleAlert } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { useFehlerbericht } from "../bugreport/ui";
import { IconBadge } from "./IconBadge";

function Fallback() {
  const fehlerbericht = useFehlerbericht();

  return (
    <div role="alert" className="mx-auto flex max-w-sm flex-col items-center gap-3 py-12 text-center">
      <IconBadge icon={TriangleAlert} tone="rose" />
      <h2 className="text-[17px] font-semibold text-label">Etwas ist schiefgelaufen</h2>
      <p className="text-sm text-label2">
        Diese Ansicht konnte nicht angezeigt werden. Lade die Seite neu
        {fehlerbericht.verfuegbar ? " und melde den Fehler, falls er wieder auftritt." : "; tritt der Fehler wieder auf, wende dich an deinen Administrator."}
      </p>
      <div className="mt-2 flex flex-wrap justify-center gap-2">
        {fehlerbericht.verfuegbar && (
          <button type="button" className="btn-touch btn-ap px-4" onClick={() => fehlerbericht.aufnehmen()}>
            Fehler melden
          </button>
        )}
        <button
          type="button"
          className="btn-touch btn-ap btn-ap-primary px-4"
          onClick={() => window.location.reload()}
        >
          Neu laden
        </button>
      </div>
    </div>
  );
}

/** Faengt Render-Fehler unterhalb einer Shell (Navigation bleibt bedienbar). Mit
 * `key={pathname}` setzt ein Seitenwechsel den Fehler zurueck. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { fehler: boolean }> {
  state = { fehler: false };

  static getDerivedStateFromError() {
    return { fehler: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Landet ueber die Konsolen-Erfassung (bugreport/konsole.ts) im Fehlerbericht-Kontext.
    console.error("Render-Fehler:", error, info.componentStack);
  }

  render() {
    return this.state.fehler ? <Fallback /> : this.props.children;
  }
}

/** Ersatz fuer <Outlet /> in den Shell-Layouts. */
export function SeitenGrenze() {
  const { pathname } = useLocation();
  return (
    <ErrorBoundary key={pathname}>
      <Outlet />
    </ErrorBoundary>
  );
}
