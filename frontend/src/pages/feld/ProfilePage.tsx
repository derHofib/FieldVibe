import { Repeat, Timer, Wrench } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../../context/AuthContext";
import { istModulAktiv } from "../../utils/module";
import { ROLE_LABEL } from "../UsersPage";

export function ProfilePage() {
  const { currentUser, hatRecht, logout } = useAuth();
  const navigate = useNavigate();

  // "Disponieren" (Techniker einteilen, Dauer-Auftraege verwalten) bleibt
  // hier auf dem Profil, weil es operative Alltagsarbeit ist, nicht
  // Verwaltung -- die Einstellungen-Seite (Zahnrad im Header) buendelt
  // stattdessen Account-Verwaltung/Firmendaten/Integrationen.
  const kannDisponieren = hatRecht("dispo", "bearbeiten");

  return (
    <div className="space-y-4">
      <div className="border border-ind-line bg-ind-bg p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center border border-ind-line text-lg font-bold text-ind-ink-2">
            {currentUser?.name?.slice(0, 1)}
          </div>
          <div>
            <div className="font-semibold text-ind-ink">{currentUser?.name}</div>
            <div className="text-sm text-ind-ink-3">
              {currentUser &&
                (currentUser.role === "custom"
                  ? (currentUser.account_typ_name ?? "Account")
                  : ROLE_LABEL[currentUser.role])}
            </div>
          </div>
        </div>
        <dl className="mt-4 space-y-1 text-sm">
          <div className="flex justify-between">
            <dt className="text-ind-ink-3">E-Mail</dt>
            <dd className="text-ind-ink">{currentUser?.email}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-ind-ink-3">Mandant</dt>
            <dd className="text-ind-ink">{currentUser?.mandant_name}</dd>
          </div>
        </dl>
      </div>

      {kannDisponieren && (
        <button
          onClick={() => navigate("/techniker-zuweisungen")}
          className="card-interactive btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-slate-700 shadow-xs dark:bg-stone-900 dark:text-stone-300 dark:shadow-none dark:ring-1 dark:ring-stone-800"
        >
          <Wrench size={16} strokeWidth={2} className="text-emerald-500" /> Techniker-Zuweisungen
        </button>
      )}

      {kannDisponieren && istModulAktiv(currentUser, "dauerauftrag") && (
        <button
          onClick={() => navigate("/dauerauftraege")}
          className="card-interactive btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-slate-700 shadow-xs dark:bg-stone-900 dark:text-stone-300 dark:shadow-none dark:ring-1 dark:ring-stone-800"
        >
          <Repeat size={16} strokeWidth={2} className="text-amber-500" /> Dauer-Aufträge
        </button>
      )}

      {istModulAktiv(currentUser, "statistik") && (
        <button
          onClick={() => navigate("/statistik")}
          className="card-interactive btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-slate-700 shadow-xs dark:bg-stone-900 dark:text-stone-300 dark:shadow-none dark:ring-1 dark:ring-stone-800"
        >
          <Timer size={16} strokeWidth={2} className="text-cyan-500" />{" "}
          {currentUser?.nur_zugewiesene_kunden ? "Meine Zeiterfassung" : "Zeiterfassung"}
        </button>
      )}

      <button
        onClick={logout}
        className="card-interactive btn-touch w-full rounded-md bg-white py-2 font-medium text-slate-600 shadow-xs dark:bg-stone-900 dark:text-stone-300 dark:shadow-none dark:ring-1 dark:ring-stone-800"
      >
        Abmelden
      </button>
    </div>
  );
}
