import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { kundenportalApi } from "../../api/endpoints";
import { SkeletonCard } from "../../components/Skeleton";
import { openPdfBlob } from "../../utils/pdf";
import { ANGEBOT_STATUS_BADGE, ANGEBOT_STATUS_ERKLAERUNG, ANGEBOT_STATUS_LABEL } from "./status";

export function PortalAngebotDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [fehler, setFehler] = useState<string | null>(null);
  const meldeFehler = (err: unknown) =>
    setFehler(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen.");

  const { data: angebot } = useQuery({
    queryKey: ["portal-angebot", id],
    queryFn: () => kundenportalApi.angebot(id!),
    enabled: !!id,
  });

  const antwortMutation = useMutation({
    mutationFn: (status: "angenommen" | "abgelehnt") => kundenportalApi.antwortAufAngebot(id!, status),
    onSuccess: () => {
      setFehler(null);
      queryClient.invalidateQueries({ queryKey: ["portal-angebot", id] });
      queryClient.invalidateQueries({ queryKey: ["portal-angebote"] });
    },
    onError: meldeFehler,
  });

  const pdfMutation = useMutation({
    mutationFn: () => kundenportalApi.angebotPdf(id!),
    onSuccess: openPdfBlob,
    onError: meldeFehler,
  });

  if (!angebot) return <SkeletonCard />;

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-label2">
        ← Zurück
      </button>

      <div className="border border-sep bg-card p-4">
        <div className="flex items-start justify-between">
          <div className="text-xs text-label2">Angebot Nr. {angebot.angebotsnummer}</div>
          <span className={`px-2 py-1 text-xs font-semibold ${ANGEBOT_STATUS_BADGE[angebot.status]}`}>
            {ANGEBOT_STATUS_LABEL[angebot.status]}
          </span>
        </div>
        <p className="mt-1 text-xs text-label2">{ANGEBOT_STATUS_ERKLAERUNG[angebot.status]}</p>
        {angebot.gueltig_bis && (
          <p className="mt-1 text-xs text-label2">
            Gültig bis {new Date(angebot.gueltig_bis).toLocaleDateString("de-DE")}
          </p>
        )}
        <button
          onClick={() => pdfMutation.mutate()}
          disabled={pdfMutation.isPending}
          className="btn-touch mt-3 flex items-center justify-center gap-1 rounded-md bg-fill px-3 py-1.5 text-sm font-medium text-label disabled:opacity-50 "
        >
          <FileText size={14} strokeWidth={2} /> {pdfMutation.isPending ? "PDF wird geladen…" : "PDF anzeigen"}
        </button>
      </div>

      {fehler && <p className="text-sm text-st-fehlt ">{fehler}</p>}

      <div className="border border-sep bg-card p-4">
        <h2 className="mb-2 text-sm font-semibold text-label2">Positionen</h2>
        {angebot.positionen.length === 0 ? (
          <p className="text-sm text-label2">Keine Positionen.</p>
        ) : (
          <div className="space-y-1.5">
            {angebot.positionen.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between rounded-md bg-fill p-2 text-sm"
              >
                <div>
                  <div className="text-label">{p.beschreibung}</div>
                  <div className="text-xs text-label2">
                    {p.menge} {p.einheit} × {p.einzelpreis} EUR
                  </div>
                </div>
                <div className="font-medium text-label">{p.gesamt} EUR</div>
              </div>
            ))}
          </div>
        )}
        <div className="mt-3 border-t border-sep pt-2 text-right text-sm ">
          <div className="text-label2">Netto: {angebot.gesamt_netto} EUR</div>
          <div className="font-semibold text-label">
            Brutto: {angebot.gesamt_brutto} EUR
          </div>
        </div>
      </div>

      {angebot.status === "versendet" && (
        <div className="flex gap-2">
          <button
            onClick={() => antwortMutation.mutate("angenommen")}
            disabled={antwortMutation.isPending}
            className="btn-touch flex-1 rounded-md bg-st-erledigt-dot px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Annehmen
          </button>
          <button
            onClick={() => {
              if (window.confirm("Angebot wirklich ablehnen? Der Betrieb wird darüber benachrichtigt.")) {
                antwortMutation.mutate("abgelehnt");
              }
            }}
            disabled={antwortMutation.isPending}
            className="btn-touch flex-1 rounded-md bg-st-fehlt-dot px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Ablehnen
          </button>
        </div>
      )}
      {angebot.status === "angenommen" && (
        <p className="text-center text-sm text-st-erledigt ">
          Sie haben dieses Angebot angenommen.
        </p>
      )}
      {angebot.status === "abgelehnt" && (
        <p className="text-center text-sm text-st-fehlt ">
          Sie haben dieses Angebot abgelehnt.
        </p>
      )}
    </div>
  );
}
