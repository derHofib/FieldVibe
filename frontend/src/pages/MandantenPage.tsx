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
  aktiv: "border border-st-erledigt text-st-erledigt ",
  pausiert: "border border-st-arbeit text-st-arbeit ",
  gekuendigt: "border border-st-fehlt text-st-fehlt ",
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
        <h2 className="mb-4 text-lg font-bold text-label">Neuen Mandanten anlegen</h2>
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-label">Name</label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="btn-touch border border-sep bg-transparent px-3 py-2 text-label"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-label">
              Slug (Subdomain)
            </label>
            <input
              required
              pattern="[a-z0-9][a-z0-9-]*[a-z0-9]"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              className="btn-touch border border-sep bg-transparent px-3 py-2 text-label"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-label">Branche</label>
            <input
              value={branche}
              onChange={(e) => setBranche(e.target.value)}
              className="btn-touch border border-sep bg-transparent px-3 py-2 text-label"
            />
          </div>
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="btn-touch btn-ap-primary"
          >
            Anlegen
          </button>
        </form>
        {formError && <p className="mt-2 text-sm text-st-fehlt ">{formError}</p>}
      </section>

      <section>
        <h2 className="mb-4 text-lg font-bold text-label">Mandanten</h2>
        {isLoading ? (
          <p className="text-label2">Lädt…</p>
        ) : (
          <table className="w-full overflow-hidden rounded-lg bg-white text-left shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 ">
            <thead className="bg-slate-50 text-sm text-label dark:bg-stone-800/60 ">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Slug</th>
                <th className="px-4 py-3">Branche</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Aktion</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-sep text-sm ">
              {mandanten?.map((m) => (
                <tr key={m.id}>
                  <td className="px-4 py-3 font-medium text-label">{m.name}</td>
                  <td className="px-4 py-3 text-label2">{m.slug}</td>
                  <td className="px-4 py-3 text-label2">{m.branche ?? "–"}</td>
                  <td className="px-4 py-3">
                    <span className={`px-3 py-1 text-xs font-semibold ${STATUS_BADGE[m.status]}`}>
                      {STATUS_LABEL[m.status]}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      to={`/mandanten/${m.id}`}
                      className="btn-touch rounded-md bg-slate-100 px-3 py-2 text-xs font-semibold text-label hover:bg-slate-200 dark:bg-stone-800 dark:hover:bg-stone-700"
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
