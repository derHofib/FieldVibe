import { Navigate, Route, Routes } from "react-router-dom";

import { FeldLayout } from "./components/FeldLayout";
import { Layout } from "./components/Layout";
import { useAuth } from "./context/AuthContext";
import { AuditLogPage } from "./pages/AuditLogPage";
import { LoginPage } from "./pages/LoginPage";
import { MandantenPage } from "./pages/MandantenPage";
import { UsersPage } from "./pages/UsersPage";
import { AngebotDetailPage } from "./pages/feld/AngebotDetailPage";
import { AnlageProfilePage } from "./pages/feld/AnlageProfilePage";
import { DispoBoardPage } from "./pages/feld/DispoBoardPage";
import { FeedPage } from "./pages/feld/FeedPage";
import { GeschaeftPage } from "./pages/feld/GeschaeftPage";
import { HighlightsPage } from "./pages/feld/HighlightsPage";
import { InsightsPage } from "./pages/feld/InsightsPage";
import { KundeProfilePage } from "./pages/feld/KundeProfilePage";
import { NewVorgangPage } from "./pages/feld/NewVorgangPage";
import { NotificationsPage } from "./pages/feld/NotificationsPage";
import { PruefmittelPage } from "./pages/feld/PruefmittelPage";
import { ProfilePage } from "./pages/feld/ProfilePage";
import { RechnungDetailPage } from "./pages/feld/RechnungDetailPage";
import { SearchPage } from "./pages/feld/SearchPage";
import { VorgangDetailPage } from "./pages/feld/VorgangDetailPage";
import { KundenPortalApp } from "./portal/KundenPortalApp";

export function App() {
  const { currentUser, isAuthenticated, isImpersonating, isLoading } = useAuth();

  // Das Kundenportal ist unabhaengig vom Staff-Login erreichbar -- diese Route
  // muss vor der isAuthenticated-Verzweigung ausgewertet werden, sonst wuerde
  // ein nicht eingeloggter Mitarbeiter-Browser jeden /portal/*-Aufruf auf
  // /login statt /portal/login umleiten.
  if (isLoading) return <div className="p-6">Lädt…</div>;

  // Platform administration (Mandanten/Accounts/Audit-Log, no Social-UX) is
  // only for a genuine, non-impersonating super_admin. The moment that
  // person starts "Login als Mandant", they should see exactly what a real
  // mandant_admin/disponent/techniker in that tenant would see -- the whole
  // point of impersonation as a support tool -- so they get routed into the
  // Feld-App below instead, same as any real tenant user.
  const isPlatformAdmin = currentUser?.role === "super_admin" && !isImpersonating;

  return (
    <Routes>
      <Route path="/portal/*" element={<KundenPortalApp />} />

      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />}
      />

      {!isAuthenticated && <Route path="*" element={<Navigate to="/login" replace />} />}

      {isAuthenticated && isPlatformAdmin && (
        <Route element={<Layout />}>
          <Route path="/mandanten" element={<MandantenPage />} />
          <Route path="/accounts" element={<UsersPage />} />
          <Route path="/audit-log" element={<AuditLogPage />} />
          <Route path="*" element={<Navigate to="/mandanten" replace />} />
        </Route>
      )}

      {isAuthenticated && !isPlatformAdmin && (
        <Route element={<FeldLayout />}>
          <Route path="/feed" element={<FeedPage />} />
          <Route path="/suche" element={<SearchPage />} />
          <Route path="/neu" element={<NewVorgangPage />} />
          <Route path="/benachrichtigungen" element={<NotificationsPage />} />
          <Route path="/profil" element={<ProfilePage />} />
          <Route path="/vorgaenge/:id" element={<VorgangDetailPage />} />
          <Route path="/kunden/:id" element={<KundeProfilePage />} />
          <Route path="/anlagen/:id" element={<AnlageProfilePage />} />
          <Route path="/dispo" element={<DispoBoardPage />} />
          <Route path="/pruefmittel" element={<PruefmittelPage />} />
          <Route path="/geschaeft" element={<GeschaeftPage />} />
          <Route path="/angebote/:id" element={<AngebotDetailPage />} />
          <Route path="/rechnungen/:id" element={<RechnungDetailPage />} />
          <Route path="/highlights" element={<HighlightsPage />} />
          <Route path="/insights" element={<InsightsPage />} />
          <Route path="*" element={<Navigate to="/feed" replace />} />
        </Route>
      )}
    </Routes>
  );
}
