import { AlertTriangle } from "lucide-react";

import { useAuth } from "../context/AuthContext";

export function ImpersonationBanner() {
  const { isImpersonating, currentUser, endImpersonation } = useAuth();

  if (!isImpersonating) return null;

  return (
    <div className="sticky top-0 z-50 flex items-center justify-between gap-4 bg-amber-500 px-4 py-3 text-sm font-semibold text-amber-950 shadow-xs">
      <span className="flex items-center gap-1.5">
        <AlertTriangle size={16} strokeWidth={2} className="shrink-0" />
        Support-Zugriff aktiv: Du agierst als Mandant „{currentUser?.mandant_name ?? "…"}“.
        Alle Aktionen werden im Audit-Log protokolliert.
      </span>
      <button
        onClick={endImpersonation}
        className="btn-touch rounded-md bg-amber-950 px-4 py-2 text-amber-50 hover:bg-amber-900"
      >
        Beenden
      </button>
    </div>
  );
}
