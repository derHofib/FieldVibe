import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { Link } from "react-router-dom";

import { auditLogApi, mandantenApi, systemApi, usersApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";

function SystemStatus() {
  const { data: health, isLoading, isError } = useQuery({
    queryKey: ["system-health"],
    queryFn: systemApi.healthz,
    // /healthz braucht kein Login, aber ein haengender Backend-Container
    // soll hier trotzdem sichtbar werden statt endlos zu laden.
    retry: 1,
  });

  if (isLoading) return null;

  const ok = !isError && health?.status === "ok";
  return (
    <div
      className={`flex items-center justify-between rounded-lg px-4 py-3 text-sm ${
        ok
          ? "bg-green-50 text-green-800 dark:bg-green-500/10 dark:text-green-300"
          : "bg-red-50 text-red-800 dark:bg-red-500/10 dark:text-red-300"
      }`}
    >
      <span className="flex items-center gap-1.5 font-medium">
        {ok ? (
          <>
            <CheckCircle2 size={15} strokeWidth={2} /> Backend erreichbar
          </>
        ) : (
          <>
            <AlertTriangle size={15} strokeWidth={2} /> Backend nicht erreichbar
          </>
        )}
      </span>
      <span className="text-xs">
        {health?.scheduler_letzter_lauf
          ? `Letzter Scheduler-Lauf: ${new Date(health.scheduler_letzter_lauf).toLocaleString("de-DE")}`
          : "Scheduler noch ohne erfolgreichen Lauf"}
      </span>
    </div>
  );
}

function StatKachel({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </div>
      <div className="mt-1 text-2xl font-bold text-slate-900 dark:text-slate-100">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{sub}</div>}
    </div>
  );
}

export function UebersichtPage() {
  // mandanten/audit-log sind super_admin-only: siehe MandantenPage fuer den
  // Impersonation-Race, den dieses Disablen abfaengt.
  const { isImpersonating } = useAuth();
  const { data: mandanten } = useQuery({
    queryKey: ["mandanten"],
    queryFn: mandantenApi.list,
    enabled: !isImpersonating,
  });
  const { data: users } = useQuery({ queryKey: ["users"], queryFn: usersApi.list });
  const { data: letzteEintraege } = useQuery({
    queryKey: ["audit-log", { limit: 5 }],
    queryFn: () => auditLogApi.list({ limit: 5 }),
    enabled: !isImpersonating,
  });

  const mandantenAktiv = mandanten?.filter((m) => m.status === "aktiv").length ?? 0;
  const accountsAktiv = users?.filter((u) => u.aktiv).length ?? 0;

  return (
    <div className="space-y-8">
      <SystemStatus />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatKachel
          label="Mandanten"
          value={mandanten ? String(mandantenAktiv) : "…"}
          sub={mandanten ? `${mandantenAktiv} aktiv von ${mandanten.length} gesamt` : undefined}
        />
        <StatKachel
          label="Accounts"
          value={users ? String(accountsAktiv) : "…"}
          sub={users ? `${accountsAktiv} aktiv von ${users.length} gesamt` : undefined}
        />
        <StatKachel
          label="Audit-Log"
          value={letzteEintraege ? String(letzteEintraege.length) : "…"}
          sub="letzte Einträge (siehe unten)"
        />
      </div>

      <section>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100">Letzte Aktivität</h2>
          <Link
            to="/audit-log"
            className="text-sm font-medium text-blue-700 hover:underline dark:text-blue-400"
          >
            Gesamtes Audit-Log →
          </Link>
        </div>
        {letzteEintraege && letzteEintraege.length > 0 ? (
          <ul className="divide-y divide-slate-100 rounded-lg bg-white text-sm shadow-sm dark:divide-slate-800 dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
            {letzteEintraege.map((e) => (
              <li key={e.id} className="flex items-center justify-between px-4 py-3">
                <span className="font-medium text-slate-800 dark:text-slate-100">{e.aktion}</span>
                <span className="text-slate-500 dark:text-slate-400">
                  {new Date(e.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">Noch keine Einträge.</p>
        )}
      </section>
    </div>
  );
}
