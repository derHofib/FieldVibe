import { useQuery } from "@tanstack/react-query";
import { ArrowUpCircle, CheckCircle2 } from "lucide-react";

import { versionApi } from "../api/endpoints";

function formatDatum(iso: string | null): string {
  if (!iso) return "unbekannt";
  return new Date(iso).toLocaleString("de-DE");
}

export function UpdatePage() {
  const { data, isLoading } = useQuery({
    queryKey: ["version-info"],
    queryFn: versionApi.get,
    retry: 1,
  });

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-ind-ink">Update</h1>
      <p className="text-sm text-ind-ink-2">
        Diese Ansicht zeigt nur an, ob eine neuere Version verfügbar ist. Ein
        Update wird bewusst nicht automatisch aus der Web-App heraus
        ausgeführt -- die Befehle unten müssen manuell auf dem Server
        ausgeführt werden.
      </p>

      {isLoading && <p className="text-sm text-ind-ink-3">Lädt…</p>}

      {data && (
        <div className="space-y-4">
          {data.fehler && (
            <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200">
              Der neueste Stand auf GitHub konnte nicht ermittelt werden: {data.fehler}
            </div>
          )}

          {data.update_available === true && (
            <div className="flex items-center gap-1.5 rounded-md border border-emerald-300 bg-emerald-50 p-3 text-sm font-medium text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-200">
              <ArrowUpCircle size={15} strokeWidth={2} /> Update verfügbar
            </div>
          )}
          {data.update_available === false && (
            <div className="flex items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-300">
              <CheckCircle2 size={15} strokeWidth={2} /> Aktuellste Version deployt
            </div>
          )}

          <div className="rounded-md border border-slate-200 bg-white p-4 dark:border-stone-700 dark:bg-stone-900">
            <h2 className="mb-2 text-sm font-semibold text-ind-ink-2">
              Aktuell deployt
            </h2>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-ind-ink-3">Commit</dt>
              <dd className="font-mono text-ind-ink">{data.deployed_commit}</dd>
              <dt className="text-ind-ink-3">Branch</dt>
              <dd className="font-mono text-ind-ink">{data.branch}</dd>
            </dl>
          </div>

          <div className="rounded-md border border-slate-200 bg-white p-4 dark:border-stone-700 dark:bg-stone-900">
            <h2 className="mb-2 text-sm font-semibold text-ind-ink-2">
              Neuester Commit auf GitHub
            </h2>
            {data.latest_commit_sha ? (
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                <dt className="text-ind-ink-3">Commit</dt>
                <dd className="font-mono text-ind-ink">
                  {data.latest_commit_url ? (
                    <a
                      href={data.latest_commit_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-600 underline dark:text-blue-400"
                    >
                      {data.latest_commit_sha}
                    </a>
                  ) : (
                    data.latest_commit_sha
                  )}
                </dd>
                <dt className="text-ind-ink-3">Nachricht</dt>
                <dd className="text-ind-ink">{data.latest_commit_message}</dd>
                <dt className="text-ind-ink-3">Datum</dt>
                <dd className="text-ind-ink">
                  {formatDatum(data.latest_commit_date)}
                </dd>
              </dl>
            ) : (
              <p className="text-sm text-ind-ink-3">Nicht ermittelbar.</p>
            )}
          </div>

          <div className="rounded-md border border-slate-200 bg-white p-4 dark:border-stone-700 dark:bg-stone-900">
            <h2 className="mb-2 text-sm font-semibold text-ind-ink-2">
              Manuell aktualisieren
            </h2>
            <p className="mb-2 text-sm text-ind-ink-2">
              Auf dem Server im Repo-Verzeichnis ausführen (siehe docs/DEPLOYMENT.md, Abschnitt 6):
            </p>
            <pre className="overflow-x-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">
{`git pull
export GIT_COMMIT="$(git rev-parse --short HEAD)"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm backend alembic upgrade head`}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
