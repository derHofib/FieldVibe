import { useNavigate } from "react-router-dom";

import { useAuth } from "../../context/AuthContext";
import { istModulAktiv } from "../../utils/module";
import { ROLE_LABEL } from "../UsersPage";

export function ProfilePage() {
  const { currentUser, logout } = useAuth();
  const navigate = useNavigate();
  // loesch_operativ hat ueberall dieselben Rechte wie mandant_admin (siehe
  // app/api/deps.py:require_roles()) -- die Verwaltungs-Links hier folgen
  // demselben Muster, sonst waeren die Backend-Rechte ohne Navigation dazu.
  const istMandantAdminAehnlich =
    currentUser?.role === "mandant_admin" || currentUser?.role === "loesch_operativ";

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

      {istMandantAdminAehnlich && istModulAktiv(currentUser, "statistik") && (
        <button
          onClick={() => navigate("/insights")}
          className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-slate-700 shadow-sm dark:bg-slate-900 dark:text-slate-300 dark:shadow-none dark:ring-1 dark:ring-slate-800"
        >
          📊 Insights ansehen
        </button>
      )}

      {istMandantAdminAehnlich && (
        <button
          onClick={() => navigate("/integrationen")}
          className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-slate-700 shadow-sm dark:bg-slate-900 dark:text-slate-300 dark:shadow-none dark:ring-1 dark:ring-slate-800"
        >
          🔌 Integrationen verwalten
        </button>
      )}

      {istMandantAdminAehnlich && (
        <button
          onClick={() => navigate("/accounts")}
          className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-slate-700 shadow-sm dark:bg-slate-900 dark:text-slate-300 dark:shadow-none dark:ring-1 dark:ring-slate-800"
        >
          👥 Nutzer verwalten
        </button>
      )}

      {istMandantAdminAehnlich && (
        <button
          onClick={() => navigate("/anlagen-felder")}
          className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-slate-700 shadow-sm dark:bg-slate-900 dark:text-slate-300 dark:shadow-none dark:ring-1 dark:ring-slate-800"
        >
          🏷️ Anlagen-Zusatzfelder
        </button>
      )}

      {(istMandantAdminAehnlich || currentUser?.role === "disponent") && (
        <button
          onClick={() => navigate("/techniker-zuweisungen")}
          className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-slate-700 shadow-sm dark:bg-slate-900 dark:text-slate-300 dark:shadow-none dark:ring-1 dark:ring-slate-800"
        >
          🧑‍🔧 Techniker-Zuweisungen
        </button>
      )}

      {(istMandantAdminAehnlich || currentUser?.role === "disponent") &&
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
