import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { fehlerberichteApi } from "../api/endpoints";
import { FehlerberichtProvider } from "../bugreport/ui";
import { useAuth } from "../context/AuthContext";
import { Sheet } from "./apple/Sheet";

/** Schmale App-Verdrahtung für bugreport/ui: Recht, Router und Sheet kommen von
 * hier, das UI-Modul selbst bleibt frei von App-Imports. */
export function FehlerberichtAnbindung({ children }: { children: ReactNode }) {
  const { currentUser, isAuthenticated, isImpersonating, hatRecht } = useAuth();
  const navigate = useNavigate();
  // Ein echter Super-Admin hat keinen Mandanten, dem ein Bericht zugeordnet werden könnte.
  const ohneMandant = currentUser?.role === "super_admin" && !isImpersonating;
  const darfMelden = isAuthenticated && !ohneMandant && hatRecht("fehlerberichte", "erstellen");

  return (
    <FehlerberichtProvider
      darfMelden={darfMelden}
      apiUpload={fehlerberichteApi.melden}
      Rahmen={Sheet}
      zurueck={() => navigate(-1)}
      appVersion={__APP_VERSION__}
      commitSha={__GIT_COMMIT__}
    >
      {children}
    </FehlerberichtProvider>
  );
}
