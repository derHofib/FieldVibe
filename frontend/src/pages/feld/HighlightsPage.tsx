import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Star } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { highlightsApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { Skeleton } from "../../components/Skeleton";
import { useAuth } from "../../context/AuthContext";

export function HighlightsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser, hatRecht } = useAuth();

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
      <button onClick={() => navigate(-1)} className="text-sm text-slate-500 dark:text-stone-400">
        ← Zurück
      </button>
      <h1 className="flex items-center gap-1.5 text-lg font-bold text-slate-800 dark:text-stone-100">
        <Star size={19} strokeWidth={2} className="text-amber-500" /> Highlights
      </h1>
      <p className="text-sm text-slate-500 dark:text-stone-400">
        Markierte Fotos aus abgeschlossenen und laufenden Vorgängen – eine kleine Werkschau.
      </p>

      {isLoading ? (
        <div className="grid grid-cols-2 gap-2">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="aspect-square rounded-lg" />
          ))}
        </div>
      ) : (highlights ?? []).length === 0 ? (
        <EmptyState
          icon={Star}
          text={
            <>
              Noch keine Highlights. Im Vorgangs-Chat lässt sich jedes Foto mit{" "}
              <Star size={12} strokeWidth={2} className="inline text-amber-500" /> markieren.
            </>
          }
        />
      ) : (
        <div className="grid grid-cols-2 gap-2">
          {highlights!.map((h) => (
            <div
              key={h.id}
              className="card-interactive group relative overflow-hidden rounded-lg bg-white shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800"
            >
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
                  <div className="line-clamp-1 text-xs font-medium text-slate-700 dark:text-stone-300">
                    {h.titel ?? h.vorgang_titel}
                  </div>
                  <div className="text-xs text-slate-400 dark:text-stone-500">{h.vorgangsnummer}</div>
                </div>
              </button>
              {/* Spiegelt app/api/routes/highlights.py:delete_highlight -- nur
                  mandant_admin (explizit, nicht "jede nicht-custom-Rolle")
                  oder ein custom-Account mit vorgaenge:loeschen darf fremde
                  Highlights entfernen, alle anderen nur ihr eigenes. */}
              {(currentUser?.role === "mandant_admin" ||
                (currentUser?.role === "custom" && hatRecht("vorgaenge", "loeschen")) ||
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
