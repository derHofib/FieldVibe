import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { kundenportalApi } from "../../api/endpoints";
import type { VorgangEvent, VorgangStatus } from "../../types";

const STATUS_LABEL: Record<VorgangStatus, string> = {
  neu: "Neu",
  geplant: "Geplant",
  in_arbeit: "In Arbeit",
  wartet_kunde: "Wartet auf Kunde",
  abgeschlossen: "Abgeschlossen",
  abgerechnet: "Abgerechnet",
  storniert: "Storniert",
};

function PortalEventBubble({ event }: { event: VorgangEvent }) {
  if (event.is_system) {
    return (
      <div className="my-2 text-center text-xs text-slate-400">
        {event.body ?? event.event_type} ·{" "}
        {new Date(event.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}
      </div>
    );
  }

  return (
    <div className="mb-3 rounded-lg bg-white p-3 shadow-sm">
      <div className="mb-1 text-xs text-slate-400">
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
      {event.body && <p className="whitespace-pre-wrap text-sm text-slate-800">{event.body}</p>}
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

  if (!vorgang) return <p className="text-center text-slate-500">Lädt…</p>;

  const eventsChronological = [...(events ?? [])].reverse();

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-slate-500">
        ← Zurück
      </button>

      <div className="rounded-lg bg-white p-4 shadow-sm">
        <div className="text-xs text-slate-400">{vorgang.vorgangsnummer}</div>
        <h1 className="text-lg font-bold text-slate-800">{vorgang.titel}</h1>
        {vorgang.beschreibung && <p className="mt-2 text-sm text-slate-600">{vorgang.beschreibung}</p>}
        <span className="mt-2 inline-block rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">
          {STATUS_LABEL[vorgang.status]}
        </span>
      </div>

      <div>
        {eventsChronological.length === 0 ? (
          <p className="text-center text-sm text-slate-400">Noch keine Einträge.</p>
        ) : (
          eventsChronological.map((event) => <PortalEventBubble key={event.id} event={event} />)
        )}
      </div>
    </div>
  );
}
