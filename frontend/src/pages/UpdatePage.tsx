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
      <h1 className="text-xl font-bold text-label">Update</h1>
      <p className="text-sm text-label">
        Diese Ansicht zeigt nur an, ob eine neuere Version verfügbar ist. Ein
        Update wird bewusst nicht automatisch aus der Web-App heraus
        ausgeführt -- die Befehle unten müssen manuell auf dem Server
        ausgeführt werden.
      </p>

      {isLoading && <p className="text-sm text-label2">Lädt…</p>}

      {data && (
        <div className="space-y-4">
          {data.fehler && (
            <div className="rounded-md border border-st-arbeit bg-st-arbeit-bg p-3 text-sm text-st-arbeit ">
              Der neueste Stand auf GitHub konnte nicht ermittelt werden: {data.fehler}
            </div>
          )}

          {data.update_available === true && (
            <div className="flex items-center gap-1.5 rounded-md border border-st-erledigt bg-st-erledigt-bg p-3 text-sm font-medium text-st-erledigt ">
              <ArrowUpCircle size={15} strokeWidth={2} /> Update verfügbar
            </div>
          )}
          {data.update_available === false && (
            <div className="flex items-center gap-1.5 rounded-md border border-sep bg-slate-50 p-3 text-sm text-label dark:bg-stone-800 ">
              <CheckCircle2 size={15} strokeWidth={2} /> Aktuellste Version deployt
            </div>
          )}

          <div className="rounded-md border border-sep bg-white p-4 dark:bg-stone-900">
            <h2 className="mb-2 text-sm font-semibold text-label">
              Aktuell deployt
            </h2>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-label2">Commit</dt>
              <dd className="font-mono text-label">{data.deployed_commit}</dd>
              <dt className="text-label2">Branch</dt>
              <dd className="font-mono text-label">{data.branch}</dd>
            </dl>
          </div>

          <div className="rounded-md border border-sep bg-white p-4 dark:bg-stone-900">
            <h2 className="mb-2 text-sm font-semibold text-label">
              Neuester Commit auf GitHub
            </h2>
            {data.latest_commit_sha ? (
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                <dt className="text-label2">Commit</dt>
                <dd className="font-mono text-label">
                  {data.latest_commit_url ? (
                    <a
                      href={data.latest_commit_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-tint underline "
                    >
                      {data.latest_commit_sha}
                    </a>
                  ) : (
                    data.latest_commit_sha
                  )}
                </dd>
                <dt className="text-label2">Nachricht</dt>
                <dd className="text-label">{data.latest_commit_message}</dd>
                <dt className="text-label2">Datum</dt>
                <dd className="text-label">
                  {formatDatum(data.latest_commit_date)}
                </dd>
              </dl>
            ) : (
              <p className="text-sm text-label2">Nicht ermittelbar.</p>
            )}
          </div>

          <div className="rounded-md border border-sep bg-white p-4 dark:bg-stone-900">
            <h2 className="mb-2 text-sm font-semibold text-label">
              Manuell aktualisieren
            </h2>
            <p className="mb-2 text-sm text-label">
              Auf dem Server im Repo-Verzeichnis ausführen (siehe docs/DEPLOYMENT.md, Abschnitt 6):
            </p>
            <pre className="overflow-x-auto rounded-md bg-slate-900 p-3 text-xs text-label3">
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
