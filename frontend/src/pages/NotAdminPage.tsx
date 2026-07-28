import { useAuth } from "../context/AuthContext";

export function NotAdminPage() {
  const { currentUser, logout } = useAuth();

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-100 px-6 text-center">
      <h1 className="text-xl font-bold text-slate-800">Willkommen, {currentUser?.name}</h1>
      <p className="max-w-md text-slate-600">
        Die Feed-/Chat-Oberfläche für {currentUser?.role} folgt in Phase 3 (Social-UX).
        In Phase 1 ist nur das Super-Admin-Dashboard für Mandanten- und
        Account-Verwaltung ausgeliefert.
      </p>
      <button
        onClick={logout}
        className="btn-touch rounded-md bg-slate-900 px-4 py-2 font-medium text-white hover:bg-slate-800"
      >
        Abmelden
      </button>
    </div>
  );
}
