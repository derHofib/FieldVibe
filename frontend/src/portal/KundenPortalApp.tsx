import { Navigate, Route, Routes } from "react-router-dom";

import { PortalLayout } from "../components/PortalLayout";
import { KundenAuthProvider, useKundenAuth } from "../context/KundenAuthContext";
import { PortalAnfragenPage } from "../pages/portal/PortalAnfragenPage";
import { PortalAngebotDetailPage } from "../pages/portal/PortalAngebotDetailPage";
import { PortalAngebotePage } from "../pages/portal/PortalAngebotePage";
import { PortalForgotPasswordPage } from "../pages/portal/PortalForgotPasswordPage";
import { PortalLoginPage } from "../pages/portal/PortalLoginPage";
import { PortalRechnungenPage } from "../pages/portal/PortalRechnungenPage";
import { PortalResetPasswordPage } from "../pages/portal/PortalResetPasswordPage";
import { PortalVorgangDetailPage } from "../pages/portal/PortalVorgangDetailPage";
import { PortalVorgaengePage } from "../pages/portal/PortalVorgaengePage";

function KundenPortalRoutes() {
  const { isAuthenticated, isLoading } = useKundenAuth();

  if (isLoading) return <div className="p-6">Lädt…</div>;

  return (
    <Routes>
      <Route
        path="login"
        element={isAuthenticated ? <Navigate to="/portal/vorgaenge" replace /> : <PortalLoginPage />}
      />
      <Route
        path="l/:slug"
        element={isAuthenticated ? <Navigate to="/portal/vorgaenge" replace /> : <PortalLoginPage />}
      />
      <Route path="passwort-vergessen" element={<PortalForgotPasswordPage />} />
      <Route path="passwort-zuruecksetzen" element={<PortalResetPasswordPage />} />

      {!isAuthenticated && <Route path="*" element={<Navigate to="/portal/login" replace />} />}

      {isAuthenticated && (
        <Route element={<PortalLayout />}>
          <Route path="vorgaenge" element={<PortalVorgaengePage />} />
          <Route path="vorgaenge/:id" element={<PortalVorgangDetailPage />} />
          <Route path="anfragen" element={<PortalAnfragenPage />} />
          <Route path="angebote" element={<PortalAngebotePage />} />
          <Route path="angebote/:id" element={<PortalAngebotDetailPage />} />
          <Route path="rechnungen" element={<PortalRechnungenPage />} />
          <Route path="*" element={<Navigate to="/portal/vorgaenge" replace />} />
        </Route>
      )}
    </Routes>
  );
}

// Eigene Provider-Ebene statt Wiederverwendung des staff-seitigen AuthProvider:
// das Kundenportal ist eine strukturell getrennte Identitaet (siehe
// kundenAuthStore.ts) und braucht daher auch einen eigenen React-Context,
// unabhaengig davon, ob gerade ein Mitarbeiter im selben Browser eingeloggt ist.
export function KundenPortalApp() {
  return (
    <KundenAuthProvider>
      <KundenPortalRoutes />
    </KundenAuthProvider>
  );
}
