import { useQuery } from "@tanstack/react-query";

import { auditLogApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";

export function AuditLogPage() {
  const { isImpersonating } = useAuth();
  const { data: entries, isLoading } = useQuery({
    queryKey: ["audit-log"],
    queryFn: auditLogApi.list,
    // super_admin-only: see MandantenPage for why this is disabled here too.
    enabled: !isImpersonating,
  });

  return (
    <div>
      <h2 className="mb-4 text-lg font-bold text-slate-800 dark:text-slate-100">Audit-Log</h2>
      {isLoading ? (
        <p className="text-slate-500 dark:text-slate-400">Lädt…</p>
      ) : (
        <table className="w-full overflow-hidden rounded-lg bg-white text-left shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
          <thead className="bg-slate-50 text-sm text-slate-600 dark:bg-slate-800/60 dark:text-slate-400">
            <tr>
              <th className="px-4 py-3">Zeitpunkt</th>
              <th className="px-4 py-3">Aktion</th>
              <th className="px-4 py-3">Entität</th>
              <th className="px-4 py-3">Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
            {entries?.map((e) => (
              <tr key={e.id}>
                <td className="whitespace-nowrap px-4 py-3 text-slate-500 dark:text-slate-400">
                  {new Date(e.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}
                </td>
                <td className="px-4 py-3 font-medium text-slate-800 dark:text-slate-100">{e.aktion}</td>
                <td className="px-4 py-3 text-slate-500 dark:text-slate-400">
                  {e.entity_type ? `${e.entity_type} · ${e.entity_id?.slice(0, 8)}` : "–"}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-slate-500 dark:text-slate-400">
                  {JSON.stringify(e.payload)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
