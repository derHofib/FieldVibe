import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { useAuth } from "./context/AuthContext";
import { AuditLogPage } from "./pages/AuditLogPage";
import { LoginPage } from "./pages/LoginPage";
import { MandantenPage } from "./pages/MandantenPage";
import { NotAdminPage } from "./pages/NotAdminPage";
import { UsersPage } from "./pages/UsersPage";

export function App() {
  const { currentUser, isAuthenticated, isImpersonating, isLoading } = useAuth();

  if (isLoading) return <div className="p-6">Lädt…</div>;

  // A super_admin impersonating a mandant temporarily carries role
  // "mandant_admin" (that's what makes RLS scope the session correctly),
  // so the admin shell must stay keyed off the real actor, not the
  // effective role -- otherwise the impersonation banner itself, which
  // lives inside <Layout>, would disappear the moment impersonation starts.
  const showAdminShell =
    currentUser?.role === "super_admin" || !!currentUser?.impersonated_by;

  return (
    <Routes>
      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />}
      />

      {!isAuthenticated && <Route path="*" element={<Navigate to="/login" replace />} />}

      {isAuthenticated && !showAdminShell && <Route path="*" element={<NotAdminPage />} />}

      {isAuthenticated && showAdminShell && isImpersonating && (
        // While impersonating, the active token is scoped as mandant_admin:
        // /api/admin/mandanten and /api/admin/audit-log are super_admin-only
        // and would 403. Only the Accounts view (RLS-scoped to the
        // impersonated mandant) is reachable until impersonation ends.
        <Route element={<Layout />}>
          <Route path="/accounts" element={<UsersPage />} />
          <Route path="*" element={<Navigate to="/accounts" replace />} />
        </Route>
      )}

      {isAuthenticated && showAdminShell && !isImpersonating && (
        <Route element={<Layout />}>
          <Route path="/mandanten" element={<MandantenPage />} />
          <Route path="/accounts" element={<UsersPage />} />
          <Route path="/audit-log" element={<AuditLogPage />} />
          <Route path="*" element={<Navigate to="/mandanten" replace />} />
        </Route>
      )}
    </Routes>
  );
}
