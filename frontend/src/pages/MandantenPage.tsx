import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

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
  aktiv: "bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300",
  pausiert: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  gekuendigt: "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300",
};

export function MandantenPage() {
  const queryClient = useQueryClient();
  const { isImpersonating } = useAuth();
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

  function handleCreate(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    createMutation.mutate({ name, slug, branche });
  }

  return (
    <div className="space-y-8">
      <section>
        <h2 className="mb-4 text-lg font-bold text-ind-ink">Neuen Mandanten anlegen</h2>
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-ind-ink-2">Name</label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="btn-touch border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ind-ink-2">
              Slug (Subdomain)
            </label>
            <input
              required
              pattern="[a-z0-9][a-z0-9-]*[a-z0-9]"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              className="btn-touch border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ind-ink-2">Branche</label>
            <input
              value={branche}
              onChange={(e) => setBranche(e.target.value)}
              className="btn-touch border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
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
        <h2 className="mb-4 text-lg font-bold text-ind-ink">Mandanten</h2>
        {isLoading ? (
          <p className="text-ind-ink-3">Lädt…</p>
        ) : (
          <table className="w-full overflow-hidden rounded-lg bg-white text-left shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
            <thead className="bg-slate-50 text-sm text-slate-600 dark:bg-stone-800/60 dark:text-stone-400">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Slug</th>
                <th className="px-4 py-3">Branche</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Aktion</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-sm dark:divide-stone-800">
              {mandanten?.map((m) => (
                <tr key={m.id}>
                  <td className="px-4 py-3 font-medium text-ind-ink">{m.name}</td>
                  <td className="px-4 py-3 text-ind-ink-3">{m.slug}</td>
                  <td className="px-4 py-3 text-ind-ink-3">{m.branche ?? "–"}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-3 py-1 text-xs font-semibold ${STATUS_BADGE[m.status]}`}>
                      {STATUS_LABEL[m.status]}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      to={`/mandanten/${m.id}`}
                      className="btn-touch rounded-md bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-200 dark:bg-stone-800 dark:text-stone-300 dark:hover:bg-stone-700"
                    >
                      Bearbeiten →
                    </Link>
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
