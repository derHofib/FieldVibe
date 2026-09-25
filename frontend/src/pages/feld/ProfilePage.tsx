import { LogOut, Repeat, Timer, Wrench } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { IconBadge } from "../../components/IconBadge";
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
      <div className="card-ap p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center border border-sep text-lg font-bold text-label">
            {currentUser?.name?.slice(0, 1)}
          </div>
          <div>
            <div className="font-semibold text-label">{currentUser?.name}</div>
            <div className="text-sm text-label2">
              {currentUser &&
                (currentUser.role === "custom"
                  ? (currentUser.account_typ_name ?? "Account")
                  : ROLE_LABEL[currentUser.role])}
            </div>
          </div>
        </div>
        <dl className="mt-4 space-y-1 text-sm">
          <div className="flex justify-between">
            <dt className="text-label2">E-Mail</dt>
            <dd className="text-label">{currentUser?.email}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-label2">Mandant</dt>
            <dd className="text-label">{currentUser?.mandant_name}</dd>
          </div>
        </dl>
      </div>

      {kannDisponieren && (
        <button
          onClick={() => navigate("/techniker-zuweisungen")}
          className="card-interactive btn-touch flex w-full items-center gap-3 card-ap p-4 text-left"
        >
          <IconBadge icon={Wrench} tone="emerald" size="sm" />
          <span className="font-medium text-label">Techniker-Zuweisungen</span>
        </button>
      )}

      {kannDisponieren && istModulAktiv(currentUser, "dauerauftrag") && (
        <button
          onClick={() => navigate("/dauerauftraege")}
          className="card-interactive btn-touch flex w-full items-center gap-3 card-ap p-4 text-left"
        >
          <IconBadge icon={Repeat} tone="amber" size="sm" />
          <span className="font-medium text-label">Dauer-Aufträge</span>
        </button>
      )}

      {istModulAktiv(currentUser, "zeiterfassung") && (
        <button
          onClick={() => navigate("/statistik")}
          className="card-interactive btn-touch flex w-full items-center gap-3 card-ap p-4 text-left"
        >
          <IconBadge icon={Timer} tone="cyan" size="sm" />
          <span className="font-medium text-label">
            {currentUser?.nur_zugewiesene_kunden ? "Meine Zeiterfassung" : "Zeiterfassung"}
          </span>
        </button>
      )}

      <button
        onClick={logout}
        className="btn-touch btn-ap flex w-full items-center justify-center gap-2"
      >
        <LogOut size={16} strokeWidth={1.5} /> Abmelden
      </button>
    </div>
  );
}
