import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { kundenApi } from "../../api/endpoints";

const STATUS_BADGE: Record<string, string> = {
  neu: "bg-blue-100 text-blue-800",
  geplant: "bg-purple-100 text-purple-800",
  in_arbeit: "bg-amber-100 text-amber-800",
  wartet_kunde: "bg-orange-100 text-orange-800",
  abgeschlossen: "bg-green-100 text-green-800",
  abgerechnet: "bg-slate-200 text-slate-700",
  storniert: "bg-red-100 text-red-800",
};

export function KundeProfilePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: profil, isLoading } = useQuery({
    queryKey: ["kunde-profil", id],
    queryFn: () => kundenApi.profil(id!),
    enabled: !!id,
  });

  if (isLoading || !profil) return <p className="text-center text-slate-500">Lädt…</p>;

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-slate-500">
        ← Zurück
      </button>

      <div className="rounded-lg bg-white p-4 shadow-sm">
        <div className="text-xs text-slate-400">{profil.kundennummer}</div>
        <h1 className="text-lg font-bold text-slate-800">{profil.name}</h1>
        {profil.typ && <span className="text-sm text-slate-500">{profil.typ}</span>}
        {profil.tags.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {profil.tags.map((t) => (
              <span key={t.id} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                #{t.label}
              </span>
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold text-slate-500">Anlagen</h2>
        {profil.anlagen.length === 0 ? (
          <p className="text-sm text-slate-400">Keine Anlagen.</p>
        ) : (
          <div className="space-y-2">
            {profil.anlagen.map((a) => (
              <button
                key={a.id}
                onClick={() => navigate(`/anlagen/${a.id}`)}
                className="btn-touch block w-full rounded-lg bg-white p-3 text-left shadow-sm"
              >
                <div className="text-sm font-medium text-slate-800">{a.bezeichnung}</div>
                {a.anlagentyp && <div className="text-xs text-slate-400">{a.anlagentyp}</div>}
              </button>
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold text-slate-500">Vorgänge</h2>
        {profil.vorgaenge.length === 0 ? (
          <p className="text-sm text-slate-400">Keine Vorgänge.</p>
        ) : (
          <div className="space-y-2">
            {profil.vorgaenge.map((v) => (
              <button
                key={v.id}
                onClick={() => navigate(`/vorgaenge/${v.id}`)}
                className="btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm"
              >
                <div>
                  <div className="text-xs text-slate-400">{v.vorgangsnummer}</div>
                  <div className="text-sm font-medium text-slate-800">{v.titel}</div>
                </div>
                <span className={`rounded-full px-2 py-1 text-xs font-semibold ${STATUS_BADGE[v.status]}`}>
                  {v.status}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
