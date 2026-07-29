import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { anlagenApi } from "../../api/endpoints";

const STATUS_BADGE: Record<string, string> = {
  neu: "bg-blue-100 text-blue-800",
  geplant: "bg-purple-100 text-purple-800",
  in_arbeit: "bg-amber-100 text-amber-800",
  wartet_kunde: "bg-orange-100 text-orange-800",
  abgeschlossen: "bg-green-100 text-green-800",
  abgerechnet: "bg-slate-200 text-slate-700",
  storniert: "bg-red-100 text-red-800",
};

export function AnlageProfilePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: profil, isLoading } = useQuery({
    queryKey: ["anlage-profil", id],
    queryFn: () => anlagenApi.profil(id!),
    enabled: !!id,
  });

  if (isLoading || !profil) return <p className="text-center text-slate-500">Lädt…</p>;

  const adresse = profil.adresse as { strasse?: string; ort?: string };

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-slate-500">
        ← Zurück
      </button>

      <div className="rounded-lg bg-white p-4 shadow-sm">
        <h1 className="text-lg font-bold text-slate-800">{profil.bezeichnung}</h1>
        <button
          onClick={() => navigate(`/kunden/${profil.kunde.id}`)}
          className="text-sm text-blue-700 underline-offset-2 hover:underline"
        >
          {profil.kunde.name}
        </button>
        {(adresse?.strasse || adresse?.ort) && (
          <p className="mt-1 text-sm text-slate-500">
            {[adresse.strasse, adresse.ort].filter(Boolean).join(", ")}
          </p>
        )}
        {profil.anlagentyp && <p className="text-xs text-slate-400">{profil.anlagentyp}</p>}
        {profil.qr_code && <p className="mt-2 text-xs text-slate-400">QR-Code: {profil.qr_code}</p>}
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
