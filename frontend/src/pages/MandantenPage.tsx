import { type FormEvent, useId, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { Link } from "react-router-dom";

import { mandantenApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../api/client";
import type { MandantStatus } from "../types";
import { AnlegenPanel } from "../components/AnlegenPanel";
import { EmptyState } from "../components/EmptyState";
import { FehlerZustand } from "../components/FehlerZustand";
import { SkeletonList } from "../components/Skeleton";

const STATUS_LABEL: Record<MandantStatus, string> = {
  aktiv: "Aktiv",
  pausiert: "Pausiert",
  gekuendigt: "Gekündigt",
};

const STATUS_BADGE: Record<MandantStatus, string> = {
  aktiv: "border rounded-[var(--radius-ap-pill)] border-st-erledigt text-st-erledigt ",
  pausiert: "border rounded-[var(--radius-ap-pill)] border-st-arbeit text-st-arbeit ",
  gekuendigt: "border rounded-[var(--radius-ap-pill)] border-st-fehlt text-st-fehlt ",
};

// Entspricht dem Backend-Muster für Mandanten-Slugs (Subdomain).
const SLUG_MUSTER = /^[a-z0-9][a-z0-9-]*[a-z0-9]$/;

export function MandantenPage() {
  const uid = useId();
  const queryClient = useQueryClient();
  const { isImpersonating } = useAuth();
  const [formError, setFormError] = useState<string | null>(null);
  const [zeigeNeu, setZeigeNeu] = useState(false);
  const [feldFehler, setFeldFehler] = useState<{ name?: string; slug?: string }>({});
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [branche, setBranche] = useState("elektro");

  const { data: mandanten, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
    queryKey: ["mandanten"],
    queryFn: mandantenApi.list,
    // super_admin-only endpoint: an impersonation token is scoped as
    // mandant_admin and would 403 here, and this page unmounts anyway once
    // impersonation starts (see App.tsx) -- disabling defensively closes
    // the race between that route swap and this query's own refetch.
    enabled: !isImpersonating,
  });

  const createMutation = useMutation({
    meta: { erfolg: "Angelegt" },
    mutationFn: mandantenApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mandanten"] });
      setName("");
      setSlug("");
      setZeigeNeu(false);
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : "Fehler"),
  });

  function handleCreate(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const f = {
      name: name.trim() ? undefined : "Bitte einen Namen eingeben.",
      slug: SLUG_MUSTER.test(slug)
        ? undefined
        : "Nur Kleinbuchstaben, Ziffern und Bindestriche; Anfang und Ende ohne Bindestrich.",
    };
    setFeldFehler(f);
    if (f.name || f.slug) return;
    createMutation.mutate({ name, slug, branche });
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-bold text-label">Mandanten</h2>
        <button type="button" onClick={() => setZeigeNeu(true)} className="btn-touch btn-ap px-4 py-2 text-sm font-medium">
          + Neuer Mandant
        </button>
      </div>

      <AnlegenPanel offen={zeigeNeu} titel="Neuer Mandant" onClose={() => setZeigeNeu(false)}>
        <form onSubmit={handleCreate} className="space-y-3 p-4" noValidate>
          <div>
            <label htmlFor={`${uid}-0`} className="mb-1 block text-sm font-medium text-label">
              Name <span aria-hidden="true" className="text-st-fehlt">*</span>
            </label>
            <input
              id={`${uid}-0`}
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-invalid={!!feldFehler.name}
              aria-describedby={feldFehler.name ? `${uid}-name-fehler` : undefined}
              className="btn-touch w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-3 py-2 text-label"
            />
            {feldFehler.name && (
              <p id={`${uid}-name-fehler`} role="alert" className="mt-1 text-xs text-st-fehlt">
                {feldFehler.name}
              </p>
            )}
          </div>
          <div>
            <label htmlFor={`${uid}-1`} className="mb-1 block text-sm font-medium text-label">
              Slug (Subdomain) <span aria-hidden="true" className="text-st-fehlt">*</span>
            </label>
            <input
              id={`${uid}-1`}
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              aria-invalid={!!feldFehler.slug}
              aria-describedby={feldFehler.slug ? `${uid}-slug-fehler` : undefined}
              className="btn-touch w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-3 py-2 text-label"
            />
            {feldFehler.slug && (
              <p id={`${uid}-slug-fehler`} role="alert" className="mt-1 text-xs text-st-fehlt">
                {feldFehler.slug}
              </p>
            )}
          </div>
          <div>
            <label htmlFor={`${uid}-2`} className="mb-1 block text-sm font-medium text-label">
              Branche
            </label>
            <input
              id={`${uid}-2`}
              value={branche}
              onChange={(e) => setBranche(e.target.value)}
              className="btn-touch w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-3 py-2 text-label"
            />
          </div>
          {formError && (
            <p role="alert" className="text-sm text-st-fehlt">
              {formError}
            </p>
          )}
          <button type="submit" disabled={createMutation.isPending} className="btn-touch btn-ap-primary w-full">
            Anlegen
          </button>
        </form>
      </AnlegenPanel>

      <section>
        {isLoading ? (
          <SkeletonList count={4} />
        ) : ladeFehler && !mandanten ? (
          <FehlerZustand fehler={ladeFehler} was="Die Mandanten" onErneut={() => void neuLaden()} />
        ) : !mandanten || mandanten.length === 0 ? (
          <EmptyState icon={Building2} text="Noch keine Mandanten angelegt." />
        ) : (
          <table className="w-full overflow-hidden rounded-lg bg-card text-left shadow-xs dark:shadow-none dark:ring-1 ">
            <thead className="bg-fill text-sm text-label ">
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
                      className="btn-touch rounded-md bg-fill px-3 py-2 text-xs font-semibold text-label hover:bg-fill2"
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
