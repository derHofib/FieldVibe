import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { mandantenApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../api/client";
import type { MandantStatus } from "../types";

const STATUS_LABEL: Record<MandantStatus, string> = {
  aktiv: "Aktiv",
  pausiert: "Pausiert",
  gekuendigt: "Gekündigt",
};

const STATUS_BADGE: Record<MandantStatus, string> = {
  aktiv: "bg-green-100 text-green-800",
  pausiert: "bg-amber-100 text-amber-800",
  gekuendigt: "bg-red-100 text-red-800",
};

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
      <section>
        <h2 className="mb-4 text-lg font-bold text-slate-800">Neuen Mandanten anlegen</h2>
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Name</label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="btn-touch rounded-md border border-slate-300 px-3 py-2"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">
              Slug (Subdomain)
            </label>
            <input
              required
              pattern="[a-z0-9][a-z0-9-]*[a-z0-9]"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              className="btn-touch rounded-md border border-slate-300 px-3 py-2"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Branche</label>
            <input
              value={branche}
              onChange={(e) => setBranche(e.target.value)}
              className="btn-touch rounded-md border border-slate-300 px-3 py-2"
            />
          </div>
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="btn-touch rounded-md bg-slate-900 px-4 py-2 font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            Anlegen
          </button>
        </form>
        {formError && <p className="mt-2 text-sm text-red-700">{formError}</p>}
      </section>

      <section>
        <h2 className="mb-4 text-lg font-bold text-slate-800">Mandanten</h2>
        {isLoading ? (
          <p>Lädt…</p>
        ) : (
          <table className="w-full overflow-hidden rounded-lg bg-white text-left shadow-sm">
            <thead className="bg-slate-50 text-sm text-slate-600">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Slug</th>
                <th className="px-4 py-3">Branche</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Aktion</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-sm">
              {mandanten?.map((m) => (
                <tr key={m.id}>
                  <td className="px-4 py-3 font-medium">{m.name}</td>
                  <td className="px-4 py-3 text-slate-500">{m.slug}</td>
                  <td className="px-4 py-3 text-slate-500">{m.branche ?? "–"}</td>
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
