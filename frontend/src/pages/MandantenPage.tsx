import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { mandantenApi, systemApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../api/client";
import type { Mandant, MandantModul, MandantStatus } from "../types";

const STATUS_LABEL: Record<MandantStatus, string> = {
  aktiv: "Aktiv",
  pausiert: "Pausiert",
  gekuendigt: "Gekündigt",
};

const STATUS_BADGE: Record<MandantStatus, string> = {
  aktiv: "bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300",
  pausiert: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  gekuendigt: "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300",
};

const MODUL_LABEL: Record<MandantModul, string> = {
  kundenverwaltung: "Kundenverwaltung (Ansprechpartner, Adresse, Löschen)",
  dispo: "Dispo/Termine",
  material: "Materialwirtschaft (Lager/Bestand)",
  pruefzyklen: "Prüfzyklen & Prüfmittel",
  abrechnung: "Mängel/Angebote/Rechnungen",
  kundenportal: "Kundenportal",
  dauerauftrag: "Dauer-Aufträge",
  statistik: "Statistik/Insights + Export",
  fahrzeuge: "Fahrzeug-Zuweisung & Inventur",
  highlights: "Highlights (Story-Feature)",
};
const ALLE_MODULE = Object.keys(MODUL_LABEL) as MandantModul[];

function ModulListe({ mandant }: { mandant: Mandant }) {
  const queryClient = useQueryClient();
  const [offen, setOffen] = useState(false);

  const speichernMutation = useMutation({
    mutationFn: (deaktivierteModule: MandantModul[]) =>
      mandantenApi.update(mandant.id, { deaktivierte_module: deaktivierteModule }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mandanten"] }),
  });

  function toggle(modul: MandantModul) {
    const aktuell = mandant.deaktivierte_module;
    const naechste = aktuell.includes(modul)
      ? aktuell.filter((m) => m !== modul)
      : [...aktuell, modul];
    speichernMutation.mutate(naechste);
  }

  return (
    <div>
      <button onClick={() => setOffen((v) => !v)} className="btn-touch text-xs font-medium text-blue-700 underline dark:text-blue-400">
        {offen ? "Module ausblenden" : "Module verwalten"}
      </button>
      {offen && (
        <div className="mt-2 space-y-1.5 rounded-md bg-slate-50 p-3 dark:bg-slate-800">
          <p className="text-xs text-slate-400 dark:text-slate-500">
            "Aufträge" (Anlegen, Chat/Foto/Status, Zeit start/stopp) ist immer aktiv und hier nicht
            abwählbar.
          </p>
          {ALLE_MODULE.map((modul) => (
            <label key={modul} className="btn-touch flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
              <input
                type="checkbox"
                checked={!mandant.deaktivierte_module.includes(modul)}
                disabled={speichernMutation.isPending}
                onChange={() => toggle(modul)}
              />
              {MODUL_LABEL[modul]}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

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
      <span className="font-medium">
        {ok ? "✅ Backend erreichbar" : "⚠️ Backend nicht erreichbar"}
      </span>
      <span className="text-xs">
        {health?.scheduler_letzter_lauf
          ? `Letzter Scheduler-Lauf: ${new Date(health.scheduler_letzter_lauf).toLocaleString("de-DE")}`
          : "Scheduler noch ohne erfolgreichen Lauf"}
      </span>
    </div>
  );
}

export function MandantenPage() {
  const queryClient = useQueryClient();
  const { startImpersonation, isImpersonating } = useAuth();
  const [formError, setFormError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [branche, setBranche] = useState("elektro");

  const { data: mandanten, isLoading } = useQuery({
    queryKey: ["mandanten"],
    queryFn: mandantenApi.list,
    // super_admin-only endpoint: an impersonation token is scoped as
    // mandant_admin and would 403 here, and this page unmounts anyway once
    // impersonation starts (see App.tsx) -- disabling defensively closes
    // the race between that route swap and this query's own refetch.
    enabled: !isImpersonating,
  });

  const createMutation = useMutation({
    mutationFn: mandantenApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mandanten"] });
      setName("");
      setSlug("");
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : "Fehler"),
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: MandantStatus }) =>
      mandantenApi.update(id, { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mandanten"] }),
  });

  function handleCreate(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    createMutation.mutate({ name, slug, branche });
  }

  return (
    <div className="space-y-8">
      <SystemStatus />

      <section>
        <h2 className="mb-4 text-lg font-bold text-slate-800 dark:text-slate-100">Neuen Mandanten anlegen</h2>
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Name</label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="btn-touch rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
              Slug (Subdomain)
            </label>
            <input
              required
              pattern="[a-z0-9][a-z0-9-]*[a-z0-9]"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              className="btn-touch rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Branche</label>
            <input
              value={branche}
              onChange={(e) => setBranche(e.target.value)}
              className="btn-touch rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="btn-touch rounded-md bg-slate-900 px-4 py-2 font-medium text-white hover:bg-slate-800 disabled:opacity-50 dark:bg-cyan-600 dark:hover:bg-cyan-500"
          >
            Anlegen
          </button>
        </form>
        {formError && <p className="mt-2 text-sm text-red-700 dark:text-red-400">{formError}</p>}
      </section>

      <section>
        <h2 className="mb-4 text-lg font-bold text-slate-800 dark:text-slate-100">Mandanten</h2>
        {isLoading ? (
          <p className="text-slate-500 dark:text-slate-400">Lädt…</p>
        ) : (
          <table className="w-full overflow-hidden rounded-lg bg-white text-left shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
            <thead className="bg-slate-50 text-sm text-slate-600 dark:bg-slate-800/60 dark:text-slate-400">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Slug</th>
                <th className="px-4 py-3">Branche</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Module</th>
                <th className="px-4 py-3">Aktion</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
              {mandanten?.map((m) => (
                <tr key={m.id}>
                  <td className="px-4 py-3 font-medium text-slate-800 dark:text-slate-100">{m.name}</td>
                  <td className="px-4 py-3 text-slate-500 dark:text-slate-400">{m.slug}</td>
                  <td className="px-4 py-3 text-slate-500 dark:text-slate-400">{m.branche ?? "–"}</td>
                  <td className="px-4 py-3">
                    <select
                      value={m.status}
                      onChange={(e) =>
                        statusMutation.mutate({
                          id: m.id,
                          status: e.target.value as MandantStatus,
                        })
                      }
                      className={`btn-touch rounded-full border-0 px-3 py-1 text-xs font-semibold ${STATUS_BADGE[m.status]}`}
                    >
                      {Object.entries(STATUS_LABEL).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-3">
                    <ModulListe mandant={m} />
                  </td>
                  <td className="px-4 py-3">
                    <button
                      disabled={isImpersonating || m.status !== "aktiv"}
                      onClick={() => startImpersonation(m.id)}
                      className="btn-touch rounded-md bg-amber-500 px-3 py-2 text-xs font-semibold text-amber-950 hover:bg-amber-400 disabled:opacity-40"
                      title="Support-Zugriff: Login als Mandant"
                    >
                      Login als Mandant
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
