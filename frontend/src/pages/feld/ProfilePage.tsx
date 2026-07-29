import { useNavigate } from "react-router-dom";

import { useAuth } from "../../context/AuthContext";

const ROLE_LABEL: Record<string, string> = {
  mandant_admin: "Mandanten-Admin",
  disponent: "Disponent",
  techniker: "Techniker",
};

export function ProfilePage() {
  const { currentUser, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="space-y-4">
      <div className="rounded-lg bg-white p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-200 text-lg font-bold text-slate-600">
            {currentUser?.name?.slice(0, 1)}
          </div>
          <div>
            <div className="font-semibold text-slate-800">{currentUser?.name}</div>
            <div className="text-sm text-slate-500">{currentUser && ROLE_LABEL[currentUser.role]}</div>
          </div>
        </div>
        <dl className="mt-4 space-y-1 text-sm">
          <div className="flex justify-between">
            <dt className="text-slate-500">E-Mail</dt>
            <dd className="text-slate-800">{currentUser?.email}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500">Mandant</dt>
            <dd className="text-slate-800">{currentUser?.mandant_name}</dd>
          </div>
        </dl>
      </div>

      {currentUser?.role === "mandant_admin" && (
        <button
          onClick={() => navigate("/insights")}
          className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-slate-700 shadow-sm"
        >
          📊 Insights ansehen
        </button>
      )}

      {currentUser?.role === "mandant_admin" && (
        <button
          onClick={() => navigate("/integrationen")}
          className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-slate-700 shadow-sm"
        >
          🔌 Integrationen verwalten
        </button>
      )}

      {currentUser?.role === "mandant_admin" && (
        <button
          onClick={() => navigate("/accounts")}
          className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-slate-700 shadow-sm"
        >
          👥 Nutzer verwalten
        </button>
      )}

      {(currentUser?.role === "mandant_admin" || currentUser?.role === "disponent") && (
        <button
          onClick={() => navigate("/techniker-zuweisungen")}
          className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-slate-700 shadow-sm"
        >
          🧑‍🔧 Techniker-Zuweisungen
        </button>
      )}

      <button
        onClick={logout}
        className="btn-touch w-full rounded-md bg-white py-2 font-medium text-slate-600 shadow-sm"
      >
        Abmelden
      </button>
    </div>
  );
}
