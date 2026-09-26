import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { kundenportalApi } from "../../api/endpoints";
import { SkeletonCard } from "../../components/Skeleton";
import { STATUS_BADGE, STATUS_LABEL } from "../../config/vorgangDarstellung";
import type { VorgangEvent, VorgangStatus } from "../../types";

// Kurze, laienverstaendliche Erklaerung je Status -- die internen Labels
// aus vorgangDarstellung.ts reichen fuer Technikerinnen, aber ein externer
// Kunde ohne App-Vorwissen weiss bei "Wartet auf Kunde" sonst nicht, was
// von ihm erwartet wird.
const STATUS_ERKLAERUNG: Record<VorgangStatus, string> = {
  neu: "Ihr Vorgang ist eingegangen und wird eingeplant.",
  geplant: "Für Ihren Vorgang ist bereits ein Termin vorgesehen.",
  in_arbeit: "Der Techniker arbeitet aktuell an diesem Vorgang.",
  wartet_kunde: "Wir warten auf eine Rückmeldung von Ihnen — bitte im Verlauf unten nachsehen.",
  abgeschlossen: "Die Arbeiten sind abgeschlossen.",
  abgerechnet: "Der Vorgang ist abgeschlossen und wurde bereits abgerechnet.",
  storniert: "Dieser Vorgang wurde storniert.",
};

function PortalEventBubble({ event }: { event: VorgangEvent }) {
  if (event.is_system) {
    return (
      <div className="my-2 text-center text-xs text-label2">
        {event.body ?? event.event_type} ·{" "}
        {new Date(event.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}
      </div>
    );
  }

  return (
    <div className="mb-3 card-ap p-3">
      <div className="mb-1 text-xs text-label2">
        {new Date(event.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}
      </div>
      {event.event_type === "foto" && event.foto_url && (
        <a href={event.foto_url} target="_blank" rel="noreferrer">
          <img
            src={event.foto_thumbnail_url ?? event.foto_url}
            alt="Foto"
            className="mb-2 max-h-64 rounded-md object-cover"
          />
        </a>
      )}
      {event.body && (
        <p className="whitespace-pre-wrap break-words text-sm text-label">{event.body}</p>
      )}
    </div>
  );
}

export function PortalVorgangDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: vorgang } = useQuery({
    queryKey: ["portal-vorgang", id],
    queryFn: () => kundenportalApi.vorgang(id!),
    enabled: !!id,
  });
  const { data: events } = useQuery({
    queryKey: ["portal-vorgang-events", id],
    queryFn: () => kundenportalApi.vorgangEvents(id!),
    enabled: !!id,
  });

  if (!vorgang) return <SkeletonCard />;

  const eventsChronological = [...(events ?? [])].reverse();

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-label2">
        ← Zurück
      </button>

      <div className="card-ap p-4">
        <div className="text-xs text-label2">Vorgang Nr. {vorgang.vorgangsnummer}</div>
        <h1 className="text-lg font-bold text-label">{vorgang.titel}</h1>
        {vorgang.beschreibung && (
          <p className="mt-2 text-sm text-label">{vorgang.beschreibung}</p>
        )}
        <span className={`mt-2 inline-block px-2 py-1 text-xs font-semibold ${STATUS_BADGE[vorgang.status]}`}>
          {STATUS_LABEL[vorgang.status]}
        </span>
        <p className="mt-1 text-xs text-label2">{STATUS_ERKLAERUNG[vorgang.status]}</p>
      </div>

      <div>
        {eventsChronological.length === 0 ? (
          <p className="text-center text-sm text-label2">Noch keine Einträge.</p>
        ) : (
          eventsChronological.map((event) => <PortalEventBubble key={event.id} event={event} />)
        )}
      </div>
    </div>
  );
}
