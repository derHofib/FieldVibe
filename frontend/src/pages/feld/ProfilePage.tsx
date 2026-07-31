import { useNavigate } from "react-router-dom";

import { useAuth } from "../../context/AuthContext";
import { istModulAktiv } from "../../utils/module";

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
      <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-200 text-lg font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            {currentUser?.name?.slice(0, 1)}
          </div>
          <div>
            <div className="font-semibold text-slate-800 dark:text-slate-100">{currentUser?.name}</div>
            <div className="text-sm text-slate-500 dark:text-slate-400">
              {currentUser && ROLE_LABEL[currentUser.role]}
            </div>
          </div>
        </div>
        <dl className="mt-4 space-y-1 text-sm">
          <div className="flex justify-between">
            <dt className="text-slate-500 dark:text-slate-400">E-Mail</dt>
            <dd className="text-slate-800 dark:text-slate-100">{currentUser?.email}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500 dark:text-slate-400">Mandant</dt>
            <dd className="text-slate-800 dark:text-slate-100">{currentUser?.mandant_name}</dd>
          </div>
        </dl>
      </div>

      {currentUser?.role === "mandant_admin" && istModulAktiv(currentUser, "statistik") && (
        <button
          onClick={() => navigate("/insights")}
          className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-slate-700 shadow-sm dark:bg-slate-900 dark:text-slate-300 dark:shadow-none dark:ring-1 dark:ring-slate-800"
        >
          📊 Insights ansehen
        </button>
      )}

      {currentUser?.role === "mandant_admin" && (
        <button
          onClick={() => navigate("/integrationen")}
          className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-slate-700 shadow-sm dark:bg-slate-900 dark:text-slate-300 dark:shadow-none dark:ring-1 dark:ring-slate-800"
        >
          🔌 Integrationen verwalten
        </button>
      )}

      {currentUser?.role === "mandant_admin" && (
        <button
          onClick={() => navigate("/accounts")}
          className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-slate-700 shadow-sm dark:bg-slate-900 dark:text-slate-300 dark:shadow-none dark:ring-1 dark:ring-slate-800"
        >
          👥 Nutzer verwalten
        </button>
      )}

      {(currentUser?.role === "mandant_admin" || currentUser?.role === "disponent") && (
        <button
          onClick={() => navigate("/techniker-zuweisungen")}
          className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-slate-700 shadow-sm dark:bg-slate-900 dark:text-slate-300 dark:shadow-none dark:ring-1 dark:ring-slate-800"
        >
          🧑‍🔧 Techniker-Zuweisungen
        </button>
      )}

      {(currentUser?.role === "mandant_admin" || currentUser?.role === "disponent") &&
        istModulAktiv(currentUser, "dauerauftrag") && (
          <button
            onClick={() => navigate("/dauerauftraege")}
            className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-slate-700 shadow-sm dark:bg-slate-900 dark:text-slate-300 dark:shadow-none dark:ring-1 dark:ring-slate-800"
          >
            🔁 Dauer-Aufträge
          </button>
        )}

      {istModulAktiv(currentUser, "statistik") && (
        <button
          onClick={() => navigate("/statistik")}
          className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-slate-700 shadow-sm dark:bg-slate-900 dark:text-slate-300 dark:shadow-none dark:ring-1 dark:ring-slate-800"
        >
          📊 {currentUser?.role === "techniker" ? "Meine Statistik" : "Statistik"}
        </button>
      )}

      <button
        onClick={logout}
        className="btn-touch w-full rounded-md bg-white py-2 font-medium text-slate-600 shadow-sm dark:bg-slate-900 dark:text-slate-300 dark:shadow-none dark:ring-1 dark:ring-slate-800"
      >
        Abmelden
      </button>
    </div>
  );
}
