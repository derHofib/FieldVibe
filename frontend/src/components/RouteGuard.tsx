import { Outlet, useLocation } from "react-router-dom";

import { routeErlaubt } from "../config/routenRechte";
import { useAuth } from "../context/AuthContext";
import { KeinZugriff } from "./KeinZugriff";
import { SkeletonList } from "./Skeleton";

/** Layout-Route: prueft den aktuellen Pfad gegen config/routenRechte.ts und zeigt
 * statt eines stillen Redirects "Kein Zugriff". Solange der Nutzer laedt, wird
 * nichts entschieden -- hatRecht() liefert dann false und wuerde sonst jede Seite sperren. */
export function RouteGuard({ oberflaeche }: { oberflaeche: "office" | "feld" }) {
  const { currentUser, hatRecht, isLoading } = useAuth();
  const { pathname } = useLocation();

  if (isLoading || !currentUser) return <SkeletonList className="py-4" />;

  if (!routeErlaubt(pathname, { currentUser, hatRecht, oberflaeche })) {
    const startRoute =
      currentUser.role === "loesch_ansicht" ? "/papierkorb" : oberflaeche === "office" ? "/vorgaenge" : "/feed";
    return <KeinZugriff startRoute={startRoute} alsH1={oberflaeche === "office"} />;
  }
  return <Outlet />;
}
