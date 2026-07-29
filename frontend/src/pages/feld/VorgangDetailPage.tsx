import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { kundenApi, usersApi, vorgangEventsApi, vorgaengeApi } from "../../api/endpoints";
import { MentionText } from "../../components/MentionText";
import type { VorgangEvent, VorgangStatus } from "../../types";

const STATUS_OPTIONS: VorgangStatus[] = [
  "neu",
  "geplant",
  "in_arbeit",
  "wartet_kunde",
  "abgeschlossen",
  "abgerechnet",
  "storniert",
];

const STATUS_LABEL: Record<VorgangStatus, string> = {
  neu: "Neu",
  geplant: "Geplant",
  in_arbeit: "In Arbeit",
  wartet_kunde: "Wartet auf Kunde",
  abgeschlossen: "Abgeschlossen",
  abgerechnet: "Abgerechnet",
  storniert: "Storniert",
};

const EVENT_LABEL: Partial<Record<string, string>> = {
  status_change: "Status geändert",
  foto: "Foto hinzugefügt",
  dokument: "Dokument hinzugefügt",
  mangel: "Mangel erfasst",
  angebot: "Angebot aktualisiert",
  material: "Material erfasst",
  zeit_start: "Zeit gestartet",
  zeit_stop: "Zeit gestoppt",
  termin: "Termin",
  rechnung_status: "Rechnungsstatus aktualisiert",
};

function EventBubble({ event }: { event: VorgangEvent }) {
  if (event.is_system || event.event_type === "status_change") {
    const label =
      event.event_type === "status_change"
        ? `Status: ${(event.payload as { von?: string }).von ?? "?"} → ${(event.payload as { nach?: string }).nach ?? "?"}`
        : event.body ?? EVENT_LABEL[event.event_type] ?? event.event_type;
    return (
      <div className="my-2 text-center text-xs text-slate-400">
        {label} · {new Date(event.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}
      </div>
    );
  }

  return (
    <div className="mb-3 rounded-lg bg-white p-3 shadow-sm">
      <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
        <span>{new Date(event.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}</span>
        {event.kundensichtbar && (
          <span className="rounded-full bg-blue-50 px-2 py-0.5 text-blue-600">Kundensichtbar</span>
        )}
      </div>
      <p className="whitespace-pre-wrap text-sm text-slate-800">
        {event.body ? <MentionText text={event.body} /> : EVENT_LABEL[event.event_type] ?? event.event_type}
      </p>
    </div>
  );
}

export function VorgangDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [comment, setComment] = useState("");
  const [kundensichtbar, setKundensichtbar] = useState(false);
  const [kundenansicht, setKundenansicht] = useState(false);
  const [showMentionPicker, setShowMentionPicker] = useState(false);

  const { data: vorgang } = useQuery({
    queryKey: ["vorgang", id],
    queryFn: () => vorgaengeApi.get(id!),
    enabled: !!id,
  });
  const { data: kunde } = useQuery({
    queryKey: ["kunde", vorgang?.kunde_id],
    queryFn: () => kundenApi.get(vorgang!.kunde_id),
    enabled: !!vorgang,
  });
  const { data: events } = useQuery({
    queryKey: ["vorgang-events", id],
    queryFn: () => vorgangEventsApi.list(id!),
    enabled: !!id,
  });
  const { data: users } = useQuery({ queryKey: ["users"], queryFn: usersApi.list });

  const statusMutation = useMutation({
    mutationFn: (status: VorgangStatus) => vorgaengeApi.update(id!, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vorgang", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
  });

  const commentMutation = useMutation({
    mutationFn: () =>
      vorgangEventsApi.create(id!, {
        event_type: "kommentar",
        body: comment,
        kundensichtbar,
        client_uuid: crypto.randomUUID(),
      }),
    onSuccess: () => {
      setComment("");
      setKundensichtbar(false);
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
  });

  if (!vorgang) return <p className="text-center text-slate-500">Lädt…</p>;

  const eventsChronological = [...(events ?? [])].reverse();
  const sichtbareEvents = kundenansicht
    ? eventsChronological.filter((e) => e.kundensichtbar)
    : eventsChronological;

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-slate-500">
        ← Zurück
      </button>

      <div className="rounded-lg bg-white p-4 shadow-sm">
        <div className="text-xs text-slate-400">{vorgang.vorgangsnummer}</div>
        <h1 className="text-lg font-bold text-slate-800">{vorgang.titel}</h1>
        {kunde && (
          <button
            onClick={() => navigate(`/kunden/${kunde.id}`)}
            className="text-sm text-blue-700 underline-offset-2 hover:underline"
          >
            {kunde.name}
          </button>
        )}
        {vorgang.beschreibung && <p className="mt-2 text-sm text-slate-600">{vorgang.beschreibung}</p>}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <label className="text-sm text-slate-500">Status:</label>
          <select
            value={vorgang.status}
            onChange={(e) => statusMutation.mutate(e.target.value as VorgangStatus)}
            className="btn-touch rounded-md border border-slate-300 px-2 py-1 text-sm"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABEL[s]}
              </option>
            ))}
          </select>
          <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">
            Priorität {vorgang.prioritaet}
          </span>
        </div>
      </div>

      <div className="flex items-center justify-end gap-2">
        <span className="text-sm text-slate-500">
          {kundenansicht ? "Kundenansicht" : "Interne Ansicht"}
        </span>
        <button
          onClick={() => setKundenansicht((v) => !v)}
          className={`btn-touch rounded-full px-3 py-1 text-xs font-semibold ${
            kundenansicht ? "bg-blue-600 text-white" : "bg-slate-200 text-slate-700"
          }`}
        >
          Umschalten
        </button>
      </div>

      <div>
        {sichtbareEvents.length === 0 ? (
          <p className="text-center text-sm text-slate-400">Noch keine Einträge.</p>
        ) : (
          sichtbareEvents.map((event) => <EventBubble key={event.id} event={event} />)
        )}
      </div>

      {!kundenansicht && (
        <div className="sticky bottom-16 space-y-2 rounded-lg bg-white p-3 shadow-md">
          <div className="relative">
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Kommentar schreiben…"
              rows={2}
              className="w-full resize-none rounded-md border border-slate-300 p-2 text-sm"
            />
            {showMentionPicker && (
              <div className="absolute bottom-full left-0 mb-1 max-h-40 w-full overflow-y-auto rounded-md border border-slate-200 bg-white shadow-lg">
                {users?.map((u) => (
                  <button
                    key={u.id}
                    onClick={() => {
                      setComment((c) => `${c}@[${u.name}](${u.id}) `);
                      setShowMentionPicker(false);
                    }}
                    className="btn-touch block w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
                  >
                    {u.name}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setShowMentionPicker((v) => !v)}
                className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm text-slate-600"
              >
                @ Erwähnen
              </button>
              <label className="flex items-center gap-1.5 text-sm text-slate-500">
                <input
                  type="checkbox"
                  checked={kundensichtbar}
                  onChange={(e) => setKundensichtbar(e.target.checked)}
                  className="h-4 w-4"
                />
                Für Kunde sichtbar
              </label>
            </div>
            <button
              onClick={() => commentMutation.mutate()}
              disabled={!comment.trim() || commentMutation.isPending}
              className="btn-touch rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              Senden
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
