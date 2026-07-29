import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { highlightsApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";

export function HighlightsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();

  const { data: highlights, isLoading } = useQuery({
    queryKey: ["highlights"],
    queryFn: highlightsApi.list,
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => highlightsApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["highlights"] }),
  });

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-slate-500">
        ← Zurück
      </button>
      <h1 className="text-lg font-bold text-slate-800">⭐ Highlights</h1>
      <p className="text-sm text-slate-500">
        Markierte Fotos aus abgeschlossenen und laufenden Vorgängen – eine kleine Werkschau.
      </p>

      {isLoading ? (
        <p className="text-center text-slate-500">Lädt…</p>
      ) : (highlights ?? []).length === 0 ? (
        <p className="text-center text-sm text-slate-400">
          Noch keine Highlights. Im Vorgangs-Chat lässt sich jedes Foto mit ⭐ markieren.
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          {highlights!.map((h) => (
            <div key={h.id} className="group relative overflow-hidden rounded-lg bg-white shadow-sm">
              <button
                onClick={() => navigate(`/vorgaenge/${h.vorgang_id}`)}
                className="btn-touch block w-full text-left"
              >
                {h.foto_url && (
                  <img
                    src={h.foto_thumbnail_url ?? h.foto_url}
                    alt={h.titel ?? h.vorgang_titel}
                    className="aspect-square w-full object-cover"
                  />
                )}
                <div className="p-2">
                  <div className="line-clamp-1 text-xs font-medium text-slate-700">
                    {h.titel ?? h.vorgang_titel}
                  </div>
                  <div className="text-xs text-slate-400">{h.vorgangsnummer}</div>
                </div>
              </button>
              {(currentUser?.role === "mandant_admin" ||
                currentUser?.role === "disponent" ||
                h.erstellt_von === currentUser?.id) && (
                <button
                  onClick={() => removeMutation.mutate(h.id)}
                  disabled={removeMutation.isPending}
                  title="Highlight entfernen"
                  className="btn-touch absolute right-1 top-1 rounded-full bg-black/50 px-2 py-0.5 text-xs text-white disabled:opacity-50"
                >
                  ✕
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
