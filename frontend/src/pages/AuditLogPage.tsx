import { useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { auditLogApi, mandantenApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { aktivitaetLabel } from "../utils/anzeigeNamen";
import { auditLabel } from "../utils/auditLabel";
import { FehlerZustand } from "../components/FehlerZustand";
import { SkeletonList } from "../components/Skeleton";

export function AuditLogPage() {
  const uid = useId();
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
  const { data: entries, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
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
      <h2 className="mb-4 text-lg font-bold text-label">Audit-Log</h2>

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor={`${uid}-0`} className="mb-1 block text-sm font-medium text-label">Mandant</label>
          <select id={`${uid}-0`}
            value={mandantId}
            onChange={(e) => setMandantId(e.target.value)}
            className="btn-touch border border-sep bg-transparent px-3 py-2 text-label"
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
          <label htmlFor={`${uid}-1`} className="mb-1 block text-sm font-medium text-label">Aktion</label>
          <input id={`${uid}-1`}
            value={aktion}
            onChange={(e) => setAktion(e.target.value)}
            placeholder="z.B. login_als_mandant"
            className="btn-touch border border-sep bg-transparent px-3 py-2 text-label"
          />
        </div>
        <div>
          <label htmlFor={`${uid}-2`} className="mb-1 block text-sm font-medium text-label">Von</label>
          <input id={`${uid}-2`}
            type="date"
            value={von}
            onChange={(e) => setVon(e.target.value)}
            className="btn-touch border border-sep bg-transparent px-3 py-2 text-label"
          />
        </div>
        <div>
          <label htmlFor={`${uid}-3`} className="mb-1 block text-sm font-medium text-label">Bis</label>
          <input id={`${uid}-3`}
            type="date"
            value={bis}
            onChange={(e) => setBis(e.target.value)}
            className="btn-touch border border-sep bg-transparent px-3 py-2 text-label"
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
            className="btn-touch rounded-md px-3 py-2 text-sm font-medium text-label2 hover:bg-fill"
          >
            Filter zurücksetzen
          </button>
        )}
      </div>

      {isLoading ? (
        <SkeletonList count={4} />
      ) : ladeFehler && !entries ? (
        <FehlerZustand fehler={ladeFehler} was="Das Protokoll" onErneut={() => void neuLaden()} />
      ) : (
        <table className="w-full overflow-hidden rounded-lg bg-card text-left shadow-xs dark:shadow-none dark:ring-1 ">
          <thead className="bg-fill text-sm text-label ">
            <tr>
              <th className="px-4 py-3">Zeitpunkt</th>
              <th className="px-4 py-3">Mandant</th>
              <th className="px-4 py-3">Aktion</th>
              <th className="px-4 py-3">Entität</th>
              <th className="px-4 py-3">Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-sep text-sm ">
            {entries?.map((e) => (
              <tr key={e.id}>
                <td className="whitespace-nowrap px-4 py-3 text-label2">
                  {new Date(e.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}
                </td>
                <td className="px-4 py-3 text-label2">
                  {e.mandant_id ? mandantNameById.get(e.mandant_id) ?? "–" : "–"}
                </td>
                <td className="px-4 py-3 font-medium text-label">{aktivitaetLabel(e.aktion)}</td>
                <td className="px-4 py-3 text-label2">
                  {e.entity_type ? `${auditLabel(e.entity_type)} · ${e.entity_id?.slice(0, 8)}` : "–"}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-label2">
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
