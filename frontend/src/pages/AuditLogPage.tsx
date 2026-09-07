import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { auditLogApi, mandantenApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";

export function AuditLogPage() {
  const { isImpersonating } = useAuth();
  const [mandantId, setMandantId] = useState("");
  const [aktion, setAktion] = useState("");
  const [von, setVon] = useState("");
  const [bis, setBis] = useState("");

  // Beide Endpoints sind super_admin-only: ein Impersonation-Token ist als
  // mandant_admin gescoped und wuerde hier 403en -- diese Seite unmountet
  // aber ohnehin sofort, sobald die Impersonation startet (siehe App.tsx),
  // das Disablen schliesst nur das Race bis dahin (siehe MandantenPage).
  const { data: mandanten } = useQuery({
    queryKey: ["mandanten"],
    queryFn: mandantenApi.list,
    enabled: !isImpersonating,
  });
  const { data: entries, isLoading } = useQuery({
    queryKey: ["audit-log", { mandantId, aktion, von, bis }],
    queryFn: () =>
      auditLogApi.list({
        mandant_id: mandantId || undefined,
        aktion: aktion || undefined,
        von: von || undefined,
        bis: bis || undefined,
      }),
    enabled: !isImpersonating,
  });

  const mandantNameById = new Map((mandanten ?? []).map((m) => [m.id, m.name]));

  return (
    <div>
      <h2 className="mb-4 text-lg font-bold text-ind-ink">Audit-Log</h2>

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div>
          <label className="mb-1 block text-sm font-medium text-ind-ink-2">Mandant</label>
          <select
            value={mandantId}
            onChange={(e) => setMandantId(e.target.value)}
            className="btn-touch border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
          >
            <option value="">Alle</option>
            {mandanten?.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-ind-ink-2">Aktion</label>
          <input
            value={aktion}
            onChange={(e) => setAktion(e.target.value)}
            placeholder="z.B. login_als_mandant"
            className="btn-touch border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-ind-ink-2">Von</label>
          <input
            type="date"
            value={von}
            onChange={(e) => setVon(e.target.value)}
            className="btn-touch border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-ind-ink-2">Bis</label>
          <input
            type="date"
            value={bis}
            onChange={(e) => setBis(e.target.value)}
            className="btn-touch border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
          />
        </div>
        {(mandantId || aktion || von || bis) && (
          <button
            onClick={() => {
              setMandantId("");
              setAktion("");
              setVon("");
              setBis("");
            }}
            className="btn-touch rounded-md px-3 py-2 text-sm font-medium text-slate-500 hover:bg-slate-100 dark:text-stone-400 dark:hover:bg-stone-800"
          >
            Filter zurücksetzen
          </button>
        )}
      </div>

      {isLoading ? (
        <p className="text-ind-ink-3">Lädt…</p>
      ) : (
        <table className="w-full overflow-hidden rounded-lg bg-white text-left shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
          <thead className="bg-slate-50 text-sm text-slate-600 dark:bg-stone-800/60 dark:text-stone-400">
            <tr>
              <th className="px-4 py-3">Zeitpunkt</th>
              <th className="px-4 py-3">Mandant</th>
              <th className="px-4 py-3">Aktion</th>
              <th className="px-4 py-3">Entität</th>
              <th className="px-4 py-3">Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-sm dark:divide-stone-800">
            {entries?.map((e) => (
              <tr key={e.id}>
                <td className="whitespace-nowrap px-4 py-3 text-ind-ink-3">
                  {new Date(e.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}
                </td>
                <td className="px-4 py-3 text-ind-ink-3">
                  {e.mandant_id ? mandantNameById.get(e.mandant_id) ?? "–" : "–"}
                </td>
                <td className="px-4 py-3 font-medium text-ind-ink">{e.aktion}</td>
                <td className="px-4 py-3 text-ind-ink-3">
                  {e.entity_type ? `${e.entity_type} · ${e.entity_id?.slice(0, 8)}` : "–"}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-ind-ink-3">
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
