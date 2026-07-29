import { Navigate, Route, Routes } from "react-router-dom";

import { FeldLayout } from "./components/FeldLayout";
import { Layout } from "./components/Layout";
import { useAuth } from "./context/AuthContext";
import { AuditLogPage } from "./pages/AuditLogPage";
import { LoginPage } from "./pages/LoginPage";
import { MandantenPage } from "./pages/MandantenPage";
import { UsersPage } from "./pages/UsersPage";
import { AnlageProfilePage } from "./pages/feld/AnlageProfilePage";
import { FeedPage } from "./pages/feld/FeedPage";
import { KundeProfilePage } from "./pages/feld/KundeProfilePage";
import { NewVorgangPage } from "./pages/feld/NewVorgangPage";
import { NotificationsPage } from "./pages/feld/NotificationsPage";
import { ProfilePage } from "./pages/feld/ProfilePage";
import { SearchPage } from "./pages/feld/SearchPage";
import { VorgangDetailPage } from "./pages/feld/VorgangDetailPage";

export function App() {
  const { currentUser, isAuthenticated, isImpersonating, isLoading } = useAuth();

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
          <Route path="*" element={<Navigate to="/feed" replace />} />
        </Route>
      )}
    </Routes>
  );
}
