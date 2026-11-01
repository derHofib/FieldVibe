import { Navigate, Route, Routes } from "react-router-dom";

import { PartnerAuthProvider, usePartnerAuth } from "../context/PartnerAuthContext";
import { PartnerAuftragDetailPage } from "./PartnerAuftragDetailPage";
import { PartnerAuftraegePage } from "./PartnerAuftraegePage";
import { PartnerForgotPasswordPage } from "./PartnerForgotPasswordPage";
import { PartnerLoginPage } from "./PartnerLoginPage";
import { PartnerPortalLayout } from "./PartnerPortalLayout";
import { PartnerProfilPage } from "./PartnerProfilPage";
import { PartnerRegistrierenPage } from "./PartnerRegistrierenPage";
import { PartnerResetPasswordPage } from "./PartnerResetPasswordPage";
import { PartnerZeitplanPage } from "./PartnerZeitplanPage";

function PartnerPortalRoutes() {
  const { isAuthenticated, isLoading } = usePartnerAuth();

  if (isLoading) return <div className="p-6">Lädt…</div>;

  return (
    <Routes>
      <Route
        path="login"
        element={isAuthenticated ? <Navigate to="/partnerportal/auftraege" replace /> : <PartnerLoginPage />}
      />
      <Route path="passwort-vergessen" element={<PartnerForgotPasswordPage />} />
      <Route path="passwort-zuruecksetzen" element={<PartnerResetPasswordPage />} />
      <Route path="registrieren" element={<PartnerRegistrierenPage />} />

      {!isAuthenticated && <Route path="*" element={<Navigate to="/partnerportal/login" replace />} />}

      {isAuthenticated && (
        <Route element={<PartnerPortalLayout />}>
          <Route path="auftraege" element={<PartnerAuftraegePage />} />
          <Route path="auftraege/:id" element={<PartnerAuftragDetailPage />} />
          <Route path="zeitplan" element={<PartnerZeitplanPage />} />
          <Route path="profil" element={<PartnerProfilPage />} />
          <Route path="*" element={<Navigate to="/partnerportal/auftraege" replace />} />
        </Route>
      )}
    </Routes>
  );
}

// Eigener Provider (statt AuthProvider): der Partner ist eine getrennte
// Identitaet mit eigenem Token-Typ, siehe api/partnerAuthStore.ts.
export function PartnerPortalApp() {
  return (
    <PartnerAuthProvider>
      <PartnerPortalRoutes />
    </PartnerAuthProvider>
  );
}
